"""Compare group-preference aggregation methods on reproducible group profiles.

Run:
    python ml/experiments/aggregation_comparison.py

Writes ``ml/reports/aggregation_comparison.json`` and ``.md``. Every number in
``docs/recommendation.md`` comes from this script; nothing is hand-written.

The scenarios are deliberately adversarial for a simple average - each contains
a minority whose preferences the majority could steamroll. That is the situation
the fairness-aware method exists to handle, so it is the situation we measure.
"""

# ruff: noqa: E402 - sys.path must be set before the yatraai imports so the script
# runs from a plain checkout as well as from an editable install.
from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "apps" / "api") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from yatraai.seed.loader import parse_hhmm, read_seed_files
from yatraai.services.planner.models import (
    AttractionCandidate,
    MemberProfile,
    OpeningWindow,
    TripContext,
)
from yatraai.services.recommend import aggregation, scoring
from yatraai.services.recommend.taxonomy import default_preferences

METHODS = [
    "simple_average",
    "weighted_average",
    "borda_count",
    "max_min_fairness",
    "fairness_aware",
    "fairness_aware_iterative",  # production default: re-scores after every pick
]

# Evaluate at several itinerary sizes. This matters: when the selection approaches
# the size of the candidate pool every method converges (they all pick nearly
# everything), so a single large K would hide the differences entirely. K=5 is a
# realistic two-day itinerary and is the headline figure.
SELECTION_SIZES = (5, 8, 12)
HEADLINE_K = 5


@dataclass
class Scenario:
    name: str
    description: str
    cluster: str
    members: list[MemberProfile]


def _profile(**interests) -> dict:
    base = default_preferences()
    base.update(interests)
    return base


def build_scenarios() -> list[Scenario]:
    return [
        Scenario(
            name="lone_nature_lover",
            description="3 heritage enthusiasts + 1 nature lover. Classic majority-overrule case.",
            cluster="bengaluru",
            members=[
                MemberProfile("a", "Asha", _profile(heritage=5, museums=4, nature=1, adventure=1)),
                MemberProfile(
                    "b", "Bhavna", _profile(heritage=5, museums=4, nature=1, adventure=1)
                ),
                MemberProfile(
                    "c", "Chetan", _profile(heritage=5, museums=3, nature=2, adventure=1)
                ),
                MemberProfile(
                    "d", "Divya", _profile(nature=5, relaxation=5, heritage=1, museums=1)
                ),
            ],
        ),
        Scenario(
            name="two_way_split",
            description="2 spiritual + 2 adventure. No majority; consensus is the challenge.",
            cluster="rishikesh-haridwar",
            members=[
                MemberProfile("a", "Arun", _profile(spiritual=5, relaxation=4, adventure=1)),
                MemberProfile("b", "Bela", _profile(spiritual=5, relaxation=4, adventure=1)),
                MemberProfile("c", "Chirag", _profile(adventure=5, nature=5, spiritual=1)),
                MemberProfile("d", "Deep", _profile(adventure=5, nature=4, spiritual=1)),
            ],
        ),
        Scenario(
            name="multi_generational",
            description="Seniors, parents and a child. Accessibility and pace conflict with interests.",
            cluster="delhi-agra",
            members=[
                MemberProfile(
                    "a",
                    "Grandfather",
                    _profile(heritage=5, spiritual=4, adventure=1, nature=2),
                    mobility_level="limited_walking",
                    is_senior=True,
                    pace="relaxed",
                ),
                MemberProfile(
                    "b",
                    "Grandmother",
                    _profile(spiritual=5, heritage=4, adventure=1),
                    mobility_level="limited_walking",
                    is_senior=True,
                    pace="relaxed",
                ),
                MemberProfile("c", "Parent", _profile(heritage=4, food=5, shopping=4)),
                MemberProfile(
                    "d", "Child", _profile(museums=5, adventure=4, wildlife=5), is_child=True
                ),
            ],
        ),
        Scenario(
            name="unanimous_group",
            description="Control: everyone wants the same thing. All methods should agree.",
            cluster="hyderabad",
            members=[
                MemberProfile("a", "A", _profile(heritage=5, museums=5)),
                MemberProfile("b", "B", _profile(heritage=5, museums=5)),
                MemberProfile("c", "C", _profile(heritage=5, museums=5)),
            ],
        ),
        Scenario(
            name="one_against_five",
            description="5 vs 1. The hardest fairness case in the set.",
            cluster="puri-konark",
            members=[
                *[
                    MemberProfile(f"m{i}", f"M{i}", _profile(spiritual=5, heritage=4, nature=1))
                    for i in range(5)
                ],
                MemberProfile(
                    "solo", "Solo", _profile(nature=5, wildlife=5, spiritual=1, heritage=1)
                ),
            ],
        ),
    ]


