# Architecture

## The governing constraint

> The language model must never be able to invent an itinerary fact.

Everything else follows. The system is arranged so that facts, selection, routing and scheduling
are deterministic and inspectable, and the LLM is confined to the last stage, where its output is
prose sitting *beside* a validated plan rather than the plan itself.

## Component map

```
                    ┌───────────────────────────────────────┐
                    │            apps/web (Next.js)         │
                    │  App Router · TanStack Query · Leaflet │
                    └──────────────────┬────────────────────┘
                                       │ lib/api.ts (typed, one place owns
                                       │ base URL, auth, errors, timeouts)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                              apps/api (FastAPI)                             │
│                                                                             │
│  api/v1/          deps (auth · RLS · rate limit · audit) · serializers      │
│    routes_auth · routes_destinations · routes_trips                        │
│    routes_rag   · routes_collab      · routes_analytics                    │
│                                                                             │
│  services/                                                                  │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ recommend/   taxonomy · aggregation · scoring · clustering          │    │
│  │ planner/     models · ortools_scheduler · greedy · validator ·      │    │
│  │              cost · pipeline                                        │    │
│  │ rag/         embeddings · retriever · answer                        │    │
│  │ routing/     distance · base (OSRM|haversine) · cache               │    │
│  │ weather/     base (Open-Meteo|climatology) · climatology · cache    │    │
│  │ llm/         base (anthropic|gemini|mock) · explain                 │    │
│  │ catalog · trips · replan · location · analytics · data_quality      │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  core/    errors · security · rate_limit · telemetry                        │
│  db/      base (portable types) · session · models (31 tables)              │
│  pipelines/  contracts (Pandera) · medallion (bronze/silver/gold)           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
        ┌──────────────────────────────▼──────────────────────────────┐
        │  PostgreSQL 16 + pgvector  |  SQLite (tests, offline demo)  │
        └─────────────────────────────────────────────────────────────┘
```

## Why the pure core matters

`services/planner/models.py` defines plain dataclasses — `AttractionCandidate`, `MemberProfile`,
`TripContext`, `PlannedDay`. The optimiser, scorer, validator and cost model operate **only** on
these. They import no SQLAlchemy, no FastAPI, no HTTP client.

Consequences that paid off:

- The 38 planner tests construct scenarios in-memory. No fixtures, no database, no mocking.
- `ml/experiments/*.py` runs the real production planner against real seed data with no server.
- Swapping SQLite for Postgres changed nothing in the algorithmic layer.
- The determinism test (`identical inputs → identical plan`) is trivially expressible.

`services/catalog.py` is the only seam that converts ORM rows into these dataclasses.

## Request flow: generating an itinerary

```
POST /api/v1/trips/{id}/itinerary
  │
  ├─ deps.current_user            JWT (local or Supabase) → User
  ├─ deps.require_trip_member     row-level rule: membership or 403
  ├─ deps.rate_limit_ai           tighter budget on optimiser endpoints
  │
  ├─ trips.build_context          Trip row      → TripContext
  ├─ trips.build_member_profiles  members+prefs → [MemberProfile]
  ├─ catalog.load_candidates      attractions   → [AttractionCandidate]
  │
  └─ planner.plan_trip ─────────────────────────────────────────────┐
       1. weather        provider or committed climatology fallback │
       2. eligibility    closed / inaccessible / over budget REMOVED│
       3. scoring        9 components → total, breakdown stored     │
       4. shortlist      iterative fair selection (group-aware)     │
       5. clustering     balanced k-means, geography beats balance  │
       6. matrix         OSRM or haversine, cached per leg          │
       7. optimise       CP-SAT per day, relaxation ladder          │
       8. validate       15 checks, independent of the solver       │
       9. cost           5 components, returned as a range          │
      ─────────────────────────────────────────────────────────────┘
  │
  ├─ if invalid → 422 with the full validation report (never a broken plan)
  ├─ llm.explain_itinerary        narrate the validated plan (optional)
  ├─ trips.persist_itinerary      itinerary + days + activities + scores
  ├─ audit + analytics event
  └─ 201 ItineraryOut
```

The LLM call sits between validation and persistence. If it fails, times out or is not
configured, `explain_itinerary` returns the template and the response is otherwise identical.

## Provider abstraction

Every external dependency is a `Protocol`-shaped class with at least two implementations:

| Service | Primary | Fallback | Degrades to |
|---|---|---|---|
| LLM | Anthropic / Gemini | `MockProvider` | Deterministic template composition |
| Embeddings | sentence-transformers | `HashingEmbedder` | Signed feature hashing (measured, not a stub) |
| Routing | OSRM | `HaversineRouter` | Great-circle × documented detour factor |
| Weather | Open-Meteo | `SeedClimatologyProvider` | Committed monthly normals |
| Database | PostgreSQL + pgvector | SQLite | JSON-encoded vectors, in-Python cosine |

Two rules make this honest:

1. **Fallbacks never raise.** A provider failure produces a lower-quality answer, never a 500.
2. **Fallback use is surfaced.** `core/telemetry` records it, `services/status` aggregates it,
   and the UI renders a banner naming exactly what degraded and what that means for the data.

## Data layer

`db/base.py` defines four `TypeDecorator`s so one schema serves both databases:

| Type | PostgreSQL | SQLite |
|---|---|---|
| `GUID` | native `uuid` | 36-char string |
| `JSONType` | `JSONB` | JSON-encoded `TEXT` |
| `VectorType` | `pgvector.Vector(384)` | JSON float list |
| `TZDateTime` | `timestamptz` | UTC-normalised on read/write |

This is why `pytest` needs no Docker, and why the offline demo works.

## Security boundaries

| Boundary | Control |
|---|---|
| Authentication | bcrypt (SHA-256 pre-hash so >72-byte passphrases keep entropy) + JWT |
| Row-level access | `require_trip_member` / `require_trip_owner` on every trip route |
| Rate limiting | Two tiers; optimiser and RAG endpoints get a tighter budget |
| Input | Pydantic validation, then `sanitize_text` strips markup and control chars |
| Prompt injection | Detected on user input; retrieved chunks neutralised before prompting |
| Ingestion | Source domains checked against an allow-list at the Silver gate |
| Audit | Append-only log on every sensitive trip and privacy action |
| Production config | Startup refuses a weak `JWT_SECRET`, SQLite, or plaintext CORS |

## Observability

- **Structured logs** (`structlog`) with a request ID injected via `ContextVar`.
- **Provider telemetry** — a ring buffer of the last 500 calls per service, aggregated into p50,
  p95, error rate and fallback rate, exposed at `/api/v1/metrics` and on the dashboard.
- **Health** `/health` (liveness) and `/ready` (database + provider snapshot).
- **Data quality** — 12 live checks at `/api/v1/admin/data-quality`, the same gate the Airflow
  DAG enforces.
