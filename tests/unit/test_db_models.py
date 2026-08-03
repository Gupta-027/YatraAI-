"""Schema-level guarantees: constraints, portable types, cascades."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from yatraai.db.models import (
    Attraction,
    ChunkEmbedding,
    DestinationCluster,
    DocumentChunk,
    LocationPoint,
    LocationSharingSession,
    SourceDocument,
    Trip,
    TripMember,
    User,
)


def _cluster(**kw) -> DestinationCluster:
    defaults = dict(
        slug=f"cluster-{uuid.uuid4().hex[:6]}",
        name="Test Cluster",
        state="Karnataka",
        region="south",
        summary="A test cluster.",
        travel_style=["metro"],
        center_lat=12.97,
        center_lon=77.59,
        best_months=[10, 11, 12],
        avoid_months=[5],
        daily_cost_baseline={"budget": 1500},
    )
    defaults.update(kw)
    return DestinationCluster(**defaults)


def _attraction(cluster_id, **kw) -> Attraction:
    defaults = dict(
        cluster_id=cluster_id,
        slug=f"attr-{uuid.uuid4().hex[:6]}",
        name="Test Attraction",
        locality="Central",
        city="Bengaluru",
        lat=12.98,
        lon=77.60,
        categories=["heritage"],
        summary="A place.",
        interesting_facts=["fact one"],
    )
    defaults.update(kw)
    return Attraction(**defaults)


class TestPortableTypes:
    def test_json_columns_roundtrip_nested_structures(self, db_session):
        c = _cluster(daily_cost_baseline={"budget": {"food": 400, "stay": 900}, "tiers": [1, 2]})
        db_session.add(c)
        db_session.flush()
        db_session.expire_all()
        loaded = db_session.get(DestinationCluster, c.id)
        assert loaded.daily_cost_baseline["budget"]["food"] == 400
        assert loaded.daily_cost_baseline["tiers"] == [1, 2]

    def test_uuid_primary_keys_are_uuid_objects(self, db_session):
        c = _cluster()
        db_session.add(c)
        db_session.flush()
        db_session.expire_all()
        assert isinstance(db_session.get(DestinationCluster, c.id).id, uuid.UUID)

    def test_datetimes_come_back_timezone_aware_utc(self, db_session):
        c = _cluster()
        db_session.add(c)
        db_session.flush()
        db_session.expire_all()
        loaded = db_session.get(DestinationCluster, c.id)
        assert loaded.created_at.tzinfo is not None
        assert loaded.created_at.utcoffset() == timedelta(0)

    def test_vector_column_roundtrip(self, db_session):
        doc = SourceDocument(
            doc_key=f"doc-{uuid.uuid4().hex[:6]}",
            cluster_slug="bengaluru",
            title="T",
            content_category="history",
            body="B",
            source_url="https://example.gov.in/a",
            content_hash="h",
        )
        db_session.add(doc)
        db_session.flush()
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            text="chunk text",
            cluster_slug="bengaluru",
            content_category="history",
            source_url="https://example.gov.in/a",
            content_hash="h",
        )
        db_session.add(chunk)
        db_session.flush()
        vec = [round(i / 384, 6) for i in range(384)]
        db_session.add(
            ChunkEmbedding(
                chunk_id=chunk.id, provider="hashing", model="hash-384", dim=384, vector=vec
            )
        )
        db_session.flush()
        db_session.expire_all()
        loaded = db_session.query(ChunkEmbedding).filter_by(chunk_id=chunk.id).one()
        assert len(loaded.vector) == 384
        assert loaded.vector[10] == pytest.approx(vec[10])


class TestConstraints:
    def test_attraction_latitude_range_enforced(self, db_session):
        c = _cluster()
        db_session.add(c)
        db_session.flush()
        db_session.add(_attraction(c.id, lat=120.0))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_attraction_slug_unique_within_cluster(self, db_session):
        c = _cluster()
        db_session.add(c)
        db_session.flush()
        db_session.add(_attraction(c.id, slug="dup"))
        db_session.flush()
        db_session.add(_attraction(c.id, slug="dup"))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_same_slug_allowed_in_different_clusters(self, db_session):
        c1, c2 = _cluster(), _cluster()
        db_session.add_all([c1, c2])
        db_session.flush()
        db_session.add_all([_attraction(c1.id, slug="fort"), _attraction(c2.id, slug="fort")])
        db_session.flush()  # must not raise

    def test_trip_end_date_must_not_precede_start(self, db_session):
        c = _cluster()
        u = User(email=f"{uuid.uuid4().hex[:6]}@x.com", display_name="U")
        db_session.add_all([c, u])
        db_session.flush()
        db_session.add(
            Trip(
                owner_id=u.id,
                cluster_id=c.id,
                title="Bad dates",
                start_date=date(2026, 3, 10),
                end_date=date(2026, 3, 8),
                invite_code="ABCD1234",
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_location_session_interval_floor(self, db_session):
        c = _cluster()
        u = User(email=f"{uuid.uuid4().hex[:6]}@x.com", display_name="U")
        db_session.add_all([c, u])
        db_session.flush()
        trip = Trip(
            owner_id=u.id,
            cluster_id=c.id,
            title="T",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 3),
            invite_code=uuid.uuid4().hex[:8].upper(),
        )
        db_session.add(trip)
        db_session.flush()
        member = TripMember(trip_id=trip.id, user_id=u.id, display_name="U", role="owner")
        db_session.add(member)
        db_session.flush()
        now = datetime.now(UTC)
        db_session.add(
            LocationSharingSession(
                trip_id=trip.id,
                member_id=member.id,
                consent_granted_at=now,
                expires_at=now + timedelta(hours=2),
                update_interval_seconds=5,  # below the 15s floor
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestCascades:
    def test_deleting_cluster_removes_attractions(self, db_session):
        c = _cluster()
        db_session.add(c)
        db_session.flush()
        db_session.add_all([_attraction(c.id) for _ in range(3)])
        db_session.flush()
        assert db_session.query(Attraction).filter_by(cluster_id=c.id).count() == 3
        db_session.delete(c)
        db_session.flush()
        assert db_session.query(Attraction).filter_by(cluster_id=c.id).count() == 0

    def test_deleting_session_removes_location_points(self, db_session):
        c = _cluster()
        u = User(email=f"{uuid.uuid4().hex[:6]}@x.com", display_name="U")
        db_session.add_all([c, u])
        db_session.flush()
        trip = Trip(
            owner_id=u.id,
            cluster_id=c.id,
            title="T",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 3),
            invite_code=uuid.uuid4().hex[:8].upper(),
        )
        db_session.add(trip)
        db_session.flush()
        member = TripMember(trip_id=trip.id, user_id=u.id, display_name="U")
        db_session.add(member)
        db_session.flush()
        now = datetime.now(UTC)
        sess = LocationSharingSession(
            trip_id=trip.id,
            member_id=member.id,
            consent_granted_at=now,
            expires_at=now + timedelta(hours=2),
        )
        db_session.add(sess)
        db_session.flush()
        db_session.add(
            LocationPoint(
                session_id=sess.id,
                trip_id=trip.id,
                member_id=member.id,
                lat=12.9,
                lon=77.6,
                recorded_at=now,
                expires_at=now + timedelta(minutes=120),
            )
        )
        db_session.flush()
        assert db_session.query(LocationPoint).filter_by(session_id=sess.id).count() == 1
        db_session.delete(sess)
        db_session.flush()
        assert db_session.query(LocationPoint).filter_by(session_id=sess.id).count() == 0


def test_trip_duration_days_property(db_session):
    trip = Trip(
        owner_id=uuid.uuid4(),
        cluster_id=uuid.uuid4(),
        title="T",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 4),
        invite_code="X",
    )
    assert trip.duration_days == 4
