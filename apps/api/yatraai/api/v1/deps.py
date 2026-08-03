"""Shared FastAPI dependencies: auth, database, rate limiting, audit."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from yatraai.config import Settings, get_settings
from yatraai.core.errors import AuthenticationError, AuthorizationError, NotFoundError
from yatraai.core.rate_limit import limiter
from yatraai.core.security import decode_token
from yatraai.db.models import AuditLog, Trip, TripMember, User
from yatraai.db.session import get_db
from yatraai.logging_config import request_id_ctx, user_id_ctx


def db_session() -> Iterator[Session]:
    yield from get_db()


DbSession = Annotated[Session, Depends(db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def current_user_optional(
    session: DbSession,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> User | None:
    token = _bearer_token(authorization)
    if not token:
        return None
    try:
        claims = decode_token(token)
    except AuthenticationError:
        return None

    user: User | None = None
    subject = claims.get("sub")
    if claims.get("_supabase"):
        # Supabase-issued token: match on the Supabase user id, provisioning on
        # first sight so a Supabase-only deployment needs no separate signup.
        user = session.scalar(select(User).where(User.supabase_user_id == str(subject)))
        if user is None and claims.get("email"):
            user = session.scalar(select(User).where(User.email == claims["email"]))
            if user is not None:
                user.supabase_user_id = str(subject)
    else:
        try:
            user = session.get(User, uuid.UUID(str(subject)))
        except (ValueError, TypeError):
            user = None

    if user is not None:
        user_id_ctx.set(str(user.id))
    return user


def current_user(
    user: Annotated[User | None, Depends(current_user_optional)],
) -> User:
    if user is None:
        raise AuthenticationError("Authentication required. Sign in and retry.")
    if not user.is_active:
        raise AuthorizationError("This account is disabled.")
    return user


def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_admin:
        raise AuthorizationError("Administrator access required.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(current_user_optional)]
AdminUser = Annotated[User, Depends(admin_user)]


# --------------------------------------------------------------------------- #
# Trip authorisation
# --------------------------------------------------------------------------- #
def load_trip(session: Session, trip_id: uuid.UUID) -> Trip:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("Trip not found", code="trip_not_found")
    return trip


def require_trip_member(session: Session, trip: Trip, user: User) -> TripMember:
    """Row-level rule: you must be a member of a trip to read or change it."""
    member = session.scalar(
        select(TripMember).where(TripMember.trip_id == trip.id, TripMember.user_id == user.id)
    )
    if member is None:
        if user.is_admin:
            # Admins may read for support, but are not silently made members.
            return TripMember(
                trip_id=trip.id, user_id=user.id, display_name=user.display_name, role="admin"
            )
        raise AuthorizationError("You are not a member of this trip.", code="not_a_trip_member")
    return member


def require_trip_owner(session: Session, trip: Trip, user: User) -> None:
    if trip.owner_id != user.id and not user.is_admin:
        raise AuthorizationError("Only the trip owner can do this.", code="trip_owner_required")


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
def _client_key(request: Request, user: User | None) -> str:
    if user is not None:
        return f"user:{user.id}"
    forwarded = request.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    return f"ip:{ip}"


def rate_limit_default(request: Request, user: OptionalUser) -> None:
    s = get_settings()
    limiter.check(f"default:{_client_key(request, user)}", s.rate_limit_default_per_minute)


def rate_limit_ai(request: Request, user: OptionalUser) -> None:
    """Tighter budget for endpoints that run the optimiser, RAG or an LLM."""
    s = get_settings()
    limiter.check(f"ai:{_client_key(request, user)}", s.rate_limit_ai_per_minute)


RateLimited = Annotated[None, Depends(rate_limit_default)]
AiRateLimited = Annotated[None, Depends(rate_limit_ai)]


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def write_audit(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    trip_id: uuid.UUID | None = None,
    actor: User | None = None,
    detail: dict | None = None,
) -> None:
    """Append-only record for sensitive trip and privacy actions."""
    session.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            actor_label=actor.display_name if actor else "system",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            trip_id=trip_id,
            request_id=request_id_ctx.get(),
            detail=detail or {},
        )
    )
