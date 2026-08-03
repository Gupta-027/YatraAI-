"""Product analytics and observability aggregation.

Privacy rule enforced here, not just documented: **no precise location ever
enters an analytics row**. Location is summarised as counts and coarse
aggregates only; see ``docs/privacy.md``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from yatraai.db.models import (
    AnalyticsEvent,
    Attraction,
    ChangeProposal,
    DestinationCluster,
    Feedback,
    Itinerary,
    LocationSharingSession,
    PipelineRun,
    RagEvaluation,
    Trip,
    TripMember,
)
from yatraai.logging_config import get_logger

log = get_logger(__name__)

_FORBIDDEN_PROPERTY_KEYS = {"lat", "lon", "latitude", "longitude", "coords", "coordinates"}


def record_event(
    session: Session,
    event: str,
    *,
    trip_id: uuid.UUID | None = None,
    cluster_slug: str | None = None,
    user_id: uuid.UUID | None = None,
    numeric_value: float | None = None,
    properties: dict | None = None,
) -> None:
    """Record a product event. Coordinate-like keys are stripped, not trusted."""
    clean = {
        k: v for k, v in (properties or {}).items() if k.lower() not in _FORBIDDEN_PROPERTY_KEYS
    }
    session.add(
        AnalyticsEvent(
            event=event,
            trip_id=trip_id,
            cluster_slug=cluster_slug,
            user_id=user_id,
            numeric_value=numeric_value,
            properties=clean,
        )
    )


def record_pipeline_freshness(payload: dict) -> dict:
    """Called by the Airflow DAG after a successful run."""
    from yatraai.db.session import session_scope

    with session_scope() as session:
        record_event(session, "pipeline_completed", properties=payload)
    return {"recorded": True}


# --------------------------------------------------------------------------- #
def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def dashboard_metrics(session: Session, days: int = 90) -> dict:
    """Everything the analytics dashboard renders, in one query batch."""
    since = datetime.now(UTC) - timedelta(days=days)

    total_trips = session.scalar(select(func.count()).select_from(Trip)) or 0
    total_itineraries = session.scalar(select(func.count()).select_from(Itinerary)) or 0

    # ---- destination popularity ----
    popularity = [
        {"cluster_slug": slug, "name": name, "trips": int(count)}
        for slug, name, count in session.execute(
            select(DestinationCluster.slug, DestinationCluster.name, func.count(Trip.id))
            .join(Trip, Trip.cluster_id == DestinationCluster.id, isouter=True)
            .group_by(DestinationCluster.id)
            .order_by(func.count(Trip.id).desc())
        ).all()
    ]

    # ---- averages ----
    avg_budget = session.scalar(
        select(func.avg(Trip.budget_per_person_inr)).where(Trip.budget_per_person_inr.isnot(None))
    )
    avg_group_size = session.scalar(select(func.avg(Trip.traveller_count)))
    avg_days = (
        session.scalar(
            select(func.avg(func.julianday(Trip.end_date) - func.julianday(Trip.start_date)))
        )
        if session.bind and session.bind.dialect.name == "sqlite"
        else None
    )

    # ---- itinerary quality ----
    quality = session.execute(
        select(
            func.avg(Itinerary.fairness_score),
            func.avg(Itinerary.least_satisfied_score),
            func.avg(Itinerary.consensus_score),
            func.avg(Itinerary.total_travel_km),
            func.avg(Itinerary.activity_count),
            func.avg(Itinerary.cost_per_person_low_inr),
            func.avg(Itinerary.cost_per_person_high_inr),
        ).where(Itinerary.status.in_(("active", "superseded")))
    ).one()

    invalid = (
        session.scalar(
            select(func.count()).select_from(Itinerary).where(Itinerary.is_valid.is_(False))
        )
        or 0
    )
    regenerated = (
        session.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.version > 1))
        or 0
    )
    llm_explained = (
        session.scalar(
            select(func.count()).select_from(Itinerary).where(Itinerary.explanation_source == "llm")
        )
        or 0
    )

    # ---- modification behaviour ----
    removals = (
        session.scalar(
            select(func.count())
            .select_from(Itinerary)
            .where(Itinerary.trigger.in_(("remove_activity", "replace_activity")))
        )
        or 0
    )
    proposals = session.scalar(select(func.count()).select_from(ChangeProposal)) or 0
    proposals_applied = (
        session.scalar(
            select(func.count())
            .select_from(ChangeProposal)
            .where(ChangeProposal.status == "applied")
        )
        or 0
    )

    # ---- feedback / acceptance ----
    accepted = (
        session.scalar(
            select(func.count()).select_from(Feedback).where(Feedback.accepted.is_(True))
        )
        or 0
    )
    rejected = (
        session.scalar(
            select(func.count()).select_from(Feedback).where(Feedback.accepted.is_(False))
        )
        or 0
    )
    avg_rating = session.scalar(
        select(func.avg(Feedback.rating)).where(Feedback.rating.isnot(None))
    )

    # ---- estimated vs actual spend ----
    spend_rows = session.execute(
        select(
            Feedback.actual_spend_inr,
            Itinerary.cost_per_person_low_inr,
            Itinerary.cost_per_person_high_inr,
        )
        .join(Itinerary, Feedback.itinerary_id == Itinerary.id)
        .where(Feedback.actual_spend_inr.isnot(None))
    ).all()
    spend_comparison = _spend_accuracy(spend_rows)

    # ---- RAG quality ----
    rag = session.execute(
        select(
            func.avg(RagEvaluation.retrieval_precision),
            func.avg(RagEvaluation.faithfulness),
            func.avg(RagEvaluation.citation_correctness),
            func.avg(RagEvaluation.answer_completeness),
            func.avg(RagEvaluation.latency_ms),
            func.count(),
        )
    ).one()

    # ---- data freshness ----
    last_run = session.scalar(select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(1))

    # ---- privacy-safe location summary ----
    sharing_sessions = session.scalar(select(func.count()).select_from(LocationSharingSession)) or 0
    active_sharing = (
        session.scalar(
            select(func.count())
            .select_from(LocationSharingSession)
            .where(LocationSharingSession.status == "active")
        )
        or 0
    )

    from yatraai.core.telemetry import telemetry

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "window_days": days,
        "trips": {
            "total": total_trips,
            "with_itinerary": session.scalar(select(func.count(func.distinct(Itinerary.trip_id))))
            or 0,
            "recent": session.scalar(
                select(func.count()).select_from(Trip).where(Trip.created_at >= since)
            )
            or 0,
            "average_group_size": round(float(avg_group_size or 0), 2),
            "average_budget_per_person_inr": round(float(avg_budget or 0), 2),
            "average_duration_days": round(float(avg_days), 2) if avg_days else None,
            "average_members": round(
                float(session.scalar(select(func.count()).select_from(TripMember)) or 0)
                / max(1, total_trips),
                2,
            ),
        },
        "destination_popularity": popularity,
        "itineraries": {
            "total": total_itineraries,
            "average_fairness": round(float(quality[0] or 0), 4),
            "average_least_satisfied": round(float(quality[1] or 0), 4),
            "average_consensus": round(float(quality[2] or 0), 4),
            "average_travel_km": round(float(quality[3] or 0), 2),
            "average_activities": round(float(quality[4] or 0), 2),
            "average_cost_low_inr": round(float(quality[5] or 0), 2),
            "average_cost_high_inr": round(float(quality[6] or 0), 2),
            "constraint_violation_rate": _pct(invalid, total_itineraries),
            "regeneration_rate": _pct(regenerated, total_itineraries),
            "llm_explanation_rate": _pct(llm_explained, total_itineraries),
            "attraction_removal_events": removals,
        },
        "collaboration": {
            "proposals": proposals,
            "proposals_applied": proposals_applied,
            "proposal_approval_rate": _pct(proposals_applied, proposals),
        },
        "feedback": {
            "accepted": accepted,
            "rejected": rejected,
            "acceptance_rate": _pct(accepted, accepted + rejected),
            "average_rating": round(float(avg_rating), 2) if avg_rating else None,
            "spend_comparison": spend_comparison,
        },
        "rag": {
            "evaluations": int(rag[5] or 0),
            "average_retrieval_precision": round(float(rag[0] or 0), 4),
            "average_faithfulness": round(float(rag[1] or 0), 4),
            "average_citation_correctness": round(float(rag[2] or 0), 4),
            "average_completeness": round(float(rag[3] or 0), 4),
            "average_latency_ms": round(float(rag[4] or 0), 2),
        },
        "providers": telemetry.summary(),
        "data_freshness": {
            "last_pipeline": last_run.pipeline if last_run else None,
            "last_run_at": last_run.finished_at.isoformat()
            if last_run and last_run.finished_at
            else None,
            "rows_out": last_run.rows_out if last_run else 0,
            "status": last_run.status if last_run else "never_run",
        },
        "location_privacy": {
            "sessions_total": sharing_sessions,
            "sessions_active": active_sharing,
            "note": "Counts only. Coordinates are never recorded in analytics.",
        },
    }


def _spend_accuracy(rows) -> dict:
    if not rows:
        return {
            "samples": 0,
            "note": (
                "No actual-spend feedback recorded yet, so no prediction error is reported. "
                "We do not publish an accuracy figure we have not measured."
            ),
        }
    inside = 0
    errors = []
    for actual, low, high in rows:
        actual = float(actual)
        midpoint = (float(low) + float(high)) / 2
        if low <= actual <= high:
            inside += 1
        if midpoint:
            errors.append(abs(actual - midpoint) / midpoint)
    return {
        "samples": len(rows),
        "within_estimated_range": _pct(inside, len(rows)),
        "mean_absolute_percentage_error": round(sum(errors) / len(errors), 4) if errors else None,
    }


def attraction_selection_stats(session: Session, limit: int = 20) -> list[dict]:
    """Which attractions the planner picks most, and which get removed."""
    from yatraai.db.models import RecommendationScore

    rows = session.execute(
        select(
            RecommendationScore.attraction_slug,
            func.count().label("scored"),
            func.sum(func.cast(RecommendationScore.selected, __import__("sqlalchemy").Integer)),
            func.avg(RecommendationScore.total_score),
        )
        .group_by(RecommendationScore.attraction_slug)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()

    names = dict(session.execute(select(Attraction.slug, Attraction.name)).all())
    return [
        {
            "attraction_slug": slug,
            "name": names.get(slug, slug),
            "times_scored": int(scored),
            "times_selected": int(selected or 0),
            "selection_rate": _pct(int(selected or 0), int(scored)),
            "average_score": round(float(avg_score or 0), 4),
        }
        for slug, scored, selected, avg_score in rows
    ]
