"""The eight-stage deterministic planning pipeline.

```
1. retrieve candidates          catalogue query, cluster-scoped
2. hard eligibility filters     closed / inaccessible / over-budget are REMOVED
3. score + aggregate            fairness-aware group ranking, explainable
4. geographic clustering        partition candidates into day-groups
5. travel-time matrix           OSRM, or haversine with documented assumptions
6. optimise each day            CP-SAT prize-collecting TSP with time windows
7. validate every constraint    independent re-derivation; blocks display on error
8. explain                      template first; the LLM only rewords stage 7's output
```

The LLM never appears before stage 8, and stage 8 is optional: with
``LLM_PROVIDER=mock`` the pipeline still emits a complete, validated itinerary
with deterministic explanations.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import timedelta

from yatraai.logging_config import get_logger
from yatraai.services.planner import cost as cost_module
from yatraai.services.planner.greedy import solve_day_greedy
from yatraai.services.planner.models import (
    AttractionCandidate,
    DayWeather,
    MemberProfile,
    PlanMetrics,
    PlannedDay,
    PlanResult,
    ScoredAttraction,
    TripContext,
    fingerprint,
)
from yatraai.services.planner.ortools_scheduler import (
    DayPlanRequest,
    DayPlanResult,
    build_matrix_points,
    pace_limits,
    solve_day,
)
from yatraai.services.planner.validator import validate_plan
from yatraai.services.recommend import aggregation, scoring
from yatraai.services.recommend.clustering import cluster_by_day, order_clusters_by_proximity
from yatraai.services.routing.base import RouteMatrix, get_router
from yatraai.services.weather.base import advisories_for, get_weather_provider

log = get_logger(__name__)

# How many top-ranked candidates to hand the solver per day. Larger gives the
# optimiser more freedom; the CP-SAT model is O(n^2) in arcs, so this caps
# solve time. Measured in evaluation/reports/planner_comparison.md.
CANDIDATES_PER_DAY = 9

# When a day's geographic cluster is thin we top it up from the global shortlist,
# but only within this radius of the cluster centroid.
TOP_UP_RADIUS_KM = 40.0


def plan_trip(
    ctx: TripContext,
    members: Sequence[MemberProfile],
    candidates: Sequence[AttractionCandidate],
    *,
    weather: Sequence[DayWeather] | None = None,
    generator: str = "ortools",
    aggregation_method: str = "fairness_aware",
    session=None,
    cluster_baseline: dict | None = None,
) -> PlanResult:
    """Run the full pipeline. Pure with respect to ``ctx``/``members``/``candidates``."""
    started = time.perf_counter()
    degraded: list[str] = []

    # ---- stage 1-2: candidates + weather ----------------------------------
    if not candidates:
        return _empty_result(ctx, generator, "no candidates in catalogue")

    if weather is None:
        weather = _fetch_weather(ctx, degraded)
    if any(w.is_fallback for w in weather):
        degraded.append("weather")

    # ---- stage 3: score ----------------------------------------------------
    scored, rejected = scoring.score_candidates(
        candidates, ctx, members, weather, method=aggregation_method
    )
    if not scored:
        return _empty_result(ctx, generator, "every candidate failed eligibility", rejected)

    # ---- stage 4: geographic clustering ------------------------------------
    per_day_pool = max(CANDIDATES_PER_DAY, ctx.days * 3)
    shortlist = _shortlist(scored, ctx, members, per_day_pool * ctx.days, method=aggregation_method)
    clusters = cluster_by_day(shortlist, ctx.days, seed=ctx.random_seed)
    clusters = order_clusters_by_proximity(clusters, ctx.base_lat, ctx.base_lon)

    # ---- stage 5-6: matrix + optimise each day -----------------------------
    max_activities, max_travel_min = pace_limits(ctx)
    daily_budget = _daily_activity_budget(ctx)
    mandatory = set(ctx.must_visit_slugs) | {s for m in members for s in m.must_visit_slugs}

    planned_days: list[PlannedDay] = []
    solver_stats: dict = {"days": [], "generator": generator}
    unplaced_mandatory: list[str] = []
    used_slugs: set[str] = set()

    for day_index in range(ctx.days):
        calendar_date = ctx.start_date + timedelta(days=day_index)
        cluster = clusters[day_index] if day_index < len(clusters) else None
        pool = [s for s in (cluster.members if cluster else []) if s.slug not in used_slugs]

        # Top up from the global shortlist if this cluster is thin - but only
        # with places that are actually near this day's area. Pulling in a
        # candidate 200 km away to fill a slot produces an unusable day.
        if len(pool) < 4 and cluster is not None:
            from yatraai.services.routing.distance import haversine_km

            in_pool = {s.slug for s in pool}
            extras = sorted(
                (
                    s
                    for s in shortlist
                    if s.slug not in used_slugs
                    and s.slug not in in_pool
                    and haversine_km(
                        cluster.centroid_lat, cluster.centroid_lon, s.candidate.lat, s.candidate.lon
                    )
                    <= TOP_UP_RADIUS_KM
                ),
                key=lambda s: -s.total_score,
            )[: 6 - len(pool)]
            pool = pool + extras

        pool = pool[:CANDIDATES_PER_DAY]
        day_weather = _weather_for(weather, day_index)
        day_mandatory = {s.slug for s in pool if s.slug in mandatory}

        if not pool:
            planned_days.append(_empty_day(day_index, calendar_date, ctx, day_weather))
            continue

        # The day starts and ends at a base *within that day's area*, not at a
        # single trip-wide origin. For a wide cluster like Delhi-Agra a global
        # base sits ~115 km from everything and no day can satisfy the travel
        # cap; in reality you move accommodation. `relocation_note` tells the
        # user when that is what the plan assumes.
        base_lat, base_lon, relocation_note = _day_base(ctx, cluster, pool)

        points = build_matrix_points((base_lat, base_lon), pool)
        matrix = _matrix(points, ctx.transport_mode, session)
        if matrix.is_fallback and "routing" not in degraded:
            degraded.append("routing")

        request = DayPlanRequest(
            day_index=day_index,
            calendar_date=calendar_date,
            weekday=calendar_date.weekday(),
            candidates=pool,
            base_lat=base_lat,
            base_lon=base_lon,
            day_start_min=ctx.day_start_min,
            day_end_min=ctx.day_end_min,
            matrix=matrix,
            weather=day_weather,
            max_activities=max_activities,
            max_travel_min=max_travel_min,
            daily_activity_budget=daily_budget,
            mandatory_slugs=day_mandatory,
            include_meal=(ctx.day_end_min - ctx.day_start_min) > 5 * 60,
            include_rest=ctx.pace == "relaxed" or ctx.has_seniors,
            transport_mode=ctx.transport_mode,
        )

        result = (
            solve_day(request, ctx.pace)
            if generator == "ortools"
            else solve_day_greedy(request, ctx.pace)
        )
        solver_stats["days"].append(
            {
                "day": day_index,
                "status": result.status,
                "solve_ms": result.solve_ms,
                "objective": round(result.objective, 3),
                "candidates": len(pool),
                "selected": len([a for a in result.activities if a.kind == "visit"]),
                "relaxations": result.relaxations,
            }
        )
        unplaced_mandatory.extend(result.unscheduled_mandatory)

        for activity in result.activities:
            if activity.slug:
                used_slugs.add(activity.slug)

        planned_days.append(
            PlannedDay(
                day_index=day_index,
                calendar_date=calendar_date,
                start_min=ctx.day_start_min,
                end_min=ctx.day_end_min,
                base_lat=base_lat,
                base_lon=base_lon,
                activities=result.activities,
                travel_km=result.travel_km,
                travel_min=result.travel_min,
                weather=day_weather,
                weather_advisories=(
                    advisories_for(day_weather, ctx.cluster_slug) if day_weather else []
                ),
                theme=_day_theme(result),
                notes=relocation_note,
            )
        )

    # ---- metrics, cost, validation ----------------------------------------
    candidates_by_slug = {c.slug: c for c in candidates}
    selected_slugs = {a.slug for d in planned_days for a in d.visits if a.slug}
    selected = [candidates_by_slug[s] for s in selected_slugs if s in candidates_by_slug]
    satisfaction = aggregation.evaluate_selection(members, selected)
    cost_estimate = cost_module.estimate_cost(
        planned_days, ctx, candidates_by_slug, cluster_baseline
    )
    validation = validate_plan(planned_days, ctx, candidates_by_slug, cost_estimate)

    metrics = PlanMetrics(
        total_travel_km=round(sum(d.travel_km for d in planned_days), 3),
        total_travel_min=sum(d.travel_min for d in planned_days),
        total_visit_min=sum(a.duration_min for d in planned_days for a in d.visits),
        activity_count=len(selected),
        fairness_score=satisfaction.fairness_index,
        least_satisfied_score=satisfaction.least_satisfied,
        consensus_score=satisfaction.consensus,
        utility_score=round(
            sum(s.total_score for s in scored if s.candidate.slug in selected_slugs), 4
        ),
        preference_coverage=scoring.coverage_by_interest(selected, members),
        per_member_coverage=satisfaction.per_member,
        computation_ms=round((time.perf_counter() - started) * 1000, 2),
        solver_status=",".join(sorted({d["status"] for d in solver_stats["days"]})),
    )
    solver_stats["fingerprint"] = fingerprint(
        ctx.cluster_slug,
        str(ctx.start_date),
        str(ctx.end_date),
        ctx.pace,
        ctx.transport_mode,
        sorted(ctx.must_visit_slugs),
        sorted(ctx.avoid_slugs),
        sorted((m.member_id, tuple(sorted(m.interests.items()))) for m in members),
        generator,
    )

    log.info(
        "planner.completed",
        generator=generator,
        days=len(planned_days),
        activities=metrics.activity_count,
        travel_km=metrics.total_travel_km,
        valid=validation.is_valid,
        fairness=metrics.fairness_score,
        ms=metrics.computation_ms,
    )

    return PlanResult(
        days=planned_days,
        metrics=metrics,
        cost=cost_estimate,
        validation=validation,
        generator=generator,
        scored=scored,
        degraded_services=degraded,
        solver_stats=solver_stats,
        unplaced_mandatory=sorted(set(unplaced_mandatory)),
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _shortlist(
    scored: list[ScoredAttraction],
    ctx: TripContext,
    members: Sequence[MemberProfile],
    limit: int,
    *,
    method: str,
) -> list[ScoredAttraction]:
    """Choose which attractions reach the optimiser.

    For ``fairness_aware`` this uses **iterative** selection: each pick is made
    knowing what is already shortlisted, so an item that serves a currently
    neglected member outranks a marginally better item that serves the majority
    again. Other methods use a plain top-N cut, which is what makes them
    comparable in the experiment.
    """
    del ctx  # kept for signature stability; selection is group-driven
    if method == "fairness_aware" and len(members) > 1:
        return aggregation.select_fairly(members, scored, limit)
    mandatory = [s for s in scored if s.is_mandatory]
    rest = [s for s in scored if not s.is_mandatory]
    return mandatory + rest[: max(0, limit - len(mandatory))]


RELOCATION_THRESHOLD_KM = 60.0


def _day_base(ctx: TripContext, cluster, pool) -> tuple[float, float, str]:
    """Where this day starts and ends.

    Defaults to the trip base. If the day's attractions sit far from it - which
    happens in genuinely multi-city clusters - the base moves to the day's own
    centroid and the plan says so, rather than silently generating a day that
    involves a 200 km round trip.
    """
    from yatraai.services.routing.distance import haversine_km

    if cluster is None or not pool:
        return ctx.base_lat, ctx.base_lon, ""

    centroid_lat = sum(s.candidate.lat for s in pool) / len(pool)
    centroid_lon = sum(s.candidate.lon for s in pool) / len(pool)
    distance = haversine_km(ctx.base_lat, ctx.base_lon, centroid_lat, centroid_lon)

    if distance <= RELOCATION_THRESHOLD_KM:
        return ctx.base_lat, ctx.base_lon, ""

    locality = pool[0].candidate.name
    return (
        centroid_lat,
        centroid_lon,
        (
            f"This day is planned around {locality} and its surroundings, about "
            f"{distance:.0f} km from your stated base. Plan to stay nearby the night "
            "before, or add transfer time at the start and end of the day."
        ),
    )


def _daily_activity_budget(ctx: TripContext) -> float | None:
    if not ctx.budget_per_person_inr:
        return None
    # ~45% of the daily per-person budget is available for entry fees and activities.
    return max(200.0, ctx.budget_per_person_inr / max(1, ctx.days) * 0.45)


def _fetch_weather(ctx: TripContext, degraded: list[str]) -> list[DayWeather]:
    try:
        provider = get_weather_provider()
        return provider.daily_forecast(
            ctx.base_lat, ctx.base_lon, ctx.start_date, ctx.end_date, ctx.cluster_slug
        )
    except Exception as exc:  # pragma: no cover - provider already self-heals
        log.warning("planner.weather_unavailable", error=str(exc))
        degraded.append("weather")
        from yatraai.services.weather.base import SeedClimatologyProvider

        return SeedClimatologyProvider().daily_forecast(
            ctx.base_lat, ctx.base_lon, ctx.start_date, ctx.end_date, ctx.cluster_slug
        )


def _weather_for(weather: Sequence[DayWeather], day_index: int) -> DayWeather | None:
    if not weather:
        return None
    return weather[min(day_index, len(weather) - 1)]


def _matrix(points, mode: str, session) -> RouteMatrix:
    if session is not None:
        from yatraai.services.routing.cache import cached_matrix

        return cached_matrix(session, points, mode)
    return get_router().matrix(points, mode)


def _day_theme(result: DayPlanResult) -> str:
    """A short human label derived from what actually got scheduled."""
    visits = [a for a in result.activities if a.kind == "visit"]
    if not visits:
        return ""
    if len(visits) == 1:
        return visits[0].title
    return f"{visits[0].title} + {len(visits) - 1} more"


def _empty_day(day_index, calendar_date, ctx: TripContext, weather) -> PlannedDay:
    return PlannedDay(
        day_index=day_index,
        calendar_date=calendar_date,
        start_min=ctx.day_start_min,
        end_min=ctx.day_end_min,
        base_lat=ctx.base_lat,
        base_lon=ctx.base_lon,
        activities=[],
        weather=weather,
        weather_advisories=advisories_for(weather, ctx.cluster_slug) if weather else [],
        notes="No further eligible attractions remained for this day.",
    )


def _empty_result(
    ctx: TripContext, generator: str, reason: str, rejected: list | None = None
) -> PlanResult:
    from yatraai.services.planner.models import (
        CostEstimate,
        ValidationIssue,
        ValidationReport,
    )

    report = ValidationReport(
        is_valid=False,
        issues=[
            ValidationIssue("no_feasible_plan", "error", f"Cannot build an itinerary: {reason}.")
        ],
        checks_run=1,
    )
    return PlanResult(
        days=[],
        metrics=PlanMetrics(),
        cost=CostEstimate(0, 0, 0, 0, {}, [reason]),
        validation=report,
        generator=generator,
        scored=rejected or [],
    )


def compare_generators(
    ctx: TripContext,
    members: Sequence[MemberProfile],
    candidates: Sequence[AttractionCandidate],
    weather: Sequence[DayWeather] | None = None,
) -> dict:
    """Run both planners on identical inputs and return the measured comparison."""
    results = {}
    for generator in ("greedy", "ortools"):
        result = plan_trip(ctx, members, candidates, weather=weather, generator=generator)
        results[generator] = {
            "total_travel_km": result.metrics.total_travel_km,
            "total_travel_min": result.metrics.total_travel_min,
            "activity_count": result.metrics.activity_count,
            "satisfied_preferences": len(
                [v for v in result.metrics.preference_coverage.values() if v >= 0.5]
            ),
            "constraint_violations": len(result.validation.errors),
            "constraint_warnings": len(result.validation.warnings),
            "fairness_score": result.metrics.fairness_score,
            "least_satisfied_score": result.metrics.least_satisfied_score,
            "utility_score": result.metrics.utility_score,
            "computation_ms": result.metrics.computation_ms,
            "cost_per_person_low": result.cost.per_person_low_inr,
            "cost_per_person_high": result.cost.per_person_high_inr,
            "is_valid": result.validation.is_valid,
        }
    return results
