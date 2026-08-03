"""Attraction suitability scoring - the production ranking model.

This is a **transparent, rule-based linear model**, deliberately. There is no
genuine labelled dataset of "did this group enjoy this itinerary", so a learned
ranker would be fitted to invented labels. The weights below were set from the
domain constraints in the brief and are held in one place so they can be
inspected, tuned and A/B'd; `ml/` contains a reproducible pipeline that trains
learned rankers on *clearly-labelled synthetic* data and compares them against
this model, without ever promoting them to production.

Two stages:

1. **Hard eligibility** — a place that is closed for the whole trip, physically
   unreachable for the group, or over budget is *removed*, not down-weighted.
   Anything that survives is genuinely feasible.
2. **Weighted scoring** — nine explainable components, each in [0, 1], combined
   with fixed weights. Every component is stored so the UI can render
   "Why recommended?" without re-deriving anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from yatraai.services.planner.models import (
    AttractionCandidate,
    DayWeather,
    MemberProfile,
    ScoreBreakdown,
    ScoredAttraction,
    TripContext,
)
from yatraai.services.recommend import aggregation
from yatraai.services.recommend.taxonomy import INTERESTS, interest_vector

# --------------------------------------------------------------------------- #
# Model weights. Sum of positive weights = 1.0; penalties are subtracted.
# --------------------------------------------------------------------------- #
WEIGHTS: dict[str, float] = {
    "interest_match": 0.30,
    "group_fairness": 0.15,
    "attraction_quality": 0.12,
    "weather_suitability": 0.12,
    "seasonal_suitability": 0.10,
    "accessibility_suitability": 0.09,
    "budget_suitability": 0.08,
    "evidence_quality": 0.04,
}
PENALTIES: dict[str, float] = {
    "distance_penalty": 0.10,
    "crowd_penalty": 0.06,
}
MANDATORY_BONUS = 1.0

CROWD_LEVEL_VALUE = {"low": 0.0, "medium": 0.3, "high": 0.65, "very_high": 1.0}
ACCESS_VALUE = {"yes": 1.0, "partial": 0.55, "unknown": 0.35, "no": 0.0}


@dataclass
class EligibilityResult:
    eligible: bool
    reasons: list[str]
    details: dict


def _trip_weekdays(ctx: TripContext) -> list[int]:
    return [(ctx.start_date + timedelta(days=i)).weekday() for i in range(ctx.days)]


def _trip_months(ctx: TripContext) -> set[int]:
    return {(ctx.start_date + timedelta(days=i)).month for i in range(ctx.days)}


# --------------------------------------------------------------------------- #
# Stage 1 - hard eligibility
# --------------------------------------------------------------------------- #
def check_eligibility(
    candidate: AttractionCandidate,
    ctx: TripContext,
    members: Sequence[MemberProfile],
) -> EligibilityResult:
    reasons: list[str] = []
    details: dict = {}

    if candidate.slug in ctx.avoid_slugs:
        reasons.append("excluded_by_group")

    # A place closed on every day of the trip can never be scheduled.
    open_days = [wd for wd in _trip_weekdays(ctx) if candidate.opening_windows_for(wd)]
    details["open_days"] = len(open_days)
    if not open_days:
        reasons.append("closed_for_entire_trip")

    # The minimum visit must fit inside at least one opening window that also
    # overlaps the group's daily time window.
    fits = False
    for wd in open_days:
        for opens, closes in candidate.opening_windows_for(wd):
            usable = min(closes, ctx.day_end_min) - max(opens, ctx.day_start_min)
            if usable >= candidate.min_duration_min:
                fits = True
                break
        if fits:
            break
    details["fits_day_window"] = fits
    if open_days and not fits:
        reasons.append("cannot_fit_in_daily_window")

    if ctx.accessibility_required and candidate.wheelchair_accessible == "no":
        reasons.append("not_wheelchair_accessible")

    # A member using a wheelchair vetoes inaccessible places for the whole group.
    if any(m.mobility_level == "wheelchair" for m in members) and (
        candidate.wheelchair_accessible == "no"
    ):
        reasons.append("member_requires_step_free_access")

    if any(m.mobility_level == "limited_walking" for m in members) and (
        candidate.physical_intensity >= 5
    ):
        reasons.append("too_physically_demanding_for_a_member")

    # Budget: a single entry fee that consumes the whole per-person budget is out.
    if ctx.budget_per_person_inr:
        daily_activity_budget = ctx.budget_per_person_inr / max(1, ctx.days) * 0.45
        details["daily_activity_budget"] = round(daily_activity_budget, 2)
        if candidate.entry_cost_min > max(daily_activity_budget, 150.0):
            reasons.append("entry_fee_exceeds_budget")

    # Every member's avoid list is honoured as a hard veto: the brief requires
    # that majority preference cannot simply overrule an individual.
    vetoed_by = [m.member_id for m in members if candidate.slug in m.avoid_slugs]
    if vetoed_by:
        details["vetoed_by"] = vetoed_by
        reasons.append("vetoed_by_member")

    return EligibilityResult(eligible=not reasons, reasons=reasons, details=details)


# --------------------------------------------------------------------------- #
# Stage 2 - component scores
# --------------------------------------------------------------------------- #
def seasonal_suitability(candidate: AttractionCandidate, months: set[int]) -> float:
    if not candidate.suitable_months:
        return 1.0
    suited = months & set(candidate.suitable_months)
    if not months:
        return 1.0
    ratio = len(suited) / len(months)
    # Out-of-season hurts a rain-dependent waterfall far more than a museum.
    return round(ratio + (1 - ratio) * (1.0 - candidate.weather_sensitivity), 4)


def weather_suitability(candidate: AttractionCandidate, weather: Sequence[DayWeather]) -> float:
    """Mean suitability across forecast days. 1.0 = unaffected."""
    if not weather:
        return 1.0
    scores = [_weather_day_score(candidate, w) for w in weather]
    return round(sum(scores) / len(scores), 4)


def _weather_day_score(candidate: AttractionCandidate, w: DayWeather) -> float:
    """How well this attraction holds up in one day's conditions."""
    exposure = {"indoor": 0.0, "mixed": 0.5, "outdoor": 1.0}.get(candidate.indoor_outdoor, 1.0)
    sensitivity = candidate.weather_sensitivity
    score = 1.0

    if w.is_wet:
        rain_mm = w.precipitation_mm or 0.0
        severity = min(1.0, max(rain_mm / 25.0, (w.precipitation_probability or 0.0)))
        score -= 0.75 * severity * exposure * max(0.4, sensitivity)

    if w.is_hot:
        heat = min(1.0, ((w.temp_max_c or 35) - 33) / 12.0)
        score -= 0.45 * heat * exposure

    if w.is_cold:
        cold = min(1.0, (3 - (w.temp_min_c or 3)) / 10.0)
        score -= 0.35 * cold * exposure

    if w.is_low_visibility and (
        "viewpoint" in candidate.categories or "photo-spot" in candidate.categories
    ):
        score -= 0.6

    if (w.wind_kph or 0) > 45 and exposure > 0.5:
        score -= 0.25

    return max(0.0, min(1.0, score))


