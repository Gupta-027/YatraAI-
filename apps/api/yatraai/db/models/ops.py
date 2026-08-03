"""Operational tables: caches, pipeline runs, model runs, audit logs, events."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from yatraai.db.base import (
    GUID,
    Base,
    JSONType,
    TimestampMixin,
    TZDateTime,
    UUIDPrimaryKeyMixin,
    utcnow,
)


class WeatherSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Daily forecast/climatology per cluster. Cached to survive provider outages."""

    __tablename__ = "weather_snapshots"

    cluster_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    temp_min_c: Mapped[float | None] = mapped_column(Float)
    temp_max_c: Mapped[float | None] = mapped_column(Float)
    precipitation_mm: Mapped[float | None] = mapped_column(Float)
    precipitation_probability: Mapped[float | None] = mapped_column(Float)
    wind_kph: Mapped[float | None] = mapped_column(Float)
    visibility_km: Mapped[float | None] = mapped_column(Float)
    weather_code: Mapped[int | None] = mapped_column(Integer)
    condition: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (
        UniqueConstraint(
            "cluster_slug", "target_date", "provider", name="uq_weather_cluster_date_provider"
        ),
    )


class RouteCacheEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Memoised origin->destination legs so repeat planning is fast and cheap."""

    __tablename__ = "route_cache"

    cache_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    origin_lat: Mapped[float] = mapped_column(Float, nullable=False)
    origin_lon: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lat: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lon: Mapped[float] = mapped_column(Float, nullable=False)
    mode: Mapped[str] = mapped_column(String(24), default="car", nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    duration_min: Mapped[float] = mapped_column(Float, nullable=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PipelineRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pipeline_runs"

    pipeline: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    layer: Mapped[str] = mapped_column(String(16), nullable=False)  # bronze | silver | gold
    run_key: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    rows_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    checks: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (UniqueConstraint("pipeline", "run_key", name="uq_pipeline_run_key"),)


class ModelRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A reproducible ML / optimisation experiment record."""

    __tablename__ = "model_runs"

    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    experiment: Mapped[str] = mapped_column(String(96), nullable=False)
    model_name: Mapped[str] = mapped_column(String(96), nullable=False)
    data_kind: Mapped[str] = mapped_column(
        String(24), default="synthetic", nullable=False
    )  # synthetic | real | mixed  -- honesty about label provenance
    params: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only record of sensitive trip / privacy actions."""

    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    actor_label: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(96))
    trip_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    __table_args__ = (Index("ix_audit_action_created", "action", "created_at"),)


class AnalyticsEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Privacy-safe product events. Never stores precise coordinates."""

    __tablename__ = "analytics_events"

    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), index=True)
    cluster_slug: Mapped[str | None] = mapped_column(String(64), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    numeric_value: Mapped[float | None] = mapped_column(Float)
    properties: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class ServiceCallLog(UUIDPrimaryKeyMixin, Base):
    """Latency/error telemetry for external providers (LLM, routing, weather)."""

    __tablename__ = "service_call_logs"

    service: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_kind: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, index=True, default=utcnow
    )

    __table_args__ = (Index("ix_svc_service_created", "service", "created_at"),)
