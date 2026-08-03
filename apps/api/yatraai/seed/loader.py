"""Idempotent loader for the curated seed catalogue.

Design notes
------------
* **Idempotent** - re-running never duplicates rows. Clusters and attractions
  are matched on their natural key (``slug`` / ``cluster+slug``); child rows
  (schedules, costs, sources) are replaced wholesale because they are small and
  always fully described by the seed file.
* **Content-addressed knowledge** - RAG documents are keyed by ``doc_key`` and
  carry a ``content_hash``; unchanged documents keep their existing chunks and
  embeddings so a reseed does not re-embed the whole corpus.
* **No invented facts** - every field comes from the JSON files under
  ``data/seed/``. Time-sensitive fields (hours, fees) are flagged
  ``verified=false`` and surface a "verify before visiting" badge in the UI.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from yatraai.config import get_settings
from yatraai.db.models import (
    Attraction,
    AttractionCost,
    AttractionSchedule,
    AttractionSource,
    DestinationCluster,
)
from yatraai.logging_config import get_logger
from yatraai.seed.knowledge_builder import build_knowledge_documents, sync_knowledge

log = get_logger(__name__)

DOW_NAMES = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
    "all": -1,
}


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def parse_hhmm(value: str | int | None) -> int | None:
    """``"09:30"`` -> 570 minutes from midnight. ``"24:00"`` -> 1440."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    hh, _, mm = str(value).partition(":")
    return int(hh) * 60 + int(mm or 0)


