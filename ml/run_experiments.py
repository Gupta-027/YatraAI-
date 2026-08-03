"""Reproduce every experiment in one command.

    python ml/run_experiments.py            # or: make experiments

Runs the aggregation comparison, the planner comparison and the (synthetic) ML
training, then prints where the reports were written. Every number in the README
comes from one of these.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPERIMENTS = [
    ("Group aggregation comparison", "ml/experiments/aggregation_comparison.py"),
    ("Planner vs greedy baseline", "ml/experiments/planner_comparison.py"),
    ("Attraction suitability (synthetic)", "ml/train_suitability.py"),
]


def main() -> int:
    failures: list[str] = []
    for title, script in EXPERIMENTS:
        print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
        started = time.perf_counter()
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / script)],
            cwd=REPO_ROOT,
            check=False,
        )
        elapsed = time.perf_counter() - started
        if result.returncode == 0:
            print(f"-> completed in {elapsed:.1f}s")
        else:
            print(f"-> FAILED (exit {result.returncode})")
            failures.append(title)

    print(f"\n{'=' * 70}\nReports written to:")
    for path in sorted((REPO_ROOT / "ml" / "reports").glob("*.md")):
        print(f"  {path.relative_to(REPO_ROOT)}")
    print("\nRAG benchmark is separate:  python evaluation/run_rag_eval.py")

    if failures:
        print(f"\nFAILED: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
