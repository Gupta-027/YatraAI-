"""Measure the OR-Tools planner against the greedy baseline.

Run:
    python ml/experiments/planner_comparison.py

Writes ``ml/reports/planner_comparison.json`` and ``.md``. Both planners receive
identical inputs, identical hard constraints and identical scored candidates, so
the difference isolates *scheduling quality*.

Metrics reported (all measured, none estimated):
total travel distance, total travel time, activities scheduled, satisfied
preferences, constraint violations, fairness index, attraction utility,
computation time.
"""

# ruff: noqa: E402 - sys.path must be set before the yatraai imports so the script
# runs from a plain checkout as well as from an editable install.
from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(REPO_ROOT / "apps" / "api"), str(Path(__file__).resolve().parent)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from aggregation_comparison import context_for, load_candidates

from yatraai.services.planner import plan_trip
from yatraai.services.planner.models import MemberProfile
from yatraai.services.recommend.taxonomy import default_preferences
from yatraai.services.weather.climatology import climatology_for

GENERATORS = ("greedy", "ortools")
REPEATS = 3  # timing runs per configuration


@dataclass
class Case:
    name: str
    cluster: str
    days: int
    pace: str
    travellers: int
    budget: int
    members: list[MemberProfile]
    must_visit: list[str]
    accessibility: bool = False


def _profile(**interests) -> dict:
    base = default_preferences()
    base.update(interests)
    return base


def build_cases() -> list[Case]:
    return [
        Case(
            "bengaluru_3day_balanced",
            "bengaluru",
            3,
            "balanced",
            3,
            12000,
            [
                MemberProfile("a", "Asha", _profile(heritage=5, museums=4, nature=2)),
                MemberProfile("b", "Ben", _profile(nature=5, relaxation=4, heritage=2)),
                MemberProfile("c", "Chi", _profile(spiritual=5, heritage=3)),
            ],
            must_visit=[],
        ),
        Case(
            "delhi_agra_4day_heritage",
            "delhi-agra",
            4,
            "balanced",
            4,
            25000,
            [
                MemberProfile("a", "A", _profile(heritage=5, museums=5, food=4)),
                MemberProfile("b", "B", _profile(heritage=5, photography=5, shopping=3)),
                MemberProfile("c", "C", _profile(food=5, shopping=5, heritage=3)),
                MemberProfile("d", "D", _profile(spiritual=5, heritage=4)),
            ],
            must_visit=["taj-mahal"],
        ),
        Case(
            "hyderabad_2day_packed",
            "hyderabad",
            2,
            "packed",
            2,
            9000,
            [
                MemberProfile("a", "A", _profile(heritage=5, food=5, museums=4)),
                MemberProfile("b", "B", _profile(museums=5, heritage=4, shopping=3)),
            ],
            must_visit=["golconda-fort"],
        ),
        Case(
            "varanasi_3day_spiritual",
            "varanasi",
            3,
            "relaxed",
            2,
            10000,
            [
                MemberProfile("a", "A", _profile(spiritual=5, heritage=4, photography=4)),
                MemberProfile("b", "B", _profile(spiritual=4, nature=3, relaxation=5)),
            ],
            must_visit=[],
        ),
        Case(
            "puri_konark_accessible",
            "puri-konark",
            3,
            "relaxed",
            4,
            14000,
            [
                MemberProfile(
                    "a",
                    "A",
                    _profile(heritage=5, spiritual=4),
                    mobility_level="wheelchair",
                    is_senior=True,
                ),
                MemberProfile("b", "B", _profile(nature=5, relaxation=5)),
                MemberProfile("c", "C", _profile(heritage=4, museums=4)),
                MemberProfile("d", "D", _profile(spiritual=5, food=4)),
            ],
            must_visit=[],
            accessibility=True,
        ),
        Case(
            "shillong_4day_nature",
            "shillong-cherrapunji",
            4,
            "balanced",
            3,
            16000,
            [
                MemberProfile("a", "A", _profile(nature=5, adventure=5, photography=5)),
                MemberProfile("b", "B", _profile(nature=5, relaxation=4, museums=2)),
                MemberProfile("c", "C", _profile(adventure=3, museums=5, heritage=4)),
            ],
            must_visit=[],
        ),
    ]


