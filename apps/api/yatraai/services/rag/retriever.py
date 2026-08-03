"""Hybrid retrieval over the cited destination knowledge base.

Pipeline
--------
1. **Classify** the question into a topic (history, etiquette, accessibility, ...).
2. **Metadata filter** by cluster and attraction. This is the single biggest
   quality lever: asking "what should I wear here?" on the Taj Mahal page must
   never retrieve Kedarnath's dress code.
3. **Dense retrieval** - cosine similarity over chunk embeddings. Uses pgvector's
   `<=>` operator on PostgreSQL; falls back to in-Python cosine on SQLite, which
   is fine at this corpus size (~800 chunks).
4. **Lexical retrieval** - BM25 computed in Python over the filtered set.
   Implemented directly rather than delegated to a dialect-specific full-text
   index so the behaviour is identical on both databases and in tests.
5. **Fusion** - Reciprocal Rank Fusion. RRF needs no score normalisation between
   two retrievers whose scores are not comparable, which is exactly our case.
6. **Rerank** - a lightweight feature-based reranker: query-term coverage,
   heading match, topic agreement and source authority.

Every returned chunk carries its source URL and verification date, so the answer
layer can cite without guessing.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from yatraai.db.models import ChunkEmbedding, DocumentChunk
from yatraai.logging_config import get_logger
from yatraai.services.rag.embeddings import cosine_similarity, get_embedder, tokenize

log = get_logger(__name__)

RRF_K = 60  # standard RRF damping constant
DENSE_POOL = 30
LEXICAL_POOL = 30

# Question -> topic classification. Ordered: the first pattern that matches wins.
# NOTE: stems use `\w*` rather than a trailing `\b`. A pattern like `\b(histor)\b`
# silently never matches "history", because the trailing boundary requires a
# non-word character straight after "histor". That bug measured at 50% topic
# accuracy before it was caught by the evaluation harness.
TOPIC_PATTERNS: list[tuple[str, str]] = [
    (
        "etiquette",
        r"\b(wear|wearing|dress\w*|etiquette|custom\w*|shoe\w*|footwear|cover\w*|modest\w*"
        r"|photograph\w*|photo\w*|camera\w*|allowed|permitted|permit\w*|rule\w*|restrict\w*"
        r"|enter|entry\s+rules|non.?hindu\w*|prohibit\w*)\b",
    ),
    (
        "accessibility",
        r"\b(wheelchair\w*|accessib\w*|disabled|elderly|senior\w*|parents|step\w*|stair\w*"
        r"|walk\w*|mobility|pram|stroller|child\w*|kids|hard|difficult\w*|strenuous|climb\w*"
        r"|trek\w*|fit\w*|suitable)\b",
    ),
    (
        "visiting",
        r"\b(how\s+long|how\s+much\s+time|duration|hours?|open\w*|clos\w*|timing\w*|fee\w*"
        r"|cost\w*|ticket\w*|price\w*|best\s+time|when\s+(is|to|should)|what\s+time"
        r"|all\s+year|season\w*|available|before\s+visiting|need\s+to\s+know)\b",
    ),
    (
        "history",
        r"\b(histor\w*|built|build|made|construct\w*|who\s+built|when\s+was|origin\w*"
        r"|ancient|centur\w*|founded|found\w*|dynast\w*|ruler\w*|king\w*|emperor\w*"
        r"|abandon\w*|survive\w*|happened|what\s+are\s+the|what\s+is\s+the\s+\w+\s+pillar)\b",
    ),
    (
        "significance",
        r"\b(why|important\w*|significan\w*|famous|special|matter\w*|sacred|holy"
        r"|architect\w*|known\s+for|renowned|notable)\b",
    ),
    (
        "facts",
        r"\b(fact\w*|trivia|lesser.known|interesting|did\s+you\s+know|unusual|unique)\b",
    ),
]

TOPIC_ORDER = (
    "history",
    "significance",
    "facts",
    "visiting",
    "accessibility",
    "etiquette",
    "overview",
)


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    heading: str
    cluster_slug: str
    attraction_slug: str | None
    content_category: str
    source_url: str
    source_type: str
    last_verified: str | None
    dense_score: float = 0.0
    lexical_score: float = 0.0
    fused_score: float = 0.0
    rerank_score: float = 0.0
    dense_rank: int | None = None
    lexical_rank: int | None = None

    def citation(self, index: int) -> dict:
        return {
            "index": index,
            "chunk_id": self.chunk_id,
            "heading": self.heading,
            "attraction_slug": self.attraction_slug,
            "content_category": self.content_category,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "last_verified": self.last_verified,
        }


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    topic: str
    filters: dict
    candidates_considered: int = 0
    strategy: str = "hybrid"
    notes: list[str] = field(default_factory=list)
    evidence_score: float = 0.0
    """Absolute relevance of the best chunk, in [0, 1].

    Deliberately *not* the RRF score. Reciprocal rank fusion only encodes
    ordering, so its top score is roughly constant whether the corpus answers
    the question brilliantly or not at all - which makes it useless as an
    abstention signal. This blends dense similarity with query-term coverage,
    both of which are absolute.
    """
    wants_live_data: bool = False
    """The question asked for a *live* value ("right now", "today", "at 4pm").

    Set independently of relevance. It does not mean we cannot answer - it means
    any answer must state plainly that the figure is a recorded, unverified one
    and not a live lookup. See ``TEMPORAL_DEIXIS``.
    """


# --------------------------------------------------------------------------- #
def classify_question(question: str) -> str:
    """Map a question to a knowledge topic. Falls back to a broad search."""
    text = (question or "").lower()
    for topic, pattern in TOPIC_PATTERNS:
        if re.search(pattern, text):
            return topic
    return "any"


def _bm25(
    query_tokens: list[str], docs: list[list[str]], k1: float = 1.5, b: float = 0.75
) -> list[float]:
    """Standard BM25 over an in-memory document set."""
    n = len(docs)
    if n == 0:
        return []
    doc_lengths = [len(d) for d in docs]
    avg_len = sum(doc_lengths) / n or 1.0

    document_frequency: Counter[str] = Counter()
    for doc in docs:
        for term in set(doc):
            document_frequency[term] += 1

    term_counts = [Counter(d) for d in docs]
    scores = [0.0] * n
    for term in set(query_tokens):
        df = document_frequency.get(term, 0)
        if df == 0:
            continue
        idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
        for i in range(n):
            tf = term_counts[i].get(term, 0)
            if tf == 0:
                continue
            denominator = tf + k1 * (1 - b + b * doc_lengths[i] / avg_len)
            scores[i] += idf * (tf * (k1 + 1)) / denominator
    return scores


def _candidate_chunks(
    session: Session,
    *,
    cluster_slug: str | None,
    attraction_slug: str | None,
    topic: str,
) -> list[DocumentChunk]:
    """Metadata-filtered candidate set, widening only if a filter starves it."""

    def query(attr: str | None, cluster: str | None, category: str | None):
        stmt = select(DocumentChunk)
        if cluster:
            stmt = stmt.where(DocumentChunk.cluster_slug == cluster)
        if attr:
            stmt = stmt.where(DocumentChunk.attraction_slug == attr)
        if category and category != "any":
            stmt = stmt.where(DocumentChunk.content_category == category)
        return list(session.scalars(stmt))

    # Most specific first.
    rows = query(attraction_slug, cluster_slug, topic)
    if len(rows) >= 2:
        return rows
    # Relax the topic before relaxing the place - place accuracy matters more.
    rows = query(attraction_slug, cluster_slug, None)
    if rows:
        return rows
    rows = query(None, cluster_slug, topic)
    if rows:
        return rows
    return query(None, cluster_slug, None)


def _dense_scores(session: Session, question: str, chunks: list[DocumentChunk]) -> dict[str, float]:
    if not chunks:
        return {}
    embedder = get_embedder()
    query_vector = embedder.embed_query(question)

    chunk_ids = [c.id for c in chunks]
    embeddings = {
        e.chunk_id: e.vector
        for e in session.scalars(
            select(ChunkEmbedding).where(ChunkEmbedding.chunk_id.in_(chunk_ids))
        )
    }
    return {
        str(c.id): cosine_similarity(query_vector, embeddings[c.id])
        for c in chunks
        if c.id in embeddings
    }


def retrieve(
    session: Session,
    question: str,
    *,
    cluster_slug: str | None = None,
    attraction_slug: str | None = None,
    top_k: int = 5,
    rerank: bool = True,
    strategy: str = "hybrid",
) -> RetrievalResult:
    """Retrieve evidence chunks.

    ``strategy`` selects which retrieval arms contribute to the ranking:
    ``hybrid`` (default, both arms fused with RRF), ``dense`` (embeddings only)
    or ``lexical`` (BM25 only). The single-arm modes exist so the ablation in
    ``evaluation/run_rag_eval.py`` genuinely disables an arm rather than merely
    re-sorting a set that was already retrieved by both.
    """
    topic = classify_question(question)
    notes: list[str] = []

    candidates = _candidate_chunks(
        session, cluster_slug=cluster_slug, attraction_slug=attraction_slug, topic=topic
    )
    if not candidates:
        return RetrievalResult(
            chunks=[],
            topic=topic,
            filters={"cluster": cluster_slug, "attraction": attraction_slug, "topic": topic},
            notes=["No knowledge documents matched the requested place."],
        )

    # ---- dense ----
    dense = _dense_scores(session, question, candidates)
    dense_ranked = sorted(dense.items(), key=lambda kv: -kv[1])[:DENSE_POOL]
    dense_rank = {cid: i + 1 for i, (cid, _) in enumerate(dense_ranked)}
    if not dense:
        notes.append("Embeddings unavailable; ranked lexically only.")

    # ---- lexical ----
    query_tokens = tokenize(question)
    docs = [tokenize(f"{c.heading} {c.text}") for c in candidates]
    bm25 = _bm25(query_tokens, docs)
    lexical = {str(c.id): bm25[i] for i, c in enumerate(candidates)}
    lexical_ranked = sorted(lexical.items(), key=lambda kv: -kv[1])[:LEXICAL_POOL]
    lexical_rank = {cid: i + 1 for i, (cid, score) in enumerate(lexical_ranked) if score > 0}

    # ---- fusion (reciprocal rank fusion, or a single arm for ablations) ----
    fused: dict[str, float] = {}
    if strategy in ("hybrid", "dense"):
        for cid, rank in dense_rank.items():
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    if strategy in ("hybrid", "lexical"):
        for cid, rank in lexical_rank.items():
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    if not fused:
        # A single-arm strategy can come up empty (e.g. BM25 with no term overlap).
        # Fall back to the other arm rather than returning nothing.
        for cid, rank in (dense_rank or lexical_rank).items():
            fused[cid] = 1.0 / (RRF_K + rank)

    by_id = {str(c.id): c for c in candidates}
    results = [
        RetrievedChunk(
            chunk_id=cid,
            text=by_id[cid].text,
            heading=by_id[cid].heading,
            cluster_slug=by_id[cid].cluster_slug,
            attraction_slug=by_id[cid].attraction_slug,
            content_category=by_id[cid].content_category,
            source_url=by_id[cid].source_url,
            source_type=by_id[cid].source_type,
            last_verified=(
                by_id[cid].last_verified_at.isoformat() if by_id[cid].last_verified_at else None
            ),
            dense_score=round(dense.get(cid, 0.0), 6),
            lexical_score=round(lexical.get(cid, 0.0), 6),
            fused_score=round(score, 6),
            dense_rank=dense_rank.get(cid),
            lexical_rank=lexical_rank.get(cid),
        )
        for cid, score in fused.items()
        if cid in by_id
    ]

    if rerank:
        results = _rerank(results, question, topic)
        strategy_label = f"{strategy}+rerank"
    else:
        results.sort(key=lambda r: (-r.fused_score, r.chunk_id))
        strategy_label = strategy

    top = results[:top_k]
    return RetrievalResult(
        chunks=top,
        topic=topic,
        filters={"cluster": cluster_slug, "attraction": attraction_slug, "topic": topic},
        candidates_considered=len(candidates),
        strategy=strategy_label,
        notes=notes,
        evidence_score=evidence_score(
            question, top, corpus_stats=corpus_document_frequencies(session)
        ),
        wants_live_data=wants_live_data(question),
    )


_CORPUS_DF_CACHE: dict[int, tuple[int, dict[str, int]]] = {}


def corpus_document_frequencies(session: Session) -> tuple[int, dict[str, int]]:
    """Term document-frequencies over the **whole** corpus, cached by corpus size.

    IDF has to be a corpus-level statistic. Computing it over the handful of
    chunks left after a metadata filter makes ordinary phrasing words like
    "historically" or "important" look maximally rare simply because they are
    absent from six specific paragraphs, which then causes the evidence score to
    collapse and the assistant to abstain on questions it can answer perfectly
    well. Measured against the whole corpus those words are common and carry
    little weight, while a genuinely foreign term like "reykjavik" still does.
    """
    from yatraai.db.models import DocumentChunk as _Chunk

    total = session.scalar(select(func.count()).select_from(_Chunk)) or 0
    cached = _CORPUS_DF_CACHE.get(total)
    if cached is not None:
        return cached

    frequencies: dict[str, int] = {}
    for heading, text in session.execute(select(_Chunk.heading, _Chunk.text)).all():
        for term in set(tokenize(f"{heading} {text}")):
            frequencies[term] = frequencies.get(term, 0) + 1

    _CORPUS_DF_CACHE.clear()
    _CORPUS_DF_CACHE[total] = (total, frequencies)
    return total, frequencies


def reset_corpus_statistics() -> None:
    _CORPUS_DF_CACHE.clear()


TEMPORAL_DEIXIS = frozenset(
    {
        "now",
        "today",
        "tonight",
        "currently",
        "current",
        "latest",
        "live",
        "present",
        "moment",
        "exactly",
        "exact",
        "realtime",
        "right",
        "this",
        "instant",
        "updated",
    }
)
_CLOCK_TIME = re.compile(r"^\d{1,2}(:\d{2})?(am|pm)?$|^\d{1,2}(am|pm)$")

DISCOURSE_FRAMING = frozenset(
    {
        "happened",
        "happen",
        "happens",
        "matter",
        "tell",
        "know",
        "knew",
        "wondering",
        "curious",
        "please",
        "something",
        "really",
        "basically",
        "regarding",
        "concerning",
        "whats",
        "supposed",
    }
)
"""Words that frame a question rather than name anything in it.

