# YatraAI — Implementation Progress

Living checklist. Updated at the end of every phase. Every ✅ is backed by
code in this repository and a passing test or a reproducible command.

| Phase | Status |
|---|---|
| 1. Foundation | ✅ Complete |
| 2. Data foundation | ✅ Complete |
| 3. Recommendation & optimization | ✅ Complete |
| 4. Backend APIs | ✅ Complete |
| 5. RAG | ✅ Complete |
| 6. Frontend | ✅ Complete |
| 7. Collaboration | ✅ Complete |
| 8. Analytics & production quality | ✅ Complete |
| 9. Deployment | ✅ Complete (configs verified; hosting requires your accounts) |
| 10. Interview readiness | ✅ Complete |

---

## Phase 1 — Foundation ✅

- [x] Repository inspected (was empty) and monorepo scaffolded
- [x] `pyproject.toml` with ruff / pytest / mypy / coverage configuration
- [x] Structured logging (`structlog`) with request-id correlation
- [x] Settings layer where **every** external dependency is a swappable provider
      (`llm`, `embeddings`, `weather`, `routing`, `database`) so the app runs fully offline
- [x] Portable column types — `GUID`, `JSONType`, `VectorType`, `TZDateTime` —
      so the identical schema runs on PostgreSQL+pgvector *and* SQLite
- [x] **31 tables** covering catalogue, trips, itineraries, knowledge base,
      collaboration, location privacy and observability
- [x] Alembic migrations `0001_initial_schema` and `0002_activity_opening_window` — the full
      chain applies and reverses cleanly on a fresh database
- [x] Typed error hierarchy, sliding-window rate limiter, provider telemetry buffer
- [x] Security primitives: bcrypt (with SHA-256 pre-hash so >72-byte passphrases keep
      entropy), JWT issue/verify with Supabase fallback, HTML/control-char sanitiser,
      prompt-injection detector
- [x] FastAPI app factory with CORS, request middleware, `/health`, `/ready`
- [x] Production configuration guard — the API refuses to boot with a weak `JWT_SECRET`,
      SQLite, or plaintext CORS origins when `YATRA_ENV=production`
- [x] Docker Compose (pgvector/pg16 + api + web), multi-stage API Dockerfile
- [x] GitHub Actions: backend, Postgres integration, data-quality, frontend, docker jobs
- [x] `Makefile` + `tasks.ps1` (Windows parity)
- [x] `.env.example` with variable **names only**

**Measured:** 34 tests passing, `ruff check` + `ruff format --check` clean.

---

## Phase 2 — Data foundation ✅

- [x] **10 curated destination clusters**, **130 attractions**, each with ~30 structured
      fields: coordinates, categories, history, significance, facts, duration triple,
      opening schedule, fee ranges, seasonal suitability, indoor/outdoor, crowd profile,
      accessibility, senior/child suitability, physical intensity, dress code,
      photography policy, local customs, neighbours, sources, verification date
- [x] **Provenance on every row** — 142 source records, all HTTPS, all on the
      ingestion allow-list (ASI, state tourism boards, UNESCO, official temple trusts)
- [x] **Honest verification labelling** — no schedule or fee row in the dataset claims
      to be verified; a data-quality test *fails the build* if one ever does
- [x] RAG corpus **derived from the same records**: 140 documents → **790 semantic
      chunks** (one per attraction × topic) → 790 embeddings. No second, driftable corpus.
- [x] Bronze → Silver → Gold medallion pipeline (`yatraai.pipelines.medallion`)
      with idempotent, content-hashed ingestion and incremental re-embedding
- [x] **7 executable Pandera contracts** enforced at promotion time
- [x] Runtime data-quality service (12 checks) powering the admin dashboard + Airflow gate
- [x] Two Airflow DAGs calling the *same* functions as the CLI — no duplicate implementation
- [x] `data/seed/` committed so a reviewer can run everything immediately

**Measured:** `make pipeline` → 140 bronze rows → 130 attractions + 142 sources +
164 schedules + 216 fee rows → 130 gold feature rows + 10 cluster metric rows, 0 rejected.
64 tests passing (30 of them data-quality contracts).

Two real defects were caught by the gate while building it: a cross-cluster neighbour
reference and two attractions sharing a coordinate. Both fixed.

## Phase 3 — Recommendation & optimization ✅

- [x] **Six aggregation methods** — simple/weighted average, Borda count (with tie-averaging),
      max-min fairness, single-pass fairness-aware, and **iterative fair selection** (production)
- [x] Group metrics: Jain's fairness index, consensus score, least-satisfied score,
      per-member coverage, member deficits