def minutes_to_hhmm(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def read_seed_files(seed_dir: Path | None = None) -> list[dict[str, Any]]:
    """Read every ``data/seed/attractions/*.json`` file, sorted for determinism."""
    base = Path(seed_dir) if seed_dir else get_settings().seed_dir / "attractions"
    if not base.exists():
        raise FileNotFoundError(f"Seed directory not found: {base}")
    payloads = []
    for path in sorted(base.glob("*.json")):
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["_source_file"] = path.name
        payloads.append(data)
    if not payloads:
        raise FileNotFoundError(f"No seed files found in {base}")
    return payloads


# --------------------------------------------------------------------------- #
# Upserts
# --------------------------------------------------------------------------- #
def _upsert_cluster(session: Session, payload: dict) -> DestinationCluster:
    cluster = session.scalar(
        select(DestinationCluster).where(DestinationCluster.slug == payload["slug"])
    )
    fields: dict[str, Any] = dict(  # noqa: C408 - kwargs form mirrors the model columns
        name=payload["name"],
        state=payload["state"],
        region=payload["region"],
        summary=payload["summary"],
        travel_style=payload.get("travel_style", []),
        center_lat=float(payload["center_lat"]),
        center_lon=float(payload["center_lon"]),
        timezone=payload.get("timezone", "Asia/Kolkata"),
        best_months=payload.get("best_months", []),
        avoid_months=payload.get("avoid_months", []),
        recommended_days=int(payload.get("recommended_days", 3)),
        daily_cost_baseline=payload.get("daily_cost_baseline", {}),
        intercity_hub=payload.get("intercity_hub"),
        hero_image_url=payload.get("hero_image_url"),
        image_attribution=payload.get("image_attribution"),
        is_active=payload.get("is_active", True),
    )
    if cluster is None:
        cluster = DestinationCluster(slug=payload["slug"], **fields)
        session.add(cluster)
    else:
        for key, value in fields.items():
            setattr(cluster, key, value)
    session.flush()
    return cluster


def _upsert_attraction(session: Session, cluster: DestinationCluster, payload: dict) -> Attraction:
    attraction = session.scalar(
        select(Attraction).where(
            Attraction.cluster_id == cluster.id, Attraction.slug == payload["slug"]
        )
    )
    fields: dict[str, Any] = dict(  # noqa: C408 - kwargs form mirrors the model columns
        name=payload["name"],
        locality=payload.get("locality", ""),
        city=payload["city"],
        lat=float(payload["lat"]),
        lon=float(payload["lon"]),
        categories=payload.get("categories", []),
        summary=payload["summary"],
        history=payload.get("history", ""),
        significance=payload.get("significance", ""),
        interesting_facts=payload.get("interesting_facts", []),
        typical_duration_min=int(payload["typical_duration_min"]),
        min_duration_min=int(payload.get("min_duration_min", payload["typical_duration_min"] // 2)),
        max_duration_min=int(payload.get("max_duration_min", payload["typical_duration_min"] * 2)),
        best_time_of_day=payload.get("best_time_of_day", []),
        suitable_months=payload.get("suitable_months", list(range(1, 13))),
        indoor_outdoor=payload.get("indoor_outdoor", "outdoor"),
        weather_sensitivity=float(payload.get("weather_sensitivity", 0.5)),
        typical_crowd_level=payload.get("typical_crowd_level", "medium"),
        crowd_by_time=payload.get("crowd_by_time", {}),
        wheelchair_accessible=payload.get("wheelchair_accessible", "unknown"),
        accessibility_notes=payload.get("accessibility_notes", ""),
        senior_friendly=int(payload.get("senior_friendly", 3)),
        child_friendly=int(payload.get("child_friendly", 3)),
        physical_intensity=int(payload.get("physical_intensity", 2)),
        dress_code=payload.get("dress_code", ""),
        photography_policy=payload.get("photography_policy", ""),
        local_customs=payload.get("local_customs", []),
        quality_score=float(payload.get("quality_score", 0.6)),
        popularity_rank=int(payload.get("popularity_rank", 50)),
        nearby_attraction_slugs=payload.get("nearby", []),
        hero_image_url=payload.get("hero_image_url"),
        image_attribution=payload.get("image_attribution"),
        data_confidence=payload.get("data_confidence", "medium"),
        needs_verification=bool(payload.get("needs_verification", True)),
        verification_note=payload.get(
            "verification_note",
            "Opening hours and entry fees change seasonally - verify before visiting.",
        ),
        last_verified_at=_parse_date(payload.get("last_verified")),
        is_active=payload.get("is_active", True),
    )
    if attraction is None:
        attraction = Attraction(cluster_id=cluster.id, slug=payload["slug"], **fields)
        session.add(attraction)
    else:
        for key, value in fields.items():
            setattr(attraction, key, value)
    session.flush()

    _replace_schedules(session, attraction, payload.get("schedule", []))
    _replace_costs(session, attraction, payload.get("costs", []))
    _replace_sources(session, attraction, payload.get("sources", []))
    return attraction


def _replace_schedules(session: Session, attraction: Attraction, rows: list[dict]) -> None:
    session.query(AttractionSchedule).filter_by(attraction_id=attraction.id).delete(
        synchronize_session=False
    )
    for row in rows:
        dow = row.get("day_of_week", row.get("day", "all"))
        dow_int = DOW_NAMES.get(str(dow).lower(), dow) if not isinstance(dow, int) else dow
        session.add(
            AttractionSchedule(
                attraction_id=attraction.id,
                day_of_week=int(dow_int),
                opens_min=parse_hhmm(row.get("opens")),
                closes_min=parse_hhmm(row.get("closes")),
                is_closed=bool(row.get("is_closed", False)),
                season=row.get("season", "all"),
                note=row.get("note", ""),
                # Hours are time-sensitive; the seed set never claims verification.
                verified=bool(row.get("verified", False)),
            )
        )


def _replace_costs(session: Session, attraction: Attraction, rows: list[dict]) -> None:
    session.query(AttractionCost).filter_by(attraction_id=attraction.id).delete(
        synchronize_session=False
    )
    for row in rows:
        amount_min = float(row.get("min", row.get("amount", 0)))
        amount_max = float(row.get("max", amount_min))
        session.add(
            AttractionCost(
                attraction_id=attraction.id,
                visitor_type=row.get("visitor_type", "indian_adult"),
                currency=row.get("currency", "INR"),
                amount_min=amount_min,
                amount_max=max(amount_min, amount_max),
                is_free=bool(row.get("is_free", amount_max == 0)),
                note=row.get("note", ""),
                verified=bool(row.get("verified", False)),
            )
        )


def _replace_sources(session: Session, attraction: Attraction, rows: list[dict]) -> None:
    session.query(AttractionSource).filter_by(attraction_id=attraction.id).delete(
        synchronize_session=False
    )
    for row in rows:
        session.add(
            AttractionSource(
                attraction_id=attraction.id,
                url=row["url"],
                title=row.get("title", ""),
                source_type=row.get("type", "official"),
                covers_fields=row.get("covers", []),
                last_verified_at=_parse_date(row.get("last_verified")),
            )
        )


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #
def load_seed_files(session: Session, payloads: list[dict]) -> dict[str, int]:
    counts = {"clusters": 0, "attractions": 0}
    for payload in payloads:
        cluster = _upsert_cluster(session, payload["cluster"])
        counts["clusters"] += 1
        for attraction_payload in payload.get("attractions", []):
            _upsert_attraction(session, cluster, attraction_payload)
            counts["attractions"] += 1
    session.flush()
    return counts


def load_all_seed_data(
    session: Session,
    *,
    seed_dir: Path | None = None,
    include_knowledge: bool = True,
    build_embeddings: bool = False,
) -> dict[str, int]:
    """Load catalogue (+ optionally the RAG knowledge base) idempotently."""
    payloads = read_seed_files(seed_dir)
    counts = load_seed_files(session, payloads)

    if include_knowledge:
        documents = build_knowledge_documents(payloads)
        knowledge_counts = sync_knowledge(session, documents, build_embeddings=build_embeddings)
        counts.update(knowledge_counts)

    log.info("seed.loaded", **counts)
    return counts
