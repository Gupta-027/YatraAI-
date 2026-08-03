"""Consent-based live location.

Design rules enforced at the schema level:

* A point can only exist while a session row is ``active``.
* Every session carries an explicit ``consent_granted_at`` and an ``expires_at``.
* ``precision`` records whether the member chose exact or approximate sharing.
* Points are short-lived; ``purge_expired_location_points`` deletes anything
  older than ``LOCATION_POINT_RETENTION_MINUTES``. No permanent history exists.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yatraai.db.base import GUID, Base, JSONType, TimestampMixin, TZDateTime, UUIDPrimaryKeyMixin


class LocationSharingSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "location_sharing_sessions"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trip_members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", nullable=False
    )  # active | paused | stopped | expired
    precision: Mapped[str] = mapped_column(
        String(16), default="approximate", nullable=False
    )  # exact | approximate
    update_interval_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    consent_granted_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    consent_text_version: Mapped[str] = mapped_column(String(24), default="v1", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, index=True)
    stopped_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    last_point_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    share_with: Mapped[str] = mapped_column(String(16), default="group", nullable=False)

    points: Mapped[list[LocationPoint]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("update_interval_seconds >= 15", name="loc_interval_min"),
        Index("ix_locsession_trip_status", "trip_id", "status"),
    )


class LocationPoint(UUIDPrimaryKeyMixin, Base):
    """Recent points only - purged on a fixed retention window."""

    __tablename__ = "location_points"

    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("location_sharing_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    is_approximate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, index=True)

    session: Mapped[LocationSharingSession] = relationship(back_populates="points")

    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="point_lat_range"),
        CheckConstraint("lon BETWEEN -180 AND 180", name="point_lon_range"),
        Index("ix_locpoint_trip_recorded", "trip_id", "recorded_at"),
    )


class SosAlert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """DEMO ONLY - notifies group members in-app. Never contacts emergency services."""

    __tablename__ = "sos_alerts"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("trip_members.id", ondelete="CASCADE"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    approx_lat: Mapped[float | None] = mapped_column(Float)
    approx_lon: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
