#!/usr/bin/env sh
# Applies migrations, seeds the catalogue on first boot, then execs the CMD.
set -e

echo "[entrypoint] YATRA_ENV=${YATRA_ENV:-development}"

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "[entrypoint] applying database migrations..."
  ( cd /app/apps/api && alembic upgrade head )
fi

if [ "${RUN_SEED:-1}" = "1" ]; then
  echo "[entrypoint] loading seed catalogue (idempotent)..."
  python -m yatraai.cli seed --knowledge --embeddings || echo "[entrypoint] seed skipped/failed (non-fatal)"
fi

echo "[entrypoint] starting: $*"
exec "$@"
