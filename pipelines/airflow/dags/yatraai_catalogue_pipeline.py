"""Airflow DAG: Bronze -> Silver -> Gold catalogue refresh.

Airflow is **optional for development**. The identical transformations run from
the CLI with ``python -m yatraai.cli pipeline --all`` (or ``make pipeline``), so
a reviewer never needs to start a scheduler. This DAG is what would run the same
code on a schedule in production.

Deployment note: add the repository root and ``apps/api`` to Airflow's
``PYTHONPATH`` (see ``pipelines/airflow/README.md``).
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.decorators import dag, task
from airflow.operators.empty import EmptyOperator

REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "apps" / "api"
for path in (str(API_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

DEFAULT_ARGS = {
    "owner": "yatraai-data",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=20),
    "execution_timeout": timedelta(minutes=30),
    "depends_on_past": False,
}


@dag(
    dag_id="yatraai_catalogue_pipeline",
    description="Refresh the destination catalogue through Bronze, Silver and Gold layers",
    schedule="0 3 * * *",  # 03:00 UTC daily
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["yatraai", "catalogue", "medallion"],
    doc_md=__doc__,
)
def yatraai_catalogue_pipeline():
    start = EmptyOperator(task_id="start")

    @task(task_id="bronze_land_raw_records")
    def bronze() -> dict:
        """Land seed files verbatim with ingestion timestamps and content hashes."""
        from yatraai.pipelines import medallion

        result = medallion.run_bronze()
        return {
            "rows_out": result.rows_out,
            "rows_rejected": result.rows_rejected,
            "checks": result.checks,
        }

    @task(task_id="silver_clean_and_validate")
    def silver(_bronze: dict) -> dict:
        """Normalise, deduplicate and validate against the Pandera contracts."""
        from yatraai.pipelines import medallion

        results = medallion.run_silver()
        return {name: r.rows_out for name, r in results.items()}

    @task(task_id="gold_build_features")
    def gold(_silver: dict) -> dict:
        """Derive recommendation features and cluster analytics tables."""
        from yatraai.pipelines import medallion

        results = medallion.run_gold()
        return {name: r.rows_out for name, r in results.items()}

    @task(task_id="load_into_application_database")
    def load(_gold: dict) -> dict:
        """Idempotent upsert into the operational database."""
        from yatraai.db.session import session_scope
        from yatraai.seed.loader import load_all_seed_data

        with session_scope() as session:
            return load_all_seed_data(session, include_knowledge=True, build_embeddings=True)

    @task(task_id="data_quality_gate")
    def quality_gate(load_counts: dict) -> dict:
        """Fail the run loudly rather than serve a silently degraded catalogue."""
        from yatraai.services.data_quality import run_quality_checks

        report = run_quality_checks()
        failures = [c for c in report["checks"] if c["severity"] == "error" and not c["passed"]]
        if failures:
            raise ValueError(f"Data quality gate failed: {[f['name'] for f in failures]}")
        return {"loaded": load_counts, "checks_passed": len(report["checks"]) - len(failures)}

    @task(task_id="record_freshness")
    def record_freshness(gate: dict) -> dict:
        from yatraai.services.analytics import record_pipeline_freshness

        return record_pipeline_freshness(gate)

    done = EmptyOperator(task_id="done")

    b = bronze()
    s = silver(b)
    g = gold(s)
    ld = load(g)
    gate = quality_gate(ld)
    start >> b
    record_freshness(gate) >> done


dag_instance = yatraai_catalogue_pipeline()
