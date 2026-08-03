"""Trips, membership, per-member preferences and collaboration primitives."""

from __future__ import annotations

import uuid
from datetime import date, datetime

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

from yatraai.db.base import (
    GUID,
    Base,
    JSONType,
    TimestampMixin,
    TZDateTime,
    UUIDPrimaryKeyMixin,
)


class Trip(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trips"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("destination_clusters.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    origin_label: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    origin_lat: Mapped[float | None] = mapped_column(Float)
    origin_lon: Mapped[float | None] = mapped_column(Float)

    traveller_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    budget_total_inr: Mapped[float | None] = mapped_column(Float)
    budget_per_person_inr: Mapped[float | None] = mapped_column(Float)
    budget_basis: Mapped[str] = mapped_column(String(16), default="per_person", nullable=False)

    pace: Mapped[str] = mapped_column(String(16), default="balanced", nullable=False)
    transport_mode: Mapped[str] = mapped_column(String(24), default="car", nullable=False)
    accommodation_tier: Mapped[str] = mapped_column(String(24), default="midrange", nullable=False)
    day_start_min: Mapped[int] = mapped_column(Integer, default=9 * 60, nullable=False)
    day_end_min: Mapped[int] = mapped_column(Integer, default=20 * 60, nullable=False)

    has_children: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_seniors: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accessibility_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    must_visit_slugs: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    avoid_slugs: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)

    status: Mapped[str] = mapped_column(
        String(24), default="draft", nullable=False
    )  # draft | collecting | planned | active | completed | archived
    invite_code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    invite_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    members: Mapped[list[TripMember]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    cluster: Mapped[DestinationCluster] = relationship(lazy="joined")  # noqa: F821

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="trip_date_order"),
        CheckConstraint("traveller_count >= 1", name="trip_traveller_min"),
        CheckConstraint("day_end_min > day_start_min", name="trip_day_window"),
        Index("ix_trips_owner_status", "owner_id", "status"),
    )

    @property
    def duration_days(self) -> int:
        return (self.end_date - self.start_date).days + 1


class TripMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trip_members"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="member", nullable=False)  # owner|member
    status: Mapped[str] = mapped_column(
        String(16), default="invited", nullable=False
    )  # invited | joined | opted_out
    joined_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    trip: Mapped[Trip] = relationship(back_populates="members")
    preferences: Mapped[MemberPreference | None] = relationship(
        back_populates="member", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("trip_id", "user_id", name="uq_trip_member_user"),
        CheckConstraint("weight > 0", name="member_weight_positive"),
    )


class MemberPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per member. Interest weights are 0-5 integers."""

    __tablename__ = "member_preferences"

    member_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trip_members.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interests: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    ranked_choices: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    pace: Mapped[str] = mapped_column(String(16), default="balanced", nullable=False)
    budget_sensitivity: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    indoor_outdoor_pref: Mapped[str] = mapped_column(String(16), default="mixed", nullable=False)
    dietary: Mapped[str] = mapped_column(String(24), default="any", nullable=False)
    mobility_level: Mapped[str] = mapped_column(
        String(24), default="full", nullable=False
    )  # full | limited_walking | wheelchair
    max_walk_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    earliest_start_min: Mapped[int] = mapped_column(Integer, default=9 * 60, nullable=False)
    latest_end_min: Mapped[int] = mapped_column(Integer, default=20 * 60, nullable=False)
    must_visit_slugs: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    avoid_slugs: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    member: Mapped[TripMember] = relationship(back_populates="preferences")

    __table_args__ = (
        CheckConstraint("budget_sensitivity BETWEEN 1 AND 5", name="pref_budget_sens_range"),
    )


class Vote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Approve / reject votes on an itinerary or a proposed change."""

    __tablename__ = "votes"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trip_members.id", ondelete="CASCADE"), nullable=False
    )
    subject_type: Mapped[str] = mapped_column(
        String(24), nullable=False
    )  # itinerary | proposal | attraction
    subject_id: Mapped[str] = mapped_column(String(96), nullable=False)
    value: Mapped[str] = mapped_column(String(16), nullable=False)  # up | down | abstain
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("member_id", "subject_type", "subject_id", name="uq_vote_member_subject"),
        Index("ix_votes_subject", "subject_type", "subject_id"),
    )


class ChangeProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A validated modification awaiting group approval."""

    __tablename__ = "change_proposals"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    itinerary_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("itineraries.id", ondelete="CASCADE"), nullable=False
    )
    proposed_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("trip_members.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    diff: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    candidate_itinerary_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    status: Mapped[str] = mapped_column(
        String(16), default="open", nullable=False
    )  # open | approved | rejected | applied | expired
    required_approvals: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(TZDateTime)


class ChatMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("trip_members.id", ondelete="SET NULL")
    )
    author_name: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(
        String(16), default="text", nullable=False
    )  # text | system | proposal
    meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    __table_args__ = (Index("ix_chat_trip_created", "trip_id", "created_at"),)
