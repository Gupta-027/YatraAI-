"""Weather snapshot cache.

Two jobs: keep planning fast (one provider call per cluster-day, not per trip),
and keep the demo working when the provider is unreachable. A cached snapshot is
always better than no forecast, and a stale one is labelled as such.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from yatraai.config import get_settings
from yatraai.db.models import DestinationCluster, Trip, WeatherSnapshot
from yatraai.logging_config import get_logger
from yatraai.services.planner.models import DayWeather
from yatraai.services.weather.base import get_weather_provider

log = get_logger(__name__)


def _to_snapshot(cluster_slug: str, lat: float, lon: float, w: DayWeather) -> WeatherSnapshot:
    return WeatherSnapshot(
        cluster_slug=cluster_slug,
        target_date=w.calendar_date,
        provider=w.provider,
        lat=lat,
        lon=lon,
        temp_min_c=w.temp_min_c,
        temp_max_c=w.temp_max_c,
        precipitation_mm=w.precipitation_mm,
        precipitation_probability=w.precipitation_probability,
        wind_kph=w.wind_kph,
        visibility_km=w.visibility_km,
        condition=w.condition,
        is_fallback=w.is_fallback,
        raw={},
        fetched_at=datetime.now(UTC),
    )


def _from_snapshot(row: WeatherSnapshot) -> DayWeather:
    return DayWeather(
        calendar_date=row.target_date,
        condition=row.condition,
        temp_min_c=row.temp_min_c,
        temp_max_c=row.temp_max_c,
        precipitation_mm=row.precipitation_mm,
        precipitation_probability=row.precipitation_probability,
        wind_kph=row.wind_kph,
        visibility_km=row.visibility_km,
        is_fallback=row.is_fallback,
        provider=row.provider,
    )


def cached_forecast(
    session: Session, cluster_slug: str, lat: float, lon: float, start: date, end: date
) -> list[DayWeather]:
    """Forecast for a date range, reusing fresh cached rows where possible."""
    s = get_settings()
    ttl = timedelta(seconds=s.weather_cache_ttl_seconds)
    now = datetime.now(UTC)

    rows = {
        row.target_date: row
        for row in session.scalars(
            select(WeatherSnapshot).where(
                WeatherSnapshot.cluster_slug == cluster_slug,
                WeatherSnapshot.target_date >= start,
                WeatherSnapshot.target_date <= end,
            )
        )
    }
    wanted = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    stale = [
        d
        for d in wanted
        if d not in rows or (rows[d].fetched_at is None or now - rows[d].fetched_at > ttl)
    ]

    if stale:
        fresh = get_weather_provider().daily_forecast(lat, lon, start, end, cluster_slug)
        for w in fresh:
            existing = rows.get(w.calendar_date)
            snapshot = _to_snapshot(cluster_slug, lat, lon, w)
            if existing is None:
                session.add(snapshot)
                rows[w.calendar_date] = snapshot
            else:
                for field in (
                    "provider",
                    "temp_min_c",
                    "temp_max_c",
                    "precipitation_mm",
                    "precipitation_probability",
                    "wind_kph",
                    "visibility_km",
                    "condition",
                    "is_fallback",
                    "fetched_at",
                ):
                    setattr(existing, field, getattr(snapshot, field))
        session.flush()

    return [_from_snapshot(rows[d]) for d in wanted if d in rows]


def refresh_upcoming_trip_weather(session: Session, horizon_days: int = 10) -> dict:
    """Warm the cache for every cluster with a trip starting soon."""
    today = date.today()
    horizon = today + timedelta(days=horizon_days)

    pairs = session.execute(
        select(
            DestinationCluster.slug, DestinationCluster.center_lat, DestinationCluster.center_lon
        )
        .join(Trip, Trip.cluster_id == DestinationCluster.id)
        .where(Trip.end_date >= today, Trip.start_date <= horizon)
        .distinct()
    ).all()

    refreshed = 0
    for slug, lat, lon in pairs:
        try:
            cached_forecast(session, slug, float(lat), float(lon), today, horizon)
            refreshed += 1
        except Exception as exc:  # pragma: no cover
            log.warning("weather.refresh_failed", cluster=slug, error=str(exc))

    log.info("weather.cache_refreshed", clusters=refreshed, horizon_days=horizon_days)
    return {"clusters_refreshed": refreshed, "horizon_days": horizon_days}