- [x] **Nine-component explainable score** with fixed, inspectable weights; every number
      the "Why recommended?" panel shows comes from the stored breakdown
- [x] Hard eligibility filters that **remove** infeasible places rather than down-weighting them,
      including a **per-member veto** so a majority cannot overrule one person
- [x] Geographic day-clustering: deterministic farthest-point seeding + size balancing that
      **refuses moves across a geographic gulf**
- [x] Routing abstraction: OSRM with automatic haversine fallback, documented detour factors
      and speed assumptions, persistent leg cache
- [x] Weather abstraction: Open-Meteo with committed per-cluster climatology fallback,
      flagged honestly as "seasonal averages, not a forecast"
- [x] **OR-Tools CP-SAT day scheduler** — prize-collecting TSP with time windows, `AddCircuit`
      sequencing, opening-hours propagation, mandatory nodes, meal/rest breaks, budget,
      travel and activity caps, ordered relaxation ladder, `num_workers=1` for determinism
- [x] **Greedy baseline** honouring identical constraints (a fair control, not a strawman)
- [x] **15-check constraint validator** run independently of the solver; no plan is displayed
      unless it passes
- [x] Cost estimator returning a **range** across five components with documented assumptions

### Measured results (reproduce with `make experiments`)

**Optimiser vs greedy** — 6 scenarios, 6 clusters, 3 timing repeats
([full report](ml/reports/planner_comparison.md)):

| Metric | Greedy | OR-Tools | Δ |
|---|---|---|---|
| Total travel distance | 149.8 km | **64.0 km** | **−57%** |
| Total travel time | 487 min | **275 min** | **−43%** |
| Travel km per activity | 15.61 | **6.01** | −61% |
| Activities scheduled | 9.8 | 10.3 | +0.5 |
| Constraint violations | 0.0 | 0.0 | — |
| Computation time (median) | 8.8 ms | 48.2 ms | +39 ms |

**Aggregation methods** — 5 group profiles, K=5 itinerary
([full report](ml/reports/aggregation_comparison.md)):

| Method | Mean satisfaction | Least satisfied | Spread |
|---|---|---|---|
| `simple_average` | 0.604 | 0.481 | 0.172 |
| `max_min_fairness` | 0.582 | **0.545** | 0.069 |
| `fairness_aware` (single pass) | 0.603 | 0.484 | 0.167 |
| **`select_fairly` (production)** | 0.597 | **0.522** | 0.115 |

Iterative selection captures **64% of max-min's fairness gain for 30% of its cost** in
mean satisfaction. The single-pass variant barely improves on a simple average — that
finding is *why* the iterative selector exists.

**Three real defects the experiments surfaced and fixed:**
1. Greedy scheduled meal breaks with zero travel gap → invalid plans.
2. Size-balancing dragged Delhi sites into the Agra day → a 401 km itinerary.
3. A single trip-wide base in a 230 km-wide cluster made *every* day infeasible →
   per-day base with an explicit relocation note.

**Suite:** 171 tests passing, `ruff` clean.

## Phase 4 — Backend APIs ✅

- [x] **LLM provider abstraction** — `mock` (default, deterministic template composer),
      `anthropic`, `gemini`. Every real provider falls back to mock on failure rather than
      raising, and the response records who actually answered
- [x] Itinerary explanation is **stage 8 only** — it narrates an already-validated plan and
      can never change it. Template output is used verbatim when no model is configured
- [x] Full Pydantic schema layer with real validation (interest keys, date ordering,
      minimum day length, time windows)
- [x] Auth: register / login / me / demo-login, bcrypt + JWT, **Supabase token acceptance
      with first-sight provisioning**
- [x] Row-level authorisation: `require_trip_member`, `require_trip_owner`; a non-member
      gets 403 with a machine-readable code
- [x] Two-tier rate limiting — a tighter budget on optimiser/LLM endpoints
- [x] Append-only **audit log** on every sensitive trip action
- [x] Trip lifecycle: create, list, update, join by invite, rotate invite, opt out
- [x] Per-member preference submission that back-propagates accessibility needs to the trip
- [x] Itinerary generation, versioning, history, re-validation, ranked recommendations with
      full score breakdowns
- [x] **11 modification / replanning actions**, each expressed as a change to *planner inputs*
      and re-optimised + re-validated — nothing edits a schedule in place
- [x] Group changes become `ChangeProposal` rows requiring approval instead of applying silently
- [x] Analytics service with a **privacy guard that strips coordinate-like keys** at write time
- [x] Weather snapshot cache; demo account + sample group trip

**Measured:** 216 tests passing (45 API integration), `ruff` clean. Live boot verified:
`/health`, `/ready`, 10 destinations, full Taj Mahal detail payload (369-char history,
4 facts, 2 cited sources, 3 resolved neighbours) served in 19 ms.