def budget_suitability(candidate: AttractionCandidate, ctx: TripContext) -> float:
    if not ctx.budget_per_person_inr:
        return 1.0
    daily_activity_budget = max(150.0, ctx.budget_per_person_inr / max(1, ctx.days) * 0.45)
    cost = (candidate.entry_cost_min + candidate.entry_cost_max) / 2.0
    if cost <= 0:
        return 1.0
    ratio = cost / daily_activity_budget
    return round(max(0.0, 1.0 - min(1.0, ratio)), 4)


def accessibility_suitability(
    candidate: AttractionCandidate, ctx: TripContext, members: Sequence[MemberProfile]
) -> float:
    score = ACCESS_VALUE.get(candidate.wheelchair_accessible, 0.35)
    intensity_ok = 1.0 - (candidate.physical_intensity - 1) / 4.0

    if ctx.has_seniors or any(m.is_senior for m in members):
        score = 0.5 * score + 0.5 * (candidate.senior_friendly / 5.0)
    if ctx.has_children or any(m.is_child for m in members):
        score = 0.6 * score + 0.4 * (candidate.child_friendly / 5.0)
    if not (ctx.accessibility_required or ctx.has_seniors or ctx.has_children):
        # No stated needs: only physical demand matters, and only mildly.
        score = 0.35 + 0.65 * intensity_ok

    if any(m.mobility_level == "limited_walking" for m in members):
        score = 0.5 * score + 0.5 * intensity_ok

    return round(max(0.0, min(1.0, score)), 4)


