"""Persistent memoisation of routing legs.

A 12-point matrix is 66 unique legs; regenerating a day costs nothing once the
legs are cached. The cache is keyed on rounded coordinates (≈11 m at 4 decimal
places) plus mode, so near-identical requests reuse the same row.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from yatraai.db.models import RouteCacheEntry
from yatraai.logging_config import get_logger
from yatraai.services.routing.base import Coord, RouteMatrix, get_router

log = get_logger(__name__)

COORD_PRECISION = 4


def _key(a: Coord, b: Coord, mode: str, provider: str) -> str:
    # Undirected: normalise the endpoint order so A->B and B->A share a row.
    lo, hi = sorted(
        [
            (round(a[0], COORD_PRECISION), round(a[1], COORD_PRECISION)),
            (round(b[0], COORD_PRECISION), round(b[1], COORD_PRECISION)),
        ]
    )
    raw = f"{provider}|{mode}|{lo[0]},{lo[1]}|{hi[0]},{hi[1]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def cached_matrix(session: Session | None, points: list[Coord], mode: str = "car") -> RouteMatrix:
    """Build a matrix, reusing cached legs and persisting newly computed ones."""
    router = get_router()
    if session is None or len(points) < 2:
        return router.matrix(points, mode)

    n = len(points)
    distance = [[0.0] * n for _ in range(n)]
    duration = [[0.0] * n for _ in range(n)]
    missing: list[tuple[int, int]] = []
    hits = 0

    keys = {}
    for i in range(n):
        for j in range(i + 1, n):
            keys[(i, j)] = _key(points[i], points[j], mode, router.name)

    rows = {
        r.cache_key: r
        for r in session.scalars(
            select(RouteCacheEntry).where(RouteCacheEntry.cache_key.in_(list(keys.values())))
        )
    }

    for (i, j), key in keys.items():
        entry = rows.get(key)
        if entry is None:
            missing.append((i, j))
            continue
        hits += 1
        entry.hits += 1
        distance[i][j] = distance[j][i] = entry.distance_km
        duration[i][j] = duration[j][i] = entry.duration_min

    is_fallback = False
    notes: list[str] = []
    if missing:
        # Recompute the full matrix once rather than issuing per-leg requests.
        fresh = router.matrix(points, mode)
        is_fallback = fresh.is_fallback
        notes = fresh.notes
        for i, j in missing:
            km, minutes = fresh.leg(i, j)
            distance[i][j] = distance[j][i] = km
            duration[i][j] = duration[j][i] = minutes
            session.add(
                RouteCacheEntry(
                    cache_key=keys[(i, j)],
                    origin_lat=points[i][0],
                    origin_lon=points[i][1],
                    dest_lat=points[j][0],
                    dest_lon=points[j][1],
                    mode=mode,
                    provider=fresh.provider,
                    distance_km=km,
                    duration_min=minutes,
                    is_fallback=fresh.is_fallback,
                    hits=0,
                )
            )
        session.flush()

    log.debug("routing.cache", hits=hits, misses=len(missing), points=n)
    return RouteMatrix(
        points=points,
        distance_km=distance,
        duration_min=duration,
        provider=router.name,
        is_fallback=is_fallback,
        mode=mode,
        notes=notes,
    )


def prune_route_cache(session: Session, max_age_days: int = 30) -> dict:
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    result = session.execute(delete(RouteCacheEntry).where(RouteCacheEntry.updated_at < cutoff))
    return {"deleted": int(result.rowcount or 0), "max_age_days": max_age_days}
