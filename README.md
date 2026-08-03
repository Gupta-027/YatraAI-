# YatraAI — Context-Aware Group Travel Intelligence Platform

> Fair, explainable and **feasible** group itineraries for ten curated Indian destinations.
> Structured data decides the facts. Deterministic algorithms select and schedule.
> OR-Tools optimises. A constraint validator gates every plan.
> The language model only ever explains a result it did not choose.

<p align="center">
  <a href="#quick-start"><b>Quick start</b></a> ·
  <a href="#measured-results">Measured results</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="docs/">Docs</a> ·
  <a href="#known-limitations">Limitations</a>
</p>

---

## The problem

**Business problem.** Group trips fail on coordination, not inspiration. Four people want four
different things; someone always gets ignored; the plan that emerges ignores opening hours,
travel time and weather, and falls apart on day one.

**Technical problem.** *How do you build a system that produces a fair, explainable and
physically feasible group itinerary under changing weather, time windows, budget, distance,
opening hours, individual preferences and accessibility requirements — without letting a
language model invent the facts?*

That last clause is the whole design. An LLM asked to "plan a trip to Agra" will confidently
produce an itinerary that visits the Taj Mahal on a Friday (closed), allows 20 minutes to cross
Delhi, and quotes a ticket price it invented. YatraAI splits responsibility so the parts that
must be *correct* are deterministic and inspectable, and the part that must *read well* is not
allowed anywhere near them.

---

## Responsibility separation

| Stage | Owner | Can it invent facts? |
|---|---|---|
| 1. Facts | Curated catalogue with per-row provenance | No — every field traces to a cited source |
| 2. Eligibility | Hard filters (closed, inaccessible, over budget) | No — infeasible options are *removed* |
| 3. Selection | Fairness-aware ranking, 9 explainable components | No — deterministic, reproducible |
| 4. Geography | Balanced k-means day clustering | No |
| 5. Travel | OSRM, falling back to haversine + documented speeds | No |
| 6. Schedule | **OR-Tools CP-SAT** prize-collecting TSP with time windows | No |
| 7. Validation | 15 independent constraint checks | No — errors block display |
| 8. Wording | LLM (optional) | Yes — which is why it runs *last* and changes nothing |

**Turn the LLM off entirely (`LLM_PROVIDER=mock`, the default) and the product still works.**
Explanations become deterministic templates. That is not a degraded mode bolted on afterwards;
it is the default the test suite runs against.

---

## Measured results

Every number below is produced by a script in this repository. Re-run them yourself — nothing
here is estimated or aspirational.

### Optimiser vs greedy baseline
`python ml/experiments/planner_comparison.py` → [full report](ml/reports/planner_comparison.md)

6 scenarios across 6 destination clusters, 3 timing repeats, identical inputs and constraints:

| Metric | Greedy baseline | **OR-Tools CP-SAT** | Difference |
|---|---|---|---|
| Total travel distance | 149.8 km | **64.0 km** | **−57%** |
| Total travel time | 487 min | **275 min** | **−43%** |
| Travel km per activity | 15.61 | **6.01** | −61% |
| Activities scheduled | 9.8 | 10.3 | +0.5 |
| Constraint violations | 0.0 | 0.0 | — |
| Computation time (median) | 8.8 ms | 48.2 ms | +39 ms |

### Group aggregation methods
`python ml/experiments/aggregation_comparison.py` → [full report](ml/reports/aggregation_comparison.md)

5 group profiles deliberately constructed so a simple average would steamroll a minority:

| Method | Mean satisfaction | **Least satisfied** | Spread |
|---|---|---|---|
| `simple_average` | 0.604 | 0.481 | 0.172 |
| `borda_count` | 0.618 | 0.478 | 0.197 |
| `max_min_fairness` | 0.582 | **0.545** | 0.069 |
| `fairness_aware` (single pass) | 0.603 | 0.484 | 0.167 |
| **`select_fairly` (production)** | 0.597 | **0.522** | 0.115 |

Iterative fair selection captures **64% of pure max-min's fairness gain for 30% of its cost**
in mean satisfaction. The single-pass variant barely improves on an average — that null result
is *why* the iterative selector exists.

### RAG assistant
`python evaluation/run_rag_eval.py` → [full report](evaluation/reports/rag_evaluation.md)

34-question hand-written benchmark including deliberately unanswerable and adversarial questions:

