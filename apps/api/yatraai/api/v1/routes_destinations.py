"""Destination discovery and attraction detail (the "Know this place" payload)."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from yatraai.api.v1 import serializers
from yatraai.api.v1.deps import DbSession, RateLimited
from yatraai.db.models import DocumentChunk
from yatraai.schemas.catalog import (
    AttractionDetail,
    AttractionSummary,
    ClusterDetail,
    ClusterSummary,
)
from yatraai.services import catalog

router = APIRouter(prefix="/destinations", tags=["destinations"])


@router.get(
    "",
    response_model=list[ClusterSummary],
    summary="List supported destination clusters",
)
def list_destinations(session: DbSession, _rl: RateLimited) -> list[ClusterSummary]:
    counts = catalog.cluster_attraction_counts(session)
    return [
        serializers.cluster_summary(c, counts.get(c.slug, 0))
        for c in catalog.list_clusters(session)
    ]


@router.get(
    "/{cluster_slug}",
    response_model=ClusterDetail,
    summary="Destination detail with category and accessibility coverage",
)
def get_destination(cluster_slug: str, session: DbSession, _rl: RateLimited) -> ClusterDetail:
    cluster = catalog.get_cluster(session, cluster_slug)
    attractions = catalog.list_attractions(session, cluster_slug)
    return serializers.cluster_detail(cluster, attractions)


@router.get(
    "/{cluster_slug}/attractions",
    response_model=list[AttractionSummary],
    summary="Attractions in a destination",
)
def list_attractions(
    cluster_slug: str,
    session: DbSession,
    _rl: RateLimited,
    category: list[str] | None = Query(default=None, description="Filter by category tag"),
    accessible_only: bool = Query(default=False),
    indoor_only: bool = Query(default=False),
    max_intensity: int | None = Query(default=None, ge=1, le=5),
) -> list[AttractionSummary]:
    rows = catalog.list_attractions(session, cluster_slug, categories=category)
    if accessible_only:
        rows = [a for a in rows if a.wheelchair_accessible in ("yes", "partial")]
    if indoor_only:
        rows = [a for a in rows if a.indoor_outdoor in ("indoor", "mixed")]
    if max_intensity is not None:
        rows = [a for a in rows if a.physical_intensity <= max_intensity]
    return [serializers.attraction_summary(a, cluster_slug) for a in rows]


@router.get(
    "/{cluster_slug}/attractions/{attraction_slug}",
    response_model=AttractionDetail,
    summary="Full place detail: history, significance, facts, etiquette, sources",
)
def get_attraction(
    cluster_slug: str, attraction_slug: str, session: DbSession, _rl: RateLimited
) -> AttractionDetail:
    attraction = catalog.get_attraction(session, cluster_slug, attraction_slug)
    topics = list(
        session.scalars(
            select(DocumentChunk.content_category)
            .where(DocumentChunk.attraction_slug == attraction_slug)
            .distinct()
        )
    )
    return serializers.attraction_detail(session, attraction, knowledge_topics=sorted(topics))
