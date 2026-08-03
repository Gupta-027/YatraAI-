"""Collaboration, consent-based location and privacy retention."""

from __future__ import annotations

from datetime import UTC, date, timedelta

import pytest

from tests.integration.test_api_trips import auth_headers, trip_payload


@pytest.fixture
def group(api_client):
    """A 2-member trip with a generated itinerary."""
    owner = auth_headers(api_client, "collab-owner@example.com", "Asha")
    trip = api_client.post("/api/v1/trips", json=trip_payload(), headers=owner).json()
    member = auth_headers(api_client, "collab-member@example.com", "Ben")
    api_client.post("/api/v1/trips/join", json={"invite_code": trip["invite_code"]}, headers=member)
    api_client.post(f"/api/v1/trips/{trip['id']}/itinerary", json={}, headers=owner)
    return trip, owner, member


class TestVoting:
    def test_cast_and_change_a_vote(self, api_client, group):
        trip, owner, _ = group
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/votes",
            json={"subject_type": "itinerary", "subject_id": trip["id"], "value": "up"},
            headers=owner,
        )
        assert response.status_code == 200
        assert response.json()["up"] == 1
        assert response.json()["my_vote"] == "up"

        changed = api_client.post(
            f"/api/v1/trips/{trip['id']}/votes",
            json={"subject_type": "itinerary", "subject_id": trip["id"], "value": "down"},
            headers=owner,
        ).json()
        assert changed["up"] == 0
        assert changed["down"] == 1

    def test_each_member_votes_once(self, api_client, group):
        trip, owner, member = group
        for headers in (owner, member):
            api_client.post(
                f"/api/v1/trips/{trip['id']}/votes",
                json={"subject_type": "attraction", "subject_id": "lalbagh", "value": "up"},
                headers=headers,
            )
        tally = api_client.get(
            f"/api/v1/trips/{trip['id']}/votes",
            params={"subject_type": "attraction", "subject_id": "lalbagh"},
            headers=owner,
        ).json()
        assert tally["up"] == 2
        assert tally["total_members"] == 2

    def test_non_member_cannot_vote(self, api_client, group):
        trip, _, _ = group
        stranger = auth_headers(api_client, "vote-stranger@example.com")
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/votes",
            json={"subject_type": "itinerary", "subject_id": trip["id"], "value": "up"},
            headers=stranger,
        )
        assert response.status_code == 403

    def test_invalid_vote_value_rejected(self, api_client, group):
        trip, owner, _ = group
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/votes",
            json={"subject_type": "itinerary", "subject_id": trip["id"], "value": "maybe"},
            headers=owner,
        )
        assert response.status_code == 422


class TestProposalApproval:
    def test_group_modification_creates_a_proposal_then_votes_apply_it(self, api_client, group):
        trip, owner, member = group
        itinerary = api_client.get(f"/api/v1/trips/{trip['id']}/itinerary", headers=owner).json()
        slug = next(
            a["attraction_slug"]
            for d in itinerary["days"]
            for a in d["activities"]
            if a["kind"] == "visit"
        )
        proposal = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary/modify",
            json={"action": "remove_activity", "attraction_slug": slug},
            headers=owner,
        ).json()
        assert proposal["requires_group_approval"] is True
        proposal_id = proposal["proposal_id"]

        listed = api_client.get(f"/api/v1/trips/{trip['id']}/proposals", headers=owner).json()
        assert any(p["id"] == proposal_id and p["status"] == "open" for p in listed)

        # Two members, so 2 approvals are required (n//2 + 1).
        for headers in (owner, member):
            api_client.post(
                f"/api/v1/trips/{trip['id']}/votes",
                json={"subject_type": "proposal", "subject_id": proposal_id, "value": "up"},
                headers=headers,
            )

        after = api_client.get(f"/api/v1/trips/{trip['id']}/proposals", headers=owner).json()
        applied = next(p for p in after if p["id"] == proposal_id)
        assert applied["status"] == "applied"

        current = api_client.get(f"/api/v1/trips/{trip['id']}/itinerary", headers=owner).json()
        assert slug not in [a["attraction_slug"] for d in current["days"] for a in d["activities"]]

    def test_owner_can_apply_a_proposal_directly(self, api_client, group):
        trip, owner, _ = group
        itinerary = api_client.get(f"/api/v1/trips/{trip['id']}/itinerary", headers=owner).json()
        slug = next(
            a["attraction_slug"]
            for d in itinerary["days"]
            for a in d["activities"]
            if a["kind"] == "visit"
        )
        proposal = api_client.post(
            f"/api/v1/trips/{trip['id']}/itinerary/modify",
            json={"action": "remove_activity", "attraction_slug": slug},
            headers=owner,
        ).json()
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/proposals/{proposal['proposal_id']}/apply",
            headers=owner,
        )
        assert response.status_code == 200
        assert response.json()["applied"] is True


