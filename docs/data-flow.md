# Data flow

## Lineage, end to end

```
data/seed/attractions/*.json          10 files, committed, human-reviewed, cited
        │                             every field traceable to a source URL
        │  read_seed_files()
        ▼
┌─ BRONZE ───────────────────────────────────────────────────────────────┐
│ data/bronze/raw_catalogue.jsonl                                        │
│ Verbatim capture. No interpretation. Adds ingested_at + content_hash.   │
│ Idempotent: identical content collapses to one row.        140 records │
└────────────────────────────────────────────────────────────────────────┘
        │  run_silver()
        ▼
┌─ SILVER ───────────────────────────────────────────────────────────────┐
│ Cleaned · normalised · deduplicated · VALIDATED                        │
│  · "09:30" → 570 minutes; past-midnight closes are corrected           │
│  · fees become explicit {min, max} bands                               │
│  · source domains checked against the ingestion allow-list             │
│  · coordinates bounds-checked against India                            │
│  · inconsistent duration triples repaired, not rejected                │
│                                                                        │
│ clusters 10 · attractions 130 · schedules 164 · costs 216 · sources 142│
│ Pandera contracts gate every promotion.                                │
└────────────────────────────────────────────────────────────────────────┘
        │  run_gold()
        ▼
┌─ GOLD ─────────────────────────────────────────────────────────────────┐
│ attraction_features.parquet   130 rows                                 │
│   quality · accessibility · family · indoor · crowd_penalty ·          │
│   cost_index · evidence_score · duration_hours ·                       │
│   season_score_1 … season_score_12                                     │
│ cluster_metrics.parquet        10 rows                                 │
│   coverage · mean quality · geo spread · verification debt             │
└────────────────────────────────────────────────────────────────────────┘
        │  load_all_seed_data()  (idempotent upsert on natural keys)
        ▼
┌─ OPERATIONAL DATABASE ─────────────────────────────────────────────────┐
│ destination_clusters · attractions · attraction_{schedules,costs,sources}│
│ source_documents (140) · document_chunks (790) · chunk_embeddings (790) │
└────────────────────────────────────────────────────────────────────────┘
        │
        ├─ catalog.load_candidates() → planner  (AttractionCandidate)
        └─ rag.retrieve()            → assistant (DocumentChunk + embedding)
```

## Idempotency

Re-running any stage is safe, which is what makes a cron schedule viable:

| Stage | Mechanism |
|---|---|
| Bronze | Content-hashed; identical records collapse |
| Silver / Gold | Deterministic overwrite from Bronze |
| Catalogue load | Upsert on `slug` / `(cluster, slug)`; child rows replaced wholesale |
| Knowledge load | Keyed by `doc_key` + `content_hash` — **unchanged documents keep their chunks and embeddings**, so a reseed does not re-embed the corpus |
| Embeddings | Only chunks with no current embedding are processed |

## The knowledge corpus is derived

Rather than authoring a second corpus, `knowledge_builder.py` generates the RAG documents from
the same attraction records the planner uses.

```
attraction record
   ├─ history        → chunk "History of X"
   ├─ significance   → chunk "Why X matters"
   ├─ interesting_facts → chunk "Notable facts about X"
   ├─ schedule + costs + duration + months → chunk "Visiting X"
   ├─ accessibility fields → chunk "Accessibility at X"
   └─ dress_code + photography + customs → chunk "Etiquette at X"
```

Each chunk inherits the source whose `covers` fields match its topic, so a question about opening
hours cites the source that documents hours — not the one that documents history.

Consequence: **an assistant answer cannot contradict the itinerary next to it**, because both read
the same underlying row.

## Validation gates

### Build time — `tests/data_quality` (30 tests, no database)

Coverage, identity, geography, planning fields, provenance, narrative quality. Notably:

- `test_time_sensitive_fields_are_never_claimed_as_verified` — fails if any schedule or fee row
  claims verification.
- `test_a_visit_fits_inside_at_least_one_opening_window` — an attraction whose minimum visit
  cannot fit its own hours could never be scheduled.
- `test_attractions_are_plausibly_near_their_cluster_centre` — catches coordinate typos.
- `test_no_two_attractions_share_a_coordinate` — caught two real duplicates.

### Promotion time — Pandera contracts

Seven executable schemas. A violation raises `SchemaErrors` naming the column, the check and the
failing rows, so the pipeline fails with a diagnosis rather than a stack trace.

### Runtime — `services/data_quality` (12 checks)

Evaluated against the **live database**, so drift introduced by an API write or a partial load is
visible too. Surfaced at `/api/v1/admin/data-quality` and used as the Airflow gate. An
`error`-severity failure fails the DAG.

## Weather and routing

Both are cached to survive provider outages and to keep planning fast.

```
weather:  cluster + date → weather_snapshots  (TTL-checked, falls back to climatology)
routing:  undirected leg key → route_cache    (hit counter; pruned after 30 days)
```

The route cache key normalises endpoint order, so `A→B` and `B→A` share a row, and rounds
coordinates to 4 decimal places (~11 m) so near-identical requests reuse the same leg.

## Orchestration

Airflow and the CLI call the **same functions** — there is no second implementation to drift.

| DAG | Schedule | Does |
|---|---|---|
| `yatraai_catalogue_pipeline` | `0 3 * * *` | Bronze → Silver → Gold → load → quality gate → freshness |
| `yatraai_weather_and_retention` | `0 */6 * * *` | Warm weather cache · **purge expired location data** · prune route cache |

Airflow is optional for development:

```bash
make pipeline    # bronze -> silver -> gold
make seed        # load catalogue + knowledge + embeddings
```

For the public demo, `.github/workflows/scheduled-pipeline.yml` runs the same CLI commands on a
GitHub Actions cron at zero cost. Airflow is the right answer when you need backfills, SLAs and
lineage; the Actions cron is the right answer for a portfolio deployment.

## Analytics write path

```
API action → record_event(session, event, …, properties)
                    │
                    ├─ strip coordinate-like keys  ← privacy guard, at write time
                    └─ analytics_events row
```

Aggregation happens at read time in `dashboard_metrics`, so there is no pre-aggregation to keep in
sync and no window during which a metric is stale.
