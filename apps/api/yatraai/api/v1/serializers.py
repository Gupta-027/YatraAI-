"""ORM -> response-schema conversion, kept out of the route handlers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from yatraai.db.models import Attraction, DestinationCluster, Itinerary, Trip, TripMember
from yatraai.schemas.catalog import (
    AttractionDetail,
    AttractionSummary,
    ClusterDetail,
    ClusterSummary,
    CostEntry,
    NearbyAttraction,
    ScheduleEntry,
    SourceEntry,
)
from yatraai.schemas.trip import (
    ActivityOut,
    CostOut,
    DayOut,
    ItineraryOut,
    MemberPreferenceOut,
    TripMemberOut,
    TripOut,
    ValidationOut,
)
from yatraai.services.routing.distance import haversine_km

DOW_LABEL = {
    -1: "Every day",
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}
VISITOR_LABEL = {
    "indian_adult": "Indian visitors",
    "foreign_adult": "Foreign visitors",
    "child": "Children",
    "senior": "Senior citizens",
    "camera": "Camera / videography",
    "parking": "Parking",
}


def hhmm(minutes: int | None) -> str:
    if minutes is None:
        return ""
    return f"{int(minutes) // 60:02d}:{int(minutes) % 60:02d}"


# --------------------------------------------------------------------------- #
def cluster_summary(cluster: DestinationCluster, attraction_count: int = 0) -> ClusterSummary:
    return ClusterSummary(
        id=cluster.id,
        slug=cluster.slug,
        name=cluster.name,
        state=cluster.state,
        region=cluster.region,
        summary=cluster.summary,
        travel_style=list(cluster.travel_style or []),
        center_lat=cluster.center_lat,
        center_lon=cluster.center_lon,
        best_months=list(cluster.best_months or []),
        avoid_months=list(cluster.avoid_months or []),
        recommended_days=cluster.recommended_days,
        intercity_hub=cluster.intercity_hub,
        hero_image_url=cluster.hero_image_url,
        image_attribution=cluster.image_attribution,
        attraction_count=attraction_count,
    )


def cluster_detail(cluster: DestinationCluster, attractions: list[Attraction]) -> ClusterDetail:
    categories = sorted({c for a in attractions for c in (a.categories or [])})
    accessible = [a for a in attractions if a.wheelchair_accessible in ("yes", "partial")]
    indoor = [a for a in attractions if a.indoor_outdoor in ("indoor", "mixed")]
    return ClusterDetail(
        **cluster_summary(cluster, len(attractions)).model_dump(),
        daily_cost_baseline=dict(cluster.daily_cost_baseline or {}),
        timezone=cluster.timezone,
        categories=categories,
        accessibility_summary={
            "wheelchair_friendly": len(accessible),
            "indoor_options": len(indoor),
            "senior_friendly": len([a for a in attractions if a.senior_friendly >= 4]),
            "child_friendly": len([a for a in attractions if a.child_friendly >= 4]),
            "total": len(attractions),
        },
    )


def attraction_summary(attraction: Attraction, cluster_slug: str = "") -> AttractionSummary:
    return AttractionSummary(
        id=attraction.id,
        slug=attraction.slug,
        name=attraction.name,
        locality=attraction.locality,
        city=attraction.city,
        lat=attraction.lat,
        lon=attraction.lon,
        categories=list(attraction.categories or []),
        summary=attraction.summary,
        typical_duration_min=attraction.typical_duration_min,
        indoor_outdoor=attraction.indoor_outdoor,
        typical_crowd_level=attraction.typical_crowd_level,
        wheelchair_accessible=attraction.wheelchair_accessible,
        senior_friendly=attraction.senior_friendly,
        child_friendly=attraction.child_friendly,
        physical_intensity=attraction.physical_intensity,
        quality_score=attraction.quality_score,
        hero_image_url=attraction.hero_image_url,
        image_attribution=attraction.image_attribution,
        needs_verification=attraction.needs_verification,
        cluster_slug=cluster_slug or (attraction.cluster.slug if attraction.cluster else ""),
    )


def attraction_detail(
    session: Session, attraction: Attraction, knowledge_topics: list[str] | None = None
) -> AttractionDetail:
    from yatraai.services.catalog import resolve_nearby

    schedules = [
        ScheduleEntry(
            day_of_week=s.day_of_week,
            day_label=DOW_LABEL.get(s.day_of_week, "Every day"),
            opens=hhmm(s.opens_min) or None,
            closes=hhmm(s.closes_min) or None,
            is_closed=s.is_closed,
            season=s.season,
            note=s.note,
            verified=s.verified,
        )
        for s in sorted(attraction.schedules, key=lambda s: (s.day_of_week, s.opens_min or 0))
    ]
    costs = [
        CostEntry(
            visitor_type=c.visitor_type,
            label=VISITOR_LABEL.get(c.visitor_type, c.visitor_type.replace("_", " ").title()),
            currency=c.currency,
            amount_min=c.amount_min,
            amount_max=c.amount_max,
            is_free=c.is_free,
            note=c.note,
            verified=c.verified,
        )
        for c in attraction.costs
    ]
    sources = [
        SourceEntry(
            url=s.url,
            title=s.title,
            source_type=s.source_type,
            covers_fields=list(s.covers_fields or []),
            last_verified_at=s.last_verified_at,
        )
        for s in attraction.sources
    ]
    nearby = [
        NearbyAttraction(
            slug=n.slug,
            name=n.name,
            cluster_slug=n.cluster.slug if n.cluster else "",
            distance_km=round(haversine_km(attraction.lat, attraction.lon, n.lat, n.lon), 2),
            categories=list(n.categories or []),
        )
        for n in resolve_nearby(session, attraction)
    ]

    return AttractionDetail(
        **attraction_summary(attraction).model_dump(),
        history=attraction.history,
        significance=attraction.significance,
        interesting_facts=list(attraction.interesting_facts or []),
        min_duration_min=attraction.min_duration_min,
        max_duration_min=attraction.max_duration_min,
        best_time_of_day=list(attraction.best_time_of_day or []),
        suitable_months=list(attraction.suitable_months or []),
        weather_sensitivity=attraction.weather_sensitivity,
        crowd_by_time=dict(attraction.crowd_by_time or {}),
        accessibility_notes=attraction.accessibility_notes,
        dress_code=attraction.dress_code,
        photography_policy=attraction.photography_policy,
        local_customs=list(attraction.local_customs or []),
        schedules=schedules,
        costs=costs,
        sources=sources,
        nearby=nearby,
        data_confidence=attraction.data_confidence,
        verification_note=attraction.verification_note,
        last_verified_at=attraction.last_verified_at,
        knowledge_topics=knowledge_topics or [],
    )


# --------------------------------------------------------------------------- #
def member_out(member: TripMember) -> TripMemberOut:
    prefs = member.preferences
    return TripMemberOut(
        id=member.id,
        display_name=member.display_name,
        role=member.role,
        status=member.status,
        weight=member.weight,
        joined_at=member.joined_at,
        user_id=member.user_id,
        preferences=MemberPreferenceOut.model_validate(prefs) if prefs else None,
    )


def trip_out(trip: Trip, *, has_itinerary: bool = False) -> TripOut:
    members = [member_out(m) for m in trip.members]
    return TripOut(
        id=trip.id,
        owner_id=trip.owner_id,
        cluster_id=trip.cluster_id,
        title=trip.title,
        start_date=trip.start_date,
        end_date=trip.end_date,
        origin_label=trip.origin_label,
        traveller_count=trip.traveller_count,
        budget_per_person_inr=trip.budget_per_person_inr,
        budget_total_inr=trip.budget_total_inr,
        budget_basis=trip.budget_basis,
        pace=trip.pace,
        transport_mode=trip.transport_mode,
        accommodation_tier=trip.accommodation_tier,
        day_start_min=trip.day_start_min,
        day_end_min=trip.day_end_min,
        has_children=trip.has_children,
        has_seniors=trip.has_seniors,
        accessibility_required=trip.accessibility_required,
        must_visit_slugs=list(trip.must_visit_slugs or []),
        avoid_slugs=list(trip.avoid_slugs or []),
        status=trip.status,
        invite_code=trip.invite_code,
        notes=trip.notes,
        created_at=trip.created_at,
        cluster_slug=trip.cluster.slug if trip.cluster else "",
        cluster_name=trip.cluster.name if trip.cluster else "",
        duration_days=trip.duration_days,
        members=members,
        preferences_submitted=sum(1 for m in members if m.preferences and m.preferences.submitted),
        has_itinerary=has_itinerary,
    )


def activity_out(activity) -> ActivityOut:
    return ActivityOut(
        id=activity.id,
        sequence=activity.sequence,
        kind=activity.kind,
        title=activity.title,
        attraction_slug=activity.attraction_slug,
        attraction_id=activity.attraction_id,
        start_min=activity.start_min,
        end_min=activity.end_min,
        start_time=hhmm(activity.start_min),
        end_time=hhmm(activity.end_min),
        duration_min=activity.end_min - activity.start_min,
        opens_time=hhmm(activity.opens_min) if activity.opens_min is not None else None,
        closes_time=hhmm(activity.closes_min) if activity.closes_min is not None else None,
        travel_from_prev_min=activity.travel_from_prev_min,
        travel_from_prev_km=activity.travel_from_prev_km,
        travel_mode=activity.travel_mode,
        lat=activity.lat,
        lon=activity.lon,
        est_cost_low_inr=activity.est_cost_low_inr,
        est_cost_high_inr=activity.est_cost_high_inr,
        weather_suitability=activity.weather_suitability,
        warnings=list(activity.warnings or []),
        why_selected=activity.why_selected,
        score_breakdown=dict(activity.score_breakdown or {}),
        is_mandatory=activity.is_mandatory,
        locked=activity.locked,
    )


def itinerary_out(itinerary: Itinerary) -> ItineraryOut:
    report = itinerary.validation_report or {}
    coverage = itinerary.preference_coverage or {}
    cost_meta = itinerary.cost_breakdown or {}
    return ItineraryOut(
        id=itinerary.id,
        trip_id=itinerary.trip_id,
        version=itinerary.version,
        status=itinerary.status,
        generator=itinerary.generator,
        trigger=itinerary.trigger,
        is_valid=itinerary.is_valid,
        validation=ValidationOut(
            is_valid=report.get("is_valid", itinerary.is_valid),
            checks_run=report.get("checks_run", 0),
            errors=report.get("errors", []),
            warnings=report.get("warnings", []),
        ),
        total_travel_km=itinerary.total_travel_km,
        total_travel_min=itinerary.total_travel_min,
        total_visit_min=itinerary.total_visit_min,
        activity_count=itinerary.activity_count,
        fairness_score=itinerary.fairness_score,
        least_satisfied_score=itinerary.least_satisfied_score,
        consensus_score=itinerary.consensus_score,
        utility_score=itinerary.utility_score,
        preference_coverage=coverage.get("by_interest", {}),
        per_member_coverage=coverage.get("by_member", {}),
        cost=CostOut(
            low_inr=itinerary.cost_low_inr,
            high_inr=itinerary.cost_high_inr,
            per_person_low_inr=itinerary.cost_per_person_low_inr,
            per_person_high_inr=itinerary.cost_per_person_high_inr,
            display=(
                f"Expected cost: Rs.{itinerary.cost_per_person_low_inr:,.0f}-"
                f"Rs.{itinerary.cost_per_person_high_inr:,.0f} per person"
            ),
            breakdown=cost_meta.get("components", {}),
            assumptions=cost_meta.get("assumptions", []),
        ),
        summary_text=itinerary.summary_text,
        explanation_source=itinerary.explanation_source,
        llm_provider=itinerary.llm_provider,
        degraded_services=list(itinerary.degraded_services or []),
        solver_stats=dict(itinerary.solver_stats or {}),
        created_at=itinerary.created_at,
        days=[
            DayOut(
                id=day.id,
                day_index=day.day_index,
                calendar_date=day.calendar_date,
                start_min=day.start_min,
                end_min=day.end_min,
                base_lat=day.base_lat,
                base_lon=day.base_lon,
                travel_km=day.travel_km,
                travel_min=day.travel_min,
                weather=dict(day.weather or {}),
                weather_advisories=list(day.weather_advisories or []),
                theme=day.theme,
                notes=day.notes,
                activities=[activity_out(a) for a in day.activities],
            )
            for day in sorted(itinerary.days, key=lambda d: d.day_index)
        ],
    )
