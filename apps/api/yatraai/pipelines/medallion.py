"""Bronze -> Silver -> Gold transformations over the curated catalogue.

Layer responsibilities
----------------------
**Bronze** - raw capture, no interpretation. Seed files are landed verbatim as
newline-delimited JSON with an ingestion timestamp and a content hash. Weather
and routing provider responses land here too when they are fetched.

**Silver** - cleaned, normalised, deduplicated, *validated*. Times become
minutes-from-midnight integers, fees become explicit min/max ranges, source URLs
are checked against the ingestion allow-list, coordinates are bounds-checked.
Anything violating the Pandera contract is rejected with a reason.

**Gold** - analytics- and model-ready features: per-attraction suitability
components, month-by-month seasonal scores, and per-cluster quality metrics.

Every stage is **idempotent** (same input -> same output, safe to re-run) and
records a ``PipelineRun`` row with row counts and check results.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from yatraai.config import get_settings
from yatraai.logging_config import get_logger
from yatraai.pipelines import contracts
from yatraai.seed.loader import parse_hhmm, read_seed_files

log = get_logger(__name__)

DOW_NAMES = {"all": -1, "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

CROWD_PENALTY = {"low": 0.0, "medium": 0.25, "high": 0.6, "very_high": 1.0}
ACCESS_SCORE = {"yes": 1.0, "partial": 0.55, "unknown": 0.3, "no": 0.0}
CONFIDENCE_SCORE = {"high": 1.0, "medium": 0.65, "low": 0.35}
SOURCE_TYPE_SCORE = {
    "official": 1.0,
    "government": 0.95,
    "encyclopedic": 0.6,
    "openstreetmap": 0.55,
    "editorial": 0.4,
}


@dataclass
class LayerResult:
    layer: str
    name: str
    rows_in: int = 0
    rows_out: int = 0
    rows_rejected: int = 0
    duration_ms: float = 0.0
    checks: dict[str, Any] = field(default_factory=dict)
    rejections: list[dict] = field(default_factory=list)
    path: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _write(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=False)
        return path
    except Exception:  # pragma: no cover - pyarrow always present in our deps
        csv_path = path.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        return csv_path


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------- #
# BRONZE
# --------------------------------------------------------------------------- #
def run_bronze(seed_dir: Path | None = None, out_dir: Path | None = None) -> LayerResult:
    started = time.perf_counter()
    s = get_settings()
    out_dir = out_dir or (s.data_dir / "bronze")
    out_dir.mkdir(parents=True, exist_ok=True)

    payloads = read_seed_files(seed_dir)
    ingested_at = _now().isoformat()
    records = []
    for payload in payloads:
        cluster_slug = payload["cluster"]["slug"]
        records.append(
            {
                "source_file": payload.get("_source_file", ""),
                "cluster_slug": cluster_slug,
                "record_type": "cluster",
                "record_key": cluster_slug,
                "payload": json.dumps(payload["cluster"], ensure_ascii=False),
                "content_hash": _hash(payload["cluster"]),
                "ingested_at": ingested_at,
            }
        )
        for attraction in payload.get("attractions", []):
            records.append(
                {
                    "source_file": payload.get("_source_file", ""),
                    "cluster_slug": cluster_slug,
                    "record_type": "attraction",
                    "record_key": f"{cluster_slug}::{attraction['slug']}",
                    "payload": json.dumps(attraction, ensure_ascii=False),
                    "content_hash": _hash(attraction),
                    "ingested_at": ingested_at,
                }
            )

    df = pd.DataFrame.from_records(records)
    # Idempotency: identical content hashes collapse to one row.
    before = len(df)
    df = df.drop_duplicates(subset=["record_key", "content_hash"]).reset_index(drop=True)

    path = out_dir / "raw_catalogue.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in df.to_dict("records"):
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    result = LayerResult(
        layer="bronze",
        name="raw_catalogue",
        rows_in=before,
        rows_out=len(df),
        rows_rejected=before - len(df),
        duration_ms=(time.perf_counter() - started) * 1000,
        checks={
            "files_read": len(payloads),
            "clusters": int((df["record_type"] == "cluster").sum()),
            "attractions": int((df["record_type"] == "attraction").sum()),
        },
        path=str(path),
    )
    log.info("pipeline.bronze.done", **result.checks, rows=result.rows_out)
    return result


# --------------------------------------------------------------------------- #
# SILVER
# --------------------------------------------------------------------------- #
def _normalise_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _domain_allowed(domain: str, allow: set[str]) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in allow)


def run_silver(seed_dir: Path | None = None, out_dir: Path | None = None) -> dict[str, LayerResult]:
    started = time.perf_counter()
    s = get_settings()
    out_dir = out_dir or (s.data_dir / "silver")
    payloads = read_seed_files(seed_dir)
    allow = s.allowed_ingest_domains

    cluster_rows, attraction_rows = [], []
    schedule_rows, cost_rows, source_rows = [], [], []
    rejections: list[dict] = []
    seen_keys: set[str] = set()

    for payload in payloads:
        c = payload["cluster"]
        attractions = payload.get("attractions", [])
        cluster_rows.append(
            {
                "slug": c["slug"],
                "name": c["name"].strip(),
                "state": c["state"].strip(),
                "region": c["region"].strip().lower(),
                "summary": " ".join(c["summary"].split()),
                "center_lat": float(c["center_lat"]),
                "center_lon": float(c["center_lon"]),
                "recommended_days": int(c.get("recommended_days", 3)),
                "n_best_months": len(c.get("best_months", [])),
                "n_avoid_months": len(c.get("avoid_months", [])),
                "n_attractions": len(attractions),
                "travel_style": "|".join(c.get("travel_style", [])),
                "intercity_hub": c.get("intercity_hub", ""),
            }
        )

        for a in attractions:
            key = f"{c['slug']}::{a['slug']}"
            if key in seen_keys:
                rejections.append({"key": key, "reason": "duplicate_attraction_key"})
                continue
            seen_keys.add(key)

            typical = int(a["typical_duration_min"])
            lo = int(a.get("min_duration_min", max(15, typical // 2)))
            hi = int(a.get("max_duration_min", typical * 2))
            # Repair rather than reject: clamp an inconsistent duration triple.
            lo, hi = min(lo, typical), max(hi, typical)

            attraction_rows.append(
                {
                    "cluster_slug": c["slug"],
                    "slug": a["slug"],
                    "attraction_key": key,
                    "name": a["name"].strip(),
                    "locality": a.get("locality", "").strip(),
                    "city": a["city"].strip(),
                    "lat": float(a["lat"]),
                    "lon": float(a["lon"]),
                    "categories": "|".join(a.get("categories", [])),
                    "n_categories": len(a.get("categories", [])),
                    "summary": " ".join(a["summary"].split()),
                    "typical_duration_min": typical,
                    "min_duration_min": lo,
                    "max_duration_min": hi,
                    "indoor_outdoor": a.get("indoor_outdoor", "outdoor"),
                    "weather_sensitivity": float(a.get("weather_sensitivity", 0.5)),
                    "typical_crowd_level": a.get("typical_crowd_level", "medium"),
                    "wheelchair_accessible": a.get("wheelchair_accessible", "unknown"),
                    "senior_friendly": int(a.get("senior_friendly", 3)),
                    "child_friendly": int(a.get("child_friendly", 3)),
                    "physical_intensity": int(a.get("physical_intensity", 2)),
                    "quality_score": float(a.get("quality_score", 0.6)),
                    "popularity_rank": int(a.get("popularity_rank", 50)),
                    "suitable_months": "|".join(str(m) for m in a.get("suitable_months", [])),
                    "n_suitable_months": len(a.get("suitable_months", list(range(1, 13)))),
                    "best_time_of_day": "|".join(a.get("best_time_of_day", [])),
                    "n_sources": len(a.get("sources", [])),
                    "n_facts": len(a.get("interesting_facts", [])),
                    "has_history": bool((a.get("history") or "").strip()),
                    "has_significance": bool((a.get("significance") or "").strip()),
                    "has_etiquette": bool(
                        (a.get("dress_code") or "").strip()
                        or (a.get("photography_policy") or "").strip()
                    ),
                    "data_confidence": a.get("data_confidence", "medium"),
                    "needs_verification": bool(a.get("needs_verification", True)),
                    "last_verified": a.get("last_verified"),
                }
            )

            for row in a.get("schedule", []):
                dow = row.get("day_of_week", row.get("day", "all"))
                dow_int = DOW_NAMES.get(str(dow).lower(), dow) if not isinstance(dow, int) else dow
                opens, closes = parse_hhmm(row.get("opens")), parse_hhmm(row.get("closes"))
                # A closing time before opening means the site runs past midnight.
                if opens is not None and closes is not None and closes <= opens:
                    closes += 24 * 60
                schedule_rows.append(
                    {
                        "attraction_key": key,
                        "day_of_week": int(dow_int),
                        "opens_min": opens,
                        "closes_min": closes,
                        "is_closed": bool(row.get("is_closed", False)),
                        "season": row.get("season", "all"),
                        "note": row.get("note", ""),
                        "verified": bool(row.get("verified", False)),
                    }
                )

            for row in a.get("costs", []):
                amount_min = float(row.get("min", row.get("amount", 0)))
                amount_max = float(row.get("max", amount_min))
                cost_rows.append(
                    {
                        "attraction_key": key,
                        "visitor_type": row.get("visitor_type", "indian_adult"),
                        "currency": row.get("currency", "INR"),
                        "amount_min": amount_min,
                        "amount_max": max(amount_min, amount_max),
                        "is_free": bool(row.get("is_free", amount_max == 0)),
                        "note": row.get("note", ""),
                        "verified": bool(row.get("verified", False)),
                    }
                )

            for row in a.get("sources", []):
                domain = _normalise_domain(row["url"])
                allowed = _domain_allowed(domain, allow)
                if not allowed:
                    rejections.append(
                        {"key": key, "reason": "source_domain_not_allowlisted", "domain": domain}
                    )
                    continue
                source_rows.append(
                    {
                        "attraction_key": key,
                        "url": row["url"],
                        "domain": domain,
                        "title": row.get("title", ""),
                        "source_type": row.get("type", "official"),
                        "covers": "|".join(row.get("covers", [])),
                        "allowed_domain": allowed,
                        "last_verified": row.get("last_verified"),
                    }
                )

    frames = {
        "silver_clusters": pd.DataFrame(cluster_rows),
        "silver_attractions": pd.DataFrame(attraction_rows),
        "silver_schedules": pd.DataFrame(schedule_rows),
        "silver_costs": pd.DataFrame(cost_rows),
        "silver_sources": pd.DataFrame(source_rows),
    }

    # Rejections are attributed to the dataset that dropped the row.
    rejected_by_dataset = {
        "silver_sources": sum(
            1 for r in rejections if r["reason"] == "source_domain_not_allowlisted"
        ),
        "silver_attractions": sum(
            1 for r in rejections if r["reason"] == "duplicate_attraction_key"
        ),
    }

    results: dict[str, LayerResult] = {}
    for name, df in frames.items():
        stage_started = time.perf_counter()
        validated = contracts.validate(name, df)
        path = _write(validated, out_dir / f"{name.removeprefix('silver_')}.parquet")
        results[name] = LayerResult(
            layer="silver",
            name=name,
            rows_in=len(df),
            rows_out=len(validated),
            rows_rejected=rejected_by_dataset.get(name, 0),
            duration_ms=(time.perf_counter() - stage_started) * 1000,
            checks={"contract": name, "columns": len(validated.columns)},
            rejections=[r for r in rejections if rejected_by_dataset.get(name)],
            path=str(path),
        )
    log.info(
        "pipeline.silver.done",
        clusters=len(cluster_rows),
        attractions=len(attraction_rows),
        schedules=len(schedule_rows),
        costs=len(cost_rows),
        sources=len(source_rows),
        rejections=len(rejections),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return results


# --------------------------------------------------------------------------- #
# GOLD
# --------------------------------------------------------------------------- #
def _season_scores(suitable_months: str, weather_sensitivity: float) -> dict[str, float]:
    """Month-by-month suitability in [0,1].

    A month listed as suitable scores 1.0. An unsuitable month is penalised in
    proportion to how weather-sensitive the site is, so an air-conditioned museum
    barely moves while an exposed viewpoint drops close to zero.
    """
    months = {int(m) for m in suitable_months.split("|") if m}
    out = {}
    for m in range(1, 13):
        if not months or m in months:
            out[f"season_score_{m}"] = 1.0
        else:
            out[f"season_score_{m}"] = round(max(0.0, 1.0 - 0.9 * weather_sensitivity), 4)
    return out


def run_gold(silver_dir: Path | None = None, out_dir: Path | None = None) -> dict[str, LayerResult]:
    started = time.perf_counter()
    s = get_settings()
    silver_dir = silver_dir or (s.data_dir / "silver")
    out_dir = out_dir or (s.data_dir / "gold")

    def _read(name: str) -> pd.DataFrame:
        pq, csv = silver_dir / f"{name}.parquet", silver_dir / f"{name}.csv"
        if pq.exists():
            return pd.read_parquet(pq)
        if csv.exists():
            return pd.read_csv(csv)
        raise FileNotFoundError(f"Silver dataset missing: {name}. Run the silver stage first.")

    attractions = _read("attractions")
    costs = _read("costs")
    sources = _read("sources")
    clusters = _read("clusters")

    # ---- cost index (0 = free, 1 = most expensive in the corpus) ----
    adult = costs[costs["visitor_type"] == "indian_adult"]
    cost_by_key = adult.groupby("attraction_key")["amount_max"].max()
    max_cost = float(cost_by_key.max()) if len(cost_by_key) else 1.0
    max_cost = max(max_cost, 1.0)

    # ---- evidence quality from source provenance ----
    sources = sources.copy()
    sources["type_score"] = sources["source_type"].map(SOURCE_TYPE_SCORE).fillna(0.4)
    evidence = sources.groupby("attraction_key").agg(
        best_source=("type_score", "max"), n_src=("type_score", "size")
    )

    rows = []
    for r in attractions.to_dict("records"):
        key = r["attraction_key"]
        crowd_penalty = CROWD_PENALTY.get(r["typical_crowd_level"], 0.25)
        access = ACCESS_SCORE.get(r["wheelchair_accessible"], 0.3)
        # Physical intensity matters as much as step-free access for real groups.
        accessibility_score = round(
            0.6 * access + 0.4 * (1.0 - (r["physical_intensity"] - 1) / 4.0), 4
        )
        family_score = round((r["senior_friendly"] + r["child_friendly"]) / 10.0, 4)
        indoor_score = {"indoor": 1.0, "mixed": 0.5, "outdoor": 0.0}[r["indoor_outdoor"]]
        cost_value = float(cost_by_key.get(key, 0.0))
        cost_index = round(min(1.0, cost_value / max_cost), 4)

        ev = evidence.loc[key] if key in evidence.index else None
        best_source = float(ev["best_source"]) if ev is not None else 0.4
        n_src = int(ev["n_src"]) if ev is not None else 0
        content_completeness = (
            0.4 * bool(r["has_history"])
            + 0.3 * bool(r["has_significance"])
            + 0.2 * min(1.0, r["n_facts"] / 3.0)
            + 0.1 * bool(r["has_etiquette"])
        )
        evidence_score = round(
            0.45 * best_source
            + 0.20 * min(1.0, n_src / 2.0)
            + 0.20 * CONFIDENCE_SCORE.get(r["data_confidence"], 0.65)
            + 0.15 * content_completeness,
            4,
        )

        row = {
            "attraction_key": key,
            "cluster_slug": r["cluster_slug"],
            "slug": r["slug"],
            "name": r["name"],
            "lat": r["lat"],
            "lon": r["lon"],
            "categories": r["categories"],
            "quality_score": float(r["quality_score"]),
            "accessibility_score": accessibility_score,
            "family_score": family_score,
            "indoor_score": float(indoor_score),
            "crowd_penalty": float(crowd_penalty),
            "cost_index": cost_index,
            "cost_inr_max": cost_value,
            "evidence_score": evidence_score,
            "duration_hours": round(r["typical_duration_min"] / 60.0, 3),
            "weather_sensitivity": float(r["weather_sensitivity"]),
            "physical_intensity": int(r["physical_intensity"]),
            "verification_required": bool(r["needs_verification"]),
        }
        row.update(_season_scores(r["suitable_months"], float(r["weather_sensitivity"])))
        rows.append(row)

    features = pd.DataFrame(rows)

    # ---- per-cluster metrics ----
    metric_rows = []
    for slug, group in attractions.groupby("cluster_slug"):
        coords = group[["lat", "lon"]].to_numpy()
        spread = 0.0
        if len(coords) > 1:
            centroid_lat = float(group["lat"].mean())
            centroid_lon = float(group["lon"].mean())
            spread = float(
                max(haversine_km(centroid_lat, centroid_lon, la, lo) for la, lo in coords)
            )
        cats = {c for row in group["categories"] for c in str(row).split("|") if c}
        metric_rows.append(
            {
                "cluster_slug": slug,
                "n_attractions": len(group),
                "mean_quality": round(float(group["quality_score"].mean()), 4),
                "pct_wheelchair_ok": round(
                    float((group["wheelchair_accessible"].isin(["yes", "partial"])).mean()), 4
                ),
                "pct_indoor": round(
                    float((group["indoor_outdoor"].isin(["indoor", "mixed"])).mean()), 4
                ),
                "median_duration_min": float(group["typical_duration_min"].median()),
                "geo_spread_km": round(spread, 3),
                "pct_needs_verification": round(float(group["needs_verification"].mean()), 4),
                "n_categories": len(cats),
                "mean_senior_friendly": round(float(group["senior_friendly"].mean()), 3),
                "mean_child_friendly": round(float(group["child_friendly"].mean()), 3),
            }
        )
    cluster_metrics = pd.DataFrame(metric_rows).merge(
        clusters[["slug", "name", "state", "region"]].rename(columns={"slug": "cluster_slug"}),
        on="cluster_slug",
        how="left",
    )

    results: dict[str, LayerResult] = {}
    for name, df, filename in (
        ("gold_attraction_features", features, "attraction_features.parquet"),
        ("gold_cluster_metrics", cluster_metrics, "cluster_metrics.parquet"),
    ):
        stage_started = time.perf_counter()
        validated = contracts.validate(name, df)
        path = _write(validated, out_dir / filename)
        results[name] = LayerResult(
            layer="gold",
            name=name,
            rows_in=len(df),
            rows_out=len(validated),
            duration_ms=(time.perf_counter() - stage_started) * 1000,
            checks={"contract": name, "columns": len(validated.columns)},
            path=str(path),
        )

    log.info(
        "pipeline.gold.done",
        features=len(features),
        clusters=len(cluster_metrics),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return results


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_all(seed_dir: Path | None = None, *, record_runs: bool = True) -> dict[str, LayerResult]:
    """Run the whole medallion pipeline. Safe to re-run at any time."""
    results: dict[str, LayerResult] = {}
    bronze = run_bronze(seed_dir)
    results["bronze_raw_catalogue"] = bronze
    results.update(run_silver(seed_dir))
    results.update(run_gold())

    if record_runs:
        _record_runs(results)
    return results


def _record_runs(results: dict[str, LayerResult]) -> None:
    """Persist run metadata for the data-freshness panel. Best-effort."""
    try:
        from sqlalchemy import select

        from yatraai.db.models import PipelineRun
        from yatraai.db.session import session_scope

        run_key = date.today().isoformat()
        with session_scope() as session:
            for name, result in results.items():
                existing = session.scalar(
                    select(PipelineRun).where(
                        PipelineRun.pipeline == name, PipelineRun.run_key == run_key
                    )
                )
                run = existing or PipelineRun(pipeline=name, run_key=run_key)
                run.layer = result.layer
                run.status = "success"
                run.rows_in = result.rows_in
                run.rows_out = result.rows_out
                run.rows_rejected = result.rows_rejected
                run.started_at = _now()
                run.finished_at = _now()
                run.duration_ms = result.duration_ms
                run.checks = {**result.checks, "rejections": result.rejections[:20]}
                run.error = ""
                if existing is None:
                    session.add(run)
    except Exception as exc:  # pragma: no cover - DB is optional for the pipeline
        log.warning("pipeline.run_record_failed", error=str(exc))
