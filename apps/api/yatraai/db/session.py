"""Engine / session factory with SQLite-compatible defaults."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from yatraai.config import get_settings
from yatraai.logging_config import get_logger

log = get_logger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _configure_sqlite(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


def get_engine() -> Engine:
    global _engine
    if _engine is not None:
        return _engine

    s = get_settings()
    url = s.resolved_database_url
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(pool_size=5, max_overflow=10)

    _engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        event.listen(_engine, "connect", _configure_sqlite)
    log.info("db.engine.created", dialect=_engine.dialect.name)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts and pipelines."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def ensure_extensions() -> None:
    """Create pgvector / pg_trgm extensions when running on PostgreSQL."""
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for ext in ("vector", "pg_trgm"):
            try:
                conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
            except Exception as exc:  # pragma: no cover - permissions vary
                log.warning("db.extension.failed", extension=ext, error=str(exc))


def reset_engine() -> None:
    """Dispose cached engine/session factory (tests switch databases)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