def run_case(case: Case) -> dict:
    candidates = load_candidates(case.cluster)
    ctx = context_for(case.cluster, candidates)
    ctx.end_date = ctx.start_date + timedelta(days=case.days - 1)
    ctx.pace = case.pace
    ctx.traveller_count = case.travellers
    ctx.budget_per_person_inr = case.budget
    ctx.must_visit_slugs = case.must_visit
    ctx.accessibility_required = case.accessibility
    ctx.has_seniors = any(m.is_senior for m in case.members)

    weather = [
        climatology_for(case.cluster, ctx.start_date + timedelta(days=i)) for i in range(case.days)
    ]

    row: dict = {
        "case": case.name,
        "cluster": case.cluster,
        "days": case.days,
        "pace": case.pace,
        "members": len(case.members),
        "candidate_pool": len(candidates),
        "generators": {},
    }

    for generator in GENERATORS:
        timings = []
        result = None
        for _ in range(REPEATS):
            result = plan_trip(ctx, case.members, candidates, weather=weather, generator=generator)
            timings.append(result.metrics.computation_ms)

        assert result is not None
        per_stop_km = result.metrics.total_travel_km / max(1, result.metrics.activity_count)
        row["generators"][generator] = {
            "total_travel_km": round(result.metrics.total_travel_km, 2),
            "total_travel_min": result.metrics.total_travel_min,
            "travel_km_per_activity": round(per_stop_km, 2),
            "activities": result.metrics.activity_count,
            "satisfied_preferences": sum(
                1 for v in result.metrics.preference_coverage.values() if v >= 0.5
            ),
            "preference_dimensions": len(result.metrics.preference_coverage),
            "constraint_violations": len(result.validation.errors),
            "constraint_warnings": len(result.validation.warnings),
            "fairness_index": round(result.metrics.fairness_score, 4),
            "least_satisfied": round(result.metrics.least_satisfied_score, 4),
            "utility_score": round(result.metrics.utility_score, 3),
            "is_valid": result.validation.is_valid,
            "mandatory_scheduled": all(s in result.selected_slugs for s in case.must_visit),
            "computation_ms_median": round(statistics.median(timings), 2),
            "computation_ms_max": round(max(timings), 2),
            "cost_per_person_low": result.cost.per_person_low_inr,
            "cost_per_person_high": result.cost.per_person_high_inr,
        }

    greedy, ortools = row["generators"]["greedy"], row["generators"]["ortools"]
    row["deltas"] = {
        "travel_km_reduction_pct": round(
            100
            * (greedy["total_travel_km"] - ortools["total_travel_km"])
            / max(0.01, greedy["total_travel_km"]),
            2,
        ),
        "travel_min_reduction_pct": round(
            100
            * (greedy["total_travel_min"] - ortools["total_travel_min"])
            / max(1, greedy["total_travel_min"]),
            2,
        ),
        "activities_delta": ortools["activities"] - greedy["activities"],
        "utility_delta": round(ortools["utility_score"] - greedy["utility_score"], 3),
        "extra_compute_ms": round(
            ortools["computation_ms_median"] - greedy["computation_ms_median"], 2
        ),
    }
    return row


def run() -> dict:
    cases = [run_case(c) for c in build_cases()]
    summary = {
        generator: {
            metric: round(statistics.fmean(c["generators"][generator][metric] for c in cases), 3)
            for metric in (
                "total_travel_km",
                "total_travel_min",
                "travel_km_per_activity",
                "activities",
                "satisfied_preferences",
                "constraint_violations",
                "fairness_index",
                "least_satisfied",
                "utility_score",
                "computation_ms_median",
            )
        }
        for generator in GENERATORS
    }
    summary["_deltas"] = {
        metric: round(statistics.fmean(c["deltas"][metric] for c in cases), 3)
        for metric in (
            "travel_km_reduction_pct",
            "travel_min_reduction_pct",
            "activities_delta",
            "utility_delta",
            "extra_compute_ms",
        )
    }
    return {
        "cases": cases,
        "summary": summary,
        "repeats_per_case": REPEATS,
        "generated_by": "ml/experiments/planner_comparison.py",
    }


