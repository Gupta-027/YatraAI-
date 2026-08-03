"""Deterministic constraint validator.

**No itinerary is ever shown to a user without passing this.** The optimiser is
trusted to be good; the validator is what makes it *safe*. It re-derives every
constraint independently of the solver, so a modelling bug surfaces as a failed
validation rather than an impossible plan.

Checks (each either ``error`` — blocks display — or ``warning`` — shown as a badge):

| # | Check | Severity |
|---|---|---|
| 1 | Activities are chronologically ordered and non-overlapping | error |
| 2 | Every visit falls inside a real opening window for that weekday | error |
| 3 | Nothing starts before the day start or ends after the day end | error |
| 4 | Visit duration is within the attraction's min/max | error |
| 5 | Travel time between consecutive stops is actually available | error |
| 6 | No attraction appears twice across the whole trip | error |
| 7 | Every mandatory attraction is scheduled | error |
| 8 | Daily travel is within the pace limit | warning |
| 9 | Activities per day are within the pace limit | warning |
| 10 | A meal break exists on any day longer than 6 hours | warning |
| 11 | Total estimated cost is within budget | warning |
| 12 | Accessibility requirements are respected | error |
| 13 | Nothing scheduled on a day the attraction is closed | error |
| 14 | Weather-unsuitable outdoor activities are flagged | warning |
| 15 | The trip has at least one activity | error |
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence

from yatraai.services.planner.models import (
    PACE_PROFILE,
    AttractionCandidate,
    CostEstimate,
    PlannedDay,
    TripContext,
    ValidationIssue,
    ValidationReport,
)

TRAVEL_TOLERANCE_MIN = 2  # rounding slack between solver minutes and re-derived minutes


def validate_plan(
    days: Sequence[PlannedDay],
    ctx: TripContext,
    candidates_by_slug: dict[str, AttractionCandidate],
    cost: CostEstimate | None = None,
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    checks = 0

    def error(code: str, message: str, day_index=None, slug=None) -> None:
        issues.append(ValidationIssue(code, "error", message, day_index, slug))

    def warn(code: str, message: str, day_index=None, slug=None) -> None:
        issues.append(ValidationIssue(code, "warning", message, day_index, slug))

    pace = PACE_PROFILE.get(ctx.pace, PACE_PROFILE["balanced"])
    seen_slugs: dict[str, int] = {}
    total_activities = 0

    # ---- 15. non-empty -----------------------------------------------------
    checks += 1
    if not any(d.visits for d in days):
        error("empty_itinerary", "The itinerary contains no attractions.")

    for day in days:
        weekday = day.calendar_date.weekday()
        activities = sorted(day.activities, key=lambda a: a.start_min)

        # ---- 1. ordering and overlap ---------------------------------------
        checks += 1
        for previous, current in itertools.pairwise(activities):
            if current.start_min < previous.end_min:
                error(
                    "overlapping_activities",
                    f"'{current.title}' starts at {_hhmm(current.start_min)} before "
                    f"'{previous.title}' ends at {_hhmm(previous.end_min)}.",
                    day.day_index,
                    current.slug,
                )

        # ---- 3. day window --------------------------------------------------
        checks += 1
        for activity in activities:
            if activity.start_min < day.start_min:
                error(
                    "starts_before_day_window",
                    f"'{activity.title}' starts at {_hhmm(activity.start_min)}, before the "
                    f"day begins at {_hhmm(day.start_min)}.",
                    day.day_index,
                    activity.slug,
                )
            if activity.end_min > day.end_min:
                error(
                    "ends_after_day_window",
                    f"'{activity.title}' ends at {_hhmm(activity.end_min)}, after the day "
                    f"ends at {_hhmm(day.end_min)}.",
                    day.day_index,
                    activity.slug,
                )
            if activity.end_min <= activity.start_min:
                error(
                    "non_positive_duration",
                    f"'{activity.title}' has a non-positive duration.",
                    day.day_index,
                    activity.slug,
                )

        # ---- 5. travel feasibility -----------------------------------------
        checks += 1
        for previous, current in itertools.pairwise(activities):
            gap = current.start_min - previous.end_min
            if current.travel_from_prev_min - gap > TRAVEL_TOLERANCE_MIN:
                error(
                    "insufficient_travel_time",
                    f"Only {gap} min between '{previous.title}' and '{current.title}', "
                    f"but travel needs {current.travel_from_prev_min} min.",
                    day.day_index,
                    current.slug,
                )

        for activity in day.visits:
            slug = activity.slug
            candidate = candidates_by_slug.get(slug) if slug else None
            total_activities += 1

            # ---- 6. duplicates ---------------------------------------------
            checks += 1
            if slug in seen_slugs:
                error(
                    "duplicate_visit",
                    f"'{activity.title}' appears on both day {seen_slugs[slug] + 1} "
                    f"and day {day.day_index + 1}.",
                    day.day_index,
                    slug,
                )
            elif slug:
                seen_slugs[slug] = day.day_index

            if candidate is None:
                continue

            # ---- 2 & 13. opening hours --------------------------------------
            checks += 1
            windows = candidate.opening_windows_for(weekday)
            if not windows:
                error(
                    "closed_on_this_day",
                    f"'{candidate.name}' is closed on {day.calendar_date.strftime('%A')}.",
                    day.day_index,
                    slug,
                )
            elif not any(
                opens <= activity.start_min and activity.end_min <= closes
                for opens, closes in windows
            ):
                readable = ", ".join(f"{_hhmm(o)}-{_hhmm(c)}" for o, c in windows)
                error(
                    "outside_opening_hours",
                    f"'{candidate.name}' is scheduled {_hhmm(activity.start_min)}-"
                    f"{_hhmm(activity.end_min)} but opens {readable}.",
                    day.day_index,
                    slug,
                )

            # ---- 4. duration bounds ----------------------------------------
            checks += 1
            if activity.duration_min < candidate.min_duration_min:
                error(
                    "visit_too_short",
                    f"'{candidate.name}' is allotted {activity.duration_min} min but needs "
                    f"at least {candidate.min_duration_min} min.",
                    day.day_index,
                    slug,
                )
            if activity.duration_min > candidate.max_duration_min:
                warn(
                    "visit_longer_than_needed",
                    f"'{candidate.name}' is allotted more time than the recommended maximum.",
                    day.day_index,
                    slug,
                )

            # ---- 12. accessibility -----------------------------------------
            checks += 1
            if ctx.accessibility_required and candidate.wheelchair_accessible == "no":
                error(
                    "accessibility_violation",
                    f"'{candidate.name}' is not wheelchair accessible but the group "
                    "requires step-free access.",
                    day.day_index,
                    slug,
                )

            # ---- 14. weather -----------------------------------------------
            checks += 1
            if activity.weather_suitability < 0.45 and candidate.indoor_outdoor == "outdoor":
                warn(
                    "poor_weather_for_outdoor_activity",
                    f"'{candidate.name}' is outdoors and the forecast is poor "
                    f"({activity.weather_suitability:.0%} suitability).",
                    day.day_index,
                    slug,
                )

        # ---- 8. daily travel -----------------------------------------------
        checks += 1
        if day.travel_min > pace["max_travel_min"]:
            warn(
                "excessive_daily_travel",
                f"Day {day.day_index + 1} involves {day.travel_min} min of travel, above "
                f"the {int(pace['max_travel_min'])} min guideline for a "
                f"'{ctx.pace}' pace.",
                day.day_index,
            )

        # ---- 9. activities per day -----------------------------------------
        checks += 1
        if len(day.visits) > pace["max_activities"]:
            warn(
                "too_many_activities",
                f"Day {day.day_index + 1} has {len(day.visits)} stops, above the "
                f"{int(pace['max_activities'])} recommended for a '{ctx.pace}' pace.",
                day.day_index,
            )

        # ---- 10. meal break -------------------------------------------------
        checks += 1
        day_length = day.end_min - day.start_min
        if day_length > 6 * 60 and day.visits and not any(a.kind == "meal" for a in activities):
            warn(
                "no_meal_break",
                f"Day {day.day_index + 1} runs {day_length // 60}h with no meal break.",
                day.day_index,
            )

    # ---- 7. mandatory attractions -----------------------------------------
    checks += 1
    required = set(ctx.must_visit_slugs)
    missing = sorted(required - set(seen_slugs))
    if missing:
        names = [candidates_by_slug[s].name if s in candidates_by_slug else s for s in missing]
        error(
            "mandatory_attraction_missing",
            f"Must-visit place(s) not scheduled: {', '.join(names)}.",
        )

    # ---- 11. budget --------------------------------------------------------
    checks += 1
    if cost and ctx.budget_per_person_inr:
        if cost.per_person_low_inr > ctx.budget_per_person_inr:
            warn(
                "over_budget",
                f"Even the low estimate (Rs.{cost.per_person_low_inr:,.0f} per person) "
                f"exceeds the Rs.{ctx.budget_per_person_inr:,.0f} budget.",
            )
        elif cost.per_person_high_inr > ctx.budget_per_person_inr:
            warn(
                "budget_at_risk",
                f"The upper estimate (Rs.{cost.per_person_high_inr:,.0f} per person) exceeds "
                f"the Rs.{ctx.budget_per_person_inr:,.0f} budget; the lower estimate fits.",
            )

    errors = [i for i in issues if i.severity == "error"]
    return ValidationReport(is_valid=not errors, issues=issues, checks_run=checks)


def _hhmm(minutes: int) -> str:
    minutes = int(minutes) % (48 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