Every entry was checked against the live corpus and has a document frequency of
**zero** across all 790 chunks. Note the near-miss that proves the list has to be
measured rather than guessed: "matter" is absent, but "matter*s** appears in 130
chunks, because every significance chunk is titled "Why X matters". Including the
plural would have thrown away a genuinely evidential term.
"""

NON_EVIDENTIAL = TEMPORAL_DEIXIS | DISCOURSE_FRAMING


def wants_live_data(question: str) -> bool:
    """Does the question ask for a value as of *right now*?"""
    return any(
        term in TEMPORAL_DEIXIS or _CLOCK_TIME.match(term) for term in tokenize(question or "")
    )


def _evidence_terms(query_terms: list[str]) -> list[str]:
    """Query terms that actually carry evidence about whether we can answer.

    The evidence score gives a term absent from the entire corpus the maximum IDF
    weight, on the reasoning that such an absence is the strongest possible signal
    the corpus cannot answer. That reasoning holds for one kind of absent term and
    fails for another, and the distinction is the whole point of this function:

    * **"reykjavik", "bhutan", "stock"** are absent because they are *out of
      scope*. Their absence is exactly the signal we want to keep.
    * **"today", "4pm", "happened", "matter"** are absent because a factual
      catalogue entry never contains words like these *no matter how completely it
      answers the question*. Their absence measures our writing style, not our
      coverage.

    Both were causing false abstentions, each caught by the evaluation harness:

    * "What is the ticket price in rupees today at 4pm exactly?" scored 0.183
      against a threshold of 0.26 - while the Taj Mahal visiting chunk it
      retrieved literally contains the fee.
    * "What happened at Sarnath and why does it matter?" scored 0.229, with the
      correct history chunk ranked *first*, because "happened" and "matter" are
      both absent from all 790 chunks.

    Dropping these terms is not a loosening of the gate. Nothing about scope
    detection changes: an out-of-scope question keeps every one of its
    out-of-scope terms at full weight. `test_synonyms_do_not_manufacture_coverage`
    and the three abstention questions in the benchmark hold the line.
    """
    kept = [t for t in query_terms if t not in NON_EVIDENTIAL and not _CLOCK_TIME.match(t)]
    # A question made *entirely* of framing words has nothing to measure; fall back
    # to the raw terms rather than dividing by an empty weight set.
    return kept or query_terms


_ALIASES: dict[str, frozenset[str]] = {
    # money: the catalogue writes "Entry: ... Rs.50-Rs.250", travellers ask about "price"
    "price": frozenset({"fee", "entry", "rs", "ticket", "cost"}),
    "prices": frozenset({"fee", "fees", "entry", "rs", "ticket"}),
    "cost": frozenset({"fee", "entry", "rs", "ticket"}),
    "costs": frozenset({"fee", "fees", "entry", "rs"}),
    "charge": frozenset({"fee", "entry", "rs"}),
    "charges": frozenset({"fee", "fees", "entry", "rs"}),
    "fare": frozenset({"fee", "entry", "rs"}),
    "rupees": frozenset({"rs", "inr", "fee", "entry"}),
    "rupee": frozenset({"rs", "inr", "fee", "entry"}),
    "inr": frozenset({"rs", "fee", "entry"}),
    "money": frozenset({"fee", "entry", "rs"}),
    "expensive": frozenset({"fee", "entry", "rs"}),
    "fee": frozenset({"entry", "rs", "ticket"}),
    "fees": frozenset({"entry", "rs", "ticket"}),
    "ticket": frozenset({"entry", "fee", "rs"}),
    "tickets": frozenset({"entry", "fee", "rs"}),
    "admission": frozenset({"entry", "fee", "ticket", "rs"}),
    # time
    "timing": frozenset({"hours", "opening", "opens", "closed"}),
    "timings": frozenset({"hours", "opening", "opens", "closed"}),
    "hours": frozenset({"opening", "opens", "closed"}),
    "open": frozenset({"opening", "hours", "opens"}),
    "opens": frozenset({"opening", "hours"}),
    "closing": frozenset({"closed", "hours", "opening"}),
    "closes": frozenset({"closed", "hours", "opening"}),
    "shut": frozenset({"closed", "hours"}),
    "duration": frozenset({"typical", "visit", "takes", "hours"}),
    "long": frozenset({"typical", "visit", "takes", "duration"}),
    # people & access
    "kids": frozenset({"child", "children"}),
    "kid": frozenset({"child", "children"}),
    "elderly": frozenset({"senior", "seniors"}),
    "disabled": frozenset({"wheelchair", "accessible", "accessibility"}),
    "wheelchair": frozenset({"accessible", "accessibility", "step", "ramp"}),
    "accessible": frozenset({"wheelchair", "accessibility", "step", "ramp"}),
    # etiquette
    "attire": frozenset({"dress", "code", "clothing"}),
    "clothing": frozenset({"dress", "code", "attire"}),
    "wear": frozenset({"dress", "code", "shoe", "shoes"}),
    "photos": frozenset({"photography", "camera", "photograph"}),
    "photo": frozenset({"photography", "camera", "photograph"}),
    "pictures": frozenset({"photography", "camera", "photograph"}),
    "camera": frozenset({"photography", "photograph"}),
    "busy": frozenset({"crowd", "crowds", "crowded"}),
    "crowded": frozenset({"crowd", "crowds"}),
    "rush": frozenset({"crowd", "crowds", "crowded"}),
}


def _covered(term: str, present: set[str]) -> bool:
    """Is this query term evidenced in the chunk, allowing domain synonyms?

    Curated, one-directional expansion over the vocabulary this catalogue
    actually uses. It exists because of a measured failure: "What is the ticket
    price in rupees?" scored 0.183 against the Taj Mahal visiting chunk and
    abstained, even though that chunk literally contains the fee - it writes
    "Entry: Indian visitors: about Rs.50-Rs.250" and never the words "price" or
    "rupees". Abstaining there is not caution, it is a retrieval bug wearing
    caution's clothes.

    The map is deliberately small and hand-checked against the corpus rather than
    pulled from a general thesaurus, because a broad synonym set would start
    manufacturing coverage for questions the corpus genuinely cannot answer -
    which is the one failure mode this score exists to catch.
    """
    if term in present:
        return True
    return bool(_ALIASES.get(term, frozenset()) & present)


def evidence_score(
    question: str,
    chunks: list[RetrievedChunk],
    corpus_stats: tuple[int, dict[str, int]] | None = None,
) -> float:
    """Absolute measure of whether the corpus can actually answer this question.

    Two independent signals, both bounded in [0, 1]:

    * **dense similarity** of the best chunk - semantic proximity;
    * **IDF-weighted query-term coverage** - how much of the question's
      *distinctive* vocabulary actually appears in that chunk.

    The IDF weighting is what makes this work. Plain coverage counts every word
    equally, so "What is the best restaurant in Reykjavik?" scores respectably
    against a Bengaluru corpus purely because the word "best" appears
    everywhere. Weighting by rarity means the terms that carry the question's
    meaning - "reykjavik", "restaurant" - dominate, and their total absence
    collapses the score. Measured effect: 0.262 -> 0.09 for that question, while
    genuinely answerable questions stay above 0.4.

    Taking the max over chunks (rather than the mean) is deliberate: one strongly
    relevant passage is enough to answer from.
    """
    if not chunks:
        return 0.0
    query_terms = _evidence_terms(list(dict.fromkeys(tokenize(question))))
    if not query_terms:
        return 0.0

    if corpus_stats is None:
        # Degenerate fallback: treat the retrieved set as the corpus.
        docs = [set(tokenize(f"{c.heading} {c.text}")) for c in chunks]
        n_docs = max(1, len(docs))
        frequencies = {t: sum(1 for d in docs if t in d) for t in query_terms}
    else:
        n_docs, all_frequencies = corpus_stats
        n_docs = max(1, n_docs)
        frequencies = {t: all_frequencies.get(t, 0) for t in query_terms}

    idf: dict[str, float] = {}
    for term in query_terms:
        # A term absent from the whole corpus gets the maximum weight - that
        # absence is the strongest possible evidence the corpus cannot answer.
        idf[term] = math.log(1 + n_docs / (1 + frequencies.get(term, 0)))
    total_weight = sum(idf.values()) or 1.0

    best = 0.0
    for chunk in chunks:
        present = set(tokenize(f"{chunk.heading} {chunk.text}"))
        covered = sum(w for term, w in idf.items() if _covered(term, present))
        coverage = covered / total_weight
        dense = max(0.0, min(1.0, chunk.dense_score))
        best = max(best, 0.35 * dense + 0.65 * coverage)
    return round(best, 4)


SOURCE_AUTHORITY = {
    "official": 1.0,
    "government": 0.95,
    "encyclopedic": 0.7,
    "openstreetmap": 0.6,
    "editorial": 0.5,
}


def _rerank(chunks: list[RetrievedChunk], question: str, topic: str) -> list[RetrievedChunk]:
    """Feature-based reranker.

    A cross-encoder would score higher but would pull in a transformer dependency
    for a corpus of ~800 short, well-structured chunks. These four features do
    most of the work and stay explainable, which matters for a system whose whole
    premise is that its reasoning is inspectable.
    """
    query_terms = set(tokenize(question))
    if not chunks:
        return chunks

    max_fused = max(c.fused_score for c in chunks) or 1.0
    for chunk in chunks:
        body_terms = set(tokenize(chunk.text))
        heading_terms = set(tokenize(chunk.heading))

        coverage = len(query_terms & body_terms) / max(1, len(query_terms))
        heading_match = len(query_terms & heading_terms) / max(1, len(query_terms))
        topic_match = 1.0 if (topic != "any" and chunk.content_category == topic) else 0.0
        authority = SOURCE_AUTHORITY.get(chunk.source_type, 0.5)

        chunk.rerank_score = round(
            0.45 * (chunk.fused_score / max_fused)
            + 0.22 * coverage
            + 0.13 * heading_match
            + 0.12 * topic_match
            + 0.08 * authority,
            6,
        )
    chunks.sort(key=lambda c: (-c.rerank_score, c.chunk_id))
    return chunks