| Metric | Value |
|---|---|
| Open retrieval top-1 (no attraction hint) | **0.903** |
| Open retrieval top-3 | **1.000** |
| Open retrieval MRR | **0.952** |
| Retrieval recall | **1.000** |
| Topic classification accuracy | 0.941 |
| Faithfulness | 0.995 |
| Citation correctness / coverage | 1.000 / 1.000 |
| **Abstention accuracy** | **1.000** |
| Mean evidence — answerable / out-of-scope | 0.582 / 0.071 |
| Latency p50 / p95 | 8.1 ms / 34.4 ms |

Ablation (genuinely disabling a retrieval arm, not re-sorting):

| Configuration | Top-1 | MRR |
|---|---|---|
| **hybrid + rerank (default)** | **0.903** | **0.952** |
| hybrid, no rerank | 0.774 | 0.874 |
| dense only + rerank | 0.871 | 0.935 |
| lexical only + rerank | 0.903 | 0.946 |

### Test suite

| Suite | Count |
|---|---|
| Python (unit + integration + data quality) | **295** |
| Frontend (Vitest) | **43** |
| **Total** | **338** |

`ruff check` and `ruff format --check` clean; `tsc --noEmit` clean; `next lint` clean.

---

## Quick start

### One command (Windows)

```powershell
.\start.ps1
```
Creates the venv, seeds the database, starts the API and opens the browser.

### Full stack, manual

```bash
# 1. Backend
python -m venv .venv
.venv/bin/pip install -e ".[dev]"          # Windows: .venv\Scripts\pip
.venv/bin/python -m yatraai.cli migrate
.venv/bin/python -m yatraai.cli seed --knowledge --embeddings
.venv/bin/uvicorn yatraai.main:app --app-dir apps/api --port 8000

# 2. Frontend (second terminal)
cd apps/web
npm install
npm run dev
```

Open **http://localhost:3000**. The API's self-contained console is at **http://localhost:8000/**
(it renders offline; `/docs` needs internet because Swagger UI loads from a CDN).

### Docker

```bash
docker compose up -d --build      # Postgres + pgvector, API, web
```

### Demo credentials

| | |
|---|---|
| Email | `demo@yatraai.example` |
| Password | `yatraai-demo-2026` |

Or click **“Open the demo account”** on the sign-in page — no typing needed. It has a
three-member Bengaluru trip whose members want deliberately conflicting things, which is the
case a simple average gets wrong.

> Demo data is **synthetic** and labelled as such throughout the product and in analytics.

---

## Screens

| Screen | Route | What it demonstrates |
|---|---|---|
| Landing | `/` | The responsibility-separation argument, with measured numbers |
| Destination explorer | `/destinations` | 10 clusters, filterable |
| Destination detail | `/destinations/[slug]` | Map, coverage stats, accessibility filters |
| **Place detail drawer** | (in-page) | History, significance, facts, etiquette, hours, fees, sources, RAG assistant |
| Trip planner | `/plan` | 6-step wizard; every input becomes a constraint |
| Generated itinerary | `/trips/[id]` | Day timeline with opening windows, cost range, **solver trace**, 11 modification actions |
| Group preference room | `/trips/[id]/group` | Invite, per-member preferences, proposals, voting, chat |
| Live group map | `/trips/[id]/map` | Consent gate, precision control, separation warning, ETAs, demo SOS |
| Why these places? | `/trips/[id]/analytics` | Version history, fairness over time, ranked candidates with score components |
| Metrics | `/analytics` | Popularity, quality, provider health, data freshness |
| Admin data quality | `/admin` | 12 live checks, coverage, pipeline runs, RAG evaluations |
| Assistant | `/assistant` | Cited Q&A with abstention, plus a live **retrieval inspector** |
| Auth | `/login`, `/register` | Local + Supabase-compatible |

Two panels exist specifically to make the machine learning legible rather than asserted:

- **Solver trace** (`components/Pipeline.tsx`) reads back CP-SAT's own status, wall-clock,
  objective value and candidates-considered for each day of the plan on screen, and names any
  constraint that had to be relaxed.
- **Retrieval inspector** (`components/RetrievalInspector.tsx`) calls `/assistant/retrieve` for
  the question you just asked and plots what each arm — dense, BM25, reranker — scored every
  candidate chunk. Bars are normalised *within* each arm, because cosine, BM25 and a feature score
  are not on a comparable scale.

