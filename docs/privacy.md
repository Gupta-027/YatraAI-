# Privacy design

Location is the most sensitive data this product touches. Every guarantee below is **enforced in
code and covered by a test**, not merely stated as policy.

## Principles

| Principle | Implementation | Test |
|---|---|---|
| **Opt-in only** | A session cannot exist without `consent_granted_at` and a consent-text version. `consent_granted=false` → HTTP 403 `consent_required` | `test_sharing_requires_explicit_consent` |
| **Approximate by default** | `precision="approximate"` snaps to a ~500 m grid **before storage** — the exact position is never written | `test_approximate_mode_snaps_before_storage` |
| **Always expiring** | Every session has `expires_at` (12 h hard cap); every point has its own `expires_at` | DB `CHECK` + `test_session_duration_is_capped` |
| **Minimal retention** | `purge_expired_location_data` hard-deletes. No archive table, no soft delete | `test_purge_deletes_expired_points` |
| **Stop means delete** | Stopping deletes the trail immediately, not just hides it | `test_stopping_deletes_the_trail_immediately` |
| **Trip-scoped** | Position is visible only to members of the same trip | `test_non_member_cannot_read_chat` and route-level `require_trip_member` |
| **No background tracking** | The server never requests a position. The client posts one, only while sharing is `active`, and the timer is destroyed on stop/unmount | `useEffect` teardown in `app/trips/[id]/map/page.tsx` |
| **Never in analytics** | Coordinate-like keys are stripped at write time | `test_dashboard_never_exposes_coordinates` |
| **Minimum interval** | ≥ 15 s, enforced by DB constraint *and* API validation | `test_update_interval_floor_enforced` |

## What is stored

### `location_sharing_sessions`
`trip_id`, `member_id`, `status`, `precision`, `update_interval_seconds`, `consent_granted_at`,
`consent_text_version`, `expires_at`, `stopped_at`, `last_point_at`.

The consent-text **version** is stored so we can always tell what a user actually agreed to.

### `location_points`
`session_id`, `trip_id`, `member_id`, `lat`, `lon`, `accuracy_m`, `is_approximate`,
`recorded_at`, `expires_at`.

In approximate mode `lat`/`lon` are already snapped. There is no column holding the original.

## Retention

```
LOCATION_POINT_RETENTION_MINUTES = 120   (default)
LOCATION_SESSION_MAX_HOURS       = 12    (hard cap)
```

Purging runs from three places, so no single failure leaves data behind:

1. The `yatraai_weather_and_retention` Airflow DAG, every 6 hours.
2. `python -m yatraai.cli purge-locations`, callable from any scheduler.
3. Immediately, when a user stops sharing.

`purge_expired_location_data` also deletes **orphan points** whose session no longer exists — a
safety net so a point can never outlive its consent record.

## The consent text

Served from `GET /api/v1/trips/{id}/location/consent-text` so the UI cannot drift from the
recorded version:

> I agree to share my location with members of this trip. I understand that sharing stops
> automatically when the session expires, that I can pause or stop it at any time, and that
> recent points are deleted after the retention window.

Shown alongside the guarantees, in the UI, before the toggle can be enabled.

## Approximation

```python
APPROXIMATE_GRID_DEGREES = 0.005  # ~555 m of latitude


def _snap(v):
    return round(round(v / 0.005) * 0.005, 5)
```

Applied in `record_point` **before** the row is constructed. This is deliberate: sanitising on
read would leave the precise value in the database, where a backup, a log or a future query
could expose it.

## What analytics sees

```python
_FORBIDDEN_PROPERTY_KEYS = {"lat", "lon", "latitude", "longitude", "coords", "coordinates"}
```

`record_event` strips these before the row is written. The dashboard reports only:

```json
{"sessions_total": 12, "sessions_active": 3,
 "note": "Counts only. Coordinates are never recorded in analytics."}
```

`test_dashboard_never_exposes_coordinates` posts a real coordinate and asserts the string does
not appear anywhere in the dashboard payload.

## SOS is a demonstration

The SOS feature creates an in-app notification for trip members. **It does not contact emergency
services, police, or any external party.**

This is stated in four places: the OpenAPI description, the response body `disclaimer`, the UI
callout, and the system chat message it posts. The endpoint also **refuses to fire** unless the
caller passes `acknowledge_demo: true`, so it cannot be triggered by accident or by a client that
has not shown the warning.

Stored coordinates on an alert are snapped to the approximate grid regardless of session
precision.

## Other personal data

| Data | Retention | Notes |
|---|---|---|
| Email, display name | Until account deletion | Password stored only as a bcrypt hash |
| Trip preferences | Life of the trip | Interest weights, not free-text profiling |
| Chat messages | Life of the trip | Sanitised of markup on write |
| Audit log | Append-only | Actions and IDs; no message bodies, no coordinates |
| Analytics events | Aggregate | Coordinate keys stripped at write time |

## Deliberate non-goals

- **No third-party analytics or trackers.** No Google Analytics, no pixels, no session replay.
- **No location history.** There is no table that could hold one.
- **No cross-trip correlation.** Location is scoped to a trip and expires with the session.
- **No background geolocation.** No service worker, no `watchPosition` while backgrounded.

## Browser permissions

`next.config.mjs` sets:

```
Permissions-Policy: camera=(), microphone=(), geolocation=(self)
```

Camera and microphone are disabled outright — the product has no use for them, so the safest
configuration is to make that explicit rather than rely on nobody asking.
