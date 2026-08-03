"""Bronze/Silver/Gold data pipeline. Importable without Airflow."""

from yatraai.pipelines.medallion import run_all, run_bronze, run_gold, run_silver

__all__ = ["run_all", "run_bronze", "run_gold", "run_silver"]
