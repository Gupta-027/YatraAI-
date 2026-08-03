"""Alembic environment - reads the URL from application settings."""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from yatraai.config import get_settings
from yatraai.db import models
from yatraai.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.resolved_database_url)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.resolved_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=settings.resolved_database_url.startswith("sqlite"),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            from sqlalchemy import text

            for ext in ("vector", "pg_trgm"):
                try:
                    connection.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
                    connection.commit()
                except Exception:  # pragma: no cover
                    connection.rollback()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
            render_as_batch=connection.dialect.name == "sqlite",
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
