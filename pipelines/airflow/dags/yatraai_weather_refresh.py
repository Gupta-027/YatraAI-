"""Airflow DAG: refresh cached weather for active trips and purge expired location data.

Runs frequently and cheaply. Two responsibilities:

1. **Weather cache warm-up** - pre-fetch forecasts for every cluster that has an
   upcoming trip so the planner never blocks on a provider call, and so the demo
   still works when Open-Meteo is unreachable.
2. **Privacy retention** - hard-delete location points past their retention
   window and expire stale sharing sessions. This is a compliance task, not a
   nice-to-have: see ``docs/privacy.md``.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.decorators import dag, task

REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "apps" / "api"
for path in (str(API_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

DEFAULT_ARGS = {
    "owner": "yatraai-data",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "execution_timeout": timedelta(minutes=10),
}


@dag(
    dag_id="yatraai_weather_and_retention",
    description="Warm the weather cache and enforce location-data retention",
    schedule="0 */6 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["yatraai", "weather", "privacy"],
    doc_md=__doc__,
)
def yatraai_weather_and_retention():
    @task(task_id="refresh_weather_cache")
    def refresh_weather() -> dict:
        from yatraai.db.session import session_scope
        from yatraai.services.weather.cache import refresh_upcoming_trip_weather

        with session_scope() as session:
            return refresh_upcoming_trip_weather(session, horizon_days=10)

    @task(task_id="purge_expired_location_data")
    def purge() -> dict:
        from yatraai.db.session import session_scope
        from yatraai.services.location import purge_expired_location_data

        with session_scope() as session:
            return purge_expired_location_data(session)

    @task(task_id="prune_route_cache")
    def prune_routes() -> dict:
        from yatraai.db.session import session_scope
        from yatraai.services.routing.cache import prune_route_cache

        with session_scope() as session:
            return prune_route_cache(session, max_age_days=30)

    refresh_weather()
    purge()
    prune_routes()


dag_instance = yatraai_weather_and_retention()
