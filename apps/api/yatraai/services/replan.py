"""Itinerary modification and dynamic replanning.

Every user-facing "change this" button routes through here. The rule that makes
this safe: a modification is expressed as a **change to the planner's inputs**,
then the whole deterministic pipeline runs again and the result is re-validated.
Nothing edits the schedule in place, so a modification cannot produce a state the
optimiser would never have generated.

Supported triggers map onto the brief's replanning scenarios:

| Action | Input change |
|---|---|
| `remove_activity` | add the slug to `avoid_slugs` |
| `replace_activity` | avoid the old slug, force the new one |
| `regenerate_day` | exclude that day's current picks and re-solve |
| `make_day_relaxed` | pace -> relaxed |
| `reduce_cost` | shrink `budget_per_person_inr` |
| `reduce_travel` | pace -> relaxed and tighten the travel cap |
| `add_theme` | boost one interest across every member profile |
| `shift_start_time` | move `day_start_min` (the "we started late" case) |
| `weather_replan` | refetch the forecast and re-score |
| `member_opted_out` | drop that member from aggregation |
| `attraction_unavailable` | hard-exclude the slug |

On a trip with more than one active member, a change is stored as a
``ChangeProposal`` for group approval instead of being applied.
"""

from __future__ import annotations

import uuid
from dataclasses import replace as dataclass_replace
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from yatraai.core.errors import NotFoundError, PlanningInfeasibleError, ValidationFailure
from yatraai.db.models import ChangeProposal, Itinerary, Trip, TripMember, User
from yatraai.logging_config import get_logger
from yatraai.schemas.trip import (
    ItineraryDiff,
    ModifyItineraryRequest,
    ModifyItineraryResponse,
    ValidationOut,
)
from yatraai.services import catalog
from yatraai.services import trips as trip_service
from yatraai.services.planner.models import PACE_PROFILE, TripContext
from yatraai.services.planner.validator import validate_plan

log = get_logger(__name__)

THEME_INTERESTS = {
    "historical": "heritage",
    "heritage": "heritage",
    "spiritual": "spiritual",
    "nature": "nature",
    "food": "food",
    "adventure": "adventure",
    "museums": "museums",
    "relaxed": "relaxation",
}


# --------------------------------------------------------------------------- #
def _active_member_count(session: Session, trip: Trip) -> int:
    return len(
        list(
            session.scalars(
                select(TripMember).where(
                    TripMember.trip_id == trip.id, TripMember.status == "joined"
                )
            )
        )
    )


def _itinerary_slugs(itinerary: Itinerary) -> list[str]:
    return [
        a.attraction_slug
        for day in itinerary.days
        for a in day.activities
        if a.kind == "visit" and a.attraction_slug
    ]


def _day_slugs(itinerary: Itinerary, day_index: int) -> list[str]:
    for day in itinerary.days:
        if day.day_index == day_index:
            return [
                a.attraction_slug for a in day.activities if a.kind == "visit" and a.attraction_slug
            ]
    return []


def _build_diff(before: Itinerary, after: Itinerary) -> ItineraryDiff:
    before_slugs = _itinerary_slugs(before)
    after_slugs = _itinerary_slugs(after)
    added = [s for s in after_slugs if s not in before_slugs]
    removed = [s for s in before_slugs if s not in after_slugs]

    before_day = {
        a.attraction_slug: day.day_index
        for day in before.days
        for a in day.activities
        if a.attraction_slug
    }
    after_day = {
        a.attraction_slug: day.day_index
        for day in after.days
        for a in day.activities
        if a.attraction_slug
    }
    moved = [
        {"slug": slug, "from_day": before_day[slug], "to_day": after_day[slug]}
        for slug in set(before_day) & set(after_day)
        if before_day[slug] != after_day[slug]
    ]

    parts: list[str] = []
    if added:
        parts.append(f"added {len(added)}")
    if removed:
        parts.append(f"removed {len(removed)}")
    if moved:
        parts.append(f"moved {len(moved)}")
    km_delta = round(after.total_travel_km - before.total_travel_km, 2)
    if abs(km_delta) >= 0.5:
        parts.append(f"{km_delta:+.0f} km travel")
    cost_delta = round(after.cost_per_person_high_inr - before.cost_per_person_high_inr, 0)
    if abs(cost_delta) >= 50:
        parts.append(f"Rs.{cost_delta:+,.0f} per person")

    return ItineraryDiff(
        added=added,
        removed=removed,
        moved=moved,
        travel_km_delta=km_delta,
        travel_min_delta=after.total_travel_min - before.total_travel_min,
        cost_per_person_delta_low=round(
            after.cost_per_person_low_inr - before.cost_per_person_low_inr, 2
        ),
        cost_per_person_delta_high=cost_delta,
        fairness_delta=round(after.fairness_score - before.fairness_score, 4),
        summary="; ".join(parts) if parts else "no material change",
    )


def _validation_out(itinerary: Itinerary) -> ValidationOut:
    report = itinerary.validation_report or {}
    return ValidationOut(
        is_valid=report.get("is_valid", itinerary.is_valid),
        checks_run=report.get("checks_run", 0),
        errors=report.get("errors", []),
        warnings=report.get("warnings", []),
    )