def load_candidates(cluster_slug: str) -> list[AttractionCandidate]:
    """Load real seed attractions without needing a database."""
    for payload in read_seed_files():
        if payload["cluster"]["slug"] != cluster_slug:
            continue
        out = []
        for a in payload["attractions"]:
            windows, closed = [], set()
            for row in a.get("schedule", []):
                if row.get("is_closed"):
                    day = row.get("day_of_week", -1)
                    if isinstance(day, int) and day >= 0:
                        closed.add(day)
                    continue
                opens, closes = parse_hhmm(row.get("opens")), parse_hhmm(row.get("closes"))
                if opens is None or closes is None:
                    continue
                if closes <= opens:
                    closes += 24 * 60
                windows.append(OpeningWindow(int(row.get("day_of_week", -1)), opens, closes))
            adult = [c for c in a.get("costs", []) if c.get("visitor_type") == "indian_adult"]
            cost_min = min((float(c.get("min", 0)) for c in adult), default=0.0)
            cost_max = max((float(c.get("max", c.get("min", 0))) for c in adult), default=0.0)
            out.append(
                AttractionCandidate(
                    slug=a["slug"],
                    name=a["name"],
                    lat=a["lat"],
                    lon=a["lon"],
                    categories=a.get("categories", []),
                    typical_duration_min=a["typical_duration_min"],
                    min_duration_min=a.get("min_duration_min", a["typical_duration_min"] // 2),
                    max_duration_min=a.get("max_duration_min", a["typical_duration_min"] * 2),
                    quality_score=a.get("quality_score", 0.6),
                    indoor_outdoor=a.get("indoor_outdoor", "outdoor"),
                    weather_sensitivity=a.get("weather_sensitivity", 0.5),
                    typical_crowd_level=a.get("typical_crowd_level", "medium"),
                    suitable_months=a.get("suitable_months", list(range(1, 13))),
                    wheelchair_accessible=a.get("wheelchair_accessible", "unknown"),
                    senior_friendly=a.get("senior_friendly", 3),
                    child_friendly=a.get("child_friendly", 3),
                    physical_intensity=a.get("physical_intensity", 2),
                    entry_cost_min=cost_min,
                    entry_cost_max=cost_max,
                    windows=windows,
                    closed_weekdays=closed,
                    cluster_slug=cluster_slug,
                )
            )
        return out
    raise ValueError(f"cluster not found: {cluster_slug}")


def context_for(cluster_slug: str, candidates: list[AttractionCandidate]) -> TripContext:
    lat = sum(c.lat for c in candidates) / len(candidates)
    lon = sum(c.lon for c in candidates) / len(candidates)
    return TripContext(
        trip_id=f"exp-{cluster_slug}",
        cluster_slug=cluster_slug,
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 13),
        traveller_count=4,
        budget_per_person_inr=15000,
        base_lat=lat,
        base_lon=lon,
    )


