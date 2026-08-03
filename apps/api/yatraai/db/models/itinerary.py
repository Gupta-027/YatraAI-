"""Generated itineraries, their days/activities, score breakdowns and feedback."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yatraai.db.base import GUID, Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class Itinerary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "itineraries"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_itinerary_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    status: Mapped[str] = mapped_column(
        String(24), default="draft", nullable=False
    )  # draft | candidate | active | superseded | rejected
    generator: Mapped[str] = mapped_column(
        String(24), default="ortools", nullable=False
    )  # ortools | greedy
    trigger: Mapped[str] = mapped_column(String(40), default="initial", nullable=False)

    # --- validated aggregate metrics ----------------------------------------
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validation_report: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    total_travel_km: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_travel_min: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_visit_min: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activity_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fairness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    least_satisfied_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    consensus_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    utility_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    preference_coverage: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    # --- cost estimate (range, never false precision) -----------------------
    cost_low_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_high_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_per_person_low_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_per_person_high_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_breakdown: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    # --- explanation & provenance -------------------------------------------
    summary_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    explanation_source: Mapped[str] = mapped_column(
        String(24), default="template", nullable=False
    )  # template | llm
    llm_provider: Mapped[str | None] = mapped_column(String(24))
    degraded_services: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    solver_stats: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    days: Mapped[list[ItineraryDay]] = relationship(
        back_populates="itinerary", cascade="all, delete-orphan", order_by="ItineraryDay.day_index"
    )

    __table_args__ = (
        UniqueConstraint("trip_id", "version", name="uq_itinerary_trip_version"),
        Index("ix_itineraries_trip_status", "trip_id", "status"),
    )


class ItineraryDay(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "itinerary_days"

    itinerary_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("itineraries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    calendar_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_min: Mapped[int] = mapped_column(Integer, nullable=False)
    end_min: Mapped[int] = mapped_column(Integer, nullable=False)
    base_lat: Mapped[float] = mapped_column(Float, nullable=False)
    base_lon: Mapped[float] = mapped_column(Float, nullable=False)
    travel_km: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    travel_min: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weather: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    weather_advisories: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    theme: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    itinerary: Mapped[Itinerary] = relationship(back_populates="days")
    activities: Mapped[list[ItineraryActivity]] = relationship(
        back_populates="day", cascade="all, delete-orphan", order_by="ItineraryActivity.sequence"
    )

    __table_args__ = (UniqueConstraint("itinerary_id", "day_index", name="uq_day_itinerary_index"),)


class ItineraryActivity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "itinerary_activities"

    day_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("itinerary_days.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(
        String(16), default="visit", nullable=False
    )  # visit | meal | rest | transfer
    attraction_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("attractions.id", ondelete="SET NULL")
    )
    attraction_slug: Mapped[str | None] = mapped_column(String(96))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    start_min: Mapped[int] = mapped_column(Integer, nullable=False)
    end_min: Mapped[int] = mapped_column(Integer, nullable=False)
    # The opening window this visit was scheduled inside, on that weekday.
    # Nullable on purpose: meals and rests have none, and an attraction with no
    # recorded hours must read as "not recorded" rather than "open all day".
    opens_min: Mapped[int | None] = mapped_column(Integer)
    closes_min: Mapped[int | None] = mapped_column(Integer)
    travel_from_prev_min: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    travel_from_prev_km: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    travel_mode: Mapped[str] = mapped_column(String(24), default="car", nullable=False)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)

    est_cost_low_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    est_cost_high_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    weather_suitability: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    why_selected: Mapped[str] = mapped_column(Text, default="", nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    day: Mapped[ItineraryDay] = relationship(back_populates="activities")

    __table_args__ = (
        CheckConstraint("end_min > start_min", name="activity_time_order"),
        UniqueConstraint("day_id", "sequence", name="uq_activity_day_sequence"),
    )


class RecommendationScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Explainable per-attraction score breakdown for one trip's ranking run."""

    __tablename__ = "recommendation_scores"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    itinerary_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("itineraries.id", ondelete="CASCADE")
    )
    attraction_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("attractions.id", ondelete="CASCADE"), nullable=False
    )
    attraction_slug: Mapped[str] = mapped_column(String(96), nullable=False)
    method: Mapped[str] = mapped_column(String(32), default="fairness_aware", nullable=False)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    components: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    per_member_scores: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    eligibility: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (Index("ix_recscore_trip_rank", "trip_id", "rank"),)


class Feedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback"

    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    itinerary_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("itineraries.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    subject_type: Mapped[str] = mapped_column(String(24), default="itinerary", nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(96))
    rating: Mapped[int | None] = mapped_column(Integer)
    accepted: Mapped[bool | None] = mapped_column(Boolean)
    actual_spend_inr: Mapped[float | None] = mapped_column(Float)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="fb_rating"),
    )