> **Screenshots**: not committed. Run `.\start.ps1` plus `npm run dev` and the screens above are
> live in under two minutes. Committing stale screenshots of a UI that changes would be worse
> than none.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  apps/web — Next.js 14 · TypeScript · Tailwind · TanStack Query · Leaflet │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ typed client (lib/api.ts)
┌───────────────────────────────▼──────────────────────────────────────────┐
│  apps/api — FastAPI                                                       │
│  ┌────────────┬──────────────┬─────────────┬───────────┬───────────────┐ │
│  │ auth/trips │ destinations │ assistant   │ collab    │ analytics     │ │
│  └────────────┴──────────────┴─────────────┴───────────┴───────────────┘ │
│  services/                                                                │
│   recommend/  aggregation · scoring · clustering · taxonomy               │
│   planner/    ortools_scheduler · greedy · validator · cost · pipeline    │
│   rag/        retriever (hybrid) · answer (cited) · embeddings            │
│   routing/    OSRM → haversine fallback + persistent leg cache            │
│   weather/    Open-Meteo → committed climatology fallback                 │
│   llm/        anthropic | gemini | mock (deterministic template)          │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ SQLAlchemy 2.0 + Alembic
┌───────────────────────────────▼──────────────────────────────────────────┐
│  PostgreSQL 16 + pgvector   (SQLite for tests / offline demo)             │
│  31 tables: catalogue · trips · itineraries · knowledge · collab · ops    │
└───────────────────────────────▲──────────────────────────────────────────┘
                                │ idempotent load
