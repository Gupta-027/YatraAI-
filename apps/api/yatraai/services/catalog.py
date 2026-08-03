"""Catalogue access: DB rows -> planner domain types.

Keeping this conversion in one place is what lets the whole optimisation stack
stay database-free and unit-testable.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from yatraai.core.errors import NotFoundError
from yatraai.db.models import (
    Attraction,
    AttractionCost,
    AttractionSchedule,
    DestinationCluster,
)
from yatraai.services.planner.models import AttractionCandidate, OpeningWindow

# Which visitor types contribute to the "what a domestic adult pays" estimate.
PRIMARY_COST_TYPES = {"indian_adult"}


def get_cluster(session: Session, slug: str) -> DestinationCluster:
    cluster = session.scalar(select(DestinationCluster).where(DestinationCluster.slug == slug))
    if cluster is None:
        raise NotFoundError(f"Destination '{slug}' not found", code="cluster_not_found")
    return cluster


def list_clusters(session: Session, *, active_only: bool = True) -> list[DestinationCluster]:
    stmt = select(DestinationCluster).order_by(DestinationCluster.name)
    if active_only:
        stmt = stmt.where(DestinationCluster.is_active.is_(True))
    return list(session.scalars(stmt))


def cluster_attraction_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(DestinationCluster.slug, func.count(Attraction.id))
        .join(Attraction, Attraction.cluster_id == DestinationCluster.id, isouter=True)
        .where(Attraction.is_active.is_(True))
        .group_by(DestinationCluster.slug)
    ).all()
    return {slug: int(count) for slug, count in rows}


def get_attraction(session: Session, cluster_slug: str, attraction_slug: str) -> Attraction:
    attraction = session.scalar(
        select(Attraction)
        .join(DestinationCluster)
        .where(
            DestinationCluster.slug == cluster_slug,
            Attraction.slug == attraction_slug,
        )
        .options(
            selectinload(Attraction.schedules),
            selectinload(Attraction.costs),
            selectinload(Attraction.sources),
            selectinload(Attraction.cluster),
        )
    )
    if attraction is None:
        raise NotFoundError(
            f"Attraction '{attraction_slug}' not found in '{cluster_slug}'",
            code="attraction_not_found",
        )
    return attraction


def find_attraction_by_slug(session: Session, slug: str) -> Attraction | None:
    """Global lookup - used to resolve cross-cluster 'nearby' references."""
    return session.scalar(
        select(Attraction)
        .where(Attraction.slug == slug, Attraction.is_active.is_(True))
        .options(selectinload(Attraction.cluster))
        .limit(1)
    )


def list_attractions(
    session: Session,
    cluster_slug: str,
    *,
    categories: Sequence[str] | None = None,
    active_only: bool = True,
) -> list[Attraction]:
    stmt = (
        select(Attraction)
        .join(DestinationCluster)
        .where(DestinationCluster.slug == cluster_slug)
        .options(
            selectinload(Attraction.schedules),
            selectinload(Attraction.costs),
            selectinload(Attraction.sources),
        )
        .order_by(Attraction.popularity_rank, Attraction.name)
    )
    if active_only:
        stmt = stmt.where(Attraction.is_active.is_(True))
    rows = list(session.scalars(stmt))
    if categories:
        wanted = {c.lower() for c in categories}
        rows = [a for a in rows if wanted & {c.lower() for c in (a.categories or [])}]
    return rows


# --------------------------------------------------------------------------- #
# Conversion
# --------------------------------------------------------------------------- #
def _entry_cost_band(costs: Sequence[AttractionCost]) -> tuple[float, float]:
    primary = [c for c in costs if c.visitor_type in PRIMARY_COST_TYPES]
    if not primary:
        # No domestic-adult row: assume free rather than inventing a number.
        return 0.0, 0.0
    return (
        float(min(c.amount_min for c in primary)),
        float(max(c.amount_max for c in primary)),
    )


def _windows(schedules: Sequence[AttractionSchedule]) -> tuple[list[OpeningWindow], set[int]]:
    windows: list[OpeningWindow] = []
    closed_days: set[int] = set()
    for row in schedules:
        if row.is_closed:
            if row.day_of_week >= 0:
                closed_days.add(row.day_of_week)
            continue
        if row.opens_min is None or row.closes_min is None:
            continue
        windows.append(
            OpeningWindow(
                day_of_week=row.day_of_week,
                opens_min=int(row.opens_min),
                closes_min=int(row.closes_min),
                season=row.season,
            )
        )
    return windows, closed_days


def to_candidate(
    attraction: Attraction, *, evidence_score: float | None = None
) -> AttractionCandidate:
    windows, closed_days = _windows(attraction.schedules)
    cost_min, cost_max = _entry_cost_band(attraction.costs)
    return AttractionCandidate(
        slug=attraction.slug,
        name=attraction.name,
        lat=float(attraction.lat),
        lon=float(attraction.lon),
        categories=list(attraction.categories or []),
        typical_duration_min=int(attraction.typical_duration_min),
        min_duration_min=int(attraction.min_duration_min),
        max_duration_min=int(attraction.max_duration_min),
        quality_score=float(attraction.quality_score),
        indoor_outdoor=attraction.indoor_outdoor,
        weather_sensitivity=float(attraction.weather_sensitivity),
        typical_crowd_level=attraction.typical_crowd_level,
        crowd_by_time=dict(attraction.crowd_by_time or {}),
        suitable_months=list(attraction.suitable_months or range(1, 13)),
        best_time_of_day=list(attraction.best_time_of_day or []),
        wheelchair_accessible=attraction.wheelchair_accessible,
        senior_friendly=int(attraction.senior_friendly),
        child_friendly=int(attraction.child_friendly),
        physical_intensity=int(attraction.physical_intensity),
        entry_cost_min=cost_min,
        entry_cost_max=cost_max,
        windows=windows,
        closed_weekdays=closed_days,
        needs_verification=bool(attraction.needs_verification),
        verification_note=attraction.verification_note or "",
        evidence_score=(
            evidence_score if evidence_score is not None else _evidence_score(attraction)
        ),
        attraction_id=str(attraction.id),
        cluster_slug=attraction.cluster.slug if attraction.cluster else "",
    )


def _evidence_score(attraction: Attraction) -> float:
    """Mirror of the Gold-layer evidence feature, computed from ORM rows."""
    type_scores = {
        "official": 1.0,
        "government": 0.95,
        "encyclopedic": 0.6,
        "openstreetmap": 0.55,
        "editorial": 0.4,
    }
    sources = attraction.sources or []
    best = max((type_scores.get(s.source_type, 0.4) for s in sources), default=0.4)
    confidence = {"high": 1.0, "medium": 0.65, "low": 0.35}.get(attraction.data_confidence, 0.65)
    completeness = (
        0.4 * bool((attraction.history or "").strip())
        + 0.3 * bool((attraction.significance or "").strip())
        + 0.2 * min(1.0, len(attraction.interesting_facts or []) / 3.0)
        + 0.1
        * bool(
            (attraction.dress_code or "").strip() or (attraction.photography_policy or "").strip()
        )
    )
    return round(
        0.45 * best + 0.20 * min(1.0, len(sources) / 2.0) + 0.20 * confidence + 0.15 * completeness,
        4,
    )


def load_candidates(session: Session, cluster_slug: str) -> list[AttractionCandidate]:
    return [to_candidate(a) for a in list_attractions(session, cluster_slug)]


def resolve_nearby(session: Session, attraction: Attraction, limit: int = 5) -> list[Attraction]:
    """Resolve neighbour slugs, preferring the same cluster then falling back globally."""
    out: list[Attraction] = []
    for slug in (attraction.nearby_attraction_slugs or [])[:limit]:
        row = session.scalar(
            select(Attraction).where(
                Attraction.cluster_id == attraction.cluster_id, Attraction.slug == slug
            )
        )
        if row is None:
            row = find_attraction_by_slug(session, slug)
        if row is not None and row.id != attraction.id:
            out.append(row)
    return out


def attraction_by_id(session: Session, attraction_id: str | uuid.UUID) -> Attraction:
    row = session.get(Attraction, uuid.UUID(str(attraction_id)))
    if row is None:
        raise NotFoundError("Attraction not found", code="attraction_not_found")
    return row
