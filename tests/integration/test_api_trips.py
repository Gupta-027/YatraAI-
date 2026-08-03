"""End-to-end API tests over the real seeded catalogue and the real planner."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

PASSWORD = "correct-horse-battery"


def auth_headers(client, email: str, name: str = "Tester") -> dict:
    """Register, or sign in if the account already exists (fixtures reuse emails)."""
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": name},
    )
    if response.status_code == 409:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code in (200, 201), response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def trip_payload(**overrides) -> dict:
    start = date.today() + timedelta(days=30)
    payload = {
        "cluster_slug": "bengaluru",
        "title": "Test weekend",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=2)).isoformat(),
        "traveller_count": 3,
        "budget_per_person_inr": 12000,
        "pace": "balanced",
        "transport_mode": "car",
        "day_start_min": 540,
        "day_end_min": 1140,
        "owner_preferences": {
            "interests": {"heritage": 5, "museums": 4, "nature": 2},
            "pace": "balanced",
        },
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
class TestHealth:
    def test_health(self, api_client):
        response = api_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_ready_reports_provider_status(self, api_client):
        response = api_client.get("/ready")
        assert response.status_code == 200
        checks = response.json()["checks"]
        assert checks["database"] == "ok"
        assert "llm" in checks["providers"]

    def test_openapi_document_generates(self, api_client):
        response = api_client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        assert spec["info"]["title"] == "YatraAI API"
        assert "/api/v1/trips" in spec["paths"]


class TestDestinations:
    def test_lists_all_ten_clusters(self, api_client):
        response = api_client.get("/api/v1/destinations")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 10
        assert all(c["attraction_count"] >= 12 for c in body)

    def test_cluster_detail_includes_accessibility_summary(self, api_client):
        response = api_client.get("/api/v1/destinations/bengaluru")
        assert response.status_code == 200
        body = response.json()
        assert body["accessibility_summary"]["total"] >= 12
        assert body["categories"]

    def test_unknown_cluster_returns_404_with_a_code(self, api_client):
        response = api_client.get("/api/v1/destinations/atlantis")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "cluster_not_found"

    def test_attraction_list_filters(self, api_client):
        response = api_client.get(
            "/api/v1/destinations/bengaluru/attractions", params={"indoor_only": True}
        )
        assert response.status_code == 200
        assert all(a["indoor_outdoor"] in ("indoor", "mixed") for a in response.json())

    def test_attraction_detail_has_the_full_know_this_place_payload(self, api_client):
        response = api_client.get("/api/v1/destinations/delhi-agra/attractions/taj-mahal")
        assert response.status_code == 200
        body = response.json()
        assert len(body["history"]) > 200
        assert len(body["significance"]) > 100
        assert len(body["interesting_facts"]) >= 3
        assert body["sources"] and all(s["url"].startswith("https://") for s in body["sources"])
        assert body["schedules"]
        assert body["costs"]
        assert body["needs_verification"] is True
        assert body["dress_code"]
        assert body["accessibility_notes"]

    def test_time_sensitive_rows_are_marked_unverified(self, api_client):
        body = api_client.get("/api/v1/destinations/delhi-agra/attractions/taj-mahal").json()
        assert all(s["verified"] is False for s in body["schedules"])
        assert all(c["verified"] is False for c in body["costs"])

    def test_nearby_places_resolve_with_distances(self, api_client):
        body = api_client.get("/api/v1/destinations/delhi-agra/attractions/taj-mahal").json()
        assert body["nearby"]
        assert all(n["distance_km"] is not None for n in body["nearby"])


class TestAuth:
    def test_register_login_and_me(self, api_client):
        headers = auth_headers(api_client, "flow@example.com", "Flow")
        me = api_client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["email"] == "flow@example.com"

        login = api_client.post(
            "/api/v1/auth/login",
            json={"email": "flow@example.com", "password": "correct-horse-battery"},
        )
        assert login.status_code == 200

    def test_duplicate_email_rejected(self, api_client):
        auth_headers(api_client, "dupe@example.com")
        response = api_client.post(
            "/api/v1/auth/register",
            json={
                "email": "dupe@example.com",
                "password": "another-password-1",
                "display_name": "X",
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "email_taken"

    def test_wrong_password_rejected(self, api_client):
        auth_headers(api_client, "wrongpw@example.com")
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "wrongpw@example.com", "password": "not-the-password"},
        )
        assert response.status_code == 401

    def test_protected_route_requires_a_token(self, api_client):
        assert api_client.get("/api/v1/trips").status_code == 401

    def test_garbage_token_rejected(self, api_client):
        response = api_client.get("/api/v1/trips", headers={"Authorization": "Bearer not.a.token"})
        assert response.status_code == 401

    def test_service_status_endpoint(self, api_client):
        response = api_client.get("/api/v1/auth/service-status")
        assert response.status_code == 200
        assert "providers" in response.json()


class TestTripLifecycle:
    def test_create_trip(self, api_client):
        headers = auth_headers(api_client, "owner1@example.com", "Owner")
        response = api_client.post("/api/v1/trips", json=trip_payload(), headers=headers)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["cluster_slug"] == "bengaluru"
        assert body["duration_days"] == 3
        assert len(body["invite_code"]) == 8
        assert body["members"][0]["role"] == "owner"

    def test_invalid_dates_rejected(self, api_client):
        headers = auth_headers(api_client, "baddate@example.com")
        start = date.today() + timedelta(days=10)
        response = api_client.post(
            "/api/v1/trips",
            json=trip_payload(
                start_date=start.isoformat(),
                end_date=(start - timedelta(days=2)).isoformat(),
            ),
            headers=headers,
        )
        assert response.status_code == 422

    def test_too_short_a_day_rejected(self, api_client):
        headers = auth_headers(api_client, "shortday@example.com")
        response = api_client.post(
            "/api/v1/trips",
            json=trip_payload(day_start_min=600, day_end_min=660),
            headers=headers,
        )
        assert response.status_code == 422

    def test_unknown_cluster_rejected(self, api_client):
        headers = auth_headers(api_client, "badcluster@example.com")
        response = api_client.post(
            "/api/v1/trips", json=trip_payload(cluster_slug="atlantis"), headers=headers
        )
        assert response.status_code == 404

    def test_non_member_cannot_read_a_trip(self, api_client):
        owner = auth_headers(api_client, "owner2@example.com")
        trip_id = api_client.post("/api/v1/trips", json=trip_payload(), headers=owner).json()["id"]

        stranger = auth_headers(api_client, "stranger@example.com")
        response = api_client.get(f"/api/v1/trips/{trip_id}", headers=stranger)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_a_trip_member"

    def test_only_the_owner_can_update_settings(self, api_client):
        owner = auth_headers(api_client, "owner3@example.com")
        trip = api_client.post("/api/v1/trips", json=trip_payload(), headers=owner).json()

        member = auth_headers(api_client, "member3@example.com", "Member")
        api_client.post(
            "/api/v1/trips/join",
            json={"invite_code": trip["invite_code"]},
            headers=member,
        )
        response = api_client.patch(
            f"/api/v1/trips/{trip['id']}", json={"pace": "packed"}, headers=member
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "trip_owner_required"

    def test_join_with_invite_code_and_submit_preferences(self, api_client):
        owner = auth_headers(api_client, "owner4@example.com")
        trip = api_client.post("/api/v1/trips", json=trip_payload(), headers=owner).json()

        member = auth_headers(api_client, "member4@example.com", "Bela")
        joined = api_client.post(
            "/api/v1/trips/join",
            json={"invite_code": trip["invite_code"], "display_name": "Bela"},
            headers=member,
        )
        assert joined.status_code == 200
        assert len(joined.json()["members"]) == 2

        prefs = api_client.put(
            f"/api/v1/trips/{trip['id']}/preferences",
            json={
                "interests": {"nature": 5, "relaxation": 5, "heritage": 1},
                "pace": "relaxed",
                "mobility_level": "full",
            },
            headers=member,
        )
        assert prefs.status_code == 200
        assert prefs.json()["preferences_submitted"] == 2

    def test_invalid_invite_code_rejected(self, api_client):
        member = auth_headers(api_client, "badinvite@example.com")
        response = api_client.post(
            "/api/v1/trips/join", json={"invite_code": "ZZZZZZZZ"}, headers=member
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "invalid_invite_code"

    def test_unknown_interest_key_rejected(self, api_client):
        headers = auth_headers(api_client, "badpref@example.com")
        trip = api_client.post("/api/v1/trips", json=trip_payload(), headers=headers).json()
        response = api_client.put(
            f"/api/v1/trips/{trip['id']}/preferences",
            json={"interests": {"time_travel": 5}},
            headers=headers,
        )
        assert response.status_code == 422

    def test_invite_code_can_be_rotated(self, api_client):
        headers = auth_headers(api_client, "rotate@example.com")
        trip = api_client.post("/api/v1/trips", json=trip_payload(), headers=headers).json()
        rotated = api_client.post(
            f"/api/v1/trips/{trip['id']}/invite/rotate", headers=headers
        ).json()
        assert rotated["invite_code"] != trip["invite_code"]


class TestItineraryGeneration:
    @pytest.fixture
    def trip_with_group(self, api_client):
        owner = auth_headers(api_client, "grp-owner@example.com", "Asha")
        trip = api_client.post("/api/v1/trips", json=trip_payload(), headers=owner).json()

        member = auth_headers(api_client, "grp-member@example.com", "Ben")
        api_client.post(
            "/api/v1/trips/join",
            json={"invite_code": trip["invite_code"]},
            headers=member,
        )
        api_client.put(
            f"/api/v1/trips/{trip['id']}/preferences",
            json={"interests": {"nature": 5, "relaxation": 5, "heritage": 1, "museums": 1}},
            headers=member,
        )
        return trip, owner, member

    def test_generates_a_validated_itinerary(self, api_client, trip_with_group):
        trip, owner, _ = trip_with_group
        response = api_client.post(f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["validation"]["errors"] == []
        assert body["validation"]["checks_run"] >= 15
        assert len(body["days"]) == 3
        assert body["activity_count"] > 0

    def test_every_activity_has_an_explanation_and_times(self, api_client, trip_with_group):
        trip, owner, _ = trip_with_group
        body = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner
        ).json()
        visits = [a for d in body["days"] for a in d["activities"] if a["kind"] == "visit"]
        assert visits
        for activity in visits:
            assert activity["why_selected"]
            assert activity["start_time"] and activity["end_time"]
            assert activity["score_breakdown"]
            assert activity["duration_min"] > 0

    def test_cost_is_a_range_with_assumptions(self, api_client, trip_with_group):
        trip, owner, _ = trip_with_group
        body = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner
        ).json()
        cost = body["cost"]
        assert cost["per_person_low_inr"] < cost["per_person_high_inr"]
        assert "per person" in cost["display"]
        assert len(cost["assumptions"]) >= 5
        assert set(cost["breakdown"]) == {
            "accommodation",
            "food",
            "local_transport",
            "entry_charges",
            "contingency",
        }

    def test_fairness_metrics_are_reported(self, api_client, trip_with_group):
        trip, owner, _ = trip_with_group
        body = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner
        ).json()
        assert 0 < body["fairness_score"] <= 1
        assert body["least_satisfied_score"] > 0
        assert len(body["per_member_coverage"]) == 2

    def test_without_an_llm_the_explanation_is_template_based_and_says_so(
        self, api_client, trip_with_group
    ):
        trip, owner, _ = trip_with_group
        body = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner
        ).json()
        assert body["explanation_source"] == "template"
        assert body["summary_text"]
        assert "unverified" in body["summary_text"]

    def test_second_call_returns_the_existing_itinerary(self, api_client, trip_with_group):
        trip, owner, _ = trip_with_group
        first = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner
        ).json()
        second = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner
        ).json()
        assert first["id"] == second["id"]

    def test_force_regenerate_creates_a_new_version(self, api_client, trip_with_group):
        trip, owner, _ = trip_with_group
        first = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner
        ).json()
        second = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary",
            json={"force_regenerate": True},
            headers=owner,
        ).json()
        assert second["version"] == first["version"] + 1

    def test_greedy_generator_is_selectable(self, api_client, trip_with_group):
        trip, owner, _ = trip_with_group
        body = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary",
            json={"generator": "greedy"},
            headers=owner,
        ).json()
        assert body["generator"] == "greedy"
        assert body["is_valid"] is True

    def test_recommendations_expose_score_breakdowns(self, api_client, trip_with_group):
        trip, owner, _ = trip_with_group
        api_client.post(f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner)
        response = api_client.get(f"/api/v1/trips/{trip['id']}/recommendations", headers=owner)
        assert response.status_code == 200
        rows = response.json()
        assert rows
        top = rows[0]
        assert top["rank"] == 1
        assert set(top["components"]) >= {
            "interest_match",
            "group_fairness",
            "weather_suitability",
            "accessibility_suitability",
        }
        assert top["explanation"]
        assert top["per_member_scores"]

    def test_revalidation_endpoint(self, api_client, trip_with_group):
        trip, owner, _ = trip_with_group
        api_client.post(f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner)
        response = api_client.post(f"/api/v1/trips/{trip['id']}/itinerary/validate", headers=owner)
        assert response.status_code == 200
        assert response.json()["is_valid"] is True

    def test_no_itinerary_returns_a_clear_error(self, api_client):
        headers = auth_headers(api_client, "noitin@example.com")
        trip = api_client.post("/api/v1/trips", json=trip_payload(), headers=headers).json()
        response = api_client.get(f"/api/v1/trips/{trip['id']}/itinerary", headers=headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "no_itinerary"


class TestModification:
    @pytest.fixture
    def solo_trip(self, api_client):
        headers = auth_headers(api_client, "solo@example.com", "Solo")
        trip = api_client.post("/api/v1/trips", json=trip_payload(), headers=headers).json()
        itinerary = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=headers
        ).json()
        return trip, headers, itinerary

    def test_removing_a_place_applies_immediately_for_a_solo_trip(self, api_client, solo_trip):
        trip, headers, itinerary = solo_trip
        slug = next(
            a["attraction_slug"]
            for d in itinerary["days"]
            for a in d["activities"]
            if a["kind"] == "visit"
        )
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary/modify",
            json={"action": "remove_activity", "attraction_slug": slug},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["applied"] is True
        assert slug not in [
            a["attraction_slug"] for d in body["itinerary"]["days"] for a in d["activities"]
        ]
        assert body["validation"]["is_valid"] is True

    def test_reduce_cost_lowers_the_estimate(self, api_client, solo_trip):
        trip, headers, itinerary = solo_trip
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary/modify",
            json={"action": "reduce_cost", "budget_reduction_pct": 40},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["applied"] is True
        assert (
            body["itinerary"]["cost"]["per_person_high_inr"]
            <= itinerary["cost"]["per_person_high_inr"]
        )

    def test_make_relaxed_reduces_activity_count(self, api_client, solo_trip):
        trip, headers, itinerary = solo_trip
        body = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary/modify",
            json={"action": "make_day_relaxed"},
            headers=headers,
        ).json()
        assert body["itinerary"]["activity_count"] <= itinerary["activity_count"]

    def test_late_start_reschedules_the_day(self, api_client, solo_trip):
        trip, headers, _ = solo_trip
        body = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary/modify",
            json={"action": "shift_start_time", "new_start_min": 12 * 60},
            headers=headers,
        ).json()
        assert body["applied"] is True
        for day in body["itinerary"]["days"]:
            for activity in day["activities"]:
                assert activity["start_min"] >= 12 * 60

    def test_a_group_change_requires_approval(self, api_client):
        owner = auth_headers(api_client, "grpmod-owner@example.com")
        trip = api_client.post("/api/v1/trips", json=trip_payload(), headers=owner).json()
        member = auth_headers(api_client, "grpmod-member@example.com")
        api_client.post(
            "/api/v1/trips/join", json={"invite_code": trip["invite_code"]}, headers=member
        )
        itinerary = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner
        ).json()
        slug = next(
            a["attraction_slug"]
            for d in itinerary["days"]
            for a in d["activities"]
            if a["kind"] == "visit"
        )
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary/modify",
            json={"action": "remove_activity", "attraction_slug": slug},
            headers=owner,
        ).json()
        assert response["applied"] is False
        assert response["requires_group_approval"] is True
        assert response["proposal_id"]

    def test_diff_is_reported(self, api_client, solo_trip):
        trip, headers, itinerary = solo_trip
        slug = next(
            a["attraction_slug"]
            for d in itinerary["days"]
            for a in d["activities"]
            if a["kind"] == "visit"
        )
        body = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary/modify",
            json={"action": "remove_activity", "attraction_slug": slug},
            headers=headers,
        ).json()
        assert slug in body["diff"]["removed"]
        assert body["diff"]["summary"]

    def test_unknown_attraction_rejected(self, api_client, solo_trip):
        trip, headers, _ = solo_trip
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary/modify",
            json={"action": "remove_activity", "attraction_slug": "not-a-place"},
            headers=headers,
        )
        assert response.status_code == 404

    def test_missing_required_field_rejected(self, api_client, solo_trip):
        trip, headers, _ = solo_trip
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary/modify",
            json={"action": "regenerate_day"},
            headers=headers,
        )
        assert response.status_code == 422