## Phase 5 — RAG ✅

- [x] **Hybrid retrieval** — dense cosine + BM25 lexical, fused with Reciprocal Rank Fusion
      (k=60), then a feature-based reranker (topic match, entity match, source authority,
      chunk quality)
- [x] Retrieval is **scoped**: an attraction filter requires a cluster, so an unscoped lookup
      cannot return the wrong place's dress code
- [x] **Abstention on an absolute evidence score**, not a fused rank — `0.35·dense +
      0.65·IDF-weighted term coverage`, threshold 0.26
- [x] **Citations are computed, not claimed** — each generated sentence is matched back to the
      chunk that supports it by lexical overlap (threshold 0.30); an uncited sentence is a bug
      the evaluation harness reports
- [x] Answers carry the source's `covers` fields, so an opening-hours question cites the source
      that documents hours
- [x] Prompt-injection neutralisation on both the question *and* every retrieved chunk
- [x] Never invents time-sensitive facts: schedule and fee answers always carry the
      "verify before visiting" label, because no row in the dataset claims verification
- [x] **34-question benchmark** — answerable, out-of-scope, ambiguous, adversarial — with an
      ablation harness that genuinely re-runs retrieval per strategy

### Measured results (`python evaluation/run_rag_eval.py`)

| Metric | Value |
|---|---|
| Open retrieval top-1 | 0.903 |
| Open retrieval top-3 / MRR | 1.000 / 0.952 |
| Retrieval recall | 1.000 |
| Topic classification accuracy | 0.941 |
| Citation correctness | 1.000 |
| Citation coverage | 1.000 |
| **Abstention accuracy** | **1.000** |
| Faithfulness | 0.995 |
| Mean evidence — answerable | 0.582 |
| Mean evidence — out-of-scope | 0.071 |
| Latency p50 / p95 | 8.1 ms / 34.4 ms |

Open precision@5 is 0.200 and is *structurally capped* there — one chunk per attraction per
topic means at most one of five can be the target. It is reported anyway so the cap is visible
rather than hidden.

**Ablation** (real re-runs, not re-sorts): reranking contributes **+12.9 pp top-1** (0.903 vs
0.774) for no latency saving. Hybrid beats dense-only (0.871) but only ties lexical-only
(0.903) — and the report says plainly that this is a limitation of the default hashing embedder
being a lexical projection, not a strength of BM25.

**Four real defects the harness caught** (each fixed, each with a regression test):
1. `\b(histor|…)\b` — a trailing word boundary made the topic regex unable to match "history".
   Topic accuracy 0.50 → 0.941 after switching to `\w*` stems.
2. Abstention keyed on the RRF score, which encodes only ordering and is near-constant at the
   top. Replaced with an absolute evidence score; separation went from ~0 to 0.45.