┌───────────────────────────────┴──────────────────────────────────────────┐
│  data/seed → Bronze → Silver → Gold   (Pandera contracts at each gate)    │
│  Airflow DAGs · GitHub Actions cron · same functions as the CLI           │
└──────────────────────────────────────────────────────────────────────────┘
```

Detail: [architecture](docs/architecture.md) · [data flow](docs/data-flow.md) ·
[ER diagram](docs/er-diagram.md)

---

## Technology choices, and why

| Choice | Why | The alternative I rejected |
|---|---|---|
| **OR-Tools CP-SAT** | Time windows + optional nodes + a travel objective is a natural CP model; `AddCircuit` handles sequencing and skipping in one constraint | A hand-rolled heuristic — measured 57% worse on travel |
| **Rule-based production ranker** | No genuine labelled data exists. A learned ranker would be fitted to invented labels | Shipping an ML model trained on synthetic labels and calling it ML |
| **Hashing embeddings by default** | `pip install` stays under a minute; CI needs no model download; retrieval measured at 0.90 top-1 | Making sentence-transformers mandatory (a 2 GB download for a 790-chunk corpus) |
| **RRF fusion** | Dense and BM25 scores are not comparable; RRF needs no normalisation | Weighted score blending, which requires calibration nobody maintains |
| **Portable column types** | The same schema runs on Postgres+pgvector *and* SQLite, so tests need no infrastructure | Postgres-only, making the test suite need Docker |
| **Derived RAG corpus** | The knowledge base is generated from the same rows the planner uses, so an answer cannot contradict an itinerary | A separately-authored corpus that silently drifts |
| **Polling, not WebSockets** | A group is 2–8 people; polling is one endpoint and no extra infrastructure | Realtime infrastructure for a problem that does not need it |

---

## Honesty guarantees

These are enforced by code and tests, not by policy documents:

1. **No schedule or fee row claims to be verified.** A data-quality test fails the build if one
   ever does. Every such field renders with a “verify before visiting” badge.
2. **The assistant abstains** when the corpus cannot answer — 1.000 accuracy on a benchmark that
   includes questions it *should* refuse. It also states plainly when a value is recorded rather
   than live: *"this is a recorded value from our catalogue, not a live lookup."*
3. **Citations are computed, not claimed.** They are derived from lexical overlap between each
   answer sentence and the retrieved chunk, so a model cannot cite a source it did not use.
4. **Coordinates never reach analytics.** Stripped at write time, with a test asserting a real
   posted coordinate does not appear in the dashboard payload.
5. **Approximate location is snapped before storage** — the exact position is never written.
6. **The SOS button is a demo** and says so in the API description, the UI and the response body.
7. **No invented metrics.** Every figure in this README traces to a committed script.

---

## Repository layout

```
apps/api/yatraai/     FastAPI app, services, models, pipelines, CLI
apps/web/             Next.js frontend
data/seed/            10 clusters, 130 attractions — committed, human-reviewed, cited
data/{bronze,silver,gold}/   Generated medallion layers (git-ignored)
pipelines/airflow/    DAGs calling the same functions as the CLI
ml/experiments/       Reproducible aggregation and planner comparisons
ml/reports/           Their measured output
evaluation/           RAG benchmark + harness
evaluation/reports/   Its measured output
tests/                295 Python tests (unit, integration, data quality)
docs/                 Architecture, methodology, privacy, security, deployment
infra/                Dockerfiles, Render blueprint, Postgres init
```

---

## Commands

```bash
make help          # list everything
make verify        # lint + full test suite (what CI runs)
make test          # pytest
make pipeline      # Bronze -> Silver -> Gold
make seed          # load catalogue + knowledge + embeddings
make experiments   # reproduce the planner/aggregation comparisons
make rag-eval      # reproduce the RAG benchmark
make api / make web
make docker-up
```

Windows: `./tasks.ps1 <target>` runs the same set.

---

## Known limitations

Stated plainly, because a portfolio project that claims none is not credible.

1. **The dataset is authored, not scraped.** 130 attractions written from general knowledge with
   real official source URLs attached. Coordinates and narrative content are reliable; **hours and
   fees are explicitly unverified** and labelled as such everywhere.
2. **The RAG benchmark is written by the author** (34 questions). It is small and not collected
   from real users. It is labelled as such in the report.
3. **Faithfulness is a lexical-overlap proxy.** It catches fabrication reliably but cannot catch a
   fluent paraphrase that subtly changes meaning. An NLI judge would be stronger.
4. **Lexical retrieval alone nearly matches the hybrid** on this benchmark. That is a limitation of
   the default hashing embedder (whose "dense" signal correlates with BM25), not a strength of
   BM25. A real encoder should widen the gap; that claim is untested and therefore not made.
5. **No cost-accuracy figure exists yet.** The dashboard says so rather than inventing one.
   Actual-spend feedback is captured; the metric appears once there is data.
6. **ML experiments use synthetic labels** and are labelled `data_kind="synthetic"`. The
   rule-based ranker remains the production default precisely because of this.
7. **Free-tier cold starts.** Render's free plan sleeps after ~15 minutes; the first request takes
   30–50 s. Mitigations in [docs/deployment.md](docs/deployment.md).
8. **Ten destinations, not all of India.** Deliberate. Adding more is a data-pipeline task, not a
   code change.

---

## Deployment

Not deployed by me — that needs your Vercel, Render and Supabase accounts.
[docs/deployment.md](docs/deployment.md) has the exact steps, the environment-variable
checklist and a verification script. Free-tier availability was checked in 2026: **Render is
the only one of Render / Railway / Fly.io still offering a genuine no-card free tier**, and it
sleeps when idle.

---

## Documentation

| | |
|---|---|
| [Architecture](docs/architecture.md) | Components, boundaries, request flow |
| [Data flow](docs/data-flow.md) | Bronze → Silver → Gold → serving |
| [ER diagram](docs/er-diagram.md) | All 31 tables |
| [**Interview deck**](docs/YatraAI_Interview_Deck.pptx) | **10-slide walkthrough of the whole system — `python scripts/build_deck.py`** |
| [Data dictionary](docs/data-dictionary.md) | Every catalogue field |
| [Recommendation methodology](docs/recommendation.md) | Aggregation maths and weights |
| [Optimisation formulation](docs/optimization.md) | The CP-SAT model, formally |
| [RAG architecture](docs/rag.md) | Retrieval, citation, abstention |
| [RAG evaluation](evaluation/reports/rag_evaluation.md) | Measured |
| [ML experiments](docs/ml-experiments.md) | Honest treatment of synthetic labels |
| [Privacy design](docs/privacy.md) | Location handling |
| [Security notes](docs/security.md) | Threat model and controls |
| [API reference](docs/api.md) | All endpoints |
| [Deployment](docs/deployment.md) | Step-by-step |
| [Interview talking points](docs/interview.md) | Demo script, resume bullets, likely questions |
| [Progress checklist](PROGRESS.md) | What was built, phase by phase |

---

## Licence

MIT. Destination content is compiled from public government and institutional sources, cited
per attraction with a verification date.
