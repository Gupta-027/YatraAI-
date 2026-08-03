# Deployment guide

> **Nothing here has been deployed by the author.** Vercel, Render and Supabase all require
> account credentials. Every step below is written so you can execute it yourself, with a
> verification command at each stage.

## Free-tier reality check (verified 2026)

| Platform | Free tier | Notes |
|---|---|---|
| **Render** | ✅ Real, no card | Web service sleeps after ~15 min idle; 30–50 s cold start |
| **Railway** | ❌ | One-off $5 trial credit, then $5/month Hobby |
| **Fly.io** | ❌ | Card required; 2-hour trial only |
| **Vercel** | ✅ Hobby | Generous for a Next.js frontend |
| **Supabase** | ✅ | Postgres + pgvector + auth; pauses after 7 days inactivity |

**Free tiers change.** Re-check before relying on this. The deployment config is deliberately
provider-independent: the app needs only a Python runtime, a `DATABASE_URL` and a port.

**Chosen stack:** Vercel (frontend) + Render (API) + Supabase (Postgres + pgvector).

---

## Step 1 — Supabase (database)

1. Create a project at [supabase.com](https://supabase.com). Choose a region near your users
   (Mumbai `ap-south-1` for this app).
2. **Enable pgvector.** SQL Editor → New query:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   ```

3. Copy the **pooled** connection string (Project Settings → Database → Connection pooling,
   mode `transaction`). Pooled, not direct — Render's free tier recycles connections.
4. Convert it to SQLAlchemy form by replacing the scheme:

   ```
   postgresql://…            →  postgresql+psycopg://…
   ```

**Verify:**
```bash
DATABASE_URL="postgresql+psycopg://..." python -c "
from yatraai.db.session import get_engine
from sqlalchemy import text
with get_engine().connect() as c:
    print(c.execute(text('select version()')).scalar())"
```

---

## Step 2 — migrations and seed

Run **locally, once**, pointed at Supabase:

```bash
export DATABASE_URL="postgresql+psycopg://..."
cd apps/api && alembic upgrade head && cd ../..
python -m yatraai.cli seed --knowledge --embeddings
```

**Verify:**
```bash
python -m yatraai.cli status
# Expect: 10 clusters, 130 attractions, 790 chunks, 790 embeddings
```

---

## Step 3 — Render (API)

1. New → Blueprint → connect this repository. Render reads `infra/render.yaml`.
2. Set the variables marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | Supabase pooled string, `postgresql+psycopg://…` |
   | `CORS_ORIGINS` | Your Vercel URL, e.g. `https://yatraai.vercel.app` |
   | `JWT_SECRET` | Render generates this — leave it |

   Optional: `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` plus `LLM_PROVIDER`. Leave unset and the
   app runs with deterministic template explanations.

3. Deploy. First boot runs migrations and seeds (idempotent, so redeploys are safe).

**Verify:**
```bash
curl https://<your-service>.onrender.com/health
curl https://<your-service>.onrender.com/ready
curl https://<your-service>.onrender.com/api/v1/destinations | jq 'length'   # expect 10
```

> If `/ready` reports `degraded`, check the `checks.database` field — it names the failure class.

---

## Step 4 — Vercel (frontend)

1. New Project → import this repository.
2. **Root directory: `apps/web`** (important — this is a monorepo).
3. Environment variables:

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | `https://<your-service>.onrender.com` |
   | `NEXT_PUBLIC_DEMO_MODE` | `true` |

4. Deploy.

**Verify:** open the site, click **Destinations**. If the cards are empty, the API base URL or
CORS is wrong — check the browser console for a CORS error and confirm `CORS_ORIGINS` on Render
exactly matches the Vercel origin (scheme included, no trailing slash).

---

## Step 5 — scheduled pipeline

Airflow is overkill for a portfolio deployment. `.github/workflows/scheduled-pipeline.yml`
already runs the same CLI commands on a daily cron.

Add repository secrets/variables:

| Name | Type | Value |
|---|---|---|
| `DATABASE_URL` | Secret | Supabase pooled string |
| `API_BASE_URL` | Variable | Render URL (enables the keep-warm job) |

Trigger manually once from the Actions tab to confirm it works.

For full Airflow, see [pipelines/airflow/README.md](../pipelines/airflow/README.md).

---

## Production environment-variable checklist

**Required**

- [ ] `DATABASE_URL` — Postgres, pooled, `postgresql+psycopg://`
- [ ] `JWT_SECRET` — ≥ 32 chars, unique (`python -c "import secrets;print(secrets.token_urlsafe(48))"`)
- [ ] `CORS_ORIGINS` — exact frontend origin(s), https
- [ ] `YATRA_ENV=production`
- [ ] `NEXT_PUBLIC_API_BASE_URL` (Vercel)

**Optional**

- [ ] `LLM_PROVIDER` + `ANTHROPIC_API_KEY` / `GEMINI_API_KEY`
- [ ] `EMBEDDING_PROVIDER=sentence-transformers` (needs `pip install -e ".[embeddings]"`)
- [ ] `ROUTING_PROVIDER=osrm` + `OSRM_BASE_URL`
- [ ] `SUPABASE_JWT_SECRET` to accept Supabase-issued tokens
- [ ] `YATRA_LOG_JSON=true`
- [ ] `RATE_LIMIT_AI_PER_MINUTE` (lower on a free tier)

**Never set**

- [ ] Any secret in `vercel.json`, `render.yaml` or committed files. `.env` is git-ignored and
      `.env.example` contains names only.

The API **refuses to start** in production with a weak `JWT_SECRET`, no `DATABASE_URL`, or a
plaintext non-localhost CORS origin (`Settings.assert_production_ready`). That is intentional —
failing loudly at boot beats running insecurely.

---

## Handling free-tier cold starts

Render's free web service sleeps after ~15 minutes; the first request then takes 30–50 s.

**What the app already does**

- The typed client uses a **45 s default timeout** and **120 s** for planning calls, so a cold
  start does not surface as a network error.
- `ApiRequestError` distinguishes `timeout` from `network_error`, and the UI shows a retry
  affordance rather than a dead end.
- The keep-warm job in the scheduled workflow pings `/health` with three attempts.

**What you can do**

1. Warm it before a demo: `curl https://<service>.onrender.com/health` and wait.
2. Mention it in your demo script — "this is a free tier, give it a moment" is a perfectly
   reasonable thing to say, and better than a mysterious spinner.
3. Upgrade to Render's paid Starter tier (~$7/month) if it matters; the config does not change.

Supabase also **pauses a free project after 7 days of inactivity**. Un-pause from the dashboard;
the pipeline cron keeps it active if it runs against it.

---

## Docker (self-hosting)

```bash
docker compose up -d --build
```

Brings up pgvector/pg16, the API (migrating and seeding on boot) and the web app.

Individually:

```bash
docker build -f infra/api.Dockerfile -t yatraai-api .
docker build -f apps/web/Dockerfile \
  --build-arg NEXT_PUBLIC_API_BASE_URL=https://api.example.com \
  -t yatraai-web apps/web
```

The web Dockerfile emits a standalone Next.js server (~120 MB). `NEXT_PUBLIC_*` values are baked
in at **build** time, so a different API URL needs a rebuild — that is a Next.js property, not a
choice made here.

---

## Deployment verification checklist

Run after any deploy:

- [ ] `GET /health` → `{"status":"ok"}`
- [ ] `GET /ready` → `"ready"`, `checks.database == "ok"`
- [ ] `GET /api/v1/destinations` → 10 clusters
- [ ] `GET /api/v1/destinations/delhi-agra/attractions/taj-mahal` → history, sources, `needs_verification: true`
- [ ] `GET /api/v1/auth/demo` → a token
- [ ] `POST /api/v1/trips/{id}/itinerary` → `is_valid: true`, `validation.checks_run >= 15`
- [ ] `POST /api/v1/assistant/ask` with an out-of-scope question → `abstained: true`
- [ ] Frontend loads and **Destinations** populates (proves CORS)
- [ ] `/api/v1/metrics` shows provider stats
- [ ] `GET /api/v1/admin/data-quality` (as an admin) → `status: pass`

Automated:

```bash
API_BASE_URL=https://<service>.onrender.com python scripts/verify_deployment.py
```

---

## Rollback

- **Render** — Deploys tab → any previous deploy → Rollback.
- **Vercel** — Deployments → previous → Promote to Production.
- **Database** — `cd apps/api && alembic downgrade -1`. Take a Supabase backup first; migrations
  that drop columns are not reversible without one.

---

## What I could not do, and exactly what you must do

| Blocked step | Why | What you do | How to verify |
|---|---|---|---|
| Create the Supabase project | Needs your account | supabase.com → New project | Connection test above |
| Deploy to Render | Needs your account + repo connection | Blueprint from `infra/render.yaml` | `curl /health` |
| Deploy to Vercel | Needs your account | Import repo, root `apps/web` | Destinations page populates |
| Add API keys | They are your secrets | Set in each dashboard | `/api/v1/metrics` shows the provider |
| Configure the cron | Needs repo secrets | Settings → Secrets and variables | Run the workflow manually |

Everything else — code, migrations, seed data, Docker, CI, blueprints — is committed and working.