def run() -> dict:
    results: dict = {"scenarios": [], "generated_by": "ml/experiments/aggregation_comparison.py"}

    for scenario in build_scenarios():
        candidates = load_candidates(scenario.cluster)
        ctx = context_for(scenario.cluster, candidates)
        row: dict = {
            "scenario": scenario.name,
            "description": scenario.description,
            "cluster": scenario.cluster,
            "members": len(scenario.members),
            "candidate_pool": len(candidates),
            "methods": {},
        }

        for method in METHODS:
            iterative = method == "fairness_aware_iterative"
            scoring_method = "fairness_aware" if iterative else method
            started = time.perf_counter()
            scored, _ = scoring.score_candidates(
                candidates, ctx, scenario.members, [], method=scoring_method
            )
            elapsed_ms = (time.perf_counter() - started) * 1000

            by_k: dict[str, dict] = {}
            for k in SELECTION_SIZES:
                if iterative:
                    picked = aggregation.select_fairly(scenario.members, scored, k)
                    selection = [s.candidate for s in picked]
                else:
                    selection = [s.candidate for s in scored[:k]]
                satisfaction = aggregation.evaluate_selection(scenario.members, selection)
                coverage = scoring.coverage_by_interest(selection, scenario.members)
                by_k[str(k)] = {
                    "mean_satisfaction": round(satisfaction.mean, 4),
                    "least_satisfied": round(satisfaction.least_satisfied, 4),
                    "least_satisfied_member": satisfaction.least_satisfied_member,
                    "fairness_index": round(satisfaction.fairness_index, 4),
                    "consensus": round(satisfaction.consensus, 4),
                    "satisfaction_spread": round(
                        max(satisfaction.per_member.values())
                        - min(satisfaction.per_member.values()),
                        4,
                    ),
                    "interests_covered": round(
                        sum(1 for v in coverage.values() if v >= 0.5) / max(1, len(coverage)), 4
                    ),
                }

            row["methods"][method] = {
                **by_k[str(HEADLINE_K)],
                "by_k": by_k,
                "scoring_ms": round(elapsed_ms, 2),
                "top_5": [s.candidate.slug for s in scored[:5]],
            }
        results["scenarios"].append(row)

    # ---- aggregate across scenarios ---------------------------------------
    metrics = (
        "mean_satisfaction",
        "least_satisfied",
        "fairness_index",
        "consensus",
        "satisfaction_spread",
        "interests_covered",
    )
    summary: dict = {}
    for method in METHODS:
        summary[method] = {
            metric: round(
                statistics.fmean(s["methods"][method][metric] for s in results["scenarios"]), 4
            )
            for metric in metrics
        }
        summary[method]["scoring_ms"] = round(
            statistics.fmean(s["methods"][method]["scoring_ms"] for s in results["scenarios"]), 4
        )
        summary[method]["by_k"] = {
            str(k): {
                metric: round(
                    statistics.fmean(
                        s["methods"][method]["by_k"][str(k)][metric] for s in results["scenarios"]
                    ),
                    4,
                )
                for metric in metrics
            }
            for k in SELECTION_SIZES
        }
    results["summary"] = summary
    results["headline_k"] = HEADLINE_K
    results["selection_sizes"] = list(SELECTION_SIZES)
    return results


