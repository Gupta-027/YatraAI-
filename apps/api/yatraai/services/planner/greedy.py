"""Greedy baseline scheduler - the control the optimiser is measured against.

Strategy (a reasonable, honest baseline; not a strawman):

1. Sort eligible attractions by score descending.
2. Walk the list; for each candidate compute the earliest feasible start given
   the current clock and travel from the previous stop.
3. Insert it if it fits inside its opening window and the day's budget, activity
   cap and travel cap. Otherwise skip and continue.
4. Insert the meal break at the first feasible moment after 12:00.

This is what most hand-rolled itinerary builders actually do. It respects the
same hard constraints as the CP-SAT model, so the comparison in
``ml/experiments/planner_comparison.py`` isolates *sequencing quality* rather
than constraint handling.
"""

from __future__ import annotations

import time

from yatraai.services.planner.models import PlannedActivity
from yatraai.services.planner.ortools_scheduler import (
    MEAL_DURATION_MIN,
    MEAL_TRAVEL_MIN,
    MEAL_WINDOW,
    DayPlanRequest,
    DayPlanResult,
    _activity_warnings,
    _containing_window,
    _opening_bounds,
    _service_minutes,
)


def solve_day_greedy(request: DayPlanRequest, pace: str = "balanced") -> DayPlanResult:
    started = time.perf_counter()

    ordered = sorted(
        request.candidates,
        key=lambda s: (not s.is_mandatory, -s.total_score, s.candidate.slug),
    )

    clock = request.day_start_min
    previous_node = 0  # depot
    activities: list[PlannedActivity] = []
    total_km = 0.0
    total_min = 0
    spent = 0.0
    meal_taken = not request.include_meal
    node_by_slug = {s.candidate.slug: i for i, s in enumerate(request.candidates, start=1)}

    def travel_from(prev: int, nxt: int) -> tuple[float, int]:
        if prev == nxt:
            return 0.0, 0
        return (
            float(request.matrix.distance_km[prev][nxt]),
            int(round(request.matrix.duration_min[prev][nxt])),
        )

    for scored in ordered:
        if len([a for a in activities if a.kind == "visit"]) >= request.max_activities:
            break

        node = node_by_slug[scored.candidate.slug]
        service = _service_minutes(scored, pace)
        window = _opening_bounds(
            scored, request.weekday, request.day_start_min, request.day_end_min, service
        )
        if window is None:
            continue

        leg_km, leg_min = travel_from(previous_node, node)
        if total_min + leg_min > request.max_travel_min:
            continue

        # Take the meal break first if we are inside the meal window.
        arrival = clock + leg_min
        if not meal_taken and arrival >= MEAL_WINDOW[0]:
            # The break itself needs travel time from the previous stop.
            meal_start = max(clock + MEAL_TRAVEL_MIN, MEAL_WINDOW[0])
            if meal_start + MEAL_DURATION_MIN <= min(
                MEAL_WINDOW[1] + MEAL_DURATION_MIN, request.day_end_min
            ):
                activities.append(
                    PlannedActivity(
                        kind="meal",
                        sequence=len(activities) + 1,
                        title="Meal break",
                        start_min=meal_start,
                        end_min=meal_start + MEAL_DURATION_MIN,
                        travel_from_prev_min=MEAL_TRAVEL_MIN,
                        travel_mode=request.transport_mode,
                        why_selected="Greedy baseline reserves a midday meal break.",
                    )
                )
                clock = meal_start + MEAL_DURATION_MIN
                total_min += MEAL_TRAVEL_MIN
                meal_taken = True
                arrival = clock + leg_min

        earliest, latest = window
        start_min = max(arrival, earliest)
        if start_min > latest:
            continue
        if start_min + service > request.day_end_min:
            continue

        _window = _containing_window(scored.candidate, request.weekday, start_min)

        cost = scored.candidate.entry_cost_max
        over_budget = (
            request.daily_activity_budget is not None
            and spent + cost > request.daily_activity_budget
        )
        if over_budget and not scored.is_mandatory:
            continue

        activities.append(
            PlannedActivity(
                kind="visit",
                sequence=len(activities) + 1,
                title=scored.candidate.name,
                slug=scored.candidate.slug,
                attraction_id=scored.candidate.attraction_id,
                start_min=start_min,
                end_min=start_min + service,
                opens_min=_window[0],
                closes_min=_window[1],
                lat=scored.candidate.lat,
                lon=scored.candidate.lon,
                travel_from_prev_min=leg_min,
                travel_from_prev_km=round(leg_km, 3),
                travel_mode=request.transport_mode,
                est_cost_low_inr=scored.candidate.entry_cost_min,
                est_cost_high_inr=scored.candidate.entry_cost_max,
                weather_suitability=scored.breakdown.weather_suitability,
                why_selected=scored.explanation,
                score_breakdown=scored.breakdown.to_dict(),
                is_mandatory=scored.is_mandatory,
                warnings=_activity_warnings(scored, request.weather),
            )
        )
        clock = start_min + service
        total_km += leg_km
        total_min += leg_min
        spent += cost
        previous_node = node

    # Meal break at the end if it never fitted between stops.
    if not meal_taken:
        meal_start = max(clock + MEAL_TRAVEL_MIN, MEAL_WINDOW[0])
        if meal_start + MEAL_DURATION_MIN <= request.day_end_min:
            activities.append(
                PlannedActivity(
                    kind="meal",
                    sequence=len(activities) + 1,
                    title="Meal break",
                    start_min=meal_start,
                    end_min=meal_start + MEAL_DURATION_MIN,
                    travel_from_prev_min=MEAL_TRAVEL_MIN,
                    travel_mode=request.transport_mode,
                    why_selected="Greedy baseline appended the meal break.",
                )
            )

    activities.sort(key=lambda a: a.start_min)
    for i, activity in enumerate(activities, start=1):
        activity.sequence = i

    if previous_node != 0:
        back_km, back_min = travel_from(previous_node, 0)
        total_km += back_km
        total_min += back_min

    scheduled = {a.slug for a in activities if a.slug}
    return DayPlanResult(
        day_index=request.day_index,
        activities=activities,
        travel_km=round(total_km, 3),
        travel_min=int(total_min),
        status="GREEDY",
        objective=sum(s.total_score for s in request.candidates if s.candidate.slug in scheduled),
        solve_ms=round((time.perf_counter() - started) * 1000, 3),
        unscheduled_mandatory=sorted(request.mandatory_slugs - scheduled),
    )
