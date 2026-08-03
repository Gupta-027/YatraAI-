# Data dictionary

Field reference for the curated catalogue (`data/seed/attractions/*.json`) and its
transformations. This is the contract a new destination file must satisfy.

## Destination cluster

| Field | Type | Required | Meaning |
|---|---|---|---|
| `slug` | `[a-z0-9-]+` | yes | Stable identifier. Never reused |
| `name` | string | yes | Display name |
| `state` | string | yes | Indian state or union territory |
| `region` | enum | yes | `north` `south` `east` `west` `northeast` `central` |
| `summary` | string ≥ 40 | yes | 2–3 sentences positioning the circuit |
| `travel_style` | string[] | yes | e.g. `metropolitan`, `spiritual`, `mountain` |
| `center_lat` / `center_lon` | float | yes | Bounds-checked against India |
| `best_months` | int[] 1–12 | yes | Recommended travel months |
| `avoid_months` | int[] 1–12 | no | Months to avoid |
| `recommended_days` | int 1–21 | yes | Typical trip length |
| `daily_cost_baseline` | object | yes | `{tier: {stay, food, local_transport}}` in INR |
| `intercity_hub` | string | no | Airport / rail head |
| `source_url`, `source_title`, `source_type` | | no | Provenance for the overview |

## Attraction

### Identity & location

| Field | Type | Required | Notes |
|---|---|---|---|
| `slug` | `[a-z0-9-]+` | yes | Unique **within** a cluster |
| `name` | string | yes | |
| `locality` | string | no | Neighbourhood |
| `city` | string | yes | |
| `lat` / `lon` | float | yes | Validated: inside India, < 220 km from cluster centre, not duplicated |
| `categories` | string[] ≥ 1 | yes | **Every tag must exist in the interest taxonomy** — a test enforces this |

### Narrative

| Field | Type | Required | Validation |
|---|---|---|---|
| `summary` | string 25–600 | yes | One-line description |
| `history` | string ≥ 120 | yes | Origins, builders, dates |
| `significance` | string ≥ 100 | yes | Why it matters |
| `interesting_facts` | string[] 2–8 | yes | Each > 20 chars |

These four become RAG chunks. Thin content fails the data-quality gate.

### Planning inputs

| Field | Type | Required | Notes |
|---|---|---|---|
| `typical_duration_min` | int 10–600 | yes | Used by the optimiser |
| `min_duration_min` | int | no | Defaults to half typical |
| `max_duration_min` | int | no | Defaults to double typical |
| `best_time_of_day` | string[] | no | `early_morning` `morning` `midday` `afternoon` `evening` `sunset` `night` |
| `suitable_months` | int[] 1–12 | yes | Drives seasonal scoring |
| `indoor_outdoor` | enum | yes | `indoor` `outdoor` `mixed` |
| `weather_sensitivity` | float 0–1 | yes | 0 = a museum; 1 = a monsoon-only waterfall |
| `typical_crowd_level` | enum | yes | `low` `medium` `high` `very_high` |
| `crowd_by_time` | object | no | Per time-of-day crowd level |

**Invariant:** `min ≤ typical ≤ max`. Silver repairs violations rather than rejecting the row.

### Accessibility

| Field | Type | Required | Notes |
|---|---|---|---|
| `wheelchair_accessible` | enum | yes | `yes` `partial` `no` `unknown` |
| `accessibility_notes` | string ≥ 25 | yes | Concrete: steps, ramps, distances |
| `senior_friendly` | int 1–5 | yes | |
| `child_friendly` | int 1–5 | yes | |
| `physical_intensity` | int 1–5 | yes | 5 = a multi-hour trek |

`no` + a group requiring step-free access ⇒ **removed**, not down-ranked.

### Etiquette

| Field | Type | Required | Notes |
|---|---|---|---|
| `dress_code` | string | **for religious sites** | Enforced by test |
| `photography_policy` | string | no | |
| `local_customs` | string[] | **for religious sites** | Enforced by test |