def write_report(results: dict) -> None:
    out_dir = REPO_ROOT / "ml" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "aggregation_comparison.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )

    lines = [
        "# Group aggregation: measured comparison",
        "",
        "> Generated by `python ml/experiments/aggregation_comparison.py`. "
        "Re-run to reproduce; the script is deterministic.",
        "",
        f"Scenarios: **{len(results['scenarios'])}** reproducible group profiles across real seed "
        f"destinations. Each method ranks the full candidate pool; the top **K = "
        f"{results['headline_k']}** are evaluated (a realistic two-day itinerary).",
        "",
        f"## Averages across all scenarios (K = {results['headline_k']})",
        "",
        "| Method | Mean satisfaction | **Least satisfied** | Fairness (Jain) | Consensus | Spread | Interests covered | Scoring ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for method, stats in results["summary"].items():
        marker = " **(production default)**" if method == "fairness_aware_iterative" else ""
        lines.append(
            f"| `{method}`{marker} | {stats['mean_satisfaction']:.3f} | "
            f"**{stats['least_satisfied']:.3f}** | {stats['fairness_index']:.3f} | "
            f"{stats['consensus']:.3f} | {stats['satisfaction_spread']:.3f} | "
            f"{stats['interests_covered']:.2f} | {stats['scoring_ms']:.1f} |"
        )

    best_min = max(results["summary"], key=lambda m: results["summary"][m]["least_satisfied"])
    best_mean = max(results["summary"], key=lambda m: results["summary"][m]["mean_satisfaction"])
    base = results["summary"]["simple_average"]
    chosen = results["summary"]["fairness_aware_iterative"]
    extreme = results["summary"]["max_min_fairness"]

    floor_gain = (
        100 * (chosen["least_satisfied"] - base["least_satisfied"]) / base["least_satisfied"]
    )
    mean_cost = (
        100 * (base["mean_satisfaction"] - chosen["mean_satisfaction"]) / base["mean_satisfaction"]
    )
    spread_cut = (
        100
        * (base["satisfaction_spread"] - chosen["satisfaction_spread"])
        / base["satisfaction_spread"]
    )
    max_floor_gain = (
        100 * (extreme["least_satisfied"] - base["least_satisfied"]) / base["least_satisfied"]
    )
    max_mean_cost = (
        100 * (base["mean_satisfaction"] - extreme["mean_satisfaction"]) / base["mean_satisfaction"]
    )

    lines += [
        "",
        "**Reading the table.** *Least satisfied* is the metric that matters for the brief's "
        "requirement that a majority must not ignore one member. *Spread* is the gap between the "
        "happiest and unhappiest member - lower is fairer.",
        "",
        f"- Highest mean satisfaction: `{best_mean}`",
        f"- Highest floor for the least-satisfied member: `{best_min}`",
        "",
        "## Why `fairness_aware_iterative` is the production default",
        "",
        "This is a trade-off, and the numbers make it explicit.",
        "",
        "| | Floor gain vs simple average | Mean-satisfaction cost | Spread reduction |",
        "|---|---|---|---|",
        f"| `max_min_fairness` | **+{max_floor_gain:.1f}%** | -{max_mean_cost:.1f}% | "
        f"{100 * (base['satisfaction_spread'] - extreme['satisfaction_spread']) / base['satisfaction_spread']:.0f}% |",
        f"| `fairness_aware_iterative` | +{floor_gain:.1f}% | **-{mean_cost:.1f}%** | {spread_cut:.0f}% |",
        "",
        f"Pure max-min raises the floor most, but it flattens the itinerary: it costs "
        f"{max_mean_cost:.1f}% of average satisfaction, because it keeps choosing the option "
        f"nobody objects to rather than the option most people want. The iterative method "
        f"captures **{100 * floor_gain / max_floor_gain:.0f}% of the fairness gain for "
        f"{100 * mean_cost / max_mean_cost:.0f}% of the cost**, which is why it ships.",
        "",
        "The single-pass `fairness_aware` variant barely improves on a simple average "
        f"(+{100 * (results['summary']['fairness_aware']['least_satisfied'] - base['least_satisfied']) / base['least_satisfied']:.1f}%). "
        "That is the point of measuring: scoring each attraction in isolation cannot know that "
        "the shortlist already has four temples and nothing for the one member who wanted a lake. "
        "Only recomputing satisfaction after each pick can.",
        "",
        "## Sensitivity to itinerary size",
        "",
        "As the selection approaches the size of the candidate pool, every method converges - "
        "they all end up picking nearly everything, so the choice of aggregation stops mattering. "
        "This is why the headline figure uses a realistic K rather than a large one.",
        "",
        "| Method | "
        + " | ".join(f"K={k} least-satisfied" for k in results["selection_sizes"])
        + " |",
        "|---" * (len(results["selection_sizes"]) + 1) + "|",
    ]
    for method in results["summary"]:
        cells = " | ".join(
            f"{results['summary'][method]['by_k'][str(k)]['least_satisfied']:.3f}"
            for k in results["selection_sizes"]
        )
        lines.append(f"| `{method}` | {cells} |")

    lines += [
        "",
        "## Per-scenario detail",
        "",
    ]
    for scenario in results["scenarios"]:
        lines += [
            f"### {scenario['scenario']}",
            "",
            f"{scenario['description']}  ",
            f"Destination `{scenario['cluster']}`, {scenario['members']} members, "
            f"{scenario['candidate_pool']} candidate attractions.",
            "",
            "| Method | Mean | Least satisfied | Fairness | Spread |",
            "|---|---|---|---|---|",
        ]
        for method, stats in scenario["methods"].items():
            lines.append(
                f"| `{method}` | {stats['mean_satisfaction']:.3f} | "
                f"{stats['least_satisfied']:.3f} | {stats['fairness_index']:.3f} | "
                f"{stats['satisfaction_spread']:.3f} |"
            )
        lines.append("")

    (out_dir / "aggregation_comparison.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_dir / 'aggregation_comparison.md'}")


if __name__ == "__main__":
    output = run()
    write_report(output)
    print(json.dumps(output["summary"], indent=2))
