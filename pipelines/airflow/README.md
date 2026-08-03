# Airflow pipelines

> **Airflow is optional.** Everything these DAGs do can be run directly:
> ```bash
> make pipeline      # bronze -> silver -> gold
> make seed          # load catalogue + knowledge base
> ```
> The DAGs call the *same* functions (`yatraai.pipelines.medallion`,
> `yatraai.seed.loader`), so there is no second implementation to drift.

## DAGs

| DAG | Schedule | Purpose |
|---|---|---|
| `yatraai_catalogue_pipeline` | `0 3 * * *` | Bronze → Silver → Gold → load → data-quality gate |
| `yatraai_weather_and_retention` | `0 */6 * * *` | Warm the weather cache; enforce location retention; prune route cache |

## Reliability behaviour

* **Retries** — 3 attempts with exponential backoff (2 → 20 min) on the catalogue DAG.
* **Idempotency** — every task can be re-run safely. Bronze is content-hashed,
  Silver/Gold overwrite deterministically, and the loader upserts on natural keys.
* **Incremental knowledge loading** — a knowledge document whose `content_hash`
  is unchanged keeps its chunks and embeddings, so a reseed does not re-embed the
  whole corpus.
* **Quality gate** — the DAG raises if any `error`-severity check fails, so a bad
  dataset never reaches the planner.
* **`max_active_runs=1`** — prevents concurrent writers to the same tables.

## Running locally

```bash
python -m venv .venv-airflow && . .venv-airflow/bin/activate   # separate venv: Airflow pins are strict
pip install "apache-airflow==2.10.*" --constraint \
  "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.2/constraints-3.11.txt"
pip install -e .

export AIRFLOW_HOME="$PWD/pipelines/airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/pipelines/airflow/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export PYTHONPATH="$PWD/apps/api:$PWD"
export DATABASE_URL="postgresql+psycopg://yatra:yatra@localhost:5432/yatraai"

airflow db migrate
airflow standalone           # UI at http://localhost:8080
```

Verify a DAG parses without a scheduler:

```bash
python pipelines/airflow/dags/yatraai_catalogue_pipeline.py   # no output == parsed cleanly
```

## Production alternative (free-tier friendly)

A scheduler is heavy for a portfolio deployment. The committed
`.github/workflows/scheduled-pipeline.yml` runs the identical CLI commands on a
GitHub Actions cron, which costs nothing and needs no always-on host. Use Airflow
when you need backfills, SLAs and lineage; use the Actions cron for the demo.

## Data lineage

```
data/seed/attractions/*.json        (committed, human-reviewed, cited)
        │  read_seed_files()
        ▼
data/bronze/raw_catalogue.jsonl     (verbatim + ingested_at + content_hash)
        │  run_silver()  ── normalise, dedupe, allow-list, Pandera contracts
        ▼
data/silver/{clusters,attractions,schedules,costs,sources}.parquet
        │  run_gold()    ── feature engineering, seasonal scores, cluster metrics
        ▼
data/gold/{attraction_features,cluster_metrics}.parquet
        │  load_all_seed_data()
        ▼
PostgreSQL: destination_clusters, attractions, attraction_{schedules,costs,sources},
            source_documents, document_chunks, chunk_embeddings
```
