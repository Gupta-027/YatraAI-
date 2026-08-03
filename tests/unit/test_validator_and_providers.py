"""The validator must catch broken plans, and providers must degrade honestly."""

from __future__ import annotations

from datetime import date

import pytest

from yatraai.services.planner.models import (
    AttractionCandidate,
    CostEstimate,
    OpeningWindow,
    PlannedActivity,
    PlannedDay,
    TripContext,
)
from yatraai.services.planner.validator import validate_plan
from yatraai.services.recommend.clustering import cluster_by_day
from yatraai.services.routing.base import HaversineRouter, OSRMRouter
from yatraai.services.routing.distance import estimate_leg, haversine_km
from yatraai.services.weather.base import SeedClimatologyProvider, advisories_for
from yatraai.services.weather.climatology import climatology_for


def make_candidate(slug="museum", opens=9 * 60, closes=18 * 60, **kw) -> AttractionCandidate:
    defaults = {
        "name": slug.title(),
        "lat": 12.97,
        "lon": 77.59,
        "categories": ["museum"],
        "typical_duration_min": 60,
        "min_duration_min": 40,
        "max_duration_min": 120,
        "windows": [OpeningWindow(-1, opens, closes)],
    }
    defaults.update(kw)
    return AttractionCandidate(slug=slug, **defaults)


def make_ctx(**kw) -> TripContext:
    defaults = {
        "trip_id": "t",
        "cluster_slug": "bengaluru",
        "start_date": date(2026, 11, 10),
        "end_date": date(2026, 11, 10),
        "day_start_min": 9 * 60,
        "day_end_min": 19 * 60,
        "base_lat": 12.9716,
        "base_lon": 77.5946,
    }
    defaults.update(kw)
    return TripContext(**defaults)


def make_day(activities, day_index=0, **kw) -> PlannedDay:
    defaults = {
        "day_index": day_index,
        "calendar_date": date(2026, 11, 10),
        "start_min": 9 * 60,
        "end_min": 19 * 60,
        "base_lat": 12.9716,
        "base_lon": 77.5946,
        "activities": activities,
    }
    defaults.update(kw)
    return PlannedDay(**defaults)


def visit(slug, start, end, travel=0, **kw) -> PlannedActivity:
    return PlannedActivity(
        kind="visit",
        sequence=kw.pop("sequence", 1),
        title=slug.title(),
        slug=slug,
        start_min=start,
        end_min=end,
        travel_from_prev_min=travel,
        **kw,
    )


