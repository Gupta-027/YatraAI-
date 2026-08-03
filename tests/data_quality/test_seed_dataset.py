"""Contract tests for the committed seed dataset.

These run in CI without a database. They are the gate that stops a bad data edit
from reaching the planner: if an attraction loses its source, gains an impossible
coordinate, or claims a verified opening time we cannot stand behind, the build
fails here rather than producing a confidently wrong itinerary.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest

from yatraai.config import get_settings
from yatraai.pipelines import contracts, medallion
from yatraai.seed.loader import read_seed_files

EXPECTED_CLUSTERS = {
    "bengaluru",
    "hyderabad",
    "delhi-agra",
    "varanasi",
    "rishikesh-haridwar",
    "puri-konark",
    "shillong-cherrapunji",
    "gangtok",
    "meghalaya-jaintia-dawki",
    "kedarnath",
}

MIN_ATTRACTIONS_PER_CLUSTER = 12
MAX_ATTRACTIONS_PER_CLUSTER = 20


@pytest.fixture(scope="module")
def payloads() -> list[dict]:
    return read_seed_files()


@pytest.fixture(scope="module")
def attractions(payloads) -> list[tuple[dict, dict]]:
    return [(p["cluster"], a) for p in payloads for a in p["attractions"]]


# --------------------------------------------------------------------------- #
class TestCoverage:
    def test_all_ten_clusters_present(self, payloads):
        assert {p["cluster"]["slug"] for p in payloads} == EXPECTED_CLUSTERS

    def test_each_cluster_has_enough_attractions(self, payloads):
        for p in payloads:
            n = len(p["attractions"])
            slug = p["cluster"]["slug"]
            assert MIN_ATTRACTIONS_PER_CLUSTER <= n <= MAX_ATTRACTIONS_PER_CLUSTER, (
                f"{slug} has {n} attractions; expected "
                f"{MIN_ATTRACTIONS_PER_CLUSTER}-{MAX_ATTRACTIONS_PER_CLUSTER}"
            )

    def test_clusters_span_the_intended_travel_variety(self, payloads):
        styles = {s for p in payloads for s in p["cluster"]["travel_style"]}
        # The brief asks for metro, heritage, spiritual, coastal, mountain and NE.
        for required in ("metropolitan", "heritage", "spiritual", "coastal", "mountain"):
            assert required in styles, f"no cluster covers travel style '{required}'"
        assert {p["cluster"]["region"] for p in payloads} >= {"north", "south", "east", "northeast"}

    def test_every_cluster_has_a_wet_weather_option(self, payloads):
        """Weather-aware replanning needs somewhere indoors to move activities to."""
        for p in payloads:
            indoor = [a for a in p["attractions"] if a.get("indoor_outdoor") in ("indoor", "mixed")]
            assert indoor, f"{p['cluster']['slug']} has no indoor/mixed attraction"


class TestIdentity:
    def test_attraction_keys_are_globally_unique(self, attractions):
        keys = [f"{c['slug']}::{a['slug']}" for c, a in attractions]
        dupes = [k for k, n in Counter(keys).items() if n > 1]
        assert not dupes, f"duplicate attraction keys: {dupes}"

    def test_slugs_are_url_safe(self, attractions):
        import re

        for _, a in attractions:
            assert re.fullmatch(r"[a-z0-9-]+", a["slug"]), a["slug"]

    def test_nearby_references_resolve(self, payloads):
        """Neighbour hints must resolve.

        Resolution is global rather than per-cluster because a handful of places
        genuinely sit near a neighbouring circuit (Mawlynnong is closer to Dawki
        than to Shillong). ``resolve_nearby`` in the API mirrors this: it prefers
        a same-cluster match and falls back to a global lookup.
        """
        global_slugs = {a["slug"] for p in payloads for a in p["attractions"]}
        for p in payloads:
            for a in p["attractions"]:
                for ref in a.get("nearby", []):
                    assert ref in global_slugs, (
                        f"{p['cluster']['slug']}::{a['slug']} references unknown "
                        f"nearby attraction '{ref}'"
                    )

    def test_attraction_is_not_listed_as_its_own_neighbour(self, attractions):
        for _, a in attractions:
            assert a["slug"] not in a.get("nearby", [])


class TestGeography:
    def test_coordinates_are_inside_india(self, attractions):
        for _, a in attractions:
            assert contracts.INDIA_LAT[0] <= a["lat"] <= contracts.INDIA_LAT[1], a["slug"]
            assert contracts.INDIA_LON[0] <= a["lon"] <= contracts.INDIA_LON[1], a["slug"]

    def test_attractions_are_plausibly_near_their_cluster_centre(self, payloads):
        """A typo in a coordinate usually shows up as a wildly distant point."""
        for p in payloads:
            c = p["cluster"]
            for a in p["attractions"]:
                km = medallion.haversine_km(c["center_lat"], c["center_lon"], a["lat"], a["lon"])
                assert km < 220, f"{c['slug']}::{a['slug']} is {km:.0f} km from the cluster centre"

    def test_no_two_attractions_share_a_coordinate(self, payloads):
        for p in payloads:
            seen: dict[tuple, str] = {}
            for a in p["attractions"]:
                pt = (round(a["lat"], 4), round(a["lon"], 4))
                assert pt not in seen, f"{a['slug']} shares coordinates with {seen.get(pt)}"
                seen[pt] = a["slug"]


class TestPlanningFields:
    def test_duration_triple_is_ordered(self, attractions):
        for _, a in attractions:
            lo = a.get("min_duration_min", a["typical_duration_min"])
            hi = a.get("max_duration_min", a["typical_duration_min"])
            assert lo <= a["typical_duration_min"] <= hi, a["slug"]

    def test_durations_are_realistic(self, attractions):
        for _, a in attractions:
            assert 10 <= a["typical_duration_min"] <= 600, a["slug"]

    def test_schedules_are_coherent(self, attractions):
        from yatraai.seed.loader import parse_hhmm

        for _, a in attractions:
            for row in a.get("schedule", []):
                if row.get("is_closed"):
                    continue
                opens, closes = parse_hhmm(row.get("opens")), parse_hhmm(row.get("closes"))
                assert opens is not None, f"{a['slug']} open row without opening time"
                assert closes is not None, f"{a['slug']} open row without closing time"
                assert 0 <= opens <= 1440 and 0 <= closes <= 1560

    def test_a_visit_fits_inside_at_least_one_opening_window(self, attractions):
        """An attraction whose minimum visit cannot fit its hours can never be scheduled."""
        from yatraai.seed.loader import parse_hhmm

        for _, a in attractions:
            windows = []
            for row in a.get("schedule", []):
                if row.get("is_closed"):
                    continue
                opens, closes = parse_hhmm(row.get("opens")), parse_hhmm(row.get("closes"))
                if opens is None or closes is None:
                    continue
                if closes <= opens:
                    closes += 24 * 60
                windows.append(closes - opens)
            if not windows:
                continue
            need = a.get("min_duration_min", a["typical_duration_min"])
            assert max(windows) >= need, (
                f"{a['slug']} needs {need} min but its longest opening window is {max(windows)}"
            )

    def test_costs_are_ranges_not_false_precision(self, attractions):
        for _, a in attractions:
            for row in a.get("costs", []):
                lo = float(row.get("min", row.get("amount", 0)))
                hi = float(row.get("max", lo))
                assert lo >= 0 and hi >= lo, a["slug"]

    def test_suitable_months_are_valid(self, attractions):
        for _, a in attractions:
            months = a.get("suitable_months", [])
            assert months, f"{a['slug']} has no suitable months"
            assert all(1 <= m <= 12 for m in months), a["slug"]


class TestProvenanceAndHonesty:
    def test_every_attraction_cites_at_least_one_source(self, attractions):
        for _, a in attractions:
            assert a.get("sources"), f"{a['slug']} has no source"

    def test_sources_use_https_and_allowlisted_domains(self, attractions):
        allow = get_settings().allowed_ingest_domains
        for _, a in attractions:
            for src in a["sources"]:
                assert src["url"].startswith("https://"), src["url"]
                host = (urlparse(src["url"]).hostname or "").lower().removeprefix("www.")
                assert any(host == d or host.endswith("." + d) for d in allow), (
                    f"{a['slug']} cites non-allowlisted domain {host}"
                )

    def test_time_sensitive_fields_are_never_claimed_as_verified(self, attractions):
        """Hours and fees change without notice; the dataset must not pretend otherwise."""
        for _, a in attractions:
            for row in a.get("schedule", []):
                assert row.get("verified", False) is False, (
                    f"{a['slug']} claims a verified opening time"
                )
            for row in a.get("costs", []):
                assert row.get("verified", False) is False, f"{a['slug']} claims a verified fee"

    def test_attractions_with_paid_or_timed_entry_are_flagged_for_verification(self, attractions):
        for _, a in attractions:
            has_paid = any(float(c.get("max", c.get("min", 0))) > 0 for c in a.get("costs", []))
            has_hours = any(not r.get("is_closed") for r in a.get("schedule", []))
            if has_paid or has_hours:
                assert a.get("needs_verification", True) is True or a.get("verification_note"), (
                    f"{a['slug']} has time-sensitive data but no verification flag or note"
                )

    def test_last_verified_dates_are_valid_and_not_in_the_future(self, attractions):
        today = date.today()
        for _, a in attractions:
            raw = a.get("last_verified")
            assert raw, f"{a['slug']} has no last_verified date"
            parsed = datetime.strptime(raw, "%Y-%m-%d").date()
            assert parsed <= today, f"{a['slug']} claims a future verification date"


class TestKnowledgeContent:
    def test_narrative_fields_are_substantial(self, attractions):
        for _, a in attractions:
            assert len(a.get("history", "")) >= 120, f"{a['slug']} history is too thin"
            assert len(a.get("significance", "")) >= 100, f"{a['slug']} significance is too thin"

    def test_every_attraction_has_interesting_facts(self, attractions):
        for _, a in attractions:
            facts = a.get("interesting_facts", [])
            assert 2 <= len(facts) <= 8, f"{a['slug']} has {len(facts)} facts (want 2-5+)"
            assert all(len(f) > 20 for f in facts), a["slug"]

    def test_accessibility_information_is_present(self, attractions):
        for _, a in attractions:
            assert a.get("wheelchair_accessible") in {"yes", "partial", "no", "unknown"}
            assert len(a.get("accessibility_notes", "")) >= 25, (
                f"{a['slug']} lacks usable accessibility notes"
            )

    def test_religious_sites_document_etiquette(self, attractions):
        for _, a in attractions:
            cats = set(a.get("categories", []))
            if cats & {"spiritual", "temple", "mosque", "monastery", "buddhist"}:
                assert a.get("dress_code"), f"{a['slug']} is a religious site with no dress code"
                assert a.get("local_customs"), f"{a['slug']} is a religious site with no customs"


class TestPipelineContracts:
    def test_silver_layer_passes_its_contracts(self, tmp_path: Path):
        results = medallion.run_silver(out_dir=tmp_path)
        assert results["silver_attractions"].rows_out >= 120
        assert results["silver_clusters"].rows_out == 10
        assert results["silver_sources"].rows_rejected == 0, (
            "some source domains are not allow-listed"
        )

    def test_gold_layer_passes_its_contracts(self, tmp_path: Path):
        medallion.run_silver(out_dir=tmp_path / "silver")
        results = medallion.run_gold(silver_dir=tmp_path / "silver", out_dir=tmp_path / "gold")
        assert results["gold_attraction_features"].rows_out >= 120
        assert results["gold_cluster_metrics"].rows_out == 10

    def test_pipeline_is_idempotent(self, tmp_path: Path):
        first = medallion.run_bronze(out_dir=tmp_path / "a")
        second = medallion.run_bronze(out_dir=tmp_path / "b")
        a = (tmp_path / "a" / "raw_catalogue.jsonl").read_text(encoding="utf-8").splitlines()
        b = (tmp_path / "b" / "raw_catalogue.jsonl").read_text(encoding="utf-8").splitlines()
        assert first.rows_out == second.rows_out
        # Ingestion timestamps differ; content hashes must not.
        hashes_a = [json.loads(line)["content_hash"] for line in a]
        hashes_b = [json.loads(line)["content_hash"] for line in b]
        assert hashes_a == hashes_b

    def test_gold_season_scores_penalise_weather_sensitive_sites(self, tmp_path: Path):
        medallion.run_silver(out_dir=tmp_path / "silver")
        medallion.run_gold(silver_dir=tmp_path / "silver", out_dir=tmp_path / "gold")
        import pandas as pd

        df = pd.read_parquet(tmp_path / "gold" / "attraction_features.parquet")
        # A monsoon-shut mountain trail must score worse in July than an air-conditioned museum.
        trek = df[df["slug"] == "double-decker-root-bridge"].iloc[0]
        museum = df[df["slug"] == "salar-jung-museum"].iloc[0]
        assert trek["season_score_7"] < museum["season_score_7"]
        assert museum["season_score_7"] == pytest.approx(1.0)