class TestChat:
    def test_post_and_read_messages(self, api_client, group):
        trip, owner, member = group
        posted = api_client.post(
            f"/api/v1/trips/{trip['id']}/chat",
            json={"body": "Shall we start earlier on day two?"},
            headers=owner,
        )
        assert posted.status_code == 201

        history = api_client.get(f"/api/v1/trips/{trip['id']}/chat", headers=member).json()
        assert any(m["body"] == "Shall we start earlier on day two?" for m in history)
        assert history[-1]["is_mine"] is False

    def test_html_is_stripped_from_messages(self, api_client, group):
        trip, owner, _ = group
        posted = api_client.post(
            f"/api/v1/trips/{trip['id']}/chat",
            json={"body": "<script>alert(1)</script>Hello team"},
            headers=owner,
        ).json()
        assert "<script>" not in posted["body"]
        assert "Hello team" in posted["body"]

    def test_empty_message_rejected(self, api_client, group):
        trip, owner, _ = group
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/chat", json={"body": "   "}, headers=owner
        )
        assert response.status_code in (422,)

    def test_non_member_cannot_read_chat(self, api_client, group):
        trip, _, _ = group
        stranger = auth_headers(api_client, "chat-stranger@example.com")
        assert (
            api_client.get(f"/api/v1/trips/{trip['id']}/chat", headers=stranger).status_code == 403
        )


class TestLocationConsent:
    def test_consent_text_is_published(self, api_client, group):
        trip, owner, _ = group
        response = api_client.get(
            f"/api/v1/trips/{trip['id']}/location/consent-text", headers=owner
        )
        assert response.status_code == 200
        body = response.json()
        assert body["version"]
        assert "opt-in" in " ".join(body["guarantees"]).lower()

    def test_sharing_requires_explicit_consent(self, api_client, group):
        trip, owner, _ = group
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/location/start",
            json={"consent_granted": False},
            headers=owner,
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "consent_required"

    def test_posting_a_point_without_a_session_is_refused(self, api_client, group):
        trip, _, member = group
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/location/point",
            json={"lat": 12.97, "lon": 77.59},
            headers=member,
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "sharing_not_active"

    def test_approximate_mode_snaps_before_storage(self, api_client, group):
        trip, owner, _ = group
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/start",
            json={"consent_granted": True, "precision": "approximate"},
            headers=owner,
        )
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/point",
            json={"lat": 12.971598, "lon": 77.594566},
            headers=owner,
        )
        group_state = api_client.get(
            f"/api/v1/trips/{trip['id']}/location/group", headers=owner
        ).json()
        stored = group_state["positions"][0]
        assert stored["is_approximate"] is True
        # Snapped to the ~500 m grid, so the exact position was never stored.
        assert stored["lat"] != pytest.approx(12.971598)
        assert abs(stored["lat"] - 12.971598) < 0.005

    def test_exact_mode_is_opt_in_and_recorded_as_such(self, api_client, group):
        trip, _, member = group
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/start",
            json={"consent_granted": True, "precision": "exact"},
            headers=member,
        )
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/point",
            json={"lat": 12.9507, "lon": 77.5848},
            headers=member,
        )
        state = api_client.get(f"/api/v1/trips/{trip['id']}/location/group", headers=member).json()
        mine = next(p for p in state["positions"] if p["display_name"] == "Ben")
        assert mine["is_approximate"] is False
        assert mine["lat"] == pytest.approx(12.9507)

    def test_stopping_deletes_the_trail_immediately(self, api_client, group):
        trip, owner, _ = group
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/start",
            json={"consent_granted": True},
            headers=owner,
        )
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/point",
            json={"lat": 12.97, "lon": 77.59},
            headers=owner,
        )
        before = api_client.get(f"/api/v1/trips/{trip['id']}/location/group", headers=owner).json()
        assert before["sharing_members"] >= 1

        api_client.delete(f"/api/v1/trips/{trip['id']}/location", headers=owner)
        after = api_client.get(f"/api/v1/trips/{trip['id']}/location/group", headers=owner).json()
        assert all(p["display_name"] != "Asha" for p in after["positions"])

    def test_pause_hides_the_member_from_the_group_map(self, api_client, group):
        trip, owner, _ = group
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/start",
            json={"consent_granted": True},
            headers=owner,
        )
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/point",
            json={"lat": 12.97, "lon": 77.59},
            headers=owner,
        )
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/status",
            json={"status": "paused"},
            headers=owner,
        )
        state = api_client.get(f"/api/v1/trips/{trip['id']}/location/group", headers=owner).json()
        assert all(p["display_name"] != "Asha" for p in state["positions"])

    def test_update_interval_floor_enforced(self, api_client, group):
        trip, owner, _ = group
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/location/start",
            json={"consent_granted": True, "update_interval_seconds": 5},
            headers=owner,
        )
        assert response.status_code == 422

    def test_session_duration_is_capped(self, api_client, group):
        trip, owner, _ = group
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/location/start",
            json={"consent_granted": True, "duration_hours": 99},
            headers=owner,
        )
        assert response.status_code == 422