# --------------------------------------------------------------------------- #
def _prepare_inputs(
    session: Session,
    trip: Trip,
    itinerary: Itinerary,
    payload: ModifyItineraryRequest,
) -> tuple[TripContext, set[str], dict]:
    """Translate a modification action into planner input changes."""
    ctx = trip_service.build_context(session, trip)
    excluded: set[str] = set(trip.avoid_slugs or [])
    meta: dict = {"action": payload.action}
    known = {a.slug for a in catalog.list_attractions(session, ctx.cluster_slug)}

    action = payload.action

    if action in ("remove_activity", "attraction_unavailable"):
        if not payload.attraction_slug:
            raise ValidationFailure("attraction_slug is required for this action")
        if payload.attraction_slug not in known:
            raise NotFoundError("Unknown attraction", code="attraction_not_found")
        excluded.add(payload.attraction_slug)
        ctx.must_visit_slugs = [s for s in ctx.must_visit_slugs if s != payload.attraction_slug]
        meta["removed"] = payload.attraction_slug

    elif action == "replace_activity":
        if not payload.attraction_slug:
            raise ValidationFailure("attraction_slug is required for this action")
        excluded.add(payload.attraction_slug)
        ctx.must_visit_slugs = [s for s in ctx.must_visit_slugs if s != payload.attraction_slug]
        if payload.replacement_slug:
            if payload.replacement_slug not in known:
                raise NotFoundError("Unknown replacement attraction", code="attraction_not_found")
            ctx.must_visit_slugs = [*ctx.must_visit_slugs, payload.replacement_slug]
            meta["replacement"] = payload.replacement_slug
        meta["removed"] = payload.attraction_slug

    elif action == "regenerate_day":
        if payload.day_index is None:
            raise ValidationFailure("day_index is required for this action")
        current = _day_slugs(itinerary, payload.day_index)
        excluded.update(current)
        meta["regenerated_day"] = payload.day_index
        meta["excluded"] = current

    elif action == "make_day_relaxed":
        ctx.pace = "relaxed"
        meta["pace"] = "relaxed"

    elif action == "reduce_cost":
        pct = payload.budget_reduction_pct or 20.0
        if ctx.budget_per_person_inr:
            ctx.budget_per_person_inr = ctx.budget_per_person_inr * (1 - pct / 100.0)
        else:
            # No budget stated: anchor on the current estimate.
            ctx.budget_per_person_inr = itinerary.cost_per_person_high_inr * (1 - pct / 100.0)
        meta["budget_per_person_inr"] = round(ctx.budget_per_person_inr, 2)

    elif action == "reduce_travel":
        ctx.pace = "relaxed"
        meta["pace"] = "relaxed"
        meta["note"] = "pace relaxed, which tightens the daily travel cap"

    elif action == "add_theme":
        theme = (payload.theme or "").lower()
        if theme not in THEME_INTERESTS:
            raise ValidationFailure(f"theme must be one of {sorted(THEME_INTERESTS)}")
        meta["theme"] = theme
        meta["interest"] = THEME_INTERESTS[theme]

    elif action == "shift_start_time":
        if payload.new_start_min is None:
            raise ValidationFailure("new_start_min is required for this action")
        if payload.new_start_min >= ctx.day_end_min - 120:
            raise ValidationFailure("the remaining day is too short to plan")
        ctx.day_start_min = payload.new_start_min
        meta["new_start_min"] = payload.new_start_min

    elif action == "weather_replan":
        meta["note"] = "forecast refreshed and attractions re-scored"

    elif action == "member_opted_out":
        if payload.member_id is None:
            raise ValidationFailure("member_id is required for this action")
        member = session.get(TripMember, payload.member_id)
        if member is None or member.trip_id != trip.id:
            raise NotFoundError("Member not found on this trip", code="member_not_found")
        member.status = "opted_out"
        session.flush()
        meta["member_id"] = str(payload.member_id)

    ctx.avoid_slugs = sorted(excluded)
    return ctx, excluded, meta


