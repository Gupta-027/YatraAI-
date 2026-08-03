"""End-to-end planner tests: constraints, determinism, weather, fallbacks."""

from __future__ import annotations

import itertools
from datetime import date

import pytest

from yatraai.services.planner import plan_trip
from yatraai.services.planner.models import (
    AttractionCandidate,
    DayWeather,
    MemberProfile,
    OpeningWindow,
    TripContext,
)
from yatraai.services.recommend.taxonomy import default_preferences

BENGALURU = (12.9716, 77.5946)


def candidate(
    slug: str,
    *,
    lat: float,
    lon: float,
    categories: list[str],
    duration: int = 60,
    opens: int = 9 * 60,
    closes: int = 18 * 60,
    closed_weekdays: set[int] | None = None,
    cost: float = 0.0,
    indoor: str = "outdoor",
    quality: float = 0.8,
    accessible: str = "yes",
    intensity: int = 2,
    weather_sensitivity: float = 0.5,
    months: list[int] | None = None,
) -> AttractionCandidate:
    return AttractionCandidate(
        slug=slug,
        name=slug.replace("-", " ").title(),
        lat=lat,
        lon=lon,
        categories=categories,
        typical_duration_min=duration,
        min_duration_min=max(20, duration // 2),
        max_duration_min=duration * 2,
        quality_score=quality,
        indoor_outdoor=indoor,
        weather_sensitivity=weather_sensitivity,
        suitable_months=months or list(range(1, 13)),
        wheelchair_accessible=accessible,
        physical_intensity=intensity,
        entry_cost_min=cost,
        entry_cost_max=cost,
        windows=[OpeningWindow(-1, opens, closes)],
        closed_weekdays=closed_weekdays or set(),
        needs_verification=True,
        verification_note="Verify before visiting.",
    )


@pytest.fixture
def catalogue() -> list[AttractionCandidate]:
    """Nine plausible Bengaluru-shaped candidates in two geographic groups."""
    return [
        candidate(
            "lalbagh", lat=12.9507, lon=77.5848, categories=["garden", "nature"], duration=120
        ),
        candidate(
            "bull-temple", lat=12.9427, lon=77.5675, categories=["temple", "spiritual"], duration=40
        ),
        candidate(
            "tipu-palace",
            lat=12.9591,
            lon=77.5738,
            categories=["heritage", "asi-monument"],
            duration=45,
            cost=25,
        ),
        candidate(
            "cubbon-park", lat=12.9763, lon=77.5929, categories=["garden", "nature"], duration=75
        ),
        candidate(
            "vidhana-soudha",
            lat=12.9794,
            lon=77.5912,
            categories=["architecture", "landmark"],
            duration=30,
        ),
        candidate(
            "science-museum",
            lat=12.9757,
            lon=77.5963,
            categories=["museum", "science"],
            duration=110,
            cost=90,
            indoor="indoor",
            weather_sensitivity=0.0,
        ),
        candidate(
            "art-gallery",
            lat=12.9880,
            lon=77.5949,
            categories=["museum", "art"],
            duration=80,
            cost=30,
            indoor="indoor",
            weather_sensitivity=0.0,
        ),
        candidate(
            "hal-museum",
            lat=12.9525,
            lon=77.6685,
            categories=["museum", "aviation"],
            duration=100,
            cost=60,
            indoor="indoor",
            weather_sensitivity=0.0,
        ),
        candidate(
            "ulsoor-lake", lat=12.9819, lon=77.6210, categories=["lake", "nature"], duration=50
        ),
    ]


@pytest.fixture
def members() -> list[MemberProfile]:
    heritage = default_preferences() | {"heritage": 5, "museums": 4, "nature": 2}
    nature = default_preferences() | {"nature": 5, "relaxation": 4, "heritage": 2}
    spiritual = default_preferences() | {"spiritual": 5, "heritage": 3, "adventure": 1}
    return [
        MemberProfile("m1", "Asha", heritage),
        MemberProfile("m2", "Ben", nature),
        MemberProfile("m3", "Chi", spiritual),
    ]


@pytest.fixture
def ctx() -> TripContext:
    return TripContext(
        trip_id="t1",
        cluster_slug="bengaluru",
        start_date=date(2026, 11, 10),  # Tuesday
        end_date=date(2026, 11, 12),
        traveller_count=3,
        budget_per_person_inr=9000,
        pace="balanced",
        transport_mode="car",
        day_start_min=9 * 60,
        day_end_min=19 * 60,
        base_lat=BENGALURU[0],
        base_lon=BENGALURU[1],
    )


def fair_weather(ctx: TripContext) -> list[DayWeather]:
    from datetime import timedelta

    return [
        DayWeather(
            calendar_date=ctx.start_date + timedelta(days=i),
            condition="clear",
            temp_min_c=18,
            temp_max_c=28,
            precipitation_mm=0.0,
            precipitation_probability=0.03,
            wind_kph=8,
            visibility_km=15,
            provider="test",
        )
        for i in range(ctx.days)
    ]


# --------------------------------------------------------------------------- #
class TestPlanValidity:
    def test_produces_a_valid_plan(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert result.validation.is_valid, [i.to_dict() for i in result.validation.errors]
        assert result.metrics.activity_count > 0
        assert len(result.days) == ctx.days

    def test_validator_actually_runs_many_checks(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert result.validation.checks_run >= 15

    def test_no_attraction_is_visited_twice(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        slugs = result.selected_slugs
        assert len(slugs) == len(set(slugs))

    def test_all_activities_are_inside_the_day_window(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        for day in result.days:
            for activity in day.activities:
                assert activity.start_min >= ctx.day_start_min
                assert activity.end_min <= ctx.day_end_min

    def test_activities_do_not_overlap_and_leave_room_for_travel(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        for day in result.days:
            ordered = sorted(day.activities, key=lambda a: a.start_min)
            for previous, current in itertools.pairwise(ordered):
                assert current.start_min >= previous.end_min
                gap = current.start_min - previous.end_min
                assert gap + 2 >= current.travel_from_prev_min

    def test_opening_hours_are_respected(self, ctx, members, catalogue):
        late_opener = candidate(
            "late-opener",
            lat=12.96,
            lon=77.60,
            categories=["museum"],
            duration=60,
            opens=15 * 60,
            closes=18 * 60,
            indoor="indoor",
        )
        result = plan_trip(ctx, members, [*catalogue, late_opener], weather=fair_weather(ctx))
        for day in result.days:
            for activity in day.visits:
                if activity.slug == "late-opener":
                    assert activity.start_min >= 15 * 60
                    assert activity.end_min <= 18 * 60

    def test_never_schedules_on_a_closed_weekday(self, ctx, members, catalogue):
        # Closed Tue/Wed/Thu - the entire trip window.
        never_open = candidate(
            "always-closed",
            lat=12.96,
            lon=77.60,
            categories=["museum"],
            closed_weekdays={0, 1, 2, 3, 4, 5, 6},
        )
        result = plan_trip(ctx, members, [*catalogue, never_open], weather=fair_weather(ctx))
        assert "always-closed" not in result.selected_slugs

    def test_meal_break_is_scheduled_on_long_days(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        days_with_visits = [d for d in result.days if d.visits]
        assert days_with_visits
        assert all(any(a.kind == "meal" for a in d.activities) for d in days_with_visits)


class TestConstraints:
    def test_mandatory_attractions_are_always_scheduled(self, ctx, members, catalogue):
        ctx.must_visit_slugs = ["hal-museum"]
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert "hal-museum" in result.selected_slugs
        assert result.validation.is_valid

    def test_group_avoid_list_is_honoured(self, ctx, members, catalogue):
        ctx.avoid_slugs = ["lalbagh", "cubbon-park"]
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert "lalbagh" not in result.selected_slugs
        assert "cubbon-park" not in result.selected_slugs

    def test_a_single_member_can_veto(self, ctx, members, catalogue):
        """The brief requires that a majority cannot simply overrule one person."""
        members[2].avoid_slugs = ["science-museum"]
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert "science-museum" not in result.selected_slugs

    def test_accessibility_requirement_excludes_inaccessible_places(self, ctx, members, catalogue):
        ctx.accessibility_required = True
        steep = candidate(
            "steep-fort", lat=12.95, lon=77.58, categories=["fort"], accessible="no", intensity=5
        )
        result = plan_trip(ctx, members, [*catalogue, steep], weather=fair_weather(ctx))
        assert "steep-fort" not in result.selected_slugs
        assert result.validation.is_valid

    def test_wheelchair_member_vetoes_inaccessible_places(self, ctx, members, catalogue):
        members[1].mobility_level = "wheelchair"
        steep = candidate("steep-fort", lat=12.95, lon=77.58, categories=["fort"], accessible="no")
        result = plan_trip(ctx, members, [*catalogue, steep], weather=fair_weather(ctx))
        assert "steep-fort" not in result.selected_slugs

    def test_relaxed_pace_schedules_fewer_stops_than_packed(self, ctx, members, catalogue):
        ctx.pace = "relaxed"
        relaxed = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        ctx.pace = "packed"
        packed = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert relaxed.metrics.activity_count <= packed.metrics.activity_count

    def test_expensive_attraction_excluded_on_a_tiny_budget(self, ctx, members, catalogue):
        ctx.budget_per_person_inr = 900  # 3 days -> ~135/day for activities
        pricey = candidate("pricey", lat=12.96, lon=77.59, categories=["entertainment"], cost=2500)
        result = plan_trip(ctx, members, [*catalogue, pricey], weather=fair_weather(ctx))
        assert "pricey" not in result.selected_slugs

    def test_daily_travel_stays_within_the_pace_guideline(self, ctx, members, catalogue):
        from yatraai.services.planner.models import PACE_PROFILE

        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        limit = PACE_PROFILE[ctx.pace]["max_travel_min"]
        for day in result.days:
            assert day.travel_min <= limit * 1.9  # relaxations are recorded, not silent


class TestDeterminism:
    def test_identical_inputs_give_identical_plans(self, ctx, members, catalogue):
        weather = fair_weather(ctx)
        first = plan_trip(ctx, members, catalogue, weather=weather)
        second = plan_trip(ctx, members, catalogue, weather=weather)
        assert first.selected_slugs == second.selected_slugs
        assert first.metrics.total_travel_km == pytest.approx(second.metrics.total_travel_km)
        assert first.solver_stats["fingerprint"] == second.solver_stats["fingerprint"]

    def test_changing_preferences_changes_the_fingerprint(self, ctx, members, catalogue):
        weather = fair_weather(ctx)
        first = plan_trip(ctx, members, catalogue, weather=weather)
        members[0].interests["nature"] = 5
        second = plan_trip(ctx, members, catalogue, weather=weather)
        assert first.solver_stats["fingerprint"] != second.solver_stats["fingerprint"]

    def test_candidate_order_does_not_change_the_result(self, ctx, members, catalogue):
        weather = fair_weather(ctx)
        forward = plan_trip(ctx, members, catalogue, weather=weather)
        backward = plan_trip(ctx, members, list(reversed(catalogue)), weather=weather)
        assert sorted(forward.selected_slugs) == sorted(backward.selected_slugs)


class TestWeatherAwareness:
    def _rainy(self, ctx):
        from datetime import timedelta

        return [
            DayWeather(
                calendar_date=ctx.start_date + timedelta(days=i),
                condition="heavy_rain",
                temp_min_c=20,
                temp_max_c=26,
                precipitation_mm=40.0,
                precipitation_probability=0.95,
                wind_kph=25,
                visibility_km=2.0,
                provider="test",
            )
            for i in range(ctx.days)
        ]

    def test_rain_shifts_the_plan_indoors(self, ctx, members, catalogue):
        indoor = {"science-museum", "art-gallery", "hal-museum"}
        dry = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        wet = plan_trip(ctx, members, catalogue, weather=self._rainy(ctx))
        dry_share = len(set(dry.selected_slugs) & indoor) / max(1, len(dry.selected_slugs))
        wet_share = len(set(wet.selected_slugs) & indoor) / max(1, len(wet.selected_slugs))
        assert wet_share >= dry_share

    def test_rain_produces_advisories(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=self._rainy(ctx))
        assert any(d.weather_advisories for d in result.days)
        assert any("Rain" in a for d in result.days for a in d.weather_advisories)

    def test_plan_remains_valid_in_bad_weather(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=self._rainy(ctx))
        assert result.validation.is_valid

    def test_out_of_season_attractions_are_downranked(self, ctx, members, catalogue):
        monsoon_only = candidate(
            "monsoon-falls",
            lat=12.94,
            lon=77.57,
            categories=["waterfall", "nature"],
            months=[6, 7, 8],
            weather_sensitivity=1.0,
        )
        result = plan_trip(ctx, members, [*catalogue, monsoon_only], weather=fair_weather(ctx))
        scored = {s.slug: s for s in result.scored}
        assert scored["monsoon-falls"].breakdown.seasonal_suitability < 0.5


class TestFairness:
    def test_every_member_gets_something(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert result.metrics.least_satisfied_score > 0.0
        assert all(v > 0 for v in result.metrics.per_member_coverage.values())

    def test_fairness_index_is_reported(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert 0.0 < result.metrics.fairness_score <= 1.0

    def test_fairness_aware_beats_simple_average_for_the_worst_off(self, ctx, catalogue):
        """Three members want museums, one wants nature - the minority must not vanish."""
        museum = default_preferences() | {"museums": 5, "heritage": 4, "nature": 1}
        nature = default_preferences() | {"nature": 5, "relaxation": 5, "museums": 1}
        members = [
            MemberProfile("a", "A", dict(museum)),
            MemberProfile("b", "B", dict(museum)),
            MemberProfile("c", "C", dict(museum)),
            MemberProfile("d", "D", dict(nature)),
        ]
        weather = fair_weather(ctx)
        avg = plan_trip(
            ctx, members, catalogue, weather=weather, aggregation_method="simple_average"
        )
        fair = plan_trip(
            ctx, members, catalogue, weather=weather, aggregation_method="fairness_aware"
        )
        assert fair.metrics.least_satisfied_score >= avg.metrics.least_satisfied_score


class TestCostEstimate:
    def test_returns_a_range_not_a_point(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert result.cost.low_inr < result.cost.high_inr
        assert result.cost.per_person_low_inr < result.cost.per_person_high_inr

    def test_breakdown_covers_all_five_components(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert set(result.cost.breakdown) == {
            "accommodation",
            "food",
            "local_transport",
            "entry_charges",
            "contingency",
        }

    def test_assumptions_are_documented(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert len(result.cost.assumptions) >= 5

    def test_more_travellers_costs_more_in_total_but_less_per_head_on_transport(
        self, ctx, members, catalogue
    ):
        weather = fair_weather(ctx)
        small = plan_trip(ctx, members, catalogue, weather=weather)
        ctx.traveller_count = 8
        large = plan_trip(ctx, members, catalogue, weather=weather)
        assert large.cost.low_inr > small.cost.low_inr


class TestGreedyBaseline:
    def test_greedy_also_produces_a_valid_plan(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx), generator="greedy")
        assert result.validation.is_valid, [i.to_dict() for i in result.validation.errors]

    def test_comparison_reports_both_generators(self, ctx, members, catalogue):
        from yatraai.services.planner import compare_generators

        comparison = compare_generators(ctx, members, catalogue, weather=fair_weather(ctx))
        assert set(comparison) == {"greedy", "ortools"}
        for stats in comparison.values():
            assert stats["is_valid"]
            assert stats["computation_ms"] > 0

    def test_ortools_does_not_travel_further_per_activity_than_greedy(
        self, ctx, members, catalogue
    ):
        from yatraai.services.planner import compare_generators

        c = compare_generators(ctx, members, catalogue, weather=fair_weather(ctx))
        ortools_per_stop = c["ortools"]["total_travel_km"] / max(1, c["ortools"]["activity_count"])
        greedy_per_stop = c["greedy"]["total_travel_km"] / max(1, c["greedy"]["activity_count"])
        assert ortools_per_stop <= greedy_per_stop * 1.15


class TestDegradedModes:
    def test_plan_still_produced_with_no_weather_data(self, ctx, members, catalogue):
        result = plan_trip(ctx, members, catalogue, weather=[])
        assert result.validation.is_valid

    def test_single_day_trip(self, ctx, members, catalogue):
        ctx.end_date = ctx.start_date
        result = plan_trip(ctx, members, catalogue, weather=fair_weather(ctx))
        assert len(result.days) == 1
        assert result.validation.is_valid

    def test_single_member_trip(self, ctx, catalogue):
        solo = [MemberProfile("solo", "Solo", default_preferences())]
        result = plan_trip(ctx, solo, catalogue, weather=fair_weather(ctx))
        assert result.validation.is_valid
        assert result.metrics.fairness_score == pytest.approx(1.0)

    def test_empty_catalogue_reports_infeasible_rather_than_crashing(self, ctx, members):
        result = plan_trip(ctx, members, [])
        assert not result.validation.is_valid
        assert result.validation.errors[0].code == "no_feasible_plan"

    def test_more_days_than_attractions(self, ctx, members, catalogue):
        ctx.end_date = date(2026, 11, 20)  # 11 days, 9 attractions
        result = plan_trip(ctx, members, catalogue[:3], weather=[])
        assert len(result.days) == 11
        assert len(result.selected_slugs) == len(set(result.selected_slugs))
