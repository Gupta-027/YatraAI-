"""Destination and attraction response schemas."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field

from yatraai.schemas.common import ORMModel


class ClusterSummary(ORMModel):
    id: uuid.UUID
    slug: str
    name: str
    state: str
    region: str
    summary: str
    travel_style: list[str] = Field(default_factory=list)
    center_lat: float
    center_lon: float
    best_months: list[int] = Field(default_factory=list)
    avoid_months: list[int] = Field(default_factory=list)
    recommended_days: int
    intercity_hub: str | None = None
    hero_image_url: str | None = None
    image_attribution: str | None = None
    attraction_count: int = 0


class ClusterDetail(ClusterSummary):
    daily_cost_baseline: dict = Field(default_factory=dict)
    timezone: str = "Asia/Kolkata"
    categories: list[str] = Field(default_factory=list)
    accessibility_summary: dict = Field(default_factory=dict)


class ScheduleEntry(BaseModel):
    day_of_week: int
    day_label: str
    opens: str | None = None
    closes: str | None = None
    is_closed: bool = False
    season: str = "all"
    note: str = ""
    verified: bool = False


class CostEntry(BaseModel):
    visitor_type: str
    label: str
    currency: str = "INR"
    amount_min: float
    amount_max: float
    is_free: bool = False
    note: str = ""
    verified: bool = False


class SourceEntry(BaseModel):
    url: str
    title: str = ""
    source_type: str = "official"
    covers_fields: list[str] = Field(default_factory=list)
    last_verified_at: date | None = None


class AttractionSummary(ORMModel):
    id: uuid.UUID
    slug: str
    name: str
    locality: str
    city: str
    lat: float
    lon: float
    categories: list[str] = Field(default_factory=list)
    summary: str
    typical_duration_min: int
    indoor_outdoor: str
    typical_crowd_level: str
    wheelchair_accessible: str
    senior_friendly: int
    child_friendly: int
    physical_intensity: int
    quality_score: float
    hero_image_url: str | None = None
    image_attribution: str | None = None
    needs_verification: bool = True
    cluster_slug: str = ""


class NearbyAttraction(BaseModel):
    slug: str
    name: str
    cluster_slug: str
    distance_km: float | None = None
    categories: list[str] = Field(default_factory=list)


class AttractionDetail(AttractionSummary):
    """Everything the "Know this place" drawer renders."""

    history: str = ""
    significance: str = ""
    interesting_facts: list[str] = Field(default_factory=list)
    min_duration_min: int
    max_duration_min: int
    best_time_of_day: list[str] = Field(default_factory=list)
    suitable_months: list[int] = Field(default_factory=list)
    weather_sensitivity: float = 0.5
    crowd_by_time: dict = Field(default_factory=dict)
    accessibility_notes: str = ""
    dress_code: str = ""
    photography_policy: str = ""
    local_customs: list[str] = Field(default_factory=list)
    schedules: list[ScheduleEntry] = Field(default_factory=list)
    costs: list[CostEntry] = Field(default_factory=list)
    sources: list[SourceEntry] = Field(default_factory=list)
    nearby: list[NearbyAttraction] = Field(default_factory=list)
    data_confidence: str = "medium"
    verification_note: str = ""
    last_verified_at: date | None = None
    knowledge_topics: list[str] = Field(default_factory=list)