def crowd_penalty(candidate: AttractionCandidate) -> float:
    return CROWD_LEVEL_VALUE.get(candidate.typical_crowd_level, 0.3)


def distance_penalty(candidate: AttractionCandidate, ctx: TripContext, max_km: float) -> float:
    """Normalised distance from the trip base, 0 = at base, 1 = furthest candidate."""
    from yatraai.services.routing.distance import haversine_km

    if max_km <= 0:
        return 0.0
    km = haversine_km(ctx.base_lat, ctx.base_lon, candidate.lat, candidate.lon)
    return round(min(1.0, km / max_km), 4)


# --------------------------------------------------------------------------- #
# Explanation
# --------------------------------------------------------------------------- #
def build_explanation(
    candidate: AttractionCandidate,
    breakdown: ScoreBreakdown,
    members: Sequence[MemberProfile],
    per_member: dict[str, float],
    is_mandatory: bool,
) -> str:
    """Deterministic natural-language "why" - no LLM involved."""
    if is_mandatory:
        return f"{candidate.name} is on your must-visit list, so it was scheduled first."

    parts: list[str] = []
    top_interests = sorted(interest_vector(candidate.categories).items(), key=lambda kv: -kv[1])[:2]
    named = [i for i, v in top_interests if v > 0.4]
    if named and breakdown.interest_match >= 0.4:
        readable = " and ".join(n.replace("_", " ") for n in named)
        parts.append(f"strong match for your group's interest in {readable}")

    if per_member:
        best_member_id = max(per_member, key=lambda m: per_member[m])
        best_value = per_member[best_member_id]
        name_by_id = {m.member_id: m.display_name for m in members}
        if best_value >= 0.6 and len(per_member) > 1:
            parts.append(f"a top pick for {name_by_id.get(best_member_id, 'a group member')}")
        if breakdown.group_fairness >= 0.45:
            parts.append("works for everyone in the group, not just the majority")

    if breakdown.weather_suitability >= 0.85 and candidate.indoor_outdoor != "indoor":
        parts.append("the forecast suits it")
    elif breakdown.weather_suitability < 0.55:
        parts.append("scheduled despite a mixed forecast because it scored well otherwise")
    if candidate.indoor_outdoor == "indoor" and breakdown.weather_suitability >= 0.9:
        parts.append("indoor, so it holds up if the weather turns")

    if breakdown.attraction_quality >= 0.85:
        parts.append("one of the highest-rated places in this destination")
    if breakdown.accessibility_suitability >= 0.8:
        parts.append("comfortable for everyone travelling with you")
    elif breakdown.accessibility_suitability < 0.45:
        parts.append("note that it is physically demanding")
    if breakdown.crowd_penalty >= 0.65:
        parts.append("expect crowds, so an early slot was chosen where possible")
    if breakdown.distance_penalty <= 0.25:
        parts.append("close to your base, keeping travel time down")

    if not parts:
        parts.append("it balances your group's interests against travel time and opening hours")

    sentence = "; ".join(parts[:4])
    return f"Selected because it is {sentence}." if not sentence[0].isupper() else sentence


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def score_candidates(
    candidates: Sequence[AttractionCandidate],
    ctx: TripContext,
    members: Sequence[MemberProfile],
    weather: Sequence[DayWeather] = (),
    *,
    method: str = "fairness_aware",
    satisfaction_so_far: aggregation.GroupSatisfaction | None = None,
) -> tuple[list[ScoredAttraction], list[ScoredAttraction]]:
    """Return ``(eligible_scored_desc, rejected)``.

    ``satisfaction_so_far`` makes the ranking adaptive during iterative
    selection: attractions favoured by currently-neglected members score higher.
    """
    from yatraai.services.routing.distance import haversine_km

    months = _trip_months(ctx)
    weights = {m.member_id: m.weight for m in members}
    matrix = aggregation.utility_matrix(members, candidates)
    deficits = aggregation.member_deficits(satisfaction_so_far) if satisfaction_so_far else None

    max_km = (
        max(
            (haversine_km(ctx.base_lat, ctx.base_lon, c.lat, c.lon) for c in candidates),
            default=1.0,
        )
        or 1.0
    )

    borda = aggregation.borda_count(members, candidates, matrix)

    eligible: list[ScoredAttraction] = []
    rejected: list[ScoredAttraction] = []

    for candidate in candidates:
        utilities = matrix[candidate.slug]
        elig = check_eligibility(candidate, ctx, members)
        is_mandatory = candidate.slug in ctx.must_visit_slugs or any(
            candidate.slug in m.must_visit_slugs for m in members
        )

        if method == "borda_count":
            interest_component = borda.get(candidate.slug, 0.0)
        else:
            interest_component = aggregation.aggregate(
                method, utilities, weights, member_deficits=deficits
            )

        breakdown = ScoreBreakdown(
            interest_match=round(min(1.0, interest_component), 4),
            group_fairness=round(aggregation.max_min_fairness(utilities), 4),
            seasonal_suitability=seasonal_suitability(candidate, months),
            weather_suitability=weather_suitability(candidate, weather),
            budget_suitability=budget_suitability(candidate, ctx),
            distance_penalty=distance_penalty(candidate, ctx, max_km),
            crowd_penalty=crowd_penalty(candidate),
            accessibility_suitability=accessibility_suitability(candidate, ctx, members),
            attraction_quality=round(candidate.quality_score, 4),
            evidence_quality=round(candidate.evidence_score, 4),
            mandatory_bonus=MANDATORY_BONUS if is_mandatory else 0.0,
        )

        total = sum(WEIGHTS[name] * getattr(breakdown, name) for name in WEIGHTS) - sum(
            PENALTIES[name] * getattr(breakdown, name) for name in PENALTIES
        )
        total += breakdown.mandatory_bonus

        scored = ScoredAttraction(
            candidate=candidate,
            total_score=round(total, 6),
            breakdown=breakdown,
            per_member_utility=utilities,
            eligibility={"eligible": elig.eligible, "reasons": elig.reasons, **elig.details},
            is_mandatory=is_mandatory,
            explanation=build_explanation(candidate, breakdown, members, utilities, is_mandatory),
        )

        # A must-visit that fails eligibility is reported, never silently dropped.
        if elig.eligible or is_mandatory:
            eligible.append(scored)
        else:
            rejected.append(scored)

    eligible.sort(key=lambda s: (-s.total_score, s.candidate.slug))
    for i, s in enumerate(eligible):
        s.rank = i + 1
    return eligible, rejected


def coverage_by_interest(
    selected: Sequence[AttractionCandidate], members: Sequence[MemberProfile]
) -> dict[str, float]:
    """How much of each interest the group asked for is actually represented."""
    if not members:
        return {}
    demand = {
        i: sum(float(m.interests.get(i, 3.0)) for m in members) / (5.0 * len(members))
        for i in INTERESTS
    }
    supply = dict.fromkeys(INTERESTS, 0.0)
    for c in selected:
        for interest, value in interest_vector(c.categories).items():
            supply[interest] = max(supply[interest], value)

    return {
        interest: round(min(1.0, supply[interest]) if demand[interest] > 0.35 else 1.0, 4)
        for interest in INTERESTS
        if demand[interest] > 0.35
    }
