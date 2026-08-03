"""Trip, membership, preference and itinerary schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from yatraai.schemas.common import ORMModel
from yatraai.services.recommend.taxonomy import INTERESTS

Pace = Literal["relaxed", "balanced", "packed"]
TransportMode = Literal["walk", "car", "taxi", "public", "mixed"]
Mobility = Literal["full", "limited_walking", "wheelchair"]
Tier = Literal["budget", "midrange", "premium"]


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)
    home_city: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    display_name: str
    home_city: str | None = None
    avatar_seed: str = "indigo"
    is_admin: bool = False
    is_demo: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


# --------------------------------------------------------------------------- #
# Preferences
# --------------------------------------------------------------------------- #
class PreferenceInput(BaseModel):
    interests: dict[str, int] = Field(default_factory=dict)
    ranked_choices: list[str] = Field(default_factory=list, max_length=10)
    pace: Pace = "balanced"
    budget_sensitivity: int = Field(default=3, ge=1, le=5)
    indoor_outdoor_pref: Literal["indoor", "outdoor", "mixed"] = "mixed"
    dietary: Literal["any", "vegetarian", "vegan", "jain", "halal", "no_beef", "no_pork"] = "any"
    mobility_level: Mobility = "full"
    max_walk_minutes: int = Field(default=30, ge=5, le=240)
    earliest_start_min: int = Field(default=540, ge=0, le=1439)
    latest_end_min: int = Field(default=1200, ge=1, le=1440)
    must_visit_slugs: list[str] = Field(default_factory=list, max_length=10)
    avoid_slugs: list[str] = Field(default_factory=list, max_length=20)
    is_senior: bool = False
    is_child: bool = False
    notes: str = Field(default="", max_length=1000)

    @field_validator("interests")
    @classmethod
    def _validate_interests(cls, value: dict[str, int]) -> dict[str, int]:
        unknown = set(value) - set(INTERESTS)
        if unknown:
            raise ValueError(f"unknown interests: {sorted(unknown)}")
        for k, v in value.items():
            if not 0 <= int(v) <= 5:
                raise ValueError(f"interest '{k}' must be between 0 and 5")
        return {k: int(v) for k, v in value.items()}

    @model_validator(mode="after")
    def _validate_window(self):
        if self.latest_end_min <= self.earliest_start_min:
            raise ValueError("latest_end_min must be after earliest_start_min")
        return self


class MemberPreferenceOut(ORMModel):
    interests: dict = Field(default_factory=dict)
    ranked_choices: list[str] = Field(default_factory=list)
    pace: str = "balanced"
    budget_sensitivity: int = 3
    indoor_outdoor_pref: str = "mixed"
    dietary: str = "any"
    mobility_level: str = "full"
    max_walk_minutes: int = 30
    earliest_start_min: int = 540
    latest_end_min: int = 1200
    must_visit_slugs: list[str] = Field(default_factory=list)
    avoid_slugs: list[str] = Field(default_factory=list)
    notes: str = ""
    submitted: bool = False


class TripMemberOut(ORMModel):
    id: uuid.UUID
    display_name: str
    role: str
    status: str
    weight: float = 1.0
    joined_at: datetime | None = None
    user_id: uuid.UUID | None = None
    preferences: MemberPreferenceOut | None = None


# --------------------------------------------------------------------------- #
# Trips
# --------------------------------------------------------------------------- #
class TripCreate(BaseModel):
    cluster_slug: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    start_date: date
    end_date: date
    origin_label: str = Field(default="", max_length=160)
    origin_lat: float | None = Field(default=None, ge=-90, le=90)
    origin_lon: float | None = Field(default=None, ge=-180, le=180)
    traveller_count: int = Field(default=2, ge=1, le=40)
    budget_per_person_inr: float | None = Field(default=None, ge=0, le=10_000_000)
    budget_total_inr: float | None = Field(default=None, ge=0, le=100_000_000)
    budget_basis: Literal["per_person", "total"] = "per_person"
    pace: Pace = "balanced"
    transport_mode: TransportMode = "car"
    accommodation_tier: Tier = "midrange"
    day_start_min: int = Field(default=540, ge=0, le=1439)
    day_end_min: int = Field(default=1200, ge=1, le=1440)
    has_children: bool = False
    has_seniors: bool = False
    accessibility_required: bool = False
    must_visit_slugs: list[str] = Field(default_factory=list, max_length=15)
    avoid_slugs: list[str] = Field(default_factory=list, max_length=30)
    notes: str = Field(default="", max_length=2000)
    owner_preferences: PreferenceInput | None = None

    @model_validator(mode="after")
    def _validate(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if (self.end_date - self.start_date).days > 20:
            raise ValueError("trips are limited to 21 days in this version")
        if self.day_end_min <= self.day_start_min:
            raise ValueError("day_end_min must be after day_start_min")
        if self.day_end_min - self.day_start_min < 180:
            raise ValueError("a planning day must be at least three hours long")
        return self


class TripUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    start_date: date | None = None
    end_date: date | None = None
    pace: Pace | None = None
    transport_mode: TransportMode | None = None
    accommodation_tier: Tier | None = None
    budget_per_person_inr: float | None = Field(default=None, ge=0)
    traveller_count: int | None = Field(default=None, ge=1, le=40)
    day_start_min: int | None = Field(default=None, ge=0, le=1439)
    day_end_min: int | None = Field(default=None, ge=1, le=1440)
    must_visit_slugs: list[str] | None = None
    avoid_slugs: list[str] | None = None
    accessibility_required: bool | None = None
    has_children: bool | None = None
    has_seniors: bool | None = None
    status: Literal["draft", "collecting", "planned", "active", "completed", "archived"] | None = (
        None
    )
    notes: str | None = Field(default=None, max_length=2000)


class TripOut(ORMModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    cluster_id: uuid.UUID
    title: str
    start_date: date
    end_date: date
    origin_label: str = ""
    traveller_count: int
    budget_per_person_inr: float | None = None
    budget_total_inr: float | None = None
    budget_basis: str = "per_person"
    pace: str
    transport_mode: str
    accommodation_tier: str
    day_start_min: int
    day_end_min: int
    has_children: bool
    has_seniors: bool
    accessibility_required: bool
    must_visit_slugs: list[str] = Field(default_factory=list)
    avoid_slugs: list[str] = Field(default_factory=list)
    status: str
    invite_code: str
    notes: str = ""
    created_at: datetime
    cluster_slug: str = ""
    cluster_name: str = ""
    duration_days: int = 1
    members: list[TripMemberOut] = Field(default_factory=list)
    preferences_submitted: int = 0
    has_itinerary: bool = False


class JoinTripRequest(BaseModel):
    invite_code: str = Field(min_length=4, max_length=12)
    display_name: str | None = Field(default=None, max_length=120)


# --------------------------------------------------------------------------- #
# Itineraries
# --------------------------------------------------------------------------- #
class GenerateItineraryRequest(BaseModel):
    generator: Literal["ortools", "greedy"] = "ortools"
    aggregation_method: Literal[
        "simple_average", "weighted_average", "borda_count", "max_min_fairness", "fairness_aware"
    ] = "fairness_aware"
    explain_with_llm: bool = True
    force_regenerate: bool = False


class ActivityOut(ORMModel):
    id: uuid.UUID
    sequence: int
    kind: str
    title: str
    attraction_slug: str | None = None
    attraction_id: uuid.UUID | None = None
    start_min: int
    end_min: int
    start_time: str = ""
    end_time: str = ""
    duration_min: int = 0
    # The opening window this visit sits inside. None means the attraction records
    # no hours - the UI must say so rather than imply it is open all day.
    opens_time: str | None = None
    closes_time: str | None = None
    travel_from_prev_min: int = 0
    travel_from_prev_km: float = 0.0
    travel_mode: str = "car"
    lat: float | None = None
    lon: float | None = None
    est_cost_low_inr: float = 0.0
    est_cost_high_inr: float = 0.0
    weather_suitability: float = 1.0
    warnings: list[str] = Field(default_factory=list)
    why_selected: str = ""
    score_breakdown: dict = Field(default_factory=dict)
    is_mandatory: bool = False
    locked: bool = False


class DayOut(ORMModel):
    id: uuid.UUID
    day_index: int
    calendar_date: date
    start_min: int
    end_min: int
    base_lat: float
    base_lon: float
    travel_km: float
    travel_min: int
    weather: dict = Field(default_factory=dict)
    weather_advisories: list[str] = Field(default_factory=list)
    theme: str = ""
    notes: str = ""
    activities: list[ActivityOut] = Field(default_factory=list)


class ValidationIssueOut(BaseModel):
    code: str
    severity: str
    message: str
    day_index: int | None = None
    slug: str | None = None


class ValidationOut(BaseModel):
    is_valid: bool
    checks_run: int = 0
    errors: list[ValidationIssueOut] = Field(default_factory=list)
    warnings: list[ValidationIssueOut] = Field(default_factory=list)


class CostOut(BaseModel):
    low_inr: float
    high_inr: float
    per_person_low_inr: float
    per_person_high_inr: float
    display: str = ""
    breakdown: dict = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


class ItineraryOut(ORMModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    version: int
    status: str
    generator: str
    trigger: str
    is_valid: bool
    validation: ValidationOut
    total_travel_km: float
    total_travel_min: int
    total_visit_min: int
    activity_count: int
    fairness_score: float
    least_satisfied_score: float
    consensus_score: float
    utility_score: float
    preference_coverage: dict = Field(default_factory=dict)
    per_member_coverage: dict = Field(default_factory=dict)
    cost: CostOut
    summary_text: str = ""
    explanation_source: str = "template"
    llm_provider: str | None = None
    degraded_services: list[str] = Field(default_factory=list)
    solver_stats: dict = Field(default_factory=dict)
    created_at: datetime
    days: list[DayOut] = Field(default_factory=list)


class RecommendationOut(BaseModel):
    attraction_slug: str
    name: str
    rank: int
    total_score: float
    selected: bool
    components: dict = Field(default_factory=dict)
    per_member_scores: dict = Field(default_factory=dict)
    eligibility: dict = Field(default_factory=dict)
    explanation: str = ""


# --------------------------------------------------------------------------- #
# Modification / replanning
# --------------------------------------------------------------------------- #
ModifyAction = Literal[
    "remove_activity",
    "replace_activity",
    "regenerate_day",
    "make_day_relaxed",
    "reduce_cost",
    "reduce_travel",
    "add_theme",
    "shift_start_time",
    "weather_replan",
    "member_opted_out",
    "attraction_unavailable",
]


class ModifyItineraryRequest(BaseModel):
    action: ModifyAction
    day_index: int | None = Field(default=None, ge=0, le=30)
    attraction_slug: str | None = Field(default=None, max_length=96)
    replacement_slug: str | None = Field(default=None, max_length=96)
    theme: str | None = Field(default=None, max_length=32)
    new_start_min: int | None = Field(default=None, ge=0, le=1439)
    member_id: uuid.UUID | None = None
    budget_reduction_pct: float | None = Field(default=None, ge=1, le=80)
    explain_with_llm: bool = True
    propose_only: bool = False


class ItineraryDiff(BaseModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    moved: list[dict] = Field(default_factory=list)
    travel_km_delta: float = 0.0
    travel_min_delta: int = 0
    cost_per_person_delta_low: float = 0.0
    cost_per_person_delta_high: float = 0.0
    fairness_delta: float = 0.0
    summary: str = ""


class ModifyItineraryResponse(BaseModel):
    applied: bool
    itinerary: ItineraryOut | None = None
    diff: ItineraryDiff
    validation: ValidationOut
    requires_group_approval: bool = False
    proposal_id: uuid.UUID | None = None
    message: str = ""
