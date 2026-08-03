"""Collaboration: voting, chat, change proposals, consent-based location, SOS."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from yatraai.api.v1.deps import (
    CurrentUser,
    DbSession,
    RateLimited,
    load_trip,
    require_trip_member,
    write_audit,
)
from yatraai.core.errors import NotFoundError, ValidationFailure
from yatraai.core.security import sanitize_text
from yatraai.db.models import ChangeProposal, ChatMessage, SosAlert, Vote
from yatraai.schemas.common import Ack
from yatraai.schemas.trip import ModifyItineraryResponse
from yatraai.services import location as location_service
from yatraai.services.analytics import record_event

router = APIRouter(prefix="/trips/{trip_id}", tags=["collaboration"])


# --------------------------------------------------------------------------- #
# Voting
# --------------------------------------------------------------------------- #
class VoteRequest(BaseModel):
    subject_type: str = Field(pattern="^(itinerary|proposal|attraction)$")
    subject_id: str = Field(min_length=1, max_length=96)
    value: str = Field(pattern="^(up|down|abstain)$")
    comment: str = Field(default="", max_length=500)


class VoteTally(BaseModel):
    subject_type: str
    subject_id: str
    up: int = 0
    down: int = 0
    abstain: int = 0
    total_members: int = 0
    my_vote: str | None = None
    votes: list[dict] = Field(default_factory=list)


@router.post("/votes", response_model=VoteTally, summary="Cast or change a vote")
def cast_vote(
    trip_id: uuid.UUID,
    payload: VoteRequest,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
) -> VoteTally:
    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)
    if member.id is None:
        raise ValidationFailure("Join this trip before voting.")

    existing = session.scalar(
        select(Vote).where(
            Vote.member_id == member.id,
            Vote.subject_type == payload.subject_type,
            Vote.subject_id == payload.subject_id,
        )
    )
    if existing is None:
        existing = Vote(
            trip_id=trip.id,
            member_id=member.id,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
        )
        session.add(existing)
    existing.value = payload.value
    existing.comment = sanitize_text(payload.comment, max_length=500)
    session.flush()

    # Reaching the approval threshold applies the proposal automatically.
    if payload.subject_type == "proposal":
        _maybe_apply_proposal(session, trip, uuid.UUID(payload.subject_id), user)

    session.commit()
    return _tally(session, trip, payload.subject_type, payload.subject_id, member.id)


@router.get("/votes", response_model=VoteTally, summary="Vote tally for a subject")
def get_votes(
    trip_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
    subject_type: str = Query(pattern="^(itinerary|proposal|attraction)$"),
    subject_id: str = Query(min_length=1, max_length=96),
) -> VoteTally:
    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)
    return _tally(session, trip, subject_type, subject_id, member.id)


def _tally(session, trip, subject_type: str, subject_id: str, member_id) -> VoteTally:
    from yatraai.db.models import TripMember

    rows = list(
        session.scalars(
            select(Vote).where(
                Vote.trip_id == trip.id,
                Vote.subject_type == subject_type,
                Vote.subject_id == subject_id,
            )
        )
    )
    names = {
        m.id: m.display_name
        for m in session.scalars(select(TripMember).where(TripMember.trip_id == trip.id))
    }
    total_members = (
        session.scalar(
            select(func.count())
            .select_from(TripMember)
            .where(TripMember.trip_id == trip.id, TripMember.status == "joined")
        )
        or 0
    )
    return VoteTally(
        subject_type=subject_type,
        subject_id=subject_id,
        up=sum(1 for r in rows if r.value == "up"),
        down=sum(1 for r in rows if r.value == "down"),
        abstain=sum(1 for r in rows if r.value == "abstain"),
        total_members=total_members,
        my_vote=next((r.value for r in rows if r.member_id == member_id), None),
        votes=[
            {
                "member": names.get(r.member_id, "Member"),
                "value": r.value,
                "comment": r.comment,
                "at": r.updated_at.isoformat(),
            }
            for r in rows
        ],
    )


def _maybe_apply_proposal(session, trip, proposal_id: uuid.UUID, user) -> None:
    proposal = session.get(ChangeProposal, proposal_id)
    if proposal is None or proposal.status != "open":
        return
    approvals = (
        session.scalar(
            select(func.count())
            .select_from(Vote)
            .where(
                Vote.trip_id == trip.id,
                Vote.subject_type == "proposal",
                Vote.subject_id == str(proposal_id),
                Vote.value == "up",
            )
        )
        or 0
    )
    if approvals >= proposal.required_approvals:
        from yatraai.services.replan import approve_proposal

        approve_proposal(session, trip, proposal_id, actor=user)
        session.add(
            ChatMessage(
                trip_id=trip.id,
                author_name="YatraAI",
                body=(
                    f"Proposal '{proposal.action}' reached {approvals} approvals and has "
                    "been applied to the itinerary."
                ),
                kind="system",
                meta={"proposal_id": str(proposal_id)},
            )
        )


# --------------------------------------------------------------------------- #
# Proposals
# --------------------------------------------------------------------------- #
class ProposalOut(BaseModel):
    id: uuid.UUID
    action: str
    status: str
    diff: dict = Field(default_factory=dict)
    required_approvals: int
    approvals: int = 0
    rejections: int = 0
    created_at: datetime
    resolved_at: datetime | None = None
    proposed_by: str | None = None


@router.get("/proposals", response_model=list[ProposalOut], summary="Open change proposals")
def list_proposals(
    trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> list[ProposalOut]:
    from yatraai.db.models import TripMember

    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)
    rows = list(
        session.scalars(
            select(ChangeProposal)
            .where(ChangeProposal.trip_id == trip_id)
            .order_by(ChangeProposal.created_at.desc())
            .limit(30)
        )
    )
    names = {
        m.id: m.display_name
        for m in session.scalars(select(TripMember).where(TripMember.trip_id == trip_id))
    }
    out = []
    for p in rows:
        votes = list(
            session.scalars(
                select(Vote).where(Vote.subject_type == "proposal", Vote.subject_id == str(p.id))
            )
        )
        out.append(
            ProposalOut(
                id=p.id,
                action=p.action,
                status=p.status,
                diff=p.diff or {},
                required_approvals=p.required_approvals,
                approvals=sum(1 for v in votes if v.value == "up"),
                rejections=sum(1 for v in votes if v.value == "down"),
                created_at=p.created_at,
                resolved_at=p.resolved_at,
                proposed_by=names.get(p.proposed_by_member_id),
            )
        )
    return out


@router.post(
    "/proposals/{proposal_id}/apply",
    response_model=ModifyItineraryResponse,
    summary="Apply an approved proposal (owner override)",
)
def apply_proposal(
    trip_id: uuid.UUID,
    proposal_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
) -> ModifyItineraryResponse:
    from yatraai.api.v1.deps import require_trip_owner
    from yatraai.services.replan import approve_proposal

    trip = load_trip(session, trip_id)
    require_trip_owner(session, trip, user)
    response = approve_proposal(session, trip, proposal_id, actor=user)
    write_audit(
        session,
        action="proposal.applied",
        entity_type="change_proposal",
        entity_id=str(proposal_id),
        trip_id=trip.id,
        actor=user,
    )
    session.commit()
    return response


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #
class ChatPost(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    author_name: str
    body: str
    kind: str
    meta: dict = Field(default_factory=dict)
    created_at: datetime
    is_mine: bool = False


@router.post(
    "/chat",
    response_model=ChatMessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Post a group message",
)
def post_message(
    trip_id: uuid.UUID,
    payload: ChatPost,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
) -> ChatMessageOut:
    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)
    body = sanitize_text(payload.body, max_length=2000)
    if not body:
        raise ValidationFailure("Message is empty after sanitisation.")

    row = ChatMessage(
        trip_id=trip.id,
        member_id=member.id,
        author_name=member.display_name,
        body=body,
        kind="text",
    )
    session.add(row)
    session.commit()
    return ChatMessageOut(
        id=row.id,
        author_name=row.author_name,
        body=row.body,
        kind=row.kind,
        meta=row.meta or {},
        created_at=row.created_at,
        is_mine=True,
    )


@router.get("/chat", response_model=list[ChatMessageOut], summary="Group chat history")
def list_messages(
    trip_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
    limit: int = Query(default=100, ge=1, le=500),
    since: datetime | None = Query(default=None, description="Poll for new messages"),
) -> list[ChatMessageOut]:
    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)

    stmt = select(ChatMessage).where(ChatMessage.trip_id == trip_id)
    if since is not None:
        stmt = stmt.where(ChatMessage.created_at > since)
    rows = list(session.scalars(stmt.order_by(ChatMessage.created_at.desc()).limit(limit)))
    rows.reverse()
    return [
        ChatMessageOut(
            id=r.id,
            author_name=r.author_name,
            body=r.body,
            kind=r.kind,
            meta=r.meta or {},
            created_at=r.created_at,
            is_mine=r.member_id == member.id,
        )
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Location
# --------------------------------------------------------------------------- #
class StartSharingRequest(BaseModel):
    consent_granted: bool = Field(description="Must be true - explicit opt-in is required")
    precision: str = Field(default="approximate", pattern="^(exact|approximate)$")
    update_interval_seconds: int = Field(default=60, ge=15, le=3600)
    duration_hours: int = Field(default=4, ge=1, le=12)


class SharingStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|paused|stopped)$")


class PointRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0, le=100000)


class SharingSessionOut(BaseModel):
    id: uuid.UUID
    status: str
    precision: str
    update_interval_seconds: int
    consent_granted_at: datetime
    consent_text_version: str
    expires_at: datetime
    last_point_at: datetime | None = None
    consent_text: str = ""


@router.get(
    "/location/consent-text",
    summary="The exact consent wording the user must agree to",
)
def consent_text(trip_id: uuid.UUID, _rl: RateLimited) -> dict:
    del trip_id
    return {
        "version": location_service.CONSENT_TEXT_VERSION,
        "text": location_service.CONSENT_TEXT,
        "guarantees": [
            "Sharing is opt-in and never starts by itself.",
            "You can pause or stop at any time; stopping deletes your trail immediately.",
            "Approximate mode snaps your position to roughly 500 m before it is stored.",
            "Every session expires automatically; points are deleted after the retention window.",
            "Only members of this trip can see your position.",
            "Your coordinates are never written to analytics.",
        ],
    }


@router.post(
    "/location/start",
    response_model=SharingSessionOut,
    summary="Start sharing your location (explicit consent required)",
)
def start_location_sharing(
    trip_id: uuid.UUID,
    payload: StartSharingRequest,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
) -> SharingSessionOut:
    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)
    row = location_service.start_sharing(
        session,
        trip,
        member,
        consent_granted=payload.consent_granted,
        precision=payload.precision,
        update_interval_seconds=payload.update_interval_seconds,
        duration_hours=payload.duration_hours,
    )
    write_audit(
        session,
        action="location.sharing_started",
        entity_type="location_session",
        entity_id=str(row.id),
        trip_id=trip.id,
        actor=user,
        detail={"precision": payload.precision, "expires_at": row.expires_at.isoformat()},
    )
    record_event(
        session,
        "location_sharing_started",
        trip_id=trip.id,
        user_id=user.id,
        properties={"precision": payload.precision},
    )
    session.commit()
    return SharingSessionOut(
        **{
            k: getattr(row, k)
            for k in (
                "id",
                "status",
                "precision",
                "update_interval_seconds",
                "consent_granted_at",
                "consent_text_version",
                "expires_at",
                "last_point_at",
            )
        },
        consent_text=location_service.CONSENT_TEXT,
    )


@router.post(
    "/location/status", response_model=SharingSessionOut, summary="Pause, resume or stop sharing"
)
def update_sharing_status(
    trip_id: uuid.UUID,
    payload: SharingStatusRequest,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
) -> SharingSessionOut:
    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)
    row = location_service.set_sharing_status(session, trip, member, payload.status)
    write_audit(
        session,
        action=f"location.sharing_{payload.status}",
        entity_type="location_session",
        entity_id=str(row.id),
        trip_id=trip.id,
        actor=user,
    )
    session.commit()
    return SharingSessionOut(
        **{
            k: getattr(row, k)
            for k in (
                "id",
                "status",
                "precision",
                "update_interval_seconds",
                "consent_granted_at",
                "consent_text_version",
                "expires_at",
                "last_point_at",
            )
        },
        consent_text=location_service.CONSENT_TEXT,
    )


@router.post("/location/point", response_model=Ack, summary="Post your current position")
def post_point(
    trip_id: uuid.UUID,
    payload: PointRequest,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
) -> Ack:
    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)
    point = location_service.record_point(
        session, trip, member, payload.lat, payload.lon, payload.accuracy_m
    )
    session.commit()
    return Ack(
        message=(
            "Position recorded"
            + (" (snapped to approximate grid)" if point.is_approximate else "")
            + f"; expires {point.expires_at.isoformat()}"
        )
    )


@router.get("/location/group", summary="Group map: positions, separation, meeting point, ETAs")
def group_location(
    trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> dict:
    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)
    return location_service.group_status(session, trip)


@router.delete("/location", response_model=Ack, summary="Stop sharing and delete your trail")
def delete_my_location(
    trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> Ack:
    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)
    location_service.set_sharing_status(session, trip, member, "stopped")
    write_audit(
        session,
        action="location.deleted_by_user",
        entity_type="location_session",
        trip_id=trip.id,
        actor=user,
    )
    session.commit()
    return Ack(message="Sharing stopped and your recorded positions were deleted.")


# --------------------------------------------------------------------------- #
# SOS (demo only)
# --------------------------------------------------------------------------- #
class SosRequest(BaseModel):
    message: str = Field(default="", max_length=500)
    acknowledge_demo: bool = Field(
        description="Must be true. Confirms you understand this contacts nobody."
    )


@router.post(
    "/sos",
    status_code=status.HTTP_201_CREATED,
    summary="Raise a DEMO SOS notification to trip members",
    description=(
        "**This is a demonstration mechanism only.** It creates an in-app notification for "
        "members of this trip. It does not contact emergency services, police, or any external "
        "party, and must never be relied upon in a real emergency."
    ),
)
def raise_sos(
    trip_id: uuid.UUID,
    payload: SosRequest,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
) -> dict:
    if not payload.acknowledge_demo:
        raise ValidationFailure(
            "You must acknowledge that this is a demo mechanism that contacts nobody."
        )
    trip = load_trip(session, trip_id)
    member = require_trip_member(session, trip, user)
    alert = location_service.raise_sos(session, trip, member, payload.message)

    session.add(
        ChatMessage(
            trip_id=trip.id,
            author_name="YatraAI",
            body=f"DEMO SOS raised by {member.display_name}. This is a demo and contacts nobody.",
            kind="system",
            meta={"sos_alert_id": str(alert.id), "demo": True},
        )
    )
    write_audit(
        session,
        action="sos.demo_raised",
        entity_type="sos_alert",
        entity_id=str(alert.id),
        trip_id=trip.id,
        actor=user,
    )
    session.commit()
    return {
        "id": str(alert.id),
        "status": alert.status,
        "is_demo": True,
        "disclaimer": alert.meta.get("disclaimer"),
        "notified_members": True,
    }


@router.get("/sos", summary="Open demo SOS alerts for this trip")
def list_sos(
    trip_id: uuid.UUID, session: DbSession, user: CurrentUser, _rl: RateLimited
) -> list[dict]:
    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)
    rows = session.scalars(
        select(SosAlert)
        .where(SosAlert.trip_id == trip_id)
        .order_by(SosAlert.created_at.desc())
        .limit(20)
    )
    return [
        {
            "id": str(r.id),
            "message": r.message,
            "status": r.status,
            "is_demo": r.is_demo,
            "approx_lat": r.approx_lat,
            "approx_lon": r.approx_lon,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/sos/{alert_id}/resolve", response_model=Ack, summary="Resolve a demo SOS alert")
def resolve_sos(
    trip_id: uuid.UUID,
    alert_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    _rl: RateLimited,
) -> Ack:
    trip = load_trip(session, trip_id)
    require_trip_member(session, trip, user)
    alert = session.get(SosAlert, alert_id)
    if alert is None or alert.trip_id != trip.id:
        raise NotFoundError("Alert not found", code="sos_not_found")
    alert.status = "resolved"
    session.commit()
    return Ack(message="Demo alert resolved.")