class TestGroupMap:
    def test_separation_warning_and_meeting_point(self, api_client, group):
        trip, owner, member = group
        for headers, (lat, lon) in ((owner, (12.9716, 77.5946)), (member, (13.0500, 77.7000))):
            api_client.post(
                f"/api/v1/trips/{trip['id']}/location/start",
                json={"consent_granted": True, "precision": "exact"},
                headers=headers,
            )
            api_client.post(
                f"/api/v1/trips/{trip['id']}/location/point",
                json={"lat": lat, "lon": lon},
                headers=headers,
            )
        state = api_client.get(f"/api/v1/trips/{trip['id']}/location/group", headers=owner).json()
        assert state["sharing_members"] == 2
        assert state["max_separation_km"] > 1.5
        assert state["separation_warning"] is True
        assert state["suggested_meeting_point"]["label"]
        assert state["centroid"]

    def test_eta_to_next_activity_is_reported(self, api_client, group):
        trip, owner, _ = group
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/start",
            json={"consent_granted": True, "precision": "exact"},
            headers=owner,
        )
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/point",
            json={"lat": 12.9716, "lon": 77.5946},
            headers=owner,
        )
        state = api_client.get(f"/api/v1/trips/{trip['id']}/location/group", headers=owner).json()
        if state.get("next_activity"):
            assert state["eta_to_next"]
            assert state["eta_to_next"][0]["eta_minutes"] >= 0


class TestRetention:
    def test_purge_deletes_expired_points(self, db_session):
        from datetime import datetime

        from yatraai.db.models import (
            DestinationCluster,
            LocationPoint,
            LocationSharingSession,
            Trip,
            TripMember,
            User,
        )
        from yatraai.services.location import purge_expired_location_data

        cluster = db_session.scalar(__import__("sqlalchemy").select(DestinationCluster).limit(1))
        user = User(email="purge@example.com", display_name="P")
        db_session.add(user)
        db_session.flush()
        trip = Trip(
            owner_id=user.id,
            cluster_id=cluster.id,
            title="T",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=1),
            invite_code="PURGE123",
        )
        db_session.add(trip)
        db_session.flush()
        member = TripMember(trip_id=trip.id, user_id=user.id, display_name="P")
        db_session.add(member)
        db_session.flush()

        now = datetime.now(UTC)
        sharing = LocationSharingSession(
            trip_id=trip.id,
            member_id=member.id,
            consent_granted_at=now,
            expires_at=now + timedelta(hours=1),
        )
        db_session.add(sharing)
        db_session.flush()

        db_session.add(
            LocationPoint(
                session_id=sharing.id,
                trip_id=trip.id,
                member_id=member.id,
                lat=12.9,
                lon=77.6,
                recorded_at=now - timedelta(hours=5),
                expires_at=now - timedelta(hours=1),  # already expired
            )
        )
        db_session.add(
            LocationPoint(
                session_id=sharing.id,
                trip_id=trip.id,
                member_id=member.id,
                lat=12.9,
                lon=77.6,
                recorded_at=now,
                expires_at=now + timedelta(hours=1),  # still live
            )
        )
        db_session.flush()

        stats = purge_expired_location_data(db_session)
        assert stats["points_deleted"] >= 1

    def test_approximation_helper_snaps_consistently(self):
        from yatraai.services.location import approximate

        a = approximate(12.971598, 77.594566)
        b = approximate(12.971601, 77.594570)
        assert a == b