# --------------------------------------------------------------------------- #
class TestValidatorCatchesBrokenPlans:
    def test_accepts_a_correct_plan(self):
        c = make_candidate()
        day = make_day([visit("museum", 10 * 60, 11 * 60, travel=15)])
        report = validate_plan([day], make_ctx(), {"museum": c})
        assert report.is_valid

    def test_rejects_overlapping_activities(self):
        c = make_candidate()
        c2 = make_candidate("gallery")
        day = make_day(
            [
                visit("museum", 10 * 60, 11 * 60, sequence=1),
                visit("gallery", 10 * 60 + 30, 11 * 60 + 30, sequence=2),
            ]
        )
        report = validate_plan([day], make_ctx(), {"museum": c, "gallery": c2})
        assert not report.is_valid
        assert any(i.code == "overlapping_activities" for i in report.errors)

    def test_rejects_a_visit_outside_opening_hours(self):
        c = make_candidate(opens=14 * 60, closes=17 * 60)
        day = make_day([visit("museum", 10 * 60, 11 * 60)])
        report = validate_plan([day], make_ctx(), {"museum": c})
        assert not report.is_valid
        assert any(i.code == "outside_opening_hours" for i in report.errors)

    def test_rejects_a_visit_on_a_closed_weekday(self):
        c = make_candidate(closed_weekdays={1})  # 2026-11-10 is a Tuesday
        day = make_day([visit("museum", 10 * 60, 11 * 60)])
        report = validate_plan([day], make_ctx(), {"museum": c})
        assert not report.is_valid
        assert any(i.code == "closed_on_this_day" for i in report.errors)

    def test_rejects_a_plan_that_ends_after_the_day_window(self):
        c = make_candidate(closes=23 * 60)
        day = make_day([visit("museum", 18 * 60 + 30, 20 * 60)])
        report = validate_plan([day], make_ctx(), {"museum": c})
        assert not report.is_valid
        assert any(i.code == "ends_after_day_window" for i in report.errors)

    def test_rejects_insufficient_travel_time(self):
        c1, c2 = make_candidate("a"), make_candidate("b")
        day = make_day(
            [
                visit("a", 10 * 60, 11 * 60, sequence=1),
                visit("b", 11 * 60, 12 * 60, travel=40, sequence=2),
            ]
        )
        report = validate_plan([day], make_ctx(), {"a": c1, "b": c2})
        assert not report.is_valid
        assert any(i.code == "insufficient_travel_time" for i in report.errors)

    def test_rejects_a_duplicate_visit_across_days(self):
        c = make_candidate()
        d1 = make_day([visit("museum", 10 * 60, 11 * 60)], day_index=0)
        d2 = make_day(
            [visit("museum", 10 * 60, 11 * 60)], day_index=1, calendar_date=date(2026, 11, 11)
        )
        report = validate_plan([d1, d2], make_ctx(end_date=date(2026, 11, 11)), {"museum": c})
        assert not report.is_valid
        assert any(i.code == "duplicate_visit" for i in report.errors)

    def test_rejects_a_visit_shorter_than_the_minimum(self):
        c = make_candidate()  # min 40 min
        day = make_day([visit("museum", 10 * 60, 10 * 60 + 20)])
        report = validate_plan([day], make_ctx(), {"museum": c})
        assert not report.is_valid
        assert any(i.code == "visit_too_short" for i in report.errors)

    def test_rejects_a_missing_mandatory_attraction(self):
        c = make_candidate()
        day = make_day([visit("museum", 10 * 60, 11 * 60)])
        ctx = make_ctx(must_visit_slugs=["fort"])
        report = validate_plan([day], ctx, {"museum": c, "fort": make_candidate("fort")})
        assert not report.is_valid
        assert any(i.code == "mandatory_attraction_missing" for i in report.errors)

    def test_rejects_an_accessibility_violation(self):
        c = make_candidate(wheelchair_accessible="no")
        day = make_day([visit("museum", 10 * 60, 11 * 60)])
        report = validate_plan([day], make_ctx(accessibility_required=True), {"museum": c})
        assert not report.is_valid
        assert any(i.code == "accessibility_violation" for i in report.errors)

    def test_rejects_an_empty_itinerary(self):
        report = validate_plan([make_day([])], make_ctx(), {})
        assert not report.is_valid
        assert any(i.code == "empty_itinerary" for i in report.errors)

    def test_warns_rather_than_blocks_on_budget_overrun(self):
        c = make_candidate()
        day = make_day([visit("museum", 10 * 60, 11 * 60)])
        cost = CostEstimate(50000, 60000, 25000, 30000, {}, [])
        report = validate_plan([day], make_ctx(budget_per_person_inr=10000), {"museum": c}, cost)
        assert report.is_valid  # a budget overrun is informative, not fatal
        assert any(i.code == "over_budget" for i in report.warnings)

    def test_warns_on_a_long_day_with_no_meal_break(self):
        c = make_candidate()
        day = make_day([visit("museum", 10 * 60, 11 * 60)])
        report = validate_plan([day], make_ctx(), {"museum": c})
        assert any(i.code == "no_meal_break" for i in report.warnings)

    def test_report_serialises_for_the_api(self):
        c = make_candidate()
        report = validate_plan(
            [make_day([visit("museum", 10 * 60, 11 * 60)])], make_ctx(), {"museum": c}
        )
        payload = report.to_dict()
        assert set(payload) == {"is_valid", "checks_run", "errors", "warnings"}


class TestDistanceModel:
    def test_haversine_matches_a_known_distance(self):
        # Bengaluru city centre to Nandi Hills is ~48 km straight-line.
        km = haversine_km(12.9716, 77.5946, 13.3702, 77.6835)
        assert 44 < km < 52

    def test_zero_distance_for_identical_points(self):
        assert haversine_km(12.9, 77.5, 12.9, 77.5) == 0.0

    def test_symmetry(self):
        a = haversine_km(12.9, 77.5, 13.4, 77.7)
        b = haversine_km(13.4, 77.7, 12.9, 77.5)
        assert a == pytest.approx(b)

    def test_road_distance_exceeds_straight_line(self):
        km, _ = estimate_leg(12.9716, 77.5946, 12.9507, 77.5848, "car")
        straight = haversine_km(12.9716, 77.5946, 12.9507, 77.5848)
        assert km > straight

    def test_walking_is_slower_than_driving(self):
        _, walk = estimate_leg(12.9716, 77.5946, 12.9507, 77.5848, "walk")
        _, drive = estimate_leg(12.9716, 77.5946, 12.9507, 77.5848, "car")
        assert walk > drive


class TestRouters:
    def test_haversine_matrix_is_symmetric_with_zero_diagonal(self):
        points = [(12.97, 77.59), (12.95, 77.58), (13.37, 77.68)]
        matrix = HaversineRouter().matrix(points, "car")
        assert matrix.is_fallback
        for i in range(3):
            assert matrix.distance_km[i][i] == 0.0
            for j in range(3):
                assert matrix.distance_km[i][j] == pytest.approx(matrix.distance_km[j][i])

    def test_haversine_matrix_documents_its_assumptions(self):
        matrix = HaversineRouter().matrix([(12.97, 77.59), (12.95, 77.58)])
        assert matrix.notes and "detour" in matrix.notes[0].lower()

    def test_osrm_falls_back_when_the_service_is_unreachable(self):
        router = OSRMRouter("http://127.0.0.1:9/unreachable", timeout=0.2)
        matrix = router.matrix([(12.97, 77.59), (12.95, 77.58)], "car")
        assert matrix.is_fallback
        assert matrix.provider == "haversine"
        assert any("unavailable" in n.lower() for n in matrix.notes)

    def test_osrm_with_a_single_point_degrades_gracefully(self):
        matrix = OSRMRouter("http://127.0.0.1:9", timeout=0.2).matrix([(12.97, 77.59)])
        assert matrix.size == 1


