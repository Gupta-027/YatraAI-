# Security notes

## Threat model

A portfolio deployment with real user accounts, group-scoped data and an optional LLM. The
threats that actually matter here:

| Threat | Control |
|---|---|
| Credential compromise | bcrypt with SHA-256 pre-hash; no password ever logged |
| Token forgery | HS256 JWT, signature verified, issuer checked, expiry enforced |
| Horizontal privilege escalation | `require_trip_member` / `require_trip_owner` on every trip route |
| Vertical escalation | `admin_user` dependency on all admin routes |
| Cost/DoS via expensive endpoints | Two-tier rate limiting; optimiser and RAG on the tighter budget |
| Prompt injection | Detection on input, neutralisation of retrieved text, injection-aware system prompt |
| Data poisoning via ingestion | Source-domain allow-list enforced at the Silver gate |
| Stored XSS | Markup and control characters stripped on write; the frontend never renders raw HTML |
| Location exposure | Consent gate, pre-storage approximation, expiry, write-time analytics stripping |
| Secret leakage | `.env` git-ignored, `.env.example` holds names only, production boot-time guard |

## Authentication

```python
digest = base64.b64encode(hashlib.sha256(password.encode()).digest())
bcrypt.hashpw(digest, bcrypt.gensalt(rounds=12))
```

The SHA-256 pre-hash exists because **bcrypt silently truncates at 72 bytes**. Without it, an
80-character passphrase and the same passphrase with a different ending would hash identically.
`test_long_passphrase_keeps_entropy_past_bcrypt_72_byte_limit` asserts they do not.

Login returns an identical error for "no such account" and "wrong password", and performs the
same hashing work in both cases, so response timing does not leak account existence.

### Supabase interoperability

`decode_token` tries the local secret first, then `SUPABASE_JWT_SECRET`. A Supabase-issued token
provisions a local user on first sight, so a Supabase-only deployment needs no separate signup
path. The Supabase branch verifies the `authenticated` audience.

## Authorisation

Row-level rules are dependencies, not scattered `if` statements:

```python
trip = load_trip(session, trip_id)
require_trip_member(session, trip, user)  # 403 not_a_trip_member
require_trip_owner(session, trip, user)  # 403 trip_owner_required
```

Admins may *read* a trip for support but are not silently made members — `require_trip_member`
returns an unpersisted `TripMember` with `role="admin"` for them, so they cannot vote, submit
preferences or post as a member.

Tested: `test_non_member_cannot_read_a_trip`, `test_only_the_owner_can_update_settings`,
`test_non_member_cannot_vote`, `test_admin_routes_require_admin`.

## Rate limiting

Sliding-window, in-process, two tiers:

| Tier | Default | Applies to |
|---|---|---|
| `rate_limit_default` | 120/min | Reads and light writes |
| `rate_limit_ai` | 15/min | Itinerary generation, modification, RAG |

Keyed by user ID when authenticated, else by client IP (respecting `X-Forwarded-For`).

Deliberately in-process: the demo runs as a single API process, so a Redis hop would add
operational cost with no benefit. `SlidingWindowRateLimiter.check()` is the only method the API
uses, so swapping in a distributed implementation is a one-class change.

## Input validation

Three layers:

1. **Pydantic** — types, bounds, patterns, cross-field validators (`end_date >= start_date`,
   day window ≥ 3 hours, interest keys must exist in the taxonomy).
2. **`sanitize_text`** — strips HTML tags and control characters, collapses whitespace, truncates.
   The frontend never renders raw HTML, but sanitising at the boundary keeps stored data clean for
   exports, prompts and downstream consumers.
3. **Referential** — must-visit and avoid slugs are filtered against the cluster's real attraction
   list, so a client cannot inject arbitrary slugs into planner input.

`RequestValidationError` responses strip Pydantic's `ctx` (which contains the original exception
object) — this both keeps the response JSON-serialisable and avoids leaking internals.

## Prompt injection

| Layer | Control |
|---|---|
| User question | `detect_prompt_injection` → flagged in `warnings`; text neutralised before use |
| Retrieved chunks | `safe_context` neutralises every chunk before it enters a prompt |
| System prompt | States that context is reference material and embedded instructions must be ignored |
| Evidence gate | Injection attempts score low and typically abstain before any model call |

Tested: `test_injection_in_the_question_is_flagged_and_neutralised`,
`test_injection_attempt_does_not_produce_a_confident_answer`.

## Ingestion allow-list

Source URLs are checked against `INGEST_ALLOWED_DOMAINS` (suffix-matched) at the **Silver** gate.
A citation to a non-allow-listed domain is rejected with a reason, not silently accepted.

Default: `gov.in`, `nic.in`, `ac.in`, `unesco.org`, plus named institutional domains
(`salarjungmuseum.in`, `shrikashivishwanath.org`, …), `openstreetmap.org`, `wikipedia.org`.

`test_sources_use_https_and_allowlisted_domains` fails the build if a seed edit introduces one.

## CORS

Explicit origin list from `CORS_ORIGINS` — never `*`, and credentials are allowed, which makes a
wildcard both wrong and unsafe. Methods and headers are enumerated rather than open.

## Security headers

Set by `next.config.mjs` (frontend) and the API middleware:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin  (no-referrer on the API)
Permissions-Policy: camera=(), microphone=(), geolocation=(self)
```

## Secrets

- `.env` is git-ignored; `.env.example` contains **variable names only**.
- `render.yaml` marks every secret `sync: false` — Render prompts rather than storing in the repo.
- `JWT_SECRET` uses `generateValue: true` so a strong value is produced at deploy time.
- No secret is ever logged. Structured logging records provider *names*, never keys.

## Production boot guard

```python
Settings.assert_production_ready() -> list[str]
```

With `YATRA_ENV=production` the API **refuses to start** if:

- `JWT_SECRET` is shorter than 32 characters or contains `dev-only`
- `DATABASE_URL` is unset (the SQLite fallback is refused in production)
- any non-localhost CORS origin uses plain `http://`
- `LLM_PROVIDER` names a provider whose API key is missing

Failing loudly at boot is better than running insecurely and finding out later.

## Audit log

Append-only `audit_logs` rows for: registration, trip create/update/join, invite rotation,
preference submission, opt-out, itinerary generation, every modification action, proposal
application, location sharing start/pause/stop/delete, and demo SOS.

Each row carries actor, action, entity, trip, **request ID** (so it joins to structured logs) and
a detail payload. Message bodies and coordinates are never included.

## Known gaps

Stated rather than glossed over:

1. **No refresh tokens.** Access tokens last 120 minutes and then require re-login. Fine for a
   portfolio; a production build wants rotation and revocation.
2. **Rate limiting is per-process.** Multiple API instances each enforce their own budget.
3. **No CSRF tokens.** The API is token-authenticated with no cookie auth, so the classic CSRF
   vector does not apply — but a cookie-based session would need them.
4. **No account deletion endpoint.** Cascades are defined at the schema level; the endpoint is not
   built.
5. **No 2FA.**
6. **Dependency scanning is not wired in.** `pip-audit` and `npm audit` should run in CI.
