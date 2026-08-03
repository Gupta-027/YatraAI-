"""Self-contained HTML console served at ``/``.

Why this exists: FastAPI's ``/docs`` loads Swagger UI from a public CDN, so it
renders as a blank page on a machine that is offline or behind a proxy that
blocks jsdelivr. This page has **zero external assets** - no CDN scripts, no web
fonts, no remote images - so it always renders. It doubles as a working fallback
interface until the Next.js frontend is in place.
"""

from __future__ import annotations

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YatraAI - API console</title>
<style>
  :root {
    --bg: #faf7f2; --surface: #ffffff; --ink: #1a1d2e; --muted: #5b6178;
    --line: #e6e1d8; --indigo: #23306b; --saffron: #e07a3f; --teal: #0f7b6c;
    --radius: 14px;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#12131a; --surface:#1b1d27; --ink:#f2efe9; --muted:#a8afc4;
            --line:#2c2f3d; --indigo:#8ea0e8; --saffron:#f0a06a; --teal:#4fc4b0; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 32px 20px 72px; }
  header { border-bottom:1px solid var(--line); padding-bottom:24px; margin-bottom:28px; }
  h1 { margin:0 0 6px; font-size:clamp(28px,5vw,40px); letter-spacing:-.02em; color:var(--indigo); }
  .sub { color:var(--muted); margin:0; max-width:62ch; }
  .pill { display:inline-block; padding:3px 10px; border-radius:999px; font-size:12px;
          font-weight:600; background:color-mix(in srgb,var(--teal) 15%,transparent);
          color:var(--teal); border:1px solid color-mix(in srgb,var(--teal) 35%,transparent); }
  .pill.warn { background:color-mix(in srgb,var(--saffron) 15%,transparent);
               color:var(--saffron); border-color:color-mix(in srgb,var(--saffron) 35%,transparent); }
  h2 { font-size:19px; margin:32px 0 12px; letter-spacing:-.01em; }
  .grid { display:grid; gap:14px; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); }
  .card { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
          padding:16px; }
  .card h3 { margin:0 0 4px; font-size:16px; }
  .card p { margin:0; color:var(--muted); font-size:13.5px; }
  .meta { margin-top:10px; font-size:12px; color:var(--muted); display:flex; gap:12px; flex-wrap:wrap; }
  a { color:var(--indigo); }
  ul.endpoints { list-style:none; padding:0; margin:0; }
  ul.endpoints li { border-bottom:1px solid var(--line); padding:9px 0; display:flex;
                    gap:12px; align-items:baseline; flex-wrap:wrap; }
  ul.endpoints li:last-child { border-bottom:0; }
  code { font:13px/1.5 ui-monospace,"Cascadia Code",Consolas,monospace;
         background:color-mix(in srgb,var(--ink) 7%,transparent);
         padding:2px 7px; border-radius:6px; }
  .verb { font-weight:700; font-size:11px; letter-spacing:.06em; min-width:46px; color:var(--teal); }
  .verb.post { color:var(--saffron); }
  .note { background:color-mix(in srgb,var(--saffron) 10%,transparent);
          border:1px solid color-mix(in srgb,var(--saffron) 30%,transparent);
          border-radius:var(--radius); padding:14px 16px; margin:20px 0; font-size:14px; }
  button { font:inherit; font-size:14px; font-weight:600; cursor:pointer; border-radius:10px;
           border:1px solid var(--indigo); background:var(--indigo); color:#fff;
           padding:9px 16px; }
  button.ghost { background:transparent; color:var(--indigo); }
  button:disabled { opacity:.55; cursor:progress; }
  pre { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
        padding:14px; overflow:auto; max-height:420px; font-size:12.5px; }
  .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin:10px 0; }
  footer { margin-top:44px; padding-top:18px; border-top:1px solid var(--line);
           color:var(--muted); font-size:13px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="pill" id="status-pill">checking…</span>
    <h1>YatraAI</h1>
    <p class="sub">Context-aware group travel intelligence. Structured data decides the facts,
    deterministic algorithms select and schedule, OR-Tools optimises, a validator gates every
    itinerary, and the language model only ever explains a result it did not choose.</p>
  </header>

  <div class="note">
    <strong>This is the API console, not the product UI.</strong>
    The Next.js frontend is still being built. This page is served by the backend itself with no
    external assets, so it works offline — unlike <code>/docs</code>, which loads Swagger UI from
    a CDN and shows a blank page when that CDN is unreachable.
  </div>

  <h2>Live check</h2>
  <div class="row">
    <button id="btn-load" onclick="loadAll()">Load destinations</button>
    <button class="ghost" onclick="runDemo()" id="btn-demo">Generate a demo itinerary</button>
  </div>
  <div id="out"></div>

  <h2>Destinations</h2>
  <div class="grid" id="clusters"><div class="card"><p>Press “Load destinations”.</p></div></div>

  <h2>Endpoints</h2>
  <ul class="endpoints">
    <li><span class="verb">GET</span><code>/health</code><span class="meta">liveness</span></li>
    <li><span class="verb">GET</span><code>/ready</code><span class="meta">readiness + provider status</span></li>
    <li><span class="verb">GET</span><code>/api/v1/destinations</code><span class="meta">10 curated clusters</span></li>
    <li><span class="verb">GET</span><code>/api/v1/destinations/{slug}/attractions/{slug}</code><span class="meta">full place detail with citations</span></li>
    <li><span class="verb post">POST</span><code>/api/v1/auth/register</code><span class="meta">create an account</span></li>
    <li><span class="verb">GET</span><code>/api/v1/auth/demo</code><span class="meta">demo token, no signup</span></li>
    <li><span class="verb post">POST</span><code>/api/v1/trips</code><span class="meta">create a trip</span></li>
    <li><span class="verb post">POST</span><code>/api/v1/trips/{id}/itinerary</code><span class="meta">run the planner</span></li>
    <li><span class="verb post">POST</span><code>/api/v1/trips/{id}/itinerary/modify</code><span class="meta">replan, revalidated</span></li>
    <li><span class="verb">GET</span><code>/api/v1/trips/{id}/recommendations</code><span class="meta">explainable score breakdowns</span></li>
  </ul>

  <footer>
    Machine-readable spec: <a href="/openapi.json">/openapi.json</a> ·
    Swagger UI (needs internet): <a href="/docs">/docs</a> ·
    ReDoc (needs internet): <a href="/redoc">/redoc</a>
  </footer>
</div>

<script>
const out = document.getElementById('out');
const show = (label, data) =>
  out.innerHTML = '<p style="color:var(--muted);font-size:13px;margin:6px 0">' + label +
                  '</p><pre>' + JSON.stringify(data, null, 2) + '</pre>';

async function ping() {
  const pill = document.getElementById('status-pill');
  try {
    const r = await fetch('/ready');
    const j = await r.json();
    const degraded = Object.values(j.checks.providers || {}).some(p => p && p.degraded);
    pill.textContent = j.status + (degraded ? ' · some providers on fallback' : ' · all providers nominal');
    pill.className = 'pill' + (degraded ? ' warn' : '');
  } catch (e) {
    pill.textContent = 'API unreachable';
    pill.className = 'pill warn';
  }
}

async function loadAll() {
  const btn = document.getElementById('btn-load');
  btn.disabled = true;
  try {
    const clusters = await (await fetch('/api/v1/destinations')).json();
    document.getElementById('clusters').innerHTML = clusters.map(c => `
      <div class="card">
        <h3>${c.name}</h3>
        <p>${c.summary.slice(0, 150)}…</p>
        <div class="meta">
          <span>${c.attraction_count} places</span>
          <span>${c.state}</span>
          <span>~${c.recommended_days} days</span>
        </div>
        <div class="meta">
          <a href="/api/v1/destinations/${c.slug}/attractions">browse JSON</a>
        </div>
      </div>`).join('');
    show(`Loaded ${clusters.length} destination clusters.`,
         clusters.map(c => ({ slug: c.slug, attractions: c.attraction_count, state: c.state })));
  } catch (e) {
    show('Failed to load destinations.', { error: String(e) });
  } finally { btn.disabled = false; }
}

async function runDemo() {
  const btn = document.getElementById('btn-demo');
  btn.disabled = true;
  show('Working: creating a demo account, a group trip and running the optimiser…', {});
  try {
    const auth = await (await fetch('/api/v1/auth/demo')).json();
    const h = { 'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + auth.access_token };
    const trips = await (await fetch('/api/v1/trips', { headers: h })).json();
    if (!trips.length) { show('Demo account has no trip yet.', auth.user); return; }
    const trip = trips[0];
    const it = await (await fetch(`/api/v1/trips/${trip.id}/itinerary`, {
      method: 'POST', headers: h, body: JSON.stringify({}) })).json();
    show('Validated itinerary generated by the deterministic pipeline.', {
      trip: trip.title,
      destination: trip.cluster_name,
      members: trip.members.length,
      valid: it.is_valid,
      checks_run: it.validation && it.validation.checks_run,
      activities: it.activity_count,
      travel_km: it.total_travel_km,
      fairness_index: it.fairness_score,
      least_satisfied_member: it.least_satisfied_score,
      cost: it.cost && it.cost.display,
      explanation_source: it.explanation_source,
      days: (it.days || []).map(d => ({
        date: d.calendar_date,
        stops: (d.activities || []).filter(a => a.kind === 'visit')
          .map(a => `${a.start_time}-${a.end_time} ${a.title}`)
      }))
    });
  } catch (e) {
    show('Demo run failed.', { error: String(e) });
  } finally { btn.disabled = false; }
}

ping();
</script>
</body>
</html>
"""
