# API reference

Interactive documentation: `/docs` (Swagger UI — needs internet, loads from a CDN) or `/redoc`.
Machine-readable: `/openapi.json`. A self-contained console that works offline is at `/`.

Base path: `/api/v1`. Auth: `Authorization: Bearer <jwt>`.

## Error shape

Every error returns the same envelope, so clients branch on a stable `code`:

```json
{ "error": { "code": "not_a_trip_member", "message": "You are not a member of this trip.", "detail": null } }
```

| Code | Status | Meaning |
|---|---|---|
| `unauthenticated` | 401 | Missing or invalid token |
| `forbidden` / `not_a_trip_member` / `trip_owner_required` | 403 | Authorisation failure |
| `consent_required` / `sharing_not_active` / `sharing_expired` | 403 | Location consent gate |
| `not_found` / `cluster_not_found` / `attraction_not_found` / `no_itinerary` | 404 | |
| `conflict` / `email_taken` | 409 | |
| `validation_failed` | 422 | Payload failed validation |
| `planning_infeasible` | 422 | No itinerary satisfies the constraints; `detail` has the report |
| `rate_limited` | 429 | `detail.retry_after_seconds` |
| `provider_unavailable` | 503 | External provider failed *and* no fallback sufficed |

## Ops

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | — | Liveness |
| GET | `/ready` | — | Database + provider snapshot; 503 when degraded |
| GET | `/api/v1/metrics` | — | Provider latency, error and fallback rates |
| GET | `/api/v1/auth/service-status` | — | Drives the honest degradation banner |

## Auth

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | — | `{email, password ≥ 8, display_name}` → token |
| POST | `/auth/login` | — | → token |
| GET | `/auth/me` | ✓ | Current user |
| GET | `/auth/demo` | — | Demo account + sample trip, no signup |

Supabase-issued JWTs are accepted when `SUPABASE_JWT_SECRET` is set; a local user is provisioned
on first sight.

## Destinations

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/destinations` | — | 10 clusters with attraction counts |
| GET | `/destinations/{cluster}` | — | Detail + category and accessibility coverage |
| GET | `/destinations/{cluster}/attractions` | — | `?category=&accessible_only=&indoor_only=&max_intensity=` |
| GET | `/destinations/{cluster}/attractions/{slug}` | — | **The full "Know this place" payload** |

The attraction detail response carries history, significance, facts, min/max duration, best time
of day, suitable months, crowd profile, accessibility notes, dress code, photography policy,
local customs, schedules, cost bands, **cited sources**, resolved neighbours with distances, data
confidence, verification note and knowledge topics.

## Trips

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/trips` | ✓ | Create; validates dates, day window ≥ 3 h, slugs against the cluster |
| GET | `/trips` | ✓ | Trips you belong to |
| GET | `/trips/{id}` | member | |
| PATCH | `/trips/{id}` | owner | |
| POST | `/trips/join` | ✓ | `{invite_code}` |
| POST | `/trips/{id}/invite/rotate` | owner | |
| PUT | `/trips/{id}/preferences` | member | Your own preferences only |
| POST | `/trips/{id}/opt-out` | member | Leave planning without deleting the trip |

## Itineraries

| Method | Path | Auth | Rate tier | Notes |
|---|---|---|---|---|
| POST | `/trips/{id}/itinerary` | member | AI | Runs the full pipeline; 422 `planning_infeasible` if none exists |
| GET | `/trips/{id}/itinerary` | member | default | Active version |
| GET | `/trips/{id}/itinerary/versions` | member | default | History |
| POST | `/trips/{id}/itinerary/validate` | member | default | Re-validate stored rows |
| POST | `/trips/{id}/itinerary/modify` | member | AI | 11 actions; re-optimised and re-validated |
| GET | `/trips/{id}/recommendations` | member | default | Ranked candidates + score breakdowns |

### Modification actions

