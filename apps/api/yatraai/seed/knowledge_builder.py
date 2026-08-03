"""Derive the RAG corpus from the *same* verified catalogue records.

Why derive rather than curate a second corpus?
----------------------------------------------
The catalogue is the single fact layer. If the knowledge base were authored
separately it could drift from the data the planner reasons about, and an
assistant answer could contradict the itinerary. Deriving guarantees that
every retrievable sentence is backed by a row a reviewer can inspect, with the
same source URL and verification date.

Chunking is **semantic**: one chunk per (attraction, topic) - history,
significance, facts, visiting practicalities, accessibility, etiquette - not a
blind N-character split. Topics are short and self-contained, which is what
makes citation-level attribution possible.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from yatraai.core.security import hash_content
from yatraai.db.models import ChunkEmbedding, DocumentChunk, SourceDocument
from yatraai.logging_config import get_logger

log = get_logger(__name__)

# Topics that become their own retrievable chunk.
TOPICS = (
    "history",
    "significance",
    "facts",
    "visiting",
    "accessibility",
    "etiquette",
)

_MONTH_NAMES = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

_TIME_OF_DAY_LABEL = {
    "early_morning": "early morning",
    "morning": "morning",
    "midday": "midday",
    "afternoon": "afternoon",
    "evening": "evening",
    "sunset": "around sunset",
    "night": "night",
}


def _fmt_months(months: list[int]) -> str:
    if not months or len(months) == 12:
        return "all year"
    return ", ".join(_MONTH_NAMES[m] for m in sorted(months) if 1 <= m <= 12)


def _fmt_minutes(minutes: int) -> str:
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours} hour{'s' if hours > 1 else ''}"
    return f"{mins} minutes"


def _fmt_schedule(rows: list[dict]) -> str:
    if not rows:
        return "Opening hours are not recorded in our dataset - verify before visiting."
    parts = []
    dow_label = {
        -1: "Every day",
        0: "Monday",
        1: "Tuesday",
        2: "Wednesday",
        3: "Thursday",
        4: "Friday",
        5: "Saturday",
        6: "Sunday",
    }
    for row in rows:
        day = row.get("day_of_week", row.get("day", -1))
        if isinstance(day, str):
            day = {"all": -1, "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}[
                day.lower()
            ]
        label = dow_label.get(int(day), "Every day")
        if row.get("is_closed"):
            note = row.get("note", "")
            parts.append(f"{label}: closed{f' ({note})' if note else ''}")
        else:
            parts.append(f"{label}: {row.get('opens', '?')}-{row.get('closes', '?')}")
    return "; ".join(parts)


def _fmt_costs(rows: list[dict]) -> str:
    if not rows:
        return "Entry fee is not recorded in our dataset - verify before visiting."
    labels = {
        "indian_adult": "Indian visitors",
        "foreign_adult": "foreign visitors",
        "child": "children",
        "senior": "senior citizens",
        "camera": "camera/videography",
        "parking": "parking",
    }
    parts = []
    for row in rows:
        who = labels.get(row.get("visitor_type", "indian_adult"), row.get("visitor_type"))
        lo = float(row.get("min", row.get("amount", 0)))
        hi = float(row.get("max", lo))
        if row.get("is_free") or (lo == 0 and hi == 0):
            parts.append(f"{who}: free entry")
        elif lo == hi:
            parts.append(f"{who}: around Rs.{lo:.0f}")
        else:
            parts.append(f"{who}: about Rs.{lo:.0f}-Rs.{hi:.0f}")
        if row.get("note"):
            parts[-1] += f" ({row['note']})"
    return "; ".join(parts)


# --------------------------------------------------------------------------- #
# Document construction
# --------------------------------------------------------------------------- #
def _topic_body(topic: str, attraction: dict, cluster: dict) -> tuple[str, str] | None:
    """Return ``(heading, body)`` for a topic, or ``None`` when we have no data."""
    name = attraction["name"]

    if topic == "history":
        text = (attraction.get("history") or "").strip()
        if not text:
            return None
        return f"History of {name}", text

    if topic == "significance":
        text = (attraction.get("significance") or "").strip()
        if not text:
            return None
        return f"Why {name} matters", text

    if topic == "facts":
        facts = attraction.get("interesting_facts") or []
        if not facts:
            return None
        bullets = "\n".join(f"- {f}" for f in facts)
        return f"Notable facts about {name}", f"Lesser-known details about {name}:\n{bullets}"

    if topic == "visiting":
        sentences = [
            f"{name} is in {attraction.get('locality') or attraction['city']}, "
            f"{attraction['city']}, part of the {cluster['name']} circuit.",
            f"A typical visit takes about {_fmt_minutes(attraction['typical_duration_min'])}"
            f" (plan between {_fmt_minutes(attraction.get('min_duration_min', 30))} and "
            f"{_fmt_minutes(attraction.get('max_duration_min', 180))}).",
        ]
        tod = attraction.get("best_time_of_day") or []
        if tod:
            sentences.append(
                "The best time of day to visit is "
                + " or ".join(_TIME_OF_DAY_LABEL.get(t, t) for t in tod)
                + "."
            )
        sentences.append(f"Suitable months: {_fmt_months(attraction.get('suitable_months', []))}.")
        sentences.append(
            f"This is an {attraction.get('indoor_outdoor', 'outdoor')} site with typically "
            f"{attraction.get('typical_crowd_level', 'medium').replace('_', ' ')} crowds."
        )
        sentences.append("Opening hours: " + _fmt_schedule(attraction.get("schedule", [])) + ".")
        sentences.append("Entry: " + _fmt_costs(attraction.get("costs", [])) + ".")
        sentences.append(
            "Hours and fees are time-sensitive and are recorded as unverified in this dataset; "
            "always confirm with the official source before travelling."
        )
        return f"Visiting {name}: duration, timing and entry", " ".join(sentences)

    if topic == "accessibility":
        access = attraction.get("wheelchair_accessible", "unknown")
        access_label = {
            "yes": "step-free access is available",
            "partial": "access is partial - some areas involve steps or uneven ground",
            "no": "the site is not wheelchair accessible",
            "unknown": "wheelchair access is not recorded in our dataset",
        }[access]
        parts = [f"At {name}, {access_label}."]
        if attraction.get("accessibility_notes"):
            parts.append(attraction["accessibility_notes"])
        parts.append(
            f"On a 1-5 scale this site rates {attraction.get('senior_friendly', 3)}/5 for senior "
            f"citizens and {attraction.get('child_friendly', 3)}/5 for children, with a physical "
            f"demand level of {attraction.get('physical_intensity', 2)}/5."
        )
        return f"Accessibility at {name}", " ".join(parts)

    if topic == "etiquette":
        parts = []
        if attraction.get("dress_code"):
            parts.append(f"Dress code: {attraction['dress_code']}")
        if attraction.get("photography_policy"):
            parts.append(f"Photography: {attraction['photography_policy']}")
        for custom in attraction.get("local_customs", []) or []:
            parts.append(custom)
        if not parts:
            return None
        return f"Etiquette and local customs at {name}", " ".join(
            p if p.endswith(".") else p + "." for p in parts
        )

    return None


def _pick_source(attraction: dict, topic: str) -> dict:
    """Choose the most relevant recorded source for a topic."""
    sources = attraction.get("sources") or []
    if not sources:
        return {
            "url": "https://www.incredibleindia.gov.in/",
            "title": "Incredible India (Ministry of Tourism)",
            "type": "government",
        }
    topic_fields = {
        "history": {"history", "background"},
        "significance": {"significance", "history"},
        "facts": {"facts", "history"},
        "visiting": {"hours", "fees", "practical"},
        "accessibility": {"accessibility", "practical"},
        "etiquette": {"rules", "practical", "customs"},
    }[topic]
    for src in sources:
        if topic_fields & set(src.get("covers", [])):
            return src
    return sources[0]


def build_knowledge_documents(payloads: list[dict]) -> list[dict[str, Any]]:
    """Build ``SourceDocument``-shaped dicts (with their chunks) from seed files."""
    documents: list[dict[str, Any]] = []

    for payload in payloads:
        cluster = payload["cluster"]

        # ---- cluster-level orientation document ----
        cluster_body = (
            f"{cluster['name']} ({cluster['state']}, {cluster['region']} India). "
            f"{cluster['summary']} "
            f"Best months to visit: {_fmt_months(cluster.get('best_months', []))}. "
            f"Months usually avoided: {_fmt_months(cluster.get('avoid_months', [])) or 'none'}. "
            f"A typical trip here runs about {cluster.get('recommended_days', 3)} days. "
            f"Travel styles this circuit suits: {', '.join(cluster.get('travel_style', []))}."
        )
        documents.append(
            {
                "doc_key": f"cluster::{cluster['slug']}::overview",
                "cluster_slug": cluster["slug"],
                "attraction_slug": None,
                "title": f"{cluster['name']} - destination overview",
                "content_category": "overview",
                "body": cluster_body,
                "source_url": cluster.get("source_url", "https://www.incredibleindia.gov.in/"),
                "source_title": cluster.get(
                    "source_title", "Ministry of Tourism, Government of India"
                ),
                "source_type": cluster.get("source_type", "government"),
                "last_verified": cluster.get("last_verified"),
                "time_sensitive": False,
                "chunks": [
                    {
                        "heading": f"About {cluster['name']}",
                        "text": cluster_body,
                        "keywords": [cluster["slug"], "overview", "best time to visit"],
                    }
                ],
            }
        )

        # ---- one document per attraction, chunked by topic ----
        for attraction in payload.get("attractions", []):
            chunks = []
            for topic in TOPICS:
                built = _topic_body(topic, attraction, cluster)
                if not built:
                    continue
                heading, body = built
                source = _pick_source(attraction, topic)
                chunks.append(
                    {
                        "heading": heading,
                        "text": body,
                        "topic": topic,
                        "keywords": [
                            attraction["slug"],
                            attraction["name"].lower(),
                            topic,
                            *list(attraction.get("categories", [])),
                        ],
                        "source_url": source["url"],
                        "source_type": source.get("type", "official"),
                    }
                )
            if not chunks:
                continue

            primary = _pick_source(attraction, "history")
            documents.append(
                {
                    "doc_key": f"attraction::{cluster['slug']}::{attraction['slug']}",
                    "cluster_slug": cluster["slug"],
                    "attraction_slug": attraction["slug"],
                    "title": f"{attraction['name']} - verified knowledge record",
                    "content_category": "attraction",
                    "body": "\n\n".join(f"## {c['heading']}\n{c['text']}" for c in chunks),
                    "source_url": primary["url"],
                    "source_title": primary.get("title", ""),
                    "source_type": primary.get("type", "official"),
                    "last_verified": attraction.get("last_verified"),
                    "time_sensitive": bool(attraction.get("needs_verification", True)),
                    "chunks": chunks,
                }
            )

    return documents


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def sync_knowledge(
    session: Session, documents: list[dict], *, build_embeddings: bool = False
) -> dict[str, int]:
    """Upsert documents/chunks; only re-chunk and re-embed what actually changed."""
    counts = {"documents": 0, "documents_changed": 0, "chunks": 0, "embeddings": 0}

    for doc in documents:
        body_hash = hash_content(doc["body"])
        existing = session.scalar(
            select(SourceDocument).where(SourceDocument.doc_key == doc["doc_key"])
        )
        counts["documents"] += 1

        if existing and existing.content_hash == body_hash:
            counts["chunks"] += len(existing.chunks)
            continue

        counts["documents_changed"] += 1
        if existing is None:
            existing = SourceDocument(doc_key=doc["doc_key"])
            session.add(existing)

        existing.cluster_slug = doc["cluster_slug"]
        existing.attraction_slug = doc.get("attraction_slug")
        existing.title = doc["title"]
        existing.content_category = doc["content_category"]
        existing.body = doc["body"]
        existing.source_url = doc["source_url"]
        existing.source_title = doc.get("source_title", "")
        existing.source_type = doc.get("source_type", "official")
        existing.last_verified_at = _parse_date(doc.get("last_verified"))
        existing.time_sensitive = bool(doc.get("time_sensitive", False))
        existing.content_hash = body_hash
        existing.is_active = True
        session.flush()

        session.query(DocumentChunk).filter_by(document_id=existing.id).delete(
            synchronize_session=False
        )
        session.flush()

        for index, chunk in enumerate(doc["chunks"]):
            session.add(
                DocumentChunk(
                    document_id=existing.id,
                    chunk_index=index,
                    heading=chunk.get("heading", ""),
                    text=chunk["text"],
                    token_estimate=max(1, len(chunk["text"]) // 4),
                    cluster_slug=doc["cluster_slug"],
                    attraction_slug=doc.get("attraction_slug"),
                    content_category=chunk.get("topic", doc["content_category"]),
                    source_url=chunk.get("source_url", doc["source_url"]),
                    source_type=chunk.get("source_type", doc.get("source_type", "official")),
                    last_verified_at=_parse_date(doc.get("last_verified")),
                    keywords=chunk.get("keywords", []),
                    content_hash=hash_content(chunk["text"]),
                )
            )
            counts["chunks"] += 1
        session.flush()

    if build_embeddings:
        counts["embeddings"] = embed_missing_chunks(session)

    return counts


def embed_missing_chunks(session: Session, batch_size: int = 128) -> int:
    """Embed every chunk that has no current embedding. Safe to re-run."""
    from yatraai.services.rag.embeddings import get_embedder

    embedder = get_embedder()
    pending = list(
        session.scalars(
            select(DocumentChunk)
            .outerjoin(ChunkEmbedding, ChunkEmbedding.chunk_id == DocumentChunk.id)
            .where(ChunkEmbedding.id.is_(None))
        )
    )
    if not pending:
        return 0

    written = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        texts = [f"{c.heading}\n{c.text}" for c in batch]
        vectors = embedder.embed_documents(texts)
        for chunk, vector in zip(batch, vectors, strict=True):
            session.add(
                ChunkEmbedding(
                    chunk_id=chunk.id,
                    provider=embedder.provider_name,
                    model=embedder.model_name,
                    dim=len(vector),
                    vector=list(vector),
                    norm=1.0,
                )
            )
            written += 1
        session.flush()

    log.info("knowledge.embedded", chunks=written, provider=embedder.provider_name)
    return written
