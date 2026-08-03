#!/usr/bin/env python
"""Post-deployment verification.

    python scripts/verify_deployment.py --base-url https://your-api.onrender.com
    API_BASE_URL=https://your-api.onrender.com python scripts/verify_deployment.py

Exercises the checklist in docs/deployment.md against a live deployment and exits
non-zero if anything fails, so it can be wired into CI or a release gate.

The flag is parsed with ``argparse`` specifically so an unrecognised argument is a
hard error. Reading the target from the environment alone means a mistyped flag is
silently ignored, the script quietly falls back to localhost:8000, and you get ten
connection failures that look like a broken deployment instead of a typo.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import httpx

_parser = argparse.ArgumentParser(description=__doc__)
_parser.add_argument(
    "--base-url",
    default=os.environ.get("API_BASE_URL", "http://localhost:8000"),
    help="API root to verify (default: $API_BASE_URL, else http://localhost:8000)",
)
_parser.add_argument(
    "--timeout",
    type=float,
    default=float(os.environ.get("VERIFY_TIMEOUT", "90")),
    help="Per-request timeout in seconds (default: 90)",
)
_args = _parser.parse_args()

BASE = _args.base_url.rstrip("/")
# A cold free-tier service can take 50 s to wake; do not mistake that for failure.
TIMEOUT = _args.timeout

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
results: list[tuple[str, str, str]] = []


def check(name: str, fn) -> Any:
    started = time.perf_counter()
    try:
        value = fn()
        elapsed = (time.perf_counter() - started) * 1000
        results.append((PASS, name, f"{elapsed:.0f} ms"))
        return value
    except AssertionError as exc:
        results.append((FAIL, name, str(exc)))
    except Exception as exc:
        results.append((FAIL, name, f"{type(exc).__name__}: {exc}"))
    return None


def main() -> int:
    print(f"Verifying {BASE}\n")
    client = httpx.Client(timeout=TIMEOUT, follow_redirects=True)

    def health():
        r = client.get(f"{BASE}/health")
        assert r.status_code == 200, f"expected 200, got {r.status_code}"
        assert r.json()["status"] == "ok"
        return r.json()

    def ready():
        r = client.get(f"{BASE}/ready")
        assert r.status_code == 200, f"expected 200, got {r.status_code}"
        body = r.json()
        assert body["checks"]["database"] == "ok", f"database: {body['checks']['database']}"
        return body

    def destinations():
        r = client.get(f"{BASE}/api/v1/destinations")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 10, f"expected 10 clusters, got {len(body)}"
        thin = [c["slug"] for c in body if c["attraction_count"] < 12]
        assert not thin, f"clusters with too few attractions: {thin}"
        return body

    def attraction_detail():
        r = client.get(f"{BASE}/api/v1/destinations/delhi-agra/attractions/taj-mahal")
        assert r.status_code == 200
        body = r.json()
        assert len(body["history"]) > 200, "history is too thin"
        assert body["sources"], "no cited sources"
        assert all(s["url"].startswith("https://") for s in body["sources"])
        assert body["needs_verification"] is True, "time-sensitive data not flagged"
        assert all(s["verified"] is False for s in body["schedules"]), (
            "a schedule row claims verification we cannot support"
        )
        return body

    def demo_token():
        r = client.get(f"{BASE}/api/v1/auth/demo")
        assert r.status_code == 200, f"demo login failed: {r.status_code}"
        return r.json()["access_token"]

    def itinerary(token: str):
        headers = {"Authorization": f"Bearer {token}"}
        trips = client.get(f"{BASE}/api/v1/trips", headers=headers).json()
        assert trips, "demo account has no trips"
        trip_id = trips[0]["id"]
        r = client.post(f"{BASE}/api/v1/trips/{trip_id}/itinerary", json={}, headers=headers)
        assert r.status_code in (200, 201), f"generation failed: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert body["is_valid"] is True, "itinerary failed validation"
        assert body["validation"]["checks_run"] >= 15, "too few validation checks ran"
        assert body["validation"]["errors"] == [], body["validation"]["errors"]
        assert body["activity_count"] > 0, "itinerary is empty"
        assert body["cost"]["per_person_low_inr"] < body["cost"]["per_person_high_inr"], (
            "cost is a point estimate, not a range"
        )
        return body

    def assistant_answers():
        r = client.post(
            f"{BASE}/api/v1/assistant/ask",
            json={
                "question": "Why is the Taj Mahal historically important?",
                "cluster_slug": "delhi-agra",
                "attraction_slug": "taj-mahal",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["abstained"] is False, "abstained on an answerable question"
        assert body["citations"], "answered without citations"
        return body

    def assistant_abstains():
        r = client.post(
            f"{BASE}/api/v1/assistant/ask",
            json={"question": "What is the best sushi in Tokyo?", "cluster_slug": "bengaluru"},
        )
        assert r.status_code == 200
        assert r.json()["abstained"] is True, "did not abstain on an out-of-scope question"
        return r.json()

    def metrics():
        r = client.get(f"{BASE}/api/v1/metrics")
        assert r.status_code == 200
        return r.json()

    def openapi():
        r = client.get(f"{BASE}/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert len(paths) >= 20, f"only {len(paths)} documented paths"
        return len(paths)

    check("health", health)
    check("ready (database reachable)", ready)
    check("10 destination clusters", destinations)
    check("attraction detail with citations", attraction_detail)
    token = check("demo login", demo_token)
    if token:
        check("itinerary generation + validation", lambda: itinerary(token))
    check("assistant answers with citations", assistant_answers)
    check("assistant abstains out of scope", assistant_abstains)
    check("provider metrics", metrics)
    check("openapi document", openapi)

    print(f"{'':<6}{'CHECK':<42}DETAIL")
    print("-" * 78)
    for status, name, detail in results:
        print(f"{status:<6}{name:<42}{detail}")

    failures = [r for r in results if r[0] == FAIL]
    print("-" * 78)
    print(f"{len(results) - len(failures)}/{len(results)} passed")

    if failures:
        print("\nFAILED:")
        for _, name, detail in failures:
            print(f"  - {name}: {detail}")
        return 1

    print("\nDeployment verified.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
