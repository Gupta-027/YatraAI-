"""Runtime data-quality checks, surfaced on the admin dashboard.

Same spirit as the Pandera contracts but evaluated against the *live database*
rather than the parquet layers, so drift introduced by an API write or a partial
load is visible too. Each check reports a severity: an ``error`` fails the
Airflow gate, a ``warning`` is informational.
"""

from __future__ import annotations

from datetime import UTC, date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from yatraai.db.models import (
    Attraction,
    AttractionCost,
    AttractionSchedule,
    AttractionSource,
    ChunkEmbedding,
    DestinationCluster,
    DocumentChunk,
    PipelineRun,
)
from yatraai.db.session import session_scope

STALE_AFTER_DAYS = 400


def _check(name: str, passed: bool, severity: str, detail: str, value: Any = None) -> dict:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "detail": detail,
        "value": value,
    }


def run_quality_checks(session: Session | None = None) -> dict:
    if session is None:
        with session_scope() as s:
            return run_quality_checks(s)

    checks: list[dict] = []

    n_clusters = session.scalar(select(func.count()).select_from(DestinationCluster)) or 0
    n_attractions = session.scalar(select(func.count()).select_from(Attraction)) or 0
    checks.append(
        _check(
            "clusters_loaded",
            n_clusters >= 8,
            "error",
            f"{n_clusters} destination clusters loaded (expect 10)",
            n_clusters,
        )
    )
    checks.append(
        _check(
            "attractions_loaded",
            n_attractions >= 100,
            "error",
            f"{n_attractions} attractions loaded (expect ~130)",
            n_attractions,
        )
    )

    # --- every attraction must be citable ---
    orphan_sources = (
        session.scalar(
            select(func.count())
            .select_from(Attraction)
            .where(
                ~Attraction.id.in_(select(AttractionSource.attraction_id).distinct()),
            )
        )
        or 0
    )
    checks.append(
        _check(
            "every_attraction_has_a_source",
            orphan_sources == 0,
            "error",
            f"{orphan_sources} attractions have no provenance record",
            orphan_sources,
        )
    )

    # --- schedulability ---
    no_schedule = (
        session.scalar(
            select(func.count())
            .select_from(Attraction)
            .where(~Attraction.id.in_(select(AttractionSchedule.attraction_id).distinct()))
        )
        or 0
    )
    checks.append(
        _check(
            "every_attraction_has_opening_hours",
            no_schedule == 0,
            "warning",
            f"{no_schedule} attractions have no opening hours and can only be scheduled loosely",
            no_schedule,
        )
    )

    no_cost = (
        session.scalar(
            select(func.count())
            .select_from(Attraction)
            .where(~Attraction.id.in_(select(AttractionCost.attraction_id).distinct()))
        )
        or 0
    )
    checks.append(
        _check(
            "every_attraction_has_cost_information",
            no_cost == 0,
            "warning",
            f"{no_cost} attractions have no fee information; cost estimates fall back to cluster baselines",
            no_cost,
        )
    )

    # --- coordinate sanity ---
    bad_coords = (
        session.scalar(
            select(func.count())
            .select_from(Attraction)
            .where(
                (Attraction.lat < 6.5)
                | (Attraction.lat > 37.5)
                | (Attraction.lon < 68.0)
                | (Attraction.lon > 97.5)
            )
        )
        or 0
    )
    checks.append(
        _check(
            "coordinates_within_india",
            bad_coords == 0,
            "error",
            f"{bad_coords} attractions have out-of-range coordinates",
            bad_coords,
        )
    )

    # --- freshness ---
    cutoff = date.today() - timedelta(days=STALE_AFTER_DAYS)
    stale = (
        session.scalar(
            select(func.count())
            .select_from(Attraction)
            .where((Attraction.last_verified_at.is_(None)) | (Attraction.last_verified_at < cutoff))
        )
        or 0
    )
    checks.append(
        _check(
            "source_freshness",
            stale == 0,
            "warning",
            f"{stale} attractions were last verified more than {STALE_AFTER_DAYS} days ago",
            stale,
        )
    )

    # --- RAG corpus health ---
    n_chunks = session.scalar(select(func.count()).select_from(DocumentChunk)) or 0
    n_embeddings = session.scalar(select(func.count()).select_from(ChunkEmbedding)) or 0
    checks.append(
        _check(
            "knowledge_chunks_indexed",
            n_chunks >= 300,
            "error",
            f"{n_chunks} knowledge chunks indexed",
            n_chunks,
        )
    )
    checks.append(
        _check(
            "all_chunks_embedded",
            n_chunks == n_embeddings,
            "error",
            f"{n_embeddings}/{n_chunks} chunks have embeddings",
            {"chunks": n_chunks, "embeddings": n_embeddings},
        )
    )

    # --- pipeline recency ---
    last_run = session.scalar(select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(1))
    hours_since = None
    if last_run and last_run.finished_at:
        from datetime import datetime

        hours_since = round((datetime.now(UTC) - last_run.finished_at).total_seconds() / 3600, 2)
    checks.append(
        _check(
            "pipeline_ran_recently",
            hours_since is not None and hours_since < 48,
            "warning",
            (
                f"last pipeline run finished {hours_since}h ago"
                if hours_since is not None
                else "no pipeline run recorded"
            ),
            hours_since,
        )
    )

    # --- honesty check: time-sensitive rows must not claim verification ---
    falsely_verified = (
        session.scalar(
            select(func.count()).select_from(AttractionSchedule).where(AttractionSchedule.verified)
        )
        or 0
    ) + (
        session.scalar(
            select(func.count()).select_from(AttractionCost).where(AttractionCost.verified)
        )
        or 0
    )
    checks.append(
        _check(
            "time_sensitive_data_not_falsely_verified",
            falsely_verified == 0,
            "error",
            f"{falsely_verified} schedule/fee rows claim verification we cannot support",
            falsely_verified,
        )
    )

    errors = [c for c in checks if c["severity"] == "error" and not c["passed"]]
    warnings = [c for c in checks if c["severity"] == "warning" and not c["passed"]]
    return {
        "status": "fail" if errors else ("warn" if warnings else "pass"),
        "checks": checks,
        "passed": sum(1 for c in checks if c["passed"]),
        "total": len(checks),
        "errors": len(errors),
        "warnings": len(warnings),
    }


def coverage_summary(session: Session) -> list[dict]:
    """Per-cluster catalogue coverage for the admin dashboard."""
    rows = session.execute(
        select(
            DestinationCluster.slug,
            DestinationCluster.name,
            DestinationCluster.state,
            func.count(Attraction.id).label("n_attractions"),
            func.avg(Attraction.quality_score).label("mean_quality"),
            func.sum(
                func.cast(Attraction.needs_verification, __import__("sqlalchemy").Integer)
            ).label("n_needs_verification"),
            func.min(Attraction.last_verified_at).label("oldest_verification"),
        )
        .join(Attraction, Attraction.cluster_id == DestinationCluster.id, isouter=True)
        .group_by(DestinationCluster.id)
        .order_by(DestinationCluster.name)
    ).all()

    return [
        {
            "cluster_slug": r.slug,
            "name": r.name,
            "state": r.state,
            "attractions": int(r.n_attractions or 0),
            "mean_quality": round(float(r.mean_quality or 0), 3),
            "needs_verification": int(r.n_needs_verification or 0),
            "oldest_verification": r.oldest_verification.isoformat()
            if r.oldest_verification
            else None,
        }
        for r in rows
    ]