class TestWeatherFallback:
    def test_climatology_covers_every_cluster_and_month(self):
        from yatraai.services.weather.climatology import CLIMATOLOGY

        for slug, table in CLIMATOLOGY.items():
            assert set(table) == set(range(1, 13)), slug

    def test_seed_provider_is_flagged_as_fallback(self):
        days = SeedClimatologyProvider().daily_forecast(
            25.5788, 91.8933, date(2026, 7, 1), date(2026, 7, 3), "shillong-cherrapunji"
        )
        assert len(days) == 3
        assert all(d.is_fallback for d in days)

    def test_cherrapunji_monsoon_is_wetter_than_its_winter(self):
        july = climatology_for("shillong-cherrapunji", date(2026, 7, 15))
        january = climatology_for("shillong-cherrapunji", date(2026, 1, 15))
        assert july.precipitation_mm > january.precipitation_mm * 10
        assert july.is_wet and not january.is_wet

    def test_kedarnath_winter_is_below_freezing(self):
        january = climatology_for("kedarnath", date(2026, 1, 15))
        assert january.is_cold
        assert january.temp_min_c < 0

    def test_delhi_may_is_flagged_hot(self):
        assert climatology_for("delhi-agra", date(2026, 5, 15)).is_hot

    def test_unknown_cluster_uses_the_default_profile(self):
        day = climatology_for("not-a-cluster", date(2026, 3, 1))
        assert day.temp_max_c is not None
        assert day.is_fallback

    def test_advisories_disclose_that_fallback_data_is_in_use(self):
        day = climatology_for("gangtok", date(2026, 7, 10))
        messages = advisories_for(day, "gangtok")
        assert any("seasonal averages" in m for m in messages)
        assert any("Mountain roads" in m for m in messages)

    def test_no_advisories_on_a_pleasant_forecast(self):
        from yatraai.services.planner.models import DayWeather

        good = DayWeather(
            calendar_date=date(2026, 11, 10),
            condition="clear",
            temp_min_c=18,
            temp_max_c=28,
            precipitation_mm=0.0,
            precipitation_probability=0.02,
            wind_kph=8,
            visibility_km=15,
            is_fallback=False,
        )
        assert advisories_for(good, "bengaluru") == []


class TestGeographicClustering:
    def _scored(self, points):
        from yatraai.services.planner.models import ScoreBreakdown, ScoredAttraction

        return [
            ScoredAttraction(
                candidate=make_candidate(f"a{i}", lat=lat, lon=lon),
                total_score=1.0 - i * 0.01,
                breakdown=ScoreBreakdown(),
            )
            for i, (lat, lon) in enumerate(points)
        ]

    def test_separates_two_distinct_geographic_groups(self):
        west = [(12.95, 77.55), (12.96, 77.56), (12.94, 77.54)]
        east = [(12.98, 77.68), (12.99, 77.69), (12.97, 77.67)]
        clusters = cluster_by_day(self._scored(west + east), 2)
        assert len(clusters) == 2
        groups = [{m.slug for m in c.members} for c in clusters]
        # Each group should be internally consistent, not interleaved.
        assert any(len(g) == 3 for g in groups)

    def test_is_deterministic(self):
        points = [(12.95 + i * 0.01, 77.55 + i * 0.01) for i in range(8)]
        first = cluster_by_day(self._scored(points), 3)
        second = cluster_by_day(self._scored(points), 3)
        assert [sorted(m.slug for m in c.members) for c in first] == [
            sorted(m.slug for m in c.members) for c in second
        ]

    def test_every_attraction_lands_in_exactly_one_cluster(self):
        points = [(12.9 + i * 0.02, 77.5 + i * 0.02) for i in range(11)]
        clusters = cluster_by_day(self._scored(points), 4)
        assigned = [m.slug for c in clusters for m in c.members]
        assert len(assigned) == 11
        assert len(set(assigned)) == 11

    def test_balancing_avoids_a_one_stop_day(self):
        # Eight tightly grouped points plus one outlier.
        points = [(12.95 + i * 0.002, 77.55 + i * 0.002) for i in range(8)] + [(13.37, 77.68)]
        clusters = cluster_by_day(self._scored(points), 3)
        sizes = sorted(c.size for c in clusters)
        assert sizes[0] >= 1
        assert sizes[-1] <= 7  # no single day swallows everything

    def test_single_day_returns_one_cluster(self):
        clusters = cluster_by_day(self._scored([(12.9, 77.5), (12.95, 77.55)]), 1)
        assert len(clusters) == 1
        assert clusters[0].size == 2