`remove_activity` · `replace_activity` · `regenerate_day` · `make_day_relaxed` · `reduce_cost` ·
`reduce_travel` · `add_theme` · `shift_start_time` · `weather_replan` · `member_opted_out` ·
`attraction_unavailable`

Each is expressed as a change to **planner inputs**, then the whole pipeline re-runs. Nothing
edits a schedule in place, so a modification cannot produce a state the optimiser would never
have generated.

On a trip with more than one active member the change becomes a `ChangeProposal` requiring group
approval; the response has `requires_group_approval: true` and a `proposal_id`.

## Assistant

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/assistant/ask` | — | Cited answer, or `abstained: true` |
| GET | `/assistant/suggested-questions` | — | Starter questions |
| POST | `/assistant/retrieve` | — | Raw retrieval with dense/lexical/fused/rerank scores |
| GET | `/assistant/trips/{id}/why/{slug}` | member | Selection reasoning from the stored breakdown — no LLM |

`attraction_slug` requires `cluster_slug` (422 otherwise), because an unscoped attraction lookup
is exactly how the wrong place's dress code gets returned.

## Collaboration

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/trips/{id}/votes` | member | Reaching the threshold auto-applies a proposal |
| GET | `/trips/{id}/votes` | member | `?subject_type=&subject_id=` |
| GET | `/trips/{id}/proposals` | member | With approval counts |
| POST | `/trips/{id}/proposals/{pid}/apply` | owner | Owner override |
| POST | `/trips/{id}/chat` | member | Sanitised on write |
| GET | `/trips/{id}/chat` | member | `?since=` for polling |

## Location — consent-gated

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/trips/{id}/location/consent-text` | member | Versioned wording + guarantees |
| POST | `/trips/{id}/location/start` | member | **`consent_granted` must be `true`** |
| POST | `/trips/{id}/location/status` | member | `active` / `paused` / `stopped` |
| POST | `/trips/{id}/location/point` | member | Snapped before storage in approximate mode |
| GET | `/trips/{id}/location/group` | member | Positions, separation, meeting point, ETAs |
| DELETE | `/trips/{id}/location` | member | Stop **and delete the trail** |

Constraints: `update_interval_seconds ≥ 15`, `duration_hours ≤ 12`, precision defaults to
`approximate`. See [privacy.md](privacy.md).

## SOS — demonstration only

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/trips/{id}/sos` | member | Requires `acknowledge_demo: true` |
| GET | `/trips/{id}/sos` | member | |
| POST | `/trips/{id}/sos/{alert_id}/resolve` | member | |

**Contacts nobody.** Raises an in-app notification to trip members and posts a system chat
message. Stated in the OpenAPI description, the response `disclaimer`, and the UI.

## Analytics & admin

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/feedback` | ✓ | Rating, acceptance, **actual spend** |
| GET | `/analytics/dashboard` | — | Aggregates only; coordinates never present |
| GET | `/analytics/attractions` | — | Selection rates |
| GET | `/analytics/trips/{id}` | member | Versions, fairness, coverage |
| GET | `/admin/data-quality` | admin | 12 live checks |
| GET | `/admin/coverage` | admin | Per-cluster coverage and freshness |
| GET | `/admin/pipeline-runs` | admin | |
| GET | `/admin/rag-evaluations` | admin | Stored benchmark runs |
| GET | `/admin/audit-log` | admin | Sensitive actions |

## Rate limits

| Tier | Default | Applies to |
|---|---|---|
| Default | 120/min | Reads and light writes |
| AI | 15/min | Itinerary generation, modification, assistant |

Keyed by user ID when authenticated, otherwise client IP. A 429 carries
`detail.retry_after_seconds`.

## Typed client

`apps/web/lib/api.ts` wraps every endpoint with normalised errors and sensible timeouts (45 s
default, 120 s for planning, because a cold free-tier service legitimately takes that long).
`apps/web/lib/types.ts` mirrors the response schemas; `npm run typecheck` catches drift.