### Schedule (array)

| Field | Type | Notes |
|---|---|---|
| `day_of_week` | int −1..6 or `mon`…`sun`/`all` | −1 = every day |
| `opens` / `closes` | `HH:MM` | Converted to minutes from midnight in Silver |
| `is_closed` | bool | A closure row needs no times |
| `season` | string | `all`, `winter`, `monsoon`, `apr-nov`, … |
| `note` | string | |
| `verified` | bool | **Always `false`.** A test fails the build otherwise |

A close time earlier than the open time is treated as past-midnight and corrected (+24 h).

### Costs (array)

| Field | Type | Notes |
|---|---|---|
| `visitor_type` | enum | `indian_adult` `foreign_adult` `child` `senior` `camera` `parking` |
| `min` / `max` | float ≥ 0 | Explicit band; `max ≥ min` |
| `is_free` | bool | |
| `note` | string | |
| `verified` | bool | **Always `false`** |

Only `indian_adult` feeds the cost estimator. Missing ⇒ treated as free rather than guessed.

### Provenance (array) — **required, ≥ 1**

| Field | Type | Notes |
|---|---|---|
| `url` | https URL | Must match the ingestion allow-list |
| `title` | string | |
| `type` | enum | `official` `government` `encyclopedic` `openstreetmap` `editorial` |
| `covers` | string[] | Which fields it supports: `history` `hours` `fees` `rules` `accessibility` … |
| `last_verified` | `YYYY-MM-DD` | Not in the future |

`covers` drives citation selection: a question about opening hours cites the source that
documents hours, not the one that documents history.

### Quality & verification

| Field | Type | Notes |
|---|---|---|
| `quality_score` | float 0–1 | Curated significance/interest |
| `popularity_rank` | int | Within the cluster |
| `nearby` | string[] | Neighbour slugs; resolved globally (some genuinely cross clusters) |
| `data_confidence` | enum | `high` `medium` `low` |
| `needs_verification` | bool | Drives the UI badge |
| `verification_note` | string | Shown to the user |
| `last_verified` | `YYYY-MM-DD` | Not in the future |

## Gold features

Derived in `pipelines/medallion.run_gold()`:

| Feature | Range | Derivation |
|---|---|---|
| `accessibility_score` | 0–1 | `0.6 · access + 0.4 · (1 − (intensity−1)/4)` |
| `family_score` | 0–1 | `(senior + child) / 10` |
| `indoor_score` | 0–1 | indoor 1.0, mixed 0.5, outdoor 0.0 |
| `crowd_penalty` | 0–1 | low 0.0 … very_high 1.0 |
| `cost_index` | 0–1 | Fee normalised against the corpus maximum |
| `evidence_score` | 0–1 | `0.45·best_source + 0.20·count + 0.20·confidence + 0.15·completeness` |
| `season_score_1..12` | 0–1 | 1.0 in a suitable month; else `1 − 0.9·weather_sensitivity` |

## Interest taxonomy

Ten stable dimensions members express preferences over:

`heritage` · `spiritual` · `nature` · `adventure` · `food` · `shopping` · `museums` ·
`photography` · `relaxation` · `wildlife`

Catalogue categories map onto these with weights (`CATEGORY_TO_INTERESTS`). New attractions can
introduce new tags without invalidating stored preference profiles — but a tag with no mapping
fails `test_every_seed_category_is_mapped`, because it would silently score zero everywhere.

## Adding a destination

1. Create `data/seed/attractions/NN_slug.json` with 12–20 attractions.
2. Ensure every category tag exists in the taxonomy (add mappings if not).
3. Add climatology to `services/weather/climatology.py` (12 months).
4. `make pipeline` — Pandera will name any contract violation.
5. `pytest tests/data_quality` — 30 checks.
6. `make seed`.

No application code changes. That is the point of the design.
