"""Trips: creation, membership, preferences, itinerary generation and modification."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from yatraai.api.v1 import serializers
from yatraai.api.v1.deps import (
    AiRateLimited,
    CurrentUser,
    DbSession,
    RateLimited,
    load_trip,
    require_trip_member,
    require_trip_owner,
    write_audit,
)
from yatraai.core.errors import NotFoundError, ValidationFailure
from yatraai.schemas.common import Ack
from yatraai.schemas.trip import (
    GenerateItineraryRequest,
    ItineraryOut,
    JoinTripRequest,
    ModifyItineraryRequest,
    ModifyItineraryResponse,
    PreferenceInput,
    RecommendationOut,
    TripCreate,
    TripOut,
    TripUpdate,
)
from yatraai.services import trips as trip_service

router = APIRouter(prefix="/trips", tags=["trips"])


# --------------------------------------------------------------------------- #
# Trips
# --------------------------------------------------------------------------- #
@router.post(
    "", response_model=TripOut, status_code=status.HTTP_201_CREATED, summary="Create a trip"
)
def create_trip(
    payload: TripCreate, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> TripOut:
    trip = trip_service.create_trip(session, user, payload)
    write_audit(
        session,
        action="trip.create",
        entity_type="trip",
        entity_id=str(trip.id),
        trip_id=trip.id,
        actor=user,
        detail={"cluster": payload.cluster_slug, "days": trip.duration_days},
    )
    session.commit()
    return serializers.trip_out(trip_service.load_trip_with_members(session, trip.id))


@router.get("", response_model=list[TripOut], summary="List trips you belong to")
def list_trips(session: DbSession, user: CurrentUser, _rl: RateLimited) -> list[TripOut]:
    rows = trip_service.list_trips_for_user(session, user)
    return [
        serializers.trip_out(
            t, has_itinerary=trip_service.active_itinerary(session, t.id) is not None
        )
        for t in rows
    ]


@router.get("/{trip_id}", response_model=TripOut, summary="Trip detail")
def get_trip(
    trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> TripOut:
    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)
    trip = trip_service.load_trip_with_members(session, trip_id)
    return serializers.trip_out(
        trip, has_itinerary=trip_service.active_itinerary(session, trip_id) is not None
    )


@router.patch("/{trip_id}", response_model=TripOut, summary="Update trip settings")
def update_trip(
    trip_id: uuid.UUID,
    payload: TripUpdate,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
) -> TripOut:
    trip = load_trip(session, trip_id)
    require_trip_owner(session, trip, user)

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(trip, field, value)
    if trip.end_date < trip.start_date:
        raise ValidationFailure("end_date must not be before start_date")
    if trip.day_end_min <= trip.day_start_min:
        raise ValidationFailure("day_end_min must be after day_start_min")

    write_audit(
        session,
        action="trip.update",
        entity_type="trip",
        entity_id=str(trip.id),
        trip_id=trip.id,
        actor=user,
        detail={"fields": sorted(changes)},
    )
    session.commit()
    return serializers.trip_out(trip_service.load_trip_with_members(session, trip_id))


@router.post("/join", response_model=TripOut, summary="Join a trip with an invite code")
def join_trip(
    payload: JoinTripRequest, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> TripOut:
    trip = trip_service.join_trip(session, user, payload.invite_code, payload.display_name)
    write_audit(
        session,
        action="trip.join",
        entity_type="trip",
        entity_id=str(trip.id),
        trip_id=trip.id,
        actor=user,
    )
    session.commit()
    return serializers.trip_out(trip_service.load_trip_with_members(session, trip.id))


@router.post("/{trip_id}/invite/rotate", response_model=TripOut, summary="Rotate the invite code")
def rotate_invite(
    trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> TripOut:
    trip = load_trip(session, trip_id)
    require_trip_owner(session, trip, user)
    trip.invite_code = trip_service._unique_invite_code(session)
    write_audit(
        session,
        action="trip.invite_rotated",
        entity_type="trip",
        entity_id=str(trip.id),
        trip_id=trip.id,
        actor=user,
    )
    session.commit()
    return serializers.trip_out(trip_service.load_trip_with_members(session, trip_id))


# --------------------------------------------------------------------------- #
# Preferences
# --------------------------------------------------------------------------- #
@router.put(
    "/{trip_id}/preferences",
    response_model=TripOut,
    summary="Submit or update your own preferences for this trip",
)
def submit_preferences(
    trip_id: uuid.UUID,
    payload: PreferenceInput,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
) -> TripOut:
    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)
    if member.id is None:
        raise ValidationFailure("Join this trip before submitting preferences.")
    trip_service.upsert_preferences(session, trip, member, payload)
    write_audit(
        session,
        action="trip.preferences_submitted",
        entity_type="trip_member",
        entity_id=str(member.id),
        trip_id=trip.id,
        actor=user,
    )
    session.commit()
    return serializers.trip_out(trip_service.load_trip_with_members(session, trip_id))


@router.post(
    "/{trip_id}/opt-out",
    response_model=Ack,
    summary="Leave the group for planning purposes",
)
def opt_out(trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited) -> Ack:
    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)
    member.status = "opted_out"
    write_audit(
        session,
        action="trip.member_opted_out",
        entity_type="trip_member",
        entity_id=str(member.id),
        trip_id=trip.id,
        actor=user,
    )
    session.commit()
    return Ack(message="You have been removed from planning. Regenerate the itinerary to apply.")


# --------------------------------------------------------------------------- #
# Itineraries
# --------------------------------------------------------------------------- #
@router.post(
    "/{trip_id}/itinerary",
    response_model=ItineraryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a validated itinerary",
    description=(
        "Runs the full deterministic pipeline: eligibility filters, fairness-aware scoring, "
        "geographic clustering, travel-time matrix, CP-SAT optimisation and constraint "
        "validation. Returns 422 with the validation report if no feasible plan exists - "
        "an invalid itinerary is never returned."
    ),
)
def generate_itinerary(
    trip_id: uuid.UUID,
    payload: GenerateItineraryRequest,
    session: DbSession,
    user: CurrentUser,
    _rl: AiRateLimited,
) -> ItineraryOut:
    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)

    existing = trip_service.active_itinerary(session, trip_id)
    if existing is not None and not payload.force_regenerate:
        return serializers.itinerary_out(existing)

    itinerary, _ = trip_service.generate_itinerary(
        session,
        trip,
        generator=payload.generator,
        aggregation_method=payload.aggregation_method,
        explain_with_llm=payload.explain_with_llm,
        trigger="regenerate" if existing else "initial",
    )
    write_audit(
        session,
        action="itinerary.generated",
        entity_type="itinerary",
        entity_id=str(itinerary.id),
        trip_id=trip.id,
        actor=user,
        detail={"generator": payload.generator, "version": itinerary.version},
    )
    from yatraai.services.analytics import record_event

    record_event(
        session,
        "itinerary_generated",
        trip_id=trip.id,
        cluster_slug=trip.cluster.slug if trip.cluster else None,
        user_id=user.id,
        numeric_value=itinerary.activity_count,
        properties={
            "generator": payload.generator,
            "fairness": itinerary.fairness_score,
            "travel_km": itinerary.total_travel_km,
            "degraded": itinerary.degraded_services,
        },
    )
    session.commit()
    return serializers.itinerary_out(trip_service.get_itinerary(session, itinerary.id))


@router.get(
    "/{trip_id}/itinerary",
    response_model=ItineraryOut,
    summary="Current active itinerary",
)
def get_itinerary(
    trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> ItineraryOut:
    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)
    itinerary = trip_service.active_itinerary(session, trip_id)
    if itinerary is None:
        raise NotFoundError("No itinerary generated yet.", code="no_itinerary")
    return serializers.itinerary_out(itinerary)


@router.get(
    "/{trip_id}/itinerary/versions",
    response_model=list[ItineraryOut],
    summary="Itinerary history",
)
def list_itinerary_versions(
    trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> list[ItineraryOut]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from yatraai.db.models import Itinerary, ItineraryDay

    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)
    rows = session.scalars(
        select(Itinerary)
        .where(Itinerary.trip_id == trip_id)
        .order_by(Itinerary.version.desc())
        .options(selectinload(Itinerary.days).selectinload(ItineraryDay.activities))
        .limit(20)
    )
    return [serializers.itinerary_out(i) for i in rows]


@router.post(
    "/{trip_id}/itinerary/validate",
    summary="Re-validate the active itinerary without regenerating it",
)
def validate_itinerary(
    trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> dict:
    from yatraai.services.replan import revalidate

    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)
    itinerary = trip_service.active_itinerary(session, trip_id)
    if itinerary is None:
        raise NotFoundError("No itinerary generated yet.", code="no_itinerary")
    report = revalidate(session, trip, itinerary)
    itinerary.validation_report = report
    itinerary.is_valid = report["is_valid"]
    session.commit()
    return report


@router.post(
    "/{trip_id}/itinerary/modify",
    response_model=ModifyItineraryResponse,
    summary="Modify or replan the itinerary",
    description=(
        "Every modification is re-optimised and re-validated. On a multi-member trip the "
        "change becomes a proposal requiring group approval instead of being applied directly."
    ),
)
def modify_itinerary(
    trip_id: uuid.UUID,
    payload: ModifyItineraryRequest,
    session: DbSession,
    user: CurrentUser,
    _rl: AiRateLimited,
) -> ModifyItineraryResponse:
    from yatraai.services.replan import apply_modification

    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)
    itinerary = trip_service.active_itinerary(session, trip_id)
    if itinerary is None:
        raise NotFoundError("No itinerary generated yet.", code="no_itinerary")

    response = apply_modification(session, trip, itinerary, payload, actor=user, member=member)
    write_audit(
        session,
        action=f"itinerary.{payload.action}",
        entity_type="itinerary",
        entity_id=str(itinerary.id),
        trip_id=trip.id,
        actor=user,
        detail={"applied": response.applied, "action": payload.action},
    )
    session.commit()
    return response


@router.get(
    "/{trip_id}/recommendations",
    response_model=list[RecommendationOut],
    summary="Ranked attractions with explainable score breakdowns",
)
def list_recommendations(
    trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> list[RecommendationOut]:
    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)
    rows = trip_service.list_recommendations(session, trip_id)
    if not rows:
        raise NotFoundError(
            "No recommendations yet - generate an itinerary first.", code="no_recommendations"
        )

    from yatraai.services.catalog import list_attractions

    names = {a.slug: a.name for a in list_attractions(session, trip.cluster.slug)}
    return [
        RecommendationOut(
            attraction_slug=r.attraction_slug,
            name=names.get(r.attraction_slug, r.attraction_slug),
            rank=r.rank,
            total_score=r.total_score,
            selected=r.selected,
            components=dict(r.components or {}),
            per_member_scores=dict(r.per_member_scores or {}),
            eligibility=dict(r.eligibility or {}),
            explanation=r.explanation,
        )
        for r in rows
    ]