class TestSos:
    def test_sos_requires_demo_acknowledgement(self, api_client, group):
        trip, owner, _ = group
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/sos",
            json={"message": "help", "acknowledge_demo": False},
            headers=owner,
        )
        assert response.status_code == 422

    def test_sos_is_clearly_labelled_a_demo(self, api_client, group):
        trip, owner, _ = group
        response = api_client.post(
            f"/api/v1/trips/{trip['id']}/sos",
            json={"message": "Lost near the lake", "acknowledge_demo": True},
            headers=owner,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["is_demo"] is True
        assert "does not contact emergency services" in body["disclaimer"]

    def test_sos_posts_a_system_chat_message(self, api_client, group):
        trip, owner, member = group
        api_client.post(
            f"/api/v1/trips/{trip['id']}/sos",
            json={"acknowledge_demo": True},
            headers=owner,
        )
        chat = api_client.get(f"/api/v1/trips/{trip['id']}/chat", headers=member).json()
        assert any(m["kind"] == "system" and "DEMO SOS" in m["body"] for m in chat)


class TestAnalyticsApi:
    def test_dashboard_returns_aggregates(self, api_client, group):
        response = api_client.get("/api/v1/analytics/dashboard")
        assert response.status_code == 200
        body = response.json()
        assert body["trips"]["total"] >= 1
        assert body["destination_popularity"]
        assert "constraint_violation_rate" in body["itineraries"]

    def test_dashboard_never_exposes_coordinates(self, api_client, group):
        trip, owner, _ = group
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/start",
            json={"consent_granted": True, "precision": "exact"},
            headers=owner,
        )
        api_client.post(
            f"/api/v1/trips/{trip['id']}/location/point",
            json={"lat": 12.9716, "lon": 77.5946},
            headers=owner,
        )
        body = api_client.get("/api/v1/analytics/dashboard").text
        assert "12.9716" not in body
        assert "77.5946" not in body

    def test_spend_accuracy_is_not_invented_without_data(self, api_client):
        body = api_client.get("/api/v1/analytics/dashboard").json()
        comparison = body["feedback"]["spend_comparison"]
        if comparison["samples"] == 0:
            assert "have not measured" in comparison["note"]

    def test_trip_analytics(self, api_client, group):
        trip, owner, _ = group
        response = api_client.get(f"/api/v1/analytics/trips/{trip['id']}", headers=owner)
        assert response.status_code == 200
        body = response.json()
        assert body["versions"]
        assert body["current"]["fairness"] >= 0

    def test_feedback_submission(self, api_client, group):
        trip, owner, _ = group
        response = api_client.post(
            "/api/v1/feedback",
            json={
                "trip_id": trip["id"],
                "rating": 5,
                "accepted": True,
                "actual_spend_inr": 11500,
                "comment": "Worked well",
            },
            headers=owner,
        )
        assert response.status_code == 201

    def test_admin_routes_require_admin(self, api_client, group):
        _, owner, _ = group
        assert api_client.get("/api/v1/admin/data-quality", headers=owner).status_code == 403

    def test_metrics_endpoint(self, api_client):
        response = api_client.get("/api/v1/metrics")
        assert response.status_code == 200
        assert "providers" in response.json()