def apply_modification(
    session: Session,
    trip: Trip,
    itinerary: Itinerary,
    payload: ModifyItineraryRequest,
    *,
    actor: User,
    member: TripMember | None = None,
) -> ModifyItineraryResponse:
    ctx, excluded, meta = _prepare_inputs(session, trip, itinerary, payload)

    members = trip_service.build_member_profiles(session, trip)
    if payload.action == "add_theme":
        interest = meta["interest"]
        members = [dataclass_replace(m, interests={**m.interests, interest: 5.0}) for m in members]

    candidates = catalog.load_candidates(session, ctx.cluster_slug)
    candidates = [c for c in candidates if c.slug not in excluded]

    from yatraai.db.models import DestinationCluster
    from yatraai.services.planner import plan_trip

    cluster = session.get(DestinationCluster, trip.cluster_id)
    result = plan_trip(
        ctx,
        members,
        candidates,
        generator="ortools",
        session=session,
        cluster_baseline=(cluster.daily_cost_baseline if cluster else None),
    )

    if not result.validation.is_valid:
        raise PlanningInfeasibleError(
            "That change leaves no feasible itinerary. Try a smaller adjustment.",
            detail=result.validation.to_dict(),
        )

    summary, llm_response = ("", None)
    if payload.explain_with_llm:
        from yatraai.services.llm.explain import explain_itinerary

        summary, llm_response = explain_itinerary(result, ctx)
    else:
        from yatraai.services.llm.explain import build_template_summary

        summary = build_template_summary(result, ctx)

    active_members = _active_member_count(session, trip)
    needs_approval = active_members > 1 and not payload.propose_only

    candidate_itinerary = trip_service.persist_itinerary(
        session,
        trip,
        result,
        ctx,
        generator="ortools",
        trigger=payload.action,
        summary=summary,
        llm_response=llm_response,
        status="candidate" if needs_approval else "active",
        parent_id=itinerary.id,
    )
    session.flush()

    diff = _build_diff(itinerary, candidate_itinerary)

    if needs_approval:
        proposal = ChangeProposal(
            trip_id=trip.id,
            itinerary_id=itinerary.id,
            proposed_by_member_id=member.id if member and member.id else None,
            action=payload.action,
            payload=payload.model_dump(mode="json"),
            diff=diff.model_dump(),
            candidate_itinerary_id=candidate_itinerary.id,
            status="open",
            required_approvals=max(1, active_members // 2 + 1),
        )
        session.add(proposal)
        session.flush()
        log.info(
            "replan.proposed",
            trip_id=str(trip.id),
            action=payload.action,
            members=active_members,
        )
        return ModifyItineraryResponse(
            applied=False,
            itinerary=None,
            diff=diff,
            validation=_validation_out(candidate_itinerary),
            requires_group_approval=True,
            proposal_id=proposal.id,
            message=(
                f"This trip has {active_members} active members, so the change was submitted "
                f"for group approval. {proposal.required_approvals} approval(s) are needed."
            ),
        )

    from yatraai.api.v1.serializers import itinerary_out

    log.info("replan.applied", trip_id=str(trip.id), action=payload.action)
    return ModifyItineraryResponse(
        applied=True,
        itinerary=itinerary_out(trip_service.get_itinerary(session, candidate_itinerary.id)),
        diff=diff,
        validation=_validation_out(candidate_itinerary),
        requires_group_approval=False,
        message=f"Applied: {diff.summary}.",
    )


def approve_proposal(
    session: Session, trip: Trip, proposal_id: uuid.UUID, *, actor: User
) -> ModifyItineraryResponse:
    """Promote an approved candidate itinerary to active."""
    proposal = session.get(ChangeProposal, proposal_id)
    if proposal is None or proposal.trip_id != trip.id:
        raise NotFoundError("Proposal not found", code="proposal_not_found")
    if proposal.status != "open":
        raise ValidationFailure(f"This proposal is already {proposal.status}.")

    candidate = trip_service.get_itinerary(session, proposal.candidate_itinerary_id)
    for other in session.scalars(
        select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.status == "active")
    ):
        other.status = "superseded"
    candidate.status = "active"
    proposal.status = "applied"
    proposal.resolved_at = datetime.now(UTC)
    session.flush()

    from yatraai.api.v1.serializers import itinerary_out

    return ModifyItineraryResponse(
        applied=True,
        itinerary=itinerary_out(candidate),
        diff=ItineraryDiff(**proposal.diff) if proposal.diff else ItineraryDiff(),
        validation=_validation_out(candidate),
        requires_group_approval=False,
        message="Proposal approved and applied.",
    )


def revalidate(session: Session, trip: Trip, itinerary: Itinerary) -> dict:
    """Re-run the validator against stored rows - catches drift in catalogue data."""
    from yatraai.services.planner.models import PlannedActivity, PlannedDay

    ctx = trip_service.build_context(session, trip)
    candidates = {c.slug: c for c in catalog.load_candidates(session, ctx.cluster_slug)}

    days = [
        PlannedDay(
            day_index=day.day_index,
            calendar_date=day.calendar_date,
            start_min=day.start_min,
            end_min=day.end_min,
            base_lat=day.base_lat,
            base_lon=day.base_lon,
            travel_km=day.travel_km,
            travel_min=day.travel_min,
            activities=[
                PlannedActivity(
                    kind=a.kind,
                    sequence=a.sequence,
                    title=a.title,
                    slug=a.attraction_slug,
                    start_min=a.start_min,
                    end_min=a.end_min,
                    travel_from_prev_min=a.travel_from_prev_min,
                    travel_from_prev_km=a.travel_from_prev_km,
                    weather_suitability=a.weather_suitability,
                    is_mandatory=a.is_mandatory,
                )
                for a in day.activities
            ],
        )
        for day in sorted(itinerary.days, key=lambda d: d.day_index)
    ]
    report = validate_plan(days, ctx, candidates)
    return report.to_dict()


def pace_travel_cap(pace: str) -> int:
    return int(PACE_PROFILE.get(pace, PACE_PROFILE["balanced"])["max_travel_min"])
