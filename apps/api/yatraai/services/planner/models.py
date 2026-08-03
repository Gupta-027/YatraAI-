"""Pure-Python domain types for the planning pipeline.

Nothing here touches the database or FastAPI. The optimiser, validator, scorer
and cost model all operate on these dataclasses, which is what makes them
unit-testable in isolation and deterministic under a fixed seed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

Pace = Literal["relaxed", "balanced", "packed"]
Mobility = Literal["full", "limited_walking", "wheelchair"]
TransportMode = Literal["walk", "car", "taxi", "public", "mixed"]

# Activities per day and the fraction of the day left unscheduled, by pace.
PACE_PROFILE: dict[str, dict[str, float]] = {
    "relaxed": {"max_activities": 3, "buffer_ratio": 0.30, "max_travel_min": 150},
    "balanced": {"max_activities": 4, "buffer_ratio": 0.20, "max_travel_min": 210},
    "packed": {"max_activities": 6, "buffer_ratio": 0.10, "max_travel_min": 300},
}

# Average speed assumptions for the haversine fallback, documented in
# docs/optimization.md. Deliberately conservative for Indian urban traffic.
MODE_SPEED_KMPH: dict[str, float] = {
    "walk": 4.2,
    "car": 24.0,
    "taxi": 24.0,
    "public": 16.0,
    "mixed": 21.0,
}

# Straight-line distance underestimates road distance. These multipliers are the
# documented detour factors applied to the haversine fallback.
MODE_DETOUR_FACTOR: dict[str, float] = {
    "walk": 1.25,
    "car": 1.35,
    "taxi": 1.35,
    "public": 1.45,
    "mixed": 1.35,
}


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OpeningWindow:
    """One opening interval, in minutes from midnight. ``day_of_week`` -1 = all."""

    day_of_week: int
    opens_min: int
    closes_min: int
    season: str = "all"

    def covers(self, weekday: int) -> bool:
        return self.day_of_week in (-1, weekday)


@dataclass
class AttractionCandidate:
    slug: str
    name: str
    lat: float
    lon: float
    categories: list[str]
    typical_duration_min: int
    min_duration_min: int
    max_duration_min: int
    quality_score: float = 0.6
    indoor_outdoor: str = "outdoor"
    weather_sensitivity: float = 0.5
    typical_crowd_level: str = "medium"
    crowd_by_time: dict[str, str] = field(default_factory=dict)
    suitable_months: list[int] = field(default_factory=lambda: list(range(1, 13)))
    best_time_of_day: list[str] = field(default_factory=list)
    wheelchair_accessible: str = "unknown"
    senior_friendly: int = 3
    child_friendly: int = 3
    physical_intensity: int = 2
    entry_cost_min: float = 0.0
    entry_cost_max: float = 0.0
    windows: list[OpeningWindow] = field(default_factory=list)
    closed_weekdays: set[int] = field(default_factory=set)
    needs_verification: bool = True
    verification_note: str = ""
    evidence_score: float = 0.6
    attraction_id: str | None = None
    cluster_slug: str = ""

    def opening_windows_for(self, weekday: int) -> list[tuple[int, int]]:
        """Opening intervals on a weekday. Empty list == closed all day."""
        if weekday in self.closed_weekdays:
            return []
        windows = [(w.opens_min, w.closes_min) for w in self.windows if w.covers(weekday)]
        if not windows and not self.windows:
            # No recorded hours: treat as open through the planning day but flag it.
            return [(0, 24 * 60)]
        return sorted(windows)


@dataclass
class MemberProfile:
    member_id: str
    display_name: str
    interests: dict[str, float]
    weight: float = 1.0
    ranked_choices: list[str] = field(default_factory=list)
    pace: Pace = "balanced"
    budget_sensitivity: int = 3
    indoor_outdoor_pref: str = "mixed"
    mobility_level: Mobility = "full"
    max_walk_minutes: int = 30
    earliest_start_min: int = 9 * 60
    latest_end_min: int = 20 * 60
    must_visit_slugs: list[str] = field(default_factory=list)
    avoid_slugs: list[str] = field(default_factory=list)
    is_senior: bool = False
    is_child: bool = False


@dataclass
class TripContext:
    trip_id: str
    cluster_slug: str
    start_date: date
    end_date: date
    traveller_count: int = 2
    budget_per_person_inr: float | None = None
    pace: Pace = "balanced"
    transport_mode: TransportMode = "car"
    accommodation_tier: str = "midrange"
    day_start_min: int = 9 * 60
    day_end_min: int = 20 * 60
    base_lat: float = 0.0
    base_lon: float = 0.0
    origin_label: str = ""
    has_children: bool = False
    has_seniors: bool = False
    accessibility_required: bool = False
    must_visit_slugs: list[str] = field(default_factory=list)
    avoid_slugs: list[str] = field(default_factory=list)
    random_seed: int = 20240101

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @property
    def daily_minutes(self) -> int:
        return self.day_end_min - self.day_start_min


@dataclass
class DayWeather:
    calendar_date: date
    condition: str = "unknown"
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    precipitation_mm: float | None = None
    precipitation_probability: float | None = None
    wind_kph: float | None = None
    visibility_km: float | None = None
    is_fallback: bool = False
    provider: str = "seed"

    @property
    def is_wet(self) -> bool:
        return (self.precipitation_mm or 0) >= 5.0 or (self.precipitation_probability or 0) >= 0.6

    @property
    def is_hot(self) -> bool:
        return (self.temp_max_c or 0) >= 35.0

    @property
    def is_cold(self) -> bool:
        return (self.temp_min_c if self.temp_min_c is not None else 99) <= 2.0

    @property
    def is_low_visibility(self) -> bool:
        return self.visibility_km is not None and self.visibility_km < 3.0


# --------------------------------------------------------------------------- #
# Scoring output
# --------------------------------------------------------------------------- #
@dataclass
class ScoreBreakdown:
    """Every number the UI shows in "Why recommended?" comes from here."""

    interest_match: float = 0.0
    group_fairness: float = 0.0
    seasonal_suitability: float = 1.0
    weather_suitability: float = 1.0
    budget_suitability: float = 1.0
    distance_penalty: float = 0.0
    crowd_penalty: float = 0.0
    accessibility_suitability: float = 1.0
    attraction_quality: float = 0.0
    evidence_quality: float = 0.0
    mandatory_bonus: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {k: round(float(v), 4) for k, v in self.__dict__.items()}


@dataclass
class ScoredAttraction:
    candidate: AttractionCandidate
    total_score: float
    breakdown: ScoreBreakdown
    per_member_utility: dict[str, float] = field(default_factory=dict)
    eligibility: dict[str, Any] = field(default_factory=dict)
    is_mandatory: bool = False
    explanation: str = ""
    rank: int = 0

    @property
    def slug(self) -> str:
        return self.candidate.slug


# --------------------------------------------------------------------------- #
# Plan output
# --------------------------------------------------------------------------- #
@dataclass
class PlannedActivity:
    kind: str  # visit | meal | rest
    sequence: int
    title: str
    start_min: int
    end_min: int
    slug: str | None = None
    attraction_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    travel_from_prev_min: int = 0
    travel_from_prev_km: float = 0.0
    travel_mode: str = "car"
    est_cost_low_inr: float = 0.0
    est_cost_high_inr: float = 0.0
    weather_suitability: float = 1.0
    warnings: list[str] = field(default_factory=list)
    why_selected: str = ""
    score_breakdown: dict[str, float] = field(default_factory=dict)
    is_mandatory: bool = False
    locked: bool = False
    opens_min: int | None = None
    closes_min: int | None = None
    """The opening window this visit was scheduled inside, on that weekday.

    Carried through to the UI so a traveller can see *why* a stop sits where it
    does - "10:00-11:30, open 09:00-17:00" is a schedule you can sanity-check,
    while a bare visit time asks you to trust the solver. Both are ``None`` for
    meals, rests, and any attraction with no recorded hours; the UI must not
    invent a window in that case.
    """

    @property
    def duration_min(self) -> int:
        return self.end_min - self.start_min


@dataclass
class PlannedDay:
    day_index: int
    calendar_date: date
    start_min: int
    end_min: int
    base_lat: float
    base_lon: float
    activities: list[PlannedActivity] = field(default_factory=list)
    travel_km: float = 0.0
    travel_min: int = 0
    weather: DayWeather | None = None
    weather_advisories: list[str] = field(default_factory=list)
    theme: str = ""
    notes: str = ""

    @property
    def visits(self) -> list[PlannedActivity]:
        return [a for a in self.activities if a.kind == "visit"]


@dataclass
class PlanMetrics:
    total_travel_km: float = 0.0
    total_travel_min: int = 0
    total_visit_min: int = 0
    activity_count: int = 0
    fairness_score: float = 0.0
    least_satisfied_score: float = 0.0
    consensus_score: float = 0.0
    utility_score: float = 0.0
    preference_coverage: dict[str, float] = field(default_factory=dict)
    per_member_coverage: dict[str, float] = field(default_factory=dict)
    computation_ms: float = 0.0
    solver_status: str = ""

    def to_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


@dataclass
class CostEstimate:
    low_inr: float
    high_inr: float
    per_person_low_inr: float
    per_person_high_inr: float
    breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "low_inr": round(self.low_inr, 2),
            "high_inr": round(self.high_inr, 2),
            "per_person_low_inr": round(self.per_person_low_inr, 2),
            "per_person_high_inr": round(self.per_person_high_inr, 2),
            "breakdown": self.breakdown,
            "assumptions": self.assumptions,
        }


@dataclass
class ValidationIssue:
    code: str
    severity: str  # error | warning
    message: str
    day_index: int | None = None
    slug: str | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "day_index": self.day_index,
            "slug": self.slug,
        }


@dataclass
class ValidationReport:
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    checks_run: int = 0

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "checks_run": self.checks_run,
            "errors": [i.to_dict() for i in self.errors],
            "warnings": [i.to_dict() for i in self.warnings],
        }


@dataclass
class PlanResult:
    days: list[PlannedDay]
    metrics: PlanMetrics
    cost: CostEstimate
    validation: ValidationReport
    generator: str = "ortools"
    scored: list[ScoredAttraction] = field(default_factory=list)
    degraded_services: list[str] = field(default_factory=list)
    solver_stats: dict[str, Any] = field(default_factory=dict)
    unplaced_mandatory: list[str] = field(default_factory=list)

    @property
    def selected_slugs(self) -> list[str]:
        return [a.slug for d in self.days for a in d.visits if a.slug]


def fingerprint(*parts: Any) -> str:
    """Stable hash of planner inputs - identical inputs give identical plans."""
    payload = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
