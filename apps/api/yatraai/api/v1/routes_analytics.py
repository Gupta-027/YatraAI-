"""Analytics, feedback and the admin data-quality dashboard."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from yatraai.api.v1.deps import (
    AdminUser,
    CurrentUser,
    DbSession,
    OptionalUser,
    RateLimited,
    load_trip,
    require_trip_member,
)
from yatraai.core.security import sanitize_text
from yatraai.db.models import Feedback
from yatraai.schemas.common import Ack
from yatraai.services.analytics import (
    attraction_selection_stats,
    dashboard_metrics,
    record_event,
)
from yatraai.services.data_quality import coverage_summary, run_quality_checks

router = APIRouter(tags=["analytics"])


# --------------------------------------------------------------------------- #
# Feedback
# --------------------------------------------------------------------------- #
class FeedbackRequest(BaseModel):
    trip_id: uuid.UUID | None = None
    itinerary_id: uuid.UUID | None = None
    subject_type: str = Field(default="itinerary", max_length=24)
    subject_id: str | None = Field(default=None, max_length=96)
    rating: int | None = Field(default=None, ge=1, le=5)
    accepted: bool | None = None
    actual_spend_inr: float | None = Field(default=None, ge=0, le=100_000_000)
    comment: str = Field(default="", max_length=2000)


@router.post(
    "/feedback",
    response_model=Ack,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback on an itinerary or a place",
    description=(
        "Actual-spend feedback is what will eventually let us measure cost-estimate error. "
        "Until enough is collected, the analytics dashboard reports that no accuracy figure "
        "exists rather than inventing one."
    ),
)
def submit_feedback(
    payload: FeedbackRequest, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> Ack:
    if payload.trip_id is not None:
        trip = load_trip(session, payload.trip_id)
        require_trip_member(session, trip, user)

    session.add(
        Feedback(
            trip_id=payload.trip_id,
            itinerary_id=payload.itinerary_id,
            user_id=user.id,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            rating=payload.rating,
            accepted=payload.accepted,
            actual_spend_inr=payload.actual_spend_inr,
            comment=sanitize_text(payload.comment, max_length=2000),
        )
    )
    record_event(
        session,
        "feedback_submitted",
        trip_id=payload.trip_id,
        user_id=user.id,
        numeric_value=payload.rating,
        properties={"accepted": payload.accepted, "subject": payload.subject_type},
    )
    session.commit()
    return Ack(message="Thank you - your feedback improves the recommendations.")


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
@router.get(
    "/analytics/dashboard",
    summary="Product and model analytics",
    description=(
        "Aggregate metrics only. Location is reported as counts; coordinates are stripped "
        "at write time and never reach an analytics row."
    ),
)
def analytics_dashboard(
    session: DbSession,
    user: OptionalUser,
    _rl: RateLimited,
    days: int = Query(default=90, ge=1, le=730),
) -> dict:
    del user
    return dashboard_metrics(session, days=days)


@router.get("/analytics/attractions", summary="Which attractions get selected, and how often")
def analytics_attractions(
    session: DbSession,
    _rl: RateLimited,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    return attraction_selection_stats(session, limit=limit)


@router.get(
    "/analytics/trips/{trip_id}",
    summary="Per-trip analytics: fairness, coverage, cost, versions",
)
def trip_analytics(
    trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> dict:
    from sqlalchemy import select

    from yatraai.db.models import Itinerary

    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)

    versions = list(
        session.scalars(
            select(Itinerary).where(Itinerary.trip_id == trip_id).order_by(Itinerary.version)
        )
    )
    active = next((i for i in versions if i.status == "active"), None)
    return {
        "trip_id": str(trip_id),
        "title": trip.title,
        "destination": trip.cluster.name if trip.cluster else "",
        "members": len(trip.members),
        "versions": [
            {
                "version": i.version,
                "generator": i.generator,
                "trigger": i.trigger,
                "status": i.status,
                "activities": i.activity_count,
                "travel_km": i.total_travel_km,
                "fairness": i.fairness_score,
                "least_satisfied": i.least_satisfied_score,
                "cost_low": i.cost_per_person_low_inr,
                "cost_high": i.cost_per_person_high_inr,
                "created_at": i.created_at.isoformat(),
            }
            for i in versions
        ],
        "current": (
            {
                "fairness": active.fairness_score,
                "consensus": active.consensus_score,
                "least_satisfied": active.least_satisfied_score,
                "preference_coverage": (active.preference_coverage or {}).get("by_interest", {}),
                "per_member_coverage": (active.preference_coverage or {}).get("by_member", {}),
                "validation": active.validation_report,
                "degraded_services": active.degraded_services,
                "solver_stats": active.solver_stats,
            }
            if active
            else None
        ),
    }


# --------------------------------------------------------------------------- #
# Admin / data quality
# --------------------------------------------------------------------------- #
@router.get(
    "/admin/data-quality",
    summary="Data-quality checks against the live database",
    description="Same checks that gate the Airflow pipeline. `error` failures block a release.",
)
def data_quality(session: DbSession, user: AdminUser, _rl: RateLimited) -> dict:
    del user
    return run_quality_checks(session)


@router.get("/admin/coverage", summary="Per-cluster catalogue coverage and freshness")
def catalogue_coverage(session: DbSession, user: AdminUser, _rl: RateLimited) -> list[dict]:
    del user
    return coverage_summary(session)


@router.get(
    "/admin/pipeline-runs",
    summary="Recent Bronze/Silver/Gold pipeline runs",
)
def pipeline_runs(
    session: DbSession, user: AdminUser, _rl: RateLimited, limit: int = Query(20, ge=1, le=200)
) -> list[dict]:
    del user
    from sqlalchemy import select

    from yatraai.db.models import PipelineRun

    rows = session.scalars(select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(limit))
    return [
        {
            "pipeline": r.pipeline,
            "layer": r.layer,
            "run_key": r.run_key,
            "status": r.status,
            "rows_in": r.rows_in,
            "rows_out": r.rows_out,
            "rows_rejected": r.rows_rejected,
            "duration_ms": r.duration_ms,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "checks": r.checks,
            "error": r.error,
        }
        for r in rows
    ]


@router.get("/admin/rag-evaluations", summary="Stored RAG benchmark runs")
def rag_evaluations(
    session: DbSession, user: AdminUser, _rl: RateLimited, limit: int = Query(50, ge=1, le=500)
) -> dict:
    del user
    from sqlalchemy import func, select

    from yatraai.db.models import RagEvaluation

    runs = session.execute(
        select(
            RagEvaluation.run_id,
            func.count(),
            func.avg(RagEvaluation.retrieval_precision),
            func.avg(RagEvaluation.faithfulness),
            func.avg(RagEvaluation.citation_correctness),
            func.avg(RagEvaluation.answer_completeness),
            func.avg(RagEvaluation.latency_ms),
            func.sum(func.cast(RagEvaluation.abstained, __import__("sqlalchemy").Integer)),
        )
        .group_by(RagEvaluation.run_id)
        .order_by(func.max(RagEvaluation.created_at).desc())
        .limit(limit)
    ).all()

    return {
        "runs": [
            {
                "run_id": r[0],
                "questions": int(r[1]),
                "retrieval_precision": round(float(r[2] or 0), 4),
                "faithfulness": round(float(r[3] or 0), 4),
                "citation_correctness": round(float(r[4] or 0), 4),
                "answer_completeness": round(float(r[5] or 0), 4),
                "latency_ms": round(float(r[6] or 0), 2),
                "abstained": int(r[7] or 0),
            }
            for r in runs
        ],
        "note": (
            "Generated by `python evaluation/run_rag_eval.py`. "
            "See evaluation/reports/rag_evaluation.md for the full report."
        ),
    }


@router.get("/admin/audit-log", summary="Recent sensitive actions")
def audit_log(
    session: DbSession, user: AdminUser, _rl: RateLimited, limit: int = Query(100, ge=1, le=1000)
) -> list[dict]:
    del user
    from sqlalchemy import select

    from yatraai.db.models import AuditLog

    rows = session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    return [
        {
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "actor": r.actor_label,
            "trip_id": str(r.trip_id) if r.trip_id else None,
            "request_id": r.request_id,
            "detail": r.detail,
            "at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/metrics", tags=["ops"], summary="Provider latency, errors and fallback rates")
def provider_metrics(_rl: RateLimited) -> dict:
    from yatraai.core.telemetry import telemetry
    from yatraai.services.status import active_degradations, service_status_snapshot

    return {
        "providers": service_status_snapshot(),
        "calls": telemetry.summary(),
        "degradations": active_degradations(),
    }
