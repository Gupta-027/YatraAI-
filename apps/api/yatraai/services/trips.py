"""Trip lifecycle: creation, membership, preferences, itinerary generation.

This is the seam between the HTTP layer and the pure planning stack. It converts
ORM rows into planner dataclasses, runs the deterministic pipeline, persists the
validated result, and converts it back for the API.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from yatraai.core.errors import ConflictError, NotFoundError, PlanningInfeasibleError
from yatraai.core.security import generate_invite_code, sanitize_text
from yatraai.db.models import (
    Attraction,
    DestinationCluster,
    Itinerary,
    ItineraryActivity,
    ItineraryDay,
    MemberPreference,
    RecommendationScore,
    Trip,
    TripMember,
    User,
)
from yatraai.logging_config import get_logger
from yatraai.services import catalog
from yatraai.services.planner import plan_trip
from yatraai.services.planner.models import (
    MemberProfile,
    PlanResult,
    TripContext,
)
from yatraai.services.recommend.taxonomy import default_preferences, normalise_preferences

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Creation & membership
# --------------------------------------------------------------------------- #
def _unique_invite_code(session: Session) -> str:
    for _ in range(20):
        code = generate_invite_code()
        if not session.scalar(select(Trip.id).where(Trip.invite_code == code)):
            return code
    raise ConflictError("Could not allocate an invite code; please retry.")


def create_trip(session: Session, owner: User, payload) -> Trip:
    cluster = catalog.get_cluster(session, payload.cluster_slug)
    known = {a.slug for a in catalog.list_attractions(session, cluster.slug)}

    must = [s for s in payload.must_visit_slugs if s in known]
    avoid = [s for s in payload.avoid_slugs if s in known]

    per_person = payload.budget_per_person_inr
    total = payload.budget_total_inr
    if payload.budget_basis == "total" and total:
        per_person = total / max(1, payload.traveller_count)
    elif per_person and not total:
        total = per_person * payload.traveller_count

    trip = Trip(
        owner_id=owner.id,
        cluster_id=cluster.id,
        title=sanitize_text(payload.title, max_length=160) or "Untitled trip",
        start_date=payload.start_date,
        end_date=payload.end_date,
        origin_label=sanitize_text(payload.origin_label, max_length=160),
        origin_lat=payload.origin_lat,
        origin_lon=payload.origin_lon,
        traveller_count=payload.traveller_count,
        budget_per_person_inr=per_person,
        budget_total_inr=total,
        budget_basis=payload.budget_basis,
        pace=payload.pace,
        transport_mode=payload.transport_mode,
        accommodation_tier=payload.accommodation_tier,
        day_start_min=payload.day_start_min,
        day_end_min=payload.day_end_min,
        has_children=payload.has_children,
        has_seniors=payload.has_seniors,
        accessibility_required=payload.accessibility_required,
        must_visit_slugs=must,
        avoid_slugs=avoid,
        status="collecting",
        invite_code=_unique_invite_code(session),
        notes=sanitize_text(payload.notes, max_length=2000),
    )
    session.add(trip)
    session.flush()

    member = TripMember(
        trip_id=trip.id,
        user_id=owner.id,
        display_name=owner.display_name,
        role="owner",
        status="joined",
        joined_at=datetime.now(UTC),
    )
    session.add(member)
    session.flush()

    prefs = payload.owner_preferences
    upsert_preferences(session, trip, member, prefs, known_slugs=known)
    return trip


def join_trip(session: Session, user: User, invite_code: str, display_name: str | None) -> Trip:
    trip = session.scalar(select(Trip).where(Trip.invite_code == invite_code.upper().strip()))
    if trip is None:
        raise NotFoundError("That invite code is not valid.", code="invalid_invite_code")
    if not trip.invite_enabled:
        raise ConflictError("Invites are closed for this trip.", code="invites_closed")

    existing = session.scalar(
        select(TripMember).where(TripMember.trip_id == trip.id, TripMember.user_id == user.id)
    )
    if existing is not None:
        if existing.status == "opted_out":
            existing.status = "joined"
            existing.joined_at = datetime.now(UTC)
            session.flush()
        return trip

    member = TripMember(
        trip_id=trip.id,
        user_id=user.id,
        display_name=sanitize_text(display_name or user.display_name, max_length=120),
        role="member",
        status="joined",
        joined_at=datetime.now(UTC),
    )
    session.add(member)
    session.flush()

    known = {a.slug for a in catalog.list_attractions(session, trip.cluster.slug)}
    upsert_preferences(session, trip, member, None, known_slugs=known)
    return trip


def upsert_preferences(
    session: Session,
    trip: Trip,
    member: TripMember,
    payload,
    *,
    known_slugs: set[str] | None = None,
) -> MemberPreference:
    known = known_slugs
    if known is None:
        known = {a.slug for a in catalog.list_attractions(session, trip.cluster.slug)}

    prefs = session.scalar(select(MemberPreference).where(MemberPreference.member_id == member.id))
    if prefs is None:
        prefs = MemberPreference(member_id=member.id, trip_id=trip.id)
        session.add(prefs)

    if payload is None:
        prefs.interests = prefs.interests or default_preferences()
        prefs.submitted = False
        session.flush()
        return prefs

    merged = default_preferences()
    merged.update({k: int(v) for k, v in (payload.interests or {}).items()})
    prefs.interests = merged
    prefs.ranked_choices = [s for s in payload.ranked_choices if s in known][:10]
    prefs.pace = payload.pace
    prefs.budget_sensitivity = payload.budget_sensitivity
    prefs.indoor_outdoor_pref = payload.indoor_outdoor_pref
    prefs.dietary = payload.dietary
    prefs.mobility_level = payload.mobility_level
    prefs.max_walk_minutes = payload.max_walk_minutes
    prefs.earliest_start_min = payload.earliest_start_min
    prefs.latest_end_min = payload.latest_end_min
    prefs.must_visit_slugs = [s for s in payload.must_visit_slugs if s in known][:10]
    prefs.avoid_slugs = [s for s in payload.avoid_slugs if s in known][:20]
    prefs.notes = sanitize_text(payload.notes, max_length=1000)
    prefs.submitted = True

    # A member declaring accessibility needs or age brackets updates the trip too.
    if payload.mobility_level == "wheelchair":
        trip.accessibility_required = True
    if payload.is_senior:
        trip.has_seniors = True
    if payload.is_child:
        trip.has_children = True

    session.flush()
    return prefs


def load_trip_with_members(session: Session, trip_id: uuid.UUID) -> Trip:
    trip = session.scalar(
        select(Trip)
        .where(Trip.id == trip_id)
        .options(
            selectinload(Trip.members).selectinload(TripMember.preferences),
            selectinload(Trip.members),
        )
    )
    if trip is None:
        raise NotFoundError("Trip not found", code="trip_not_found")
    return trip


def list_trips_for_user(session: Session, user: User) -> list[Trip]:
    trip_ids = select(TripMember.trip_id).where(
        TripMember.user_id == user.id, TripMember.status != "opted_out"
    )
    return list(
        session.scalars(
            select(Trip)
            .where(Trip.id.in_(trip_ids))
            .order_by(Trip.start_date.desc())
            .options(selectinload(Trip.members))
        )
    )


# --------------------------------------------------------------------------- #
# Planner input assembly
# --------------------------------------------------------------------------- #
def build_context(session: Session, trip: Trip) -> TripContext:
    cluster = session.get(DestinationCluster, trip.cluster_id)
    if cluster is None:
        raise NotFoundError("Destination cluster missing for this trip")

    base_lat = trip.origin_lat if trip.origin_lat is not None else cluster.center_lat
    base_lon = trip.origin_lon if trip.origin_lon is not None else cluster.center_lon

    return TripContext(
        trip_id=str(trip.id),
        cluster_slug=cluster.slug,
        start_date=trip.start_date,
        end_date=trip.end_date,
        traveller_count=trip.traveller_count,
        budget_per_person_inr=trip.budget_per_person_inr,
        pace=trip.pace,
        transport_mode=trip.transport_mode,
        accommodation_tier=trip.accommodation_tier,
        day_start_min=trip.day_start_min,
        day_end_min=trip.day_end_min,
        base_lat=float(base_lat),
        base_lon=float(base_lon),
        origin_label=trip.origin_label,
        has_children=trip.has_children,
        has_seniors=trip.has_seniors,
        accessibility_required=trip.accessibility_required,
        must_visit_slugs=list(trip.must_visit_slugs or []),
        avoid_slugs=list(trip.avoid_slugs or []),
    )


def build_member_profiles(session: Session, trip: Trip) -> list[MemberProfile]:
    members = list(
        session.scalars(
            select(TripMember)
            .where(TripMember.trip_id == trip.id, TripMember.status != "opted_out")
            .options(selectinload(TripMember.preferences))
            .order_by(TripMember.created_at)
        )
    )
    profiles: list[MemberProfile] = []
    for member in members:
        prefs = member.preferences
        profiles.append(
            MemberProfile(
                member_id=str(member.id),
                display_name=member.display_name,
                interests=normalise_preferences(prefs.interests if prefs else None),
                weight=float(member.weight),
                ranked_choices=list(prefs.ranked_choices) if prefs else [],
                pace=prefs.pace if prefs else trip.pace,
                budget_sensitivity=prefs.budget_sensitivity if prefs else 3,
                indoor_outdoor_pref=prefs.indoor_outdoor_pref if prefs else "mixed",
                mobility_level=prefs.mobility_level if prefs else "full",
                max_walk_minutes=prefs.max_walk_minutes if prefs else 30,
                earliest_start_min=prefs.earliest_start_min if prefs else trip.day_start_min,
                latest_end_min=prefs.latest_end_min if prefs else trip.day_end_min,
                must_visit_slugs=list(prefs.must_visit_slugs) if prefs else [],
                avoid_slugs=list(prefs.avoid_slugs) if prefs else [],
                is_senior=trip.has_seniors and (prefs.mobility_level != "full" if prefs else False),
                is_child=False,
            )
        )
    if not profiles:
        profiles.append(
            MemberProfile(
                member_id=str(trip.owner_id),
                display_name="Traveller",
                interests=normalise_preferences(None),
            )
        )
    return profiles


# --------------------------------------------------------------------------- #
# Generation & persistence
# --------------------------------------------------------------------------- #
def generate_itinerary(
    session: Session,
    trip: Trip,
    *,
    generator: str = "ortools",
    aggregation_method: str = "fairness_aware",
    explain_with_llm: bool = True,
    trigger: str = "initial",
    context_override: TripContext | None = None,
    candidate_filter: set[str] | None = None,
) -> tuple[Itinerary, PlanResult]:
    cluster = session.get(DestinationCluster, trip.cluster_id)
    ctx = context_override or build_context(session, trip)
    members = build_member_profiles(session, trip)
    candidates = catalog.load_candidates(session, ctx.cluster_slug)
    if candidate_filter is not None:
        candidates = [c for c in candidates if c.slug not in candidate_filter]

    result = plan_trip(
        ctx,
        members,
        candidates,
        generator=generator,
        aggregation_method=aggregation_method,
        session=session,
        cluster_baseline=(cluster.daily_cost_baseline if cluster else None),
    )

    if not result.validation.is_valid:
        raise PlanningInfeasibleError(
            "No itinerary satisfies these constraints.",
            detail=result.validation.to_dict(),
        )

    summary, llm_response = ("", None)
    if explain_with_llm:
        from yatraai.services.llm.explain import explain_itinerary

        summary, llm_response = explain_itinerary(result, ctx)
    else:
        from yatraai.services.llm.explain import build_template_summary

        summary = build_template_summary(result, ctx)

    itinerary = persist_itinerary(
        session,
        trip,
        result,
        ctx,
        generator=generator,
        trigger=trigger,
        summary=summary,
        llm_response=llm_response,
    )
    return itinerary, result


def persist_itinerary(
    session: Session,
    trip: Trip,
    result: PlanResult,
    ctx: TripContext,
    *,
    generator: str,
    trigger: str,
    summary: str,
    llm_response=None,
    status: str = "active",
    parent_id: uuid.UUID | None = None,
) -> Itinerary:
    next_version = (
        session.scalar(select(func.max(Itinerary.version)).where(Itinerary.trip_id == trip.id)) or 0
    ) + 1

    if status == "active":
        for previous in session.scalars(
            select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.status == "active")
        ):
            previous.status = "superseded"

    itinerary = Itinerary(
        trip_id=trip.id,
        version=next_version,
        parent_itinerary_id=parent_id,
        status=status,
        generator=generator,
        trigger=trigger,
        is_valid=result.validation.is_valid,
        validation_report=result.validation.to_dict(),
        total_travel_km=result.metrics.total_travel_km,
        total_travel_min=result.metrics.total_travel_min,
        total_visit_min=result.metrics.total_visit_min,
        activity_count=result.metrics.activity_count,
        fairness_score=result.metrics.fairness_score,
        least_satisfied_score=result.metrics.least_satisfied_score,
        consensus_score=result.metrics.consensus_score,
        utility_score=result.metrics.utility_score,
        preference_coverage={
            "by_interest": result.metrics.preference_coverage,
            "by_member": result.metrics.per_member_coverage,
        },
        cost_low_inr=result.cost.low_inr,
        cost_high_inr=result.cost.high_inr,
        cost_per_person_low_inr=result.cost.per_person_low_inr,
        cost_per_person_high_inr=result.cost.per_person_high_inr,
        cost_breakdown={
            "components": result.cost.breakdown,
            "assumptions": result.cost.assumptions,
        },
        summary_text=summary,
        explanation_source=(
            "llm" if llm_response is not None and not llm_response.is_fallback else "template"
        ),
        llm_provider=(llm_response.provider if llm_response is not None else None),
        degraded_services=result.degraded_services,
        solver_stats=result.solver_stats,
        input_fingerprint=result.solver_stats.get("fingerprint", ""),
    )
    session.add(itinerary)
    session.flush()

    attraction_ids = _attraction_id_map(session, ctx.cluster_slug)

    for day in result.days:
        day_row = ItineraryDay(
            itinerary_id=itinerary.id,
            day_index=day.day_index,
            calendar_date=day.calendar_date,
            start_min=day.start_min,
            end_min=day.end_min,
            base_lat=day.base_lat,
            base_lon=day.base_lon,
            travel_km=day.travel_km,
            travel_min=day.travel_min,
            weather=_weather_dict(day.weather),
            weather_advisories=day.weather_advisories,
            theme=day.theme,
            notes=day.notes,
        )
        session.add(day_row)
        session.flush()

        for activity in day.activities:
            session.add(
                ItineraryActivity(
                    day_id=day_row.id,
                    sequence=activity.sequence,
                    kind=activity.kind,
                    attraction_id=attraction_ids.get(activity.slug or ""),
                    attraction_slug=activity.slug,
                    title=activity.title,
                    start_min=activity.start_min,
                    end_min=activity.end_min,
                    opens_min=activity.opens_min,
                    closes_min=activity.closes_min,
                    travel_from_prev_min=activity.travel_from_prev_min,
                    travel_from_prev_km=activity.travel_from_prev_km,
                    travel_mode=activity.travel_mode,
                    lat=activity.lat,
                    lon=activity.lon,
                    est_cost_low_inr=activity.est_cost_low_inr,
                    est_cost_high_inr=activity.est_cost_high_inr,
                    weather_suitability=activity.weather_suitability,
                    warnings=activity.warnings,
                    why_selected=activity.why_selected,
                    score_breakdown=activity.score_breakdown,
                    is_mandatory=activity.is_mandatory,
                    locked=activity.locked,
                )
            )

    _persist_scores(session, trip, itinerary, result, attraction_ids)

    if status == "active":
        trip.status = "planned"
    session.flush()
    return itinerary


def _persist_scores(
    session: Session,
    trip: Trip,
    itinerary: Itinerary,
    result: PlanResult,
    attraction_ids: dict[str, uuid.UUID],
) -> None:
    session.query(RecommendationScore).filter_by(trip_id=trip.id, itinerary_id=None).delete(
        synchronize_session=False
    )
    selected = set(result.selected_slugs)
    for scored in result.scored[:60]:
        attraction_id = attraction_ids.get(scored.slug)
        if attraction_id is None:
            continue
        session.add(
            RecommendationScore(
                trip_id=trip.id,
                itinerary_id=itinerary.id,
                attraction_id=attraction_id,
                attraction_slug=scored.slug,
                method="fairness_aware",
                total_score=scored.total_score,
                rank=scored.rank,
                selected=scored.slug in selected,
                components=scored.breakdown.to_dict(),
                per_member_scores=scored.per_member_utility,
                eligibility=scored.eligibility,
                explanation=scored.explanation,
            )
        )


def _attraction_id_map(session: Session, cluster_slug: str) -> dict[str, uuid.UUID]:
    rows = session.execute(
        select(Attraction.slug, Attraction.id)
        .join(DestinationCluster)
        .where(DestinationCluster.slug == cluster_slug)
    ).all()
    return dict(rows)


def _weather_dict(weather) -> dict:
    if weather is None:
        return {}
    return {
        "date": weather.calendar_date.isoformat(),
        "condition": weather.condition,
        "temp_min_c": weather.temp_min_c,
        "temp_max_c": weather.temp_max_c,
        "precipitation_mm": weather.precipitation_mm,
        "precipitation_probability": weather.precipitation_probability,
        "wind_kph": weather.wind_kph,
        "visibility_km": weather.visibility_km,
        "is_fallback": weather.is_fallback,
        "provider": weather.provider,
    }


def active_itinerary(session: Session, trip_id: uuid.UUID) -> Itinerary | None:
    return session.scalar(
        select(Itinerary)
        .where(Itinerary.trip_id == trip_id, Itinerary.status == "active")
        .order_by(Itinerary.version.desc())
        .options(selectinload(Itinerary.days).selectinload(ItineraryDay.activities))
        .limit(1)
    )


def get_itinerary(session: Session, itinerary_id: uuid.UUID) -> Itinerary:
    itinerary = session.scalar(
        select(Itinerary)
        .where(Itinerary.id == itinerary_id)
        .options(selectinload(Itinerary.days).selectinload(ItineraryDay.activities))
    )
    if itinerary is None:
        raise NotFoundError("Itinerary not found", code="itinerary_not_found")
    return itinerary


def list_recommendations(
    session: Session, trip_id: uuid.UUID, limit: int = 40
) -> Sequence[RecommendationScore]:
    return list(
        session.scalars(
            select(RecommendationScore)
            .where(RecommendationScore.trip_id == trip_id)
            .order_by(RecommendationScore.rank)
            .limit(limit)
        )
    )
