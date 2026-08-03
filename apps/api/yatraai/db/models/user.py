"""Accounts. Password hashes only; Supabase JWTs are also accepted."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from yatraai.db.base import Base, JSONType, TimestampMixin, TZDateTime, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    supabase_user_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    avatar_seed: Mapped[str] = mapped_column(String(32), default="indigo", nullable=False)
    home_city: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Default preference profile reused when joining a new trip.
    default_preferences: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime)
