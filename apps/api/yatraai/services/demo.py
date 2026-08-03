"""Demo account and sample trip so a reviewer can explore without registering.

Everything created here is flagged ``is_demo``. It is synthetic, and the UI and
analytics label it as such - it is never presented as real user activity.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from yatraai.core.security import generate_invite_code, hash_password
from yatraai.db.models import (
    Itinerary,
    MemberPreference,
    Trip,
    TripMember,
    User,
)
from yatraai.logging_config import get_logger
from yatraai.services import trips as trip_service
from yatraai.services.recommend.taxonomy import default_preferences

log = get_logger(__name__)

DEMO_EMAIL = "demo@yatraai.example"
DEMO_PASSWORD = "yatraai-demo-2026"

DEMO_MEMBERS = [
    (
        "demo.asha@yatraai.example",
        "Asha (demo)",
        {"heritage": 5, "museums": 4, "photography": 4, "nature": 2, "adventure": 1},
    ),
    (
        "demo.ben@yatraai.example",
        "Ben (demo)",
        {"nature": 5, "relaxation": 5, "food": 4, "heritage": 2, "museums": 1},
    ),
    (
        "demo.chitra@yatraai.example",
        "Chitra (demo)",
        {"spiritual": 5, "heritage": 3, "food": 4, "adventure": 1, "nature": 3},
    ),
]


def _get_or_create_user(session: Session, email: str, name: str, *, is_owner: bool) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is not None:
        return user
    user = User(
        email=email,
        display_name=name,
        password_hash=hash_password(DEMO_PASSWORD),
        is_demo=True,
        home_city="Bengaluru" if is_owner else None,
        default_preferences=default_preferences(),
        last_login_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    return user


def ensure_demo_data(session: Session, *, reset: bool = False) -> dict:
    owner = _get_or_create_user(session, DEMO_EMAIL, "Demo Traveller", is_owner=True)

    existing = session.scalar(
        select(Trip).where(Trip.owner_id == owner.id).order_by(Trip.created_at.desc()).limit(1)
    )
    if existing is not None and not reset:
        return {
            "user_id": owner.id,
            "email": owner.email,
            "password": DEMO_PASSWORD,
            "trip_id": existing.id,
            "invite_code": existing.invite_code,
            "created": False,
        }

    if existing is not None and reset:
        for trip in session.scalars(select(Trip).where(Trip.owner_id == owner.id)):
            session.delete(trip)
        session.flush()

    from yatraai.services.catalog import get_cluster

    cluster = get_cluster(session, "bengaluru")
    start = date.today() + timedelta(days=21)
    trip = Trip(
        owner_id=owner.id,
        cluster_id=cluster.id,
        title="Bengaluru long weekend (demo)",
        start_date=start,
        end_date=start + timedelta(days=2),
        origin_label="Bengaluru city centre",
        origin_lat=cluster.center_lat,
        origin_lon=cluster.center_lon,
        traveller_count=3,
        budget_per_person_inr=12000,
        budget_total_inr=36000,
        pace="balanced",
        transport_mode="car",
        accommodation_tier="midrange",
        day_start_min=9 * 60,
        day_end_min=19 * 60,
        status="collecting",
        invite_code=generate_invite_code(),
        notes="Sample group trip created by `yatraai demo`. All members are synthetic.",
    )
    session.add(trip)
    session.flush()

    for index, (email, name, interests) in enumerate(DEMO_MEMBERS):
        user = _get_or_create_user(session, email, name, is_owner=False)
        member = TripMember(
            trip_id=trip.id,
            user_id=user.id if index else owner.id,
            display_name=name if index else "Demo Traveller",
            role="owner" if index == 0 else "member",
            status="joined",
            joined_at=datetime.now(UTC),
        )
        session.add(member)
        session.flush()

        profile = default_preferences()
        profile.update(interests)
        session.add(
            MemberPreference(
                member_id=member.id,
                trip_id=trip.id,
                interests=profile,
                pace="balanced",
                budget_sensitivity=3,
                mobility_level="full",
                earliest_start_min=9 * 60,
                latest_end_min=19 * 60,
                submitted=True,
                notes="Synthetic demo preference profile.",
            )
        )
    session.flush()

    itinerary_id = None
    try:
        itinerary, _ = trip_service.generate_itinerary(
            session, trip, trigger="demo_seed", explain_with_llm=False
        )
        itinerary_id = itinerary.id
    except Exception as exc:  # pragma: no cover - demo generation is best-effort
        log.warning("demo.itinerary_failed", error=str(exc))

    log.info("demo.created", trip_id=str(trip.id), invite_code=trip.invite_code)
    return {
        "user_id": owner.id,
        "email": owner.email,
        "password": DEMO_PASSWORD,
        "trip_id": trip.id,
        "invite_code": trip.invite_code,
        "itinerary_id": itinerary_id,
        "members": len(DEMO_MEMBERS),
        "created": True,
    }


def demo_itinerary(session: Session) -> Itinerary | None:
    owner = session.scalar(select(User).where(User.email == DEMO_EMAIL))
    if owner is None:
        return None
    trip = session.scalar(
        select(Trip).where(Trip.owner_id == owner.id).order_by(Trip.created_at.desc()).limit(1)
    )
    return trip_service.active_itinerary(session, trip.id) if trip else None