3. **A question demanding live data got no warning at all** ("the ticket price today at 4pm
   exactly"). Two causes: the disclaimer was keyed on *which chunk was retrieved* rather than on
   what was asked, and the question scored 0.183 — below the 0.26 gate — because "today", "4pm"
   and "exactly" are absent from the corpus and so drew maximum IDF weight. It abstained on a
   fee it was holding.
4. **"What happened at Sarnath and why does it matter?" abstained at 0.229** with the correct
   chunk ranked first, because "happened" and "matter" have document frequency zero across all
   790 chunks.

(3) and (4) are the same underlying error: treating *every* absent query term as evidence of
missing coverage. An absent entity ("reykjavik") is that evidence; an absent framing word
("happened") only measures our writing style. Separating the two lifted abstention accuracy
0.912 → **1.000** and citation coverage 0.903 → **1.000**, while mean out-of-scope evidence
stayed **exactly** at 0.071 — the gate did not loosen, it stopped misfiring.

## Phase 6 — Frontend ✅

- [x] Next.js 14 App Router + TypeScript strict + Tailwind design system
- [x] **15 routes / 11 screens**: landing, destinations, destination detail, plan wizard,
      trips, trip detail, itinerary, map, group, assistant, analytics, login
- [x] `PlaceDrawer` — the "Know this place" panel: Story / Visiting / Access & etiquette /
      Ask / Sources, with the verification badge shown wherever unverified data appears
- [x] Itinerary view with per-day timeline, travel legs, cost band, weather note, relocation
      note, and a "Why recommended?" panel driven by the **stored** score breakdown
- [x] Consent-gated location UI — the toggle cannot be enabled before the consent text is shown
- [x] SOS labelled as a demonstration in the UI and gated behind an explicit acknowledgement
- [x] Honest degradation banner driven by `/auth/service-status`
- [x] Typed API client with normalised errors and cold-start-aware timeouts
- [x] **Solver trace** — CP-SAT status, wall-clock, objective, candidates→selected and any
      relaxation, per day, read back from the solve that produced the plan on screen
- [x] **Retrieval inspector** — per-arm dense / BM25 / rerank scores for the question just asked,
      normalised within each arm because the three are not on a comparable scale
- [x] Simplification pass: prose replaced with the diagram or the live numbers it described;
      `/settings` removed; secondary actions moved behind a disclosure
- [x] Top nav reduced to **Plan a trip / Trips** — the one path that shows what the system does.
      Destinations, assistant, metrics and data quality moved to the footer, still one click away
- [x] **Itinerary rows show the visit slot against the place's real opening window**
      (`10:38–11:18 · Open 06:00–12:00 · unverified`), so the schedule can be checked rather than
      trusted. Persisted through a new migration — the solver already constrained against the
      window and was discarding it

**Measured:** 43 frontend tests passing, `tsc --noEmit` clean, `next lint` clean,
production build emits 15 routes, all 8 pages return HTTP 200 against a live backend.

## Phase 7 — Collaboration ✅

- [x] Voting with a threshold that auto-applies a proposal on reaching consensus
- [x] `ChangeProposal` flow — on a multi-member trip a modification requires group approval
      rather than applying silently; owner override is available and audited
- [x] Trip chat, sanitised on write, with `?since=` polling
- [x] **Consent-based location sharing** — see [privacy.md](docs/privacy.md). Approximate by
      default (~500 m grid, snapped *before* storage), 12 h hard cap, stop deletes the trail
- [x] Group view: separation distance, suggested meeting point, per-member ETA
- [x] Demo SOS that contacts **nobody** and refuses to fire without `acknowledge_demo: true`

## Phase 8 — Analytics & production quality ✅

- [x] Feedback capture including **actual spend**, so the cost estimator can be calibrated later
- [x] Analytics dashboard over aggregates only; `test_dashboard_never_exposes_coordinates`
      posts a real coordinate and asserts it appears nowhere in the payload
- [x] Admin: 12 live data-quality checks, coverage/freshness, pipeline runs, RAG evaluations,
      audit log
- [x] Provider telemetry — latency, error rate and **fallback rate** per provider at `/metrics`
- [x] `model_runs` registry where every row carries `data_kind`, so a synthetic result can
      never be displayed as a real one

## Phase 9 — Deployment ✅

- [x] Multi-stage API Dockerfile + web Dockerfile; Compose stack (pgvector/pg16 + api + web)
- [x] `render.yaml` with every secret `sync: false` and a generated `JWT_SECRET`
- [x] Vercel config for the frontend; GitHub Actions running backend, Postgres integration,
      data-quality, frontend and docker jobs
- [x] `scripts/verify_deployment.py` — 10 post-deployment checks
- [x] `start.ps1` — one command: venv, install, seed, port check, uvicorn, opens the browser
- [x] Self-contained console at `/` that renders **with no internet** (unlike `/docs`, which
      loads Swagger UI from a CDN)

**Measured:** `python scripts/verify_deployment.py` → **10/10 PASS** against a local instance.

**Not claimed:** nothing is deployed to a public URL. That step needs your Render/Vercel
accounts — the exact commands are in [deployment.md](docs/deployment.md).

## Phase 10 — Interview readiness ✅

- [x] 13 documents: architecture, data flow, ER diagram, recommendation, optimisation, RAG,
      ML experiments, security, privacy, deployment, API reference, data dictionary, interview
- [x] Every performance number in the README traceable to a script under `ml/` or `evaluation/`
- [x] `make experiments` reproduces all of them

---

## Deliberate scope decisions

| Decision | Why |
|---|---|
| 10 clusters, not all of India | Depth over breadth; the data model + pipeline add clusters without code changes |
| Hashing embeddings default | Keeps `pip install` under a minute; sentence-transformers is a one-env-var upgrade |
| SQLite fallback | Reviewers can run the whole app with zero infrastructure |
| Rule-based ranking in production | No genuine labelled data exists; ML experiments are explicitly labelled synthetic |
| SOS is a demo notification | Never contacts real emergency services |

## Note on the destination list

The brief listed "eight clusters" and then enumerated ten, where *Shillong–Cherrapunji*
and *Meghalaya* overlap. Resolved as ten distinct clusters by scoping
`shillong-cherrapunji` to the Khasi Hills circuit and `meghalaya-jaintia-dawki`
to the eastern Jaintia Hills / Dawki circuit. See `docs/data-dictionary.md`.
