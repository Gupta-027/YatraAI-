"""Consent-based live location sharing.

Design principles, enforced in code rather than documented and hoped for:

* **Opt-in only.** A session cannot exist without an explicit
  ``consent_granted_at`` and a stated consent-text version.
* **Always expiring.** Every session carries an ``expires_at``; every point
  carries its own ``expires_at``. Nothing is kept indefinitely.
* **Minimal retention.** ``purge_expired_location_data`` hard-deletes points past
  the retention window. There is no archive table and no soft delete.
* **Approximate by default.** ``precision="approximate"`` snaps coordinates to a
  ~500 m grid *before storage*, so exact positions are never written at all.
* **Trip-scoped.** Location is visible only to members of the same trip, and only
  while that trip is within its date window.
* **No background tracking.** The server never requests a position; the client
  posts one, and only while a session is ``active``.
* **Never in analytics.** Coordinates are stripped from analytics writes.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from yatraai.config import get_settings
from yatraai.core.errors import ConsentRequiredError, NotFoundError, ValidationFailure
from yatraai.db.models import (
    Itinerary,
    ItineraryActivity,
    ItineraryDay,
    LocationPoint,
    LocationSharingSession,
    SosAlert,
    Trip,
    TripMember,
)
from yatraai.logging_config import get_logger
from yatraai.services.routing.distance import estimate_leg, haversine_km

log = get_logger(__name__)

CONSENT_TEXT_VERSION = "v1"
CONSENT_TEXT = (
    "I agree to share my location with members of this trip. I understand that sharing "
    "stops automatically when the session expires, that I can pause or stop it at any "
    "time, and that recent points are deleted after the retention window."
)

# Approximate mode snaps to ~500 m. 0.005 degrees of latitude is ~555 m.
APPROXIMATE_GRID_DEGREES = 0.005
SEPARATION_WARNING_KM = 1.5


def _snap(value: float, grid: float = APPROXIMATE_GRID_DEGREES) -> float:
    return round(round(value / grid) * grid, 5)


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
def start_sharing(
    session: Session,
    trip: Trip,
    member: TripMember,
    *,
    consent_granted: bool,
    precision: str = "approximate",
    update_interval_seconds: int = 60,
    duration_hours: int = 4,
) -> LocationSharingSession:
    if not consent_granted:
        raise ConsentRequiredError(
            "Location sharing requires explicit consent.", detail={"consent_text": CONSENT_TEXT}
        )
    if precision not in ("exact", "approximate"):
        raise ValidationFailure("precision must be 'exact' or 'approximate'")
    if update_interval_seconds < 15:
        raise ValidationFailure("update_interval_seconds must be at least 15")

    s = get_settings()
    max_hours = s.location_session_max_hours
    hours = max(1, min(duration_hours, max_hours))

    # Reuse an existing live session rather than accumulating sessions.
    existing = session.scalar(
        select(LocationSharingSession).where(
            LocationSharingSession.trip_id == trip.id,
            LocationSharingSession.member_id == member.id,
            LocationSharingSession.status.in_(("active", "paused")),
        )
    )
    now = _now()
    if existing is not None:
        existing.status = "active"
        existing.precision = precision
        existing.update_interval_seconds = update_interval_seconds
        existing.consent_granted_at = now
        existing.consent_text_version = CONSENT_TEXT_VERSION
        existing.expires_at = now + timedelta(hours=hours)
        existing.stopped_at = None
        session.flush()
        return existing

    row = LocationSharingSession(
        trip_id=trip.id,
        member_id=member.id,
        status="active",
        precision=precision,
        update_interval_seconds=update_interval_seconds,
        consent_granted_at=now,
        consent_text_version=CONSENT_TEXT_VERSION,
        expires_at=now + timedelta(hours=hours),
    )
    session.add(row)
    session.flush()
    log.info(
        "location.sharing_started",
        trip_id=str(trip.id),
        precision=precision,
        expires_in_hours=hours,
    )
    return row


def set_sharing_status(
    session: Session, trip: Trip, member: TripMember, status: str
) -> LocationSharingSession:
    if status not in ("active", "paused", "stopped"):
        raise ValidationFailure("status must be 'active', 'paused' or 'stopped'")
    row = session.scalar(
        select(LocationSharingSession)
        .where(
            LocationSharingSession.trip_id == trip.id,
            LocationSharingSession.member_id == member.id,
        )
        .order_by(LocationSharingSession.created_at.desc())
    )
    if row is None:
        raise NotFoundError("No location sharing session found", code="no_sharing_session")

    row.status = status
    if status == "stopped":
        row.stopped_at = _now()
        # Stopping deletes the trail immediately - it does not merely hide it.
        deleted = session.execute(
            delete(LocationPoint).where(LocationPoint.session_id == row.id)
        ).rowcount
        log.info("location.sharing_stopped", trip_id=str(trip.id), points_deleted=deleted)
    session.flush()
    return row


def record_point(
    session: Session,
    trip: Trip,
    member: TripMember,
    lat: float,
    lon: float,
    accuracy_m: float | None = None,
) -> LocationPoint:
    row = session.scalar(
        select(LocationSharingSession).where(
            LocationSharingSession.trip_id == trip.id,
            LocationSharingSession.member_id == member.id,
            LocationSharingSession.status == "active",
        )
    )
    if row is None:
        raise ConsentRequiredError(
            "Start location sharing before posting a position.", code="sharing_not_active"
        )
    if row.expires_at <= _now():
        row.status = "expired"
        session.flush()
        raise ConsentRequiredError(
            "Your location sharing session has expired. Start a new one to continue.",
            code="sharing_expired",
        )
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValidationFailure("coordinates out of range")

    approximate = row.precision == "approximate"
    # Snap BEFORE storage - an approximate session never writes an exact position.
    stored_lat = _snap(lat) if approximate else round(lat, 6)
    stored_lon = _snap(lon) if approximate else round(lon, 6)

    s = get_settings()
    now = _now()
    point = LocationPoint(
        session_id=row.id,
        trip_id=trip.id,
        member_id=member.id,
        lat=stored_lat,
        lon=stored_lon,
        accuracy_m=accuracy_m,
        is_approximate=approximate,
        recorded_at=now,
        expires_at=now + timedelta(minutes=s.location_point_retention_minutes),
    )
    session.add(point)
    row.last_point_at = now
    session.flush()
    return point


def latest_positions(session: Session, trip: Trip) -> list[dict]:
    """Most recent non-expired point per active member."""
    now = _now()
    rows = session.execute(
        select(LocationPoint, LocationSharingSession, TripMember)
        .join(LocationSharingSession, LocationPoint.session_id == LocationSharingSession.id)
        .join(TripMember, LocationPoint.member_id == TripMember.id)
        .where(
            LocationPoint.trip_id == trip.id,
            LocationPoint.expires_at > now,
            LocationSharingSession.status == "active",
            LocationSharingSession.expires_at > now,
        )
        .order_by(LocationPoint.recorded_at.desc())
    ).all()

    seen: set[uuid.UUID] = set()
    out: list[dict] = []
    for point, sharing, member in rows:
        if point.member_id in seen:
            continue
        seen.add(point.member_id)
        out.append(
            {
                "member_id": str(member.id),
                "display_name": member.display_name,
                "lat": point.lat,
                "lon": point.lon,
                "is_approximate": point.is_approximate,
                "accuracy_m": point.accuracy_m,
                "recorded_at": point.recorded_at.isoformat(),
                "expires_at": point.expires_at.isoformat(),
                "precision": sharing.precision,
            }
        )
    return out


def group_status(session: Session, trip: Trip) -> dict:
    """Group map payload: positions, separation, meeting point, ETA to next stop."""
    positions = latest_positions(session, trip)
    result: dict = {
        "positions": positions,
        "sharing_members": len(positions),
        "separation_warning": False,
        "max_separation_km": 0.0,
        "centroid": None,
        "suggested_meeting_point": None,
        "next_activity": None,
        "consent_text": CONSENT_TEXT,
        "consent_text_version": CONSENT_TEXT_VERSION,
    }
    if not positions:
        return result

    centroid_lat = sum(p["lat"] for p in positions) / len(positions)
    centroid_lon = sum(p["lon"] for p in positions) / len(positions)
    result["centroid"] = {"lat": round(centroid_lat, 5), "lon": round(centroid_lon, 5)}

    distances = [haversine_km(centroid_lat, centroid_lon, p["lat"], p["lon"]) for p in positions]
    max_separation = max(distances) if distances else 0.0
    result["max_separation_km"] = round(max_separation, 3)
    result["separation_warning"] = max_separation > SEPARATION_WARNING_KM
    result["per_member_distance_km"] = {
        p["member_id"]: round(d, 3) for p, d in zip(positions, distances, strict=True)
    }

    # ---- meeting point: the upcoming activity if there is one, else the centroid ----
    upcoming = _next_activity(session, trip)
    if upcoming is not None:
        result["next_activity"] = upcoming
        if upcoming.get("lat") is not None:
            result["suggested_meeting_point"] = {
                "lat": upcoming["lat"],
                "lon": upcoming["lon"],
                "label": upcoming["title"],
                "reason": "Your next scheduled stop - the natural place to regroup.",
            }
            result["eta_to_next"] = [
                {
                    "member_id": p["member_id"],
                    "display_name": p["display_name"],
                    "distance_km": round(
                        estimate_leg(p["lat"], p["lon"], upcoming["lat"], upcoming["lon"])[0], 2
                    ),
                    "eta_minutes": round(
                        estimate_leg(p["lat"], p["lon"], upcoming["lat"], upcoming["lon"])[1]
                    ),
                }
                for p in positions
            ]
    if result["suggested_meeting_point"] is None:
        result["suggested_meeting_point"] = {
            "lat": round(centroid_lat, 5),
            "lon": round(centroid_lon, 5),
            "label": "Group midpoint",
            "reason": "No upcoming stop is scheduled, so the group's midpoint is suggested.",
        }
    return result


def _next_activity(session: Session, trip: Trip) -> dict | None:
    itinerary = session.scalar(
        select(Itinerary)
        .where(Itinerary.trip_id == trip.id, Itinerary.status == "active")
        .order_by(Itinerary.version.desc())
        .limit(1)
    )
    if itinerary is None:
        return None

    today = date.today()
    now_min = _now().hour * 60 + _now().minute
    rows = session.execute(
        select(ItineraryActivity, ItineraryDay)
        .join(ItineraryDay, ItineraryActivity.day_id == ItineraryDay.id)
        .where(ItineraryDay.itinerary_id == itinerary.id, ItineraryActivity.kind == "visit")
        .order_by(ItineraryDay.calendar_date, ItineraryActivity.start_min)
    ).all()

    for activity, day in rows:
        if day.calendar_date > today or (
            day.calendar_date == today and activity.end_min >= now_min
        ):
            return {
                "title": activity.title,
                "slug": activity.attraction_slug,
                "lat": activity.lat,
                "lon": activity.lon,
                "date": day.calendar_date.isoformat(),
                "start_min": activity.start_min,
            }
    return None


def raise_sos(session: Session, trip: Trip, member: TripMember, message: str = "") -> SosAlert:
    """DEMO ONLY. Notifies group members in-app; contacts nobody else."""
    positions = {p["member_id"]: p for p in latest_positions(session, trip)}
    mine = positions.get(str(member.id))
    alert = SosAlert(
        trip_id=trip.id,
        member_id=member.id,
        message=(message or "")[:500],
        approx_lat=_snap(mine["lat"]) if mine else None,
        approx_lon=_snap(mine["lon"]) if mine else None,
        status="open",
        is_demo=True,
        meta={
            "disclaimer": (
                "DEMO ONLY. This raises an in-app notification to trip members. "
                "It does not contact emergency services, and must never be relied on "
                "in a real emergency."
            )
        },
    )
    session.add(alert)
    session.flush()
    log.warning("location.sos_demo_raised", trip_id=str(trip.id), alert_id=str(alert.id))
    return alert


def purge_expired_location_data(session: Session) -> dict:
    """Hard-delete expired points and expire stale sessions. Idempotent."""
    now = _now()
    points_deleted = session.execute(
        delete(LocationPoint).where(LocationPoint.expires_at <= now)
    ).rowcount

    expired_sessions = 0
    for row in session.scalars(
        select(LocationSharingSession).where(
            LocationSharingSession.expires_at <= now,
            LocationSharingSession.status.in_(("active", "paused")),
        )
    ):
        row.status = "expired"
        expired_sessions += 1

    # Orphan safety net: no point may outlive its session.
    orphans = session.execute(
        delete(LocationPoint).where(
            LocationPoint.session_id.notin_(select(LocationSharingSession.id))
        )
    ).rowcount

    session.flush()
    remaining = session.scalar(select(func.count()).select_from(LocationPoint)) or 0
    log.info(
        "location.purged",
        points_deleted=points_deleted,
        orphans_deleted=orphans,
        sessions_expired=expired_sessions,
        points_remaining=remaining,
    )
    return {
        "points_deleted": int(points_deleted or 0),
        "orphan_points_deleted": int(orphans or 0),
        "sessions_expired": expired_sessions,
        "points_remaining": int(remaining),
    }


def approximate(lat: float, lon: float) -> tuple[float, float]:
    """Public helper so tests and the frontend share one definition."""
    return _snap(lat), _snap(lon)


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    return round(haversine_km(a[0], a[1], b[0], b[1]), 3)


def bearing_degrees(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Initial bearing from a to b, for the 'which way is the group' arrow."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return round((math.degrees(math.atan2(y, x)) + 360) % 360, 1)