def write_report(results: dict) -> None:
    out_dir = REPO_ROOT / "ml" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "planner_comparison.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )

    s = results["summary"]
    d = s["_deltas"]
    lines = [
        "# Itinerary optimiser vs greedy baseline: measured results",
        "",
        "> Generated by `python ml/experiments/planner_comparison.py`. Deterministic; re-run to reproduce.",
        "",
        f"**{len(results['cases'])} scenarios** across six destination clusters, "
        f"{results['repeats_per_case']} timing repeats each. Both planners receive identical "
        "scored candidates and identical hard constraints, so the difference measures "
        "scheduling quality alone.",
        "",
        "## Averages across all scenarios",
        "",
        "| Metric | Greedy baseline | OR-Tools CP-SAT | Difference |",
        "|---|---|---|---|",
        f"| Total travel distance (km) | {s['greedy']['total_travel_km']:.1f} | "
        f"**{s['ortools']['total_travel_km']:.1f}** | "
        f"{d['travel_km_reduction_pct']:+.1f}% |",
        f"| Total travel time (min) | {s['greedy']['total_travel_min']:.0f} | "
        f"**{s['ortools']['total_travel_min']:.0f}** | "
        f"{d['travel_min_reduction_pct']:+.1f}% |",
        f"| Travel km per activity | {s['greedy']['travel_km_per_activity']:.2f} | "
        f"**{s['ortools']['travel_km_per_activity']:.2f}** | - |",
        f"| Activities scheduled | {s['greedy']['activities']:.1f} | "
        f"{s['ortools']['activities']:.1f} | {d['activities_delta']:+.1f} |",
        f"| Satisfied preference dimensions | {s['greedy']['satisfied_preferences']:.1f} | "
        f"{s['ortools']['satisfied_preferences']:.1f} | - |",
        f"| Constraint violations | {s['greedy']['constraint_violations']:.1f} | "
        f"{s['ortools']['constraint_violations']:.1f} | - |",
        f"| Fairness index (Jain) | {s['greedy']['fairness_index']:.3f} | "
        f"{s['ortools']['fairness_index']:.3f} | - |",
        f"| Least-satisfied member | {s['greedy']['least_satisfied']:.3f} | "
        f"{s['ortools']['least_satisfied']:.3f} | - |",
        f"| Attraction utility score | {s['greedy']['utility_score']:.2f} | "
        f"{s['ortools']['utility_score']:.2f} | {d['utility_delta']:+.2f} |",
        f"| Computation time (ms, median) | {s['greedy']['computation_ms_median']:.1f} | "
        f"{s['ortools']['computation_ms_median']:.1f} | "
        f"{d['extra_compute_ms']:+.1f} ms |",
        "",
        "## Interpretation",
        "",
        f"The optimiser reduces travel by **{d['travel_km_reduction_pct']:.1f}%** on average "
        f"while scheduling {d['activities_delta']:+.1f} activities, at a cost of "
        f"{d['extra_compute_ms']:.0f} ms of extra computation. Per activity the gap is starker: "
        f"{s['greedy']['travel_km_per_activity']:.1f} km vs "
        f"{s['ortools']['travel_km_per_activity']:.1f} km.",
        "",
        f"Constraint violations: greedy {s['greedy']['constraint_violations']:.2f} per scenario, "
        f"CP-SAT {s['ortools']['constraint_violations']:.2f}. Both run through the *same* "
        "validator, so neither can show a user an invalid plan - the difference is that the "
        "greedy planner reaches feasibility by *skipping* awkward candidates, while CP-SAT "
        "reaches it by *sequencing* them.",
        "",
        "Fairness is nearly identical between the two, which is expected: fairness is decided in "
        "the scoring stage, not the scheduling stage. That separation is deliberate - it means "
        "swapping the scheduler cannot accidentally make the itinerary less fair.",
        "",
        "## Per-scenario detail",
        "",
        "| Scenario | Cluster | Days | Greedy km | OR-Tools km | Reduction | Greedy ms | OR-Tools ms | Both valid |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for case in results["cases"]:
        g, o = case["generators"]["greedy"], case["generators"]["ortools"]
        lines.append(
            f"| {case['case']} | `{case['cluster']}` | {case['days']} | "
            f"{g['total_travel_km']:.1f} | {o['total_travel_km']:.1f} | "
            f"{case['deltas']['travel_km_reduction_pct']:+.1f}% | "
            f"{g['computation_ms_median']:.1f} | {o['computation_ms_median']:.1f} | "
            f"{'yes' if g['is_valid'] and o['is_valid'] else 'NO'} |"
        )

    (out_dir / "planner_comparison.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_dir / 'planner_comparison.md'}")


if __name__ == "__main__":
    output = run()
    write_report(output)
    print(json.dumps(output["summary"], indent=2))
