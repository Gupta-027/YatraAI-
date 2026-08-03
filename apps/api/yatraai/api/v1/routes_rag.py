"""RAG assistant endpoints: cited place questions and selection reasoning."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from yatraai.api.v1.deps import (
    AiRateLimited,
    CurrentUser,
    DbSession,
    OptionalUser,
    RateLimited,
    load_trip,
    require_trip_member,
)
from yatraai.core.errors import ValidationFailure
from yatraai.services import catalog
from yatraai.services.rag.answer import (
    answer_question,
    suggested_questions,
    why_selected,
)
from yatraai.services.rag.retriever import retrieve

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    cluster_slug: str | None = Field(default=None, max_length=64)
    attraction_slug: str | None = Field(default=None, max_length=96)
    top_k: int = Field(default=5, ge=1, le=10)
    use_llm: bool = True


class CitationOut(BaseModel):
    index: int
    heading: str
    source_url: str
    source_type: str
    attraction_slug: str | None = None
    content_category: str = ""
    last_verified: str | None = None
    snippet: str = ""


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[CitationOut] = Field(default_factory=list)
    abstained: bool = False
    confidence: float = 0.0
    topic: str = ""
    strategy: str = ""
    provider: str = "template"
    is_fallback: bool = True
    latency_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)


class RetrievedChunkOut(BaseModel):
    chunk_id: str
    heading: str
    content_category: str
    attraction_slug: str | None = None
    source_url: str
    dense_score: float
    lexical_score: float
    fused_score: float
    rerank_score: float
    text: str


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a question about a place, answered only from cited sources",
    description=(
        "Hybrid retrieval (dense + BM25, fused with reciprocal rank fusion, then reranked) "
        "over the curated knowledge base. Citations are derived from lexical overlap between "
        "each answer sentence and the retrieved text, so they cannot be fabricated. "
        "If evidence is insufficient the endpoint abstains instead of guessing."
    ),
)
def ask(
    payload: AskRequest, session: DbSession, user: OptionalUser, _rl: AiRateLimited
) -> AskResponse:
    del user
    if payload.attraction_slug and not payload.cluster_slug:
        raise ValidationFailure("cluster_slug is required when attraction_slug is given")
    if payload.cluster_slug:
        catalog.get_cluster(session, payload.cluster_slug)

    result = answer_question(
        session,
        payload.question,
        cluster_slug=payload.cluster_slug,
        attraction_slug=payload.attraction_slug,
        top_k=payload.top_k,
        use_llm=payload.use_llm,
    )
    return AskResponse(**result.to_dict())


@router.get(
    "/suggested-questions",
    response_model=list[str],
    summary="Starter questions for the place assistant",
)
def get_suggested_questions(
    _rl: RateLimited, attraction_name: str | None = Query(default=None, max_length=120)
) -> list[str]:
    return suggested_questions(attraction_name)


@router.post(
    "/retrieve",
    response_model=list[RetrievedChunkOut],
    summary="Inspect raw retrieval (debug / evaluation)",
    description="Returns the retrieved chunks with dense, lexical, fused and rerank scores.",
)
def debug_retrieve(
    payload: AskRequest, session: DbSession, _rl: AiRateLimited
) -> list[RetrievedChunkOut]:
    result = retrieve(
        session,
        payload.question,
        cluster_slug=payload.cluster_slug,
        attraction_slug=payload.attraction_slug,
        top_k=payload.top_k,
    )
    return [
        RetrievedChunkOut(
            chunk_id=c.chunk_id,
            heading=c.heading,
            content_category=c.content_category,
            attraction_slug=c.attraction_slug,
            source_url=c.source_url,
            dense_score=c.dense_score,
            lexical_score=c.lexical_score,
            fused_score=c.fused_score,
            rerank_score=c.rerank_score,
            text=c.text,
        )
        for c in result.chunks
    ]


@router.get(
    "/trips/{trip_id}/why/{attraction_slug}",
    summary="Why was this place selected for our group?",
    description="Answered from the stored, explainable score breakdown - no LLM involved.",
)
def explain_selection(
    trip_id: uuid.UUID,
    attraction_slug: str,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
) -> dict:
    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)
    return {
        "attraction_slug": attraction_slug,
        "explanation": why_selected(session, trip_id, attraction_slug),
        "source": "deterministic_score_breakdown",
    }
