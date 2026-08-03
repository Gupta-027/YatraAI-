"""Shared pytest fixtures.

Every test runs against a fresh, file-backed SQLite database created from the
ORM metadata. That keeps the suite hermetic (no Docker, no network) while still
exercising real SQL, constraints and transactions.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Force fully-offline providers before any application module is imported.
os.environ.setdefault("YATRA_ENV", "test")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_PROVIDER", "hashing")
os.environ.setdefault("WEATHER_PROVIDER", "seed")
os.environ.setdefault("ROUTING_PROVIDER", "haversine")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-0123456789abcdef")

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def tmp_db_dir() -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix="yatraai-tests-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def _configure_test_database(tmp_db_dir: Path) -> Iterator[None]:
    os.environ["SQLITE_FALLBACK_PATH"] = str(tmp_db_dir / "test.sqlite3")
    from yatraai.config import reset_settings_cache
    from yatraai.db.session import reset_engine

    reset_settings_cache()
    reset_engine()
    yield
    reset_engine()


@pytest.fixture(scope="session")
def engine(_configure_test_database):
    from yatraai.db import models  # noqa: F401
    from yatraai.db.base import Base
    from yatraai.db.session import get_engine

    eng = get_engine()
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def db_session(engine) -> Iterator:
    """Function-scoped session wrapped in a transaction that is rolled back."""
    from sqlalchemy.orm import Session

    connection = engine.connect()
    trans = connection.begin()
    session = Session(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture(scope="session")
def seeded_engine(engine):
    """Engine with the curated seed catalogue + knowledge base loaded once."""
    from yatraai.db.session import get_session_factory
    from yatraai.seed.loader import load_all_seed_data

    session = get_session_factory()()
    try:
        load_all_seed_data(session, include_knowledge=True, build_embeddings=True)
        session.commit()
    finally:
        session.close()
    return engine


@pytest.fixture
def seeded_session(seeded_engine) -> Iterator:
    from sqlalchemy.orm import Session

    session = Session(bind=seeded_engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The limiter is process-global; without this, later tests hit 429 spuriously.

    Rate limiting itself is covered by dedicated tests in `tests/unit/test_security.py`
    against a fresh limiter instance, so clearing it here loses no coverage.
    """
    from yatraai.core.rate_limit import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def api_client(seeded_engine):
    """FastAPI TestClient bound to the seeded database."""
    from fastapi.testclient import TestClient

    from yatraai.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client
