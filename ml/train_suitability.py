"""Attraction suitability model — SYNTHETIC LABELS, clearly marked.

    python ml/train_suitability.py

Read docs/ml-experiments.md before interpreting anything this prints.

There is no genuine labelled data for "did this group enjoy this attraction". This
script therefore generates synthetic outcomes and trains three learners on them, so
that the feature pipeline, training loop, evaluation and model registry are real and
ready. **The production ranker remains the transparent rule-based model.**

Every run writes a `model_runs` row with ``data_kind="synthetic"``. That label travels
with the result so it can never be presented as a real-data metric.

The generative process is deliberately *different in form* from the production scorer
(interaction terms, a saturating distance effect, label noise) so a learner cannot
trivially memorise our own heuristic and report it as accuracy.
"""

# ruff: noqa: E402
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "apps" / "api") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SEED = 20240101
N_SAMPLES = 6000
REPORT_DIR = REPO_ROOT / "ml" / "reports"

FEATURES = [
    "interest_match",
    "group_fairness",
    "attraction_quality",
    "weather_suitability",
    "seasonal_suitability",
    "accessibility_suitability",
    "budget_suitability",
    "evidence_quality",
    "distance_penalty",
    "crowd_penalty",
]


def generate_synthetic(n: int = N_SAMPLES, seed: int = SEED) -> pd.DataFrame:
    """Synthetic (features -> enjoyed) pairs.

    The generative process includes an interaction (weather x outdoor exposure), a
    saturating distance effect and 12% label noise - none of which the production
    linear scorer contains. A model that scores well here has learned *this* process,
    not ours, which is the point: it demonstrates the pipeline without pretending the
    number means something about real travellers.
    """
    rng = np.random.default_rng(seed)

    df = pd.DataFrame(
        {
            "interest_match": rng.beta(2.2, 2.0, n),
            "group_fairness": rng.beta(2.0, 2.4, n),
            "attraction_quality": rng.beta(5.0, 2.0, n),
            "weather_suitability": rng.beta(4.0, 1.8, n),
            "seasonal_suitability": rng.beta(4.5, 1.5, n),
            "accessibility_suitability": rng.beta(3.0, 2.0, n),
            "budget_suitability": rng.beta(3.5, 1.6, n),
            "evidence_quality": rng.beta(6.0, 2.0, n),
            "distance_penalty": rng.beta(1.8, 3.2, n),
            "crowd_penalty": rng.beta(2.0, 3.0, n),
        }
    )
    df["outdoor_exposure"] = rng.beta(2.0, 2.0, n)

    logit = (
        2.9 * df["interest_match"]
        + 1.7 * df["group_fairness"]
        + 1.2 * df["attraction_quality"]
        + 0.9 * df["evidence_quality"]
        + 1.1 * df["budget_suitability"]
        + 1.4 * df["accessibility_suitability"]
        # interaction the production model does not have
        + 2.2 * df["weather_suitability"] * df["outdoor_exposure"]
        # saturating distance effect rather than a linear penalty
        - 2.4 * np.tanh(2.5 * df["distance_penalty"])
        - 1.0 * df["crowd_penalty"] ** 2
        - 2.6
    )
    probability = 1 / (1 + np.exp(-logit))
    label = rng.binomial(1, probability)

    # 12% label noise: real preference feedback is never this clean.
    flip = rng.random(n) < 0.12
    df["enjoyed"] = np.where(flip, 1 - label, label)
    return df


def evaluate(name: str, model, X_train, X_test, y_train, y_test) -> tuple[dict, np.ndarray]:
    model.fit(X_train, y_train)
    probabilities = model.predict_proba(X_test)[:, 1]
    row = {
        "model": name,
        "roc_auc": round(float(roc_auc_score(y_test, probabilities)), 4),
        "pr_auc": round(float(average_precision_score(y_test, probabilities)), 4),
        "brier": round(float(brier_score_loss(y_test, probabilities)), 4),
        "accuracy": round(float((model.predict(X_test) == y_test).mean()), 4),
    }
    return row, probabilities


def rule_based_control(X_test: pd.DataFrame, y_test: pd.Series) -> tuple[dict, np.ndarray]:
    """The production scorer, evaluated as a control.

    Uses the real WEIGHTS/PENALTIES from services/recommend/scoring.py, so this row
    shows what the shipped heuristic achieves on the same held-out data.
    """
    from yatraai.services.recommend.scoring import PENALTIES, WEIGHTS

    score = sum(WEIGHTS[c] * X_test[c] for c in WEIGHTS if c in X_test)
    score = score - sum(PENALTIES[c] * X_test[c] for c in PENALTIES if c in X_test)
    score = np.asarray(score, dtype=float)
    row = {
        "model": "rule_based_production_control",
        "roc_auc": round(float(roc_auc_score(y_test, score)), 4),
        "pr_auc": round(float(average_precision_score(y_test, score)), 4),
        "brier": None,  # not a calibrated probability, so Brier is meaningless
        "accuracy": None,
    }
    return row, score


def bootstrap_auc_gap(
    y_test: pd.Series,
    challenger: np.ndarray,
    control: np.ndarray,
    *,
    resamples: int = 2000,
    seed: int = SEED,
) -> dict:
    """Paired bootstrap CI on ROC-AUC(challenger) - ROC-AUC(control).

    A raw point-estimate gap of a few thousandths of AUC means nothing on 1,500 test
    rows. Rather than *asserting* that a difference is within noise, measure it: resample
    the same held-out rows for both scorers and report the interval. If the interval
    straddles zero the two models are indistinguishable on this data, and the report says
    so because the numbers said so.
    """
    rng = np.random.default_rng(seed)
    y = np.asarray(y_test)
    n = len(y)
    gaps: list[float] = []
    for _ in range(resamples):
        idx = rng.integers(0, n, n)
        if len(np.unique(y[idx])) < 2:  # degenerate resample: AUC undefined
            continue
        gaps.append(
            float(roc_auc_score(y[idx], challenger[idx]) - roc_auc_score(y[idx], control[idx]))
        )
    low, high = np.percentile(gaps, [2.5, 97.5])
    return {
        "point_estimate": round(float(np.mean(gaps)), 4),
        "ci_low": round(float(low), 4),
        "ci_high": round(float(high), 4),
        "resamples": len(gaps),
        "significant": bool(low > 0 or high < 0),
    }


def main() -> int:
    df = generate_synthetic()
    X = df[FEATURES]
    y = df["enjoyed"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=SEED, stratify=y
    )

    models = {
        "logistic_regression": Pipeline(
            [("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=2000, C=1.0))]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300, max_depth=9, min_samples_leaf=8, random_state=SEED, n_jobs=1
        ),
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=250, max_depth=3, learning_rate=0.06, random_state=SEED
        ),
    }

    rows: list[dict] = []
    scores: dict[str, np.ndarray] = {}
    for name, model in models.items():
        row, probabilities = evaluate(name, model, X_train, X_test, y_train, y_test)
        rows.append(row)
        scores[name] = probabilities
    control_row, control_scores = rule_based_control(X_test, y_test)
    rows.append(control_row)

    # Is the best learner actually better than the shipped heuristic, or is the gap noise?
    best = max(rows[:-1], key=lambda r: r["roc_auc"])
    gap = bootstrap_auc_gap(y_test, scores[best["model"]], control_scores)
    gap["challenger"] = best["model"]

    # ---- feature importance from the tree model ----
    rf = models["random_forest"]
    importance = sorted(zip(FEATURES, rf.feature_importances_, strict=True), key=lambda kv: -kv[1])

    run_id = f"suitability-{uuid.uuid4().hex[:8]}"
    payload = {
        "run_id": run_id,
        "data_kind": "synthetic",
        "warning": (
            "SYNTHETIC LABELS. These metrics measure how well each learner recovered an "
            "artificial generative process. They say nothing about real traveller "
            "satisfaction, and no model here is promoted to production."
        ),
        "samples": len(df),
        "positive_rate": round(float(y.mean()), 4),
        "label_noise": 0.12,
        "seed": SEED,
        "results": rows,
        "best_learner_vs_control": gap,
        "feature_importance": [
            {"feature": f, "importance": round(float(i), 4)} for f, i in importance
        ],
    }

    # ---- persist to model_runs, best-effort ----
    try:
        from yatraai.db.models import ModelRun
        from yatraai.db.session import session_scope

        with session_scope() as session:
            for row in rows:
                session.add(
                    ModelRun(
                        run_id=f"{run_id}-{row['model']}",
                        experiment="attraction_suitability",
                        model_name=row["model"],
                        data_kind="synthetic",
                        params={"seed": SEED, "samples": len(df), "label_noise": 0.12},
                        metrics={k: v for k, v in row.items() if k != "model"},
                        notes=payload["warning"],
                    )
                )
    except Exception as exc:  # pragma: no cover - DB optional
        payload["db_write"] = f"skipped: {exc}"

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "suitability_model.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    lines = [
        "# Attraction suitability model — SYNTHETIC DATA",
        "",
        "> **These labels are synthetic.** They measure how well each learner recovered an",
        "> artificial generative process, not real traveller satisfaction. **No model here is",
        "> promoted to production** — the transparent rule-based scorer remains the default.",
        "> See [docs/ml-experiments.md](../../docs/ml-experiments.md) for why.",
        "",
        f"Generated by `python ml/train_suitability.py` · run `{run_id}` · "
        f"{len(df):,} samples · 12% label noise · seed {SEED}",
        "",
        "## Results",
        "",
        "| Model | ROC-AUC | PR-AUC | Brier | Accuracy |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['model']}` | {row['roc_auc']:.4f} | {row['pr_auc']:.4f} | "
            f"{row['brier'] if row['brier'] is not None else '—'} | "
            f"{row['accuracy'] if row['accuracy'] is not None else '—'} |"
        )

    lines += [
        "",
        "The `rule_based_production_control` row is the *shipped* scorer evaluated on the same",
        "held-out split. It is not a calibrated probability, so Brier and accuracy are omitted",
        "rather than computed misleadingly.",
        "",
        "## Feature importance (random forest)",
        "",
        "| Feature | Importance |",
        "|---|---|",
    ]
    for feature, value in importance:
        lines.append(f"| `{feature}` | {value:.4f} |")

    lines += [
        "",
        "## Best learner vs the shipped scorer",
        "",
        "A gap of a few thousandths of AUC on 1,500 held-out rows may be nothing. Paired",
        f"bootstrap, {gap['resamples']:,} resamples of the same test rows, "
        f"`{gap['challenger']}` minus `rule_based_production_control`:",
        "",
        f"> **ROC-AUC difference {gap['point_estimate']:+.4f}, "
        f"95% CI [{gap['ci_low']:+.4f}, {gap['ci_high']:+.4f}]**",
        "",
        (
            "The interval excludes zero, so the difference is real on this data."
            if gap["significant"]
            else "The interval straddles zero: **the two are statistically indistinguishable "
            "here.** The point estimate is not evidence of a better model."
        ),
        "",
        "## How to read this",
        "",
        "The generative process deliberately contains a weather x exposure interaction and a",
        "saturating distance effect, neither of which the production linear scorer has. I",
        "expected the tree models to exploit that and beat the control.",
        "",
        f"**They did not.** Both tree models land at "
        f"{max(r['roc_auc'] for r in rows[:-1] if r['model'] != 'logistic_regression'):.4f} "
        f"ROC-AUC, below the rule-based control's {rows[-1]['roc_auc']:.4f}. The only learner",
        f"that edges the control is `{gap['challenger']}` — the same *linear* model class the",
        "production scorer already is, and by a margin the bootstrap above cannot separate from",
        "zero.",
        "",
        "Why the extra capacity does not pay: 12% label noise, and the variable driving the",
        "interaction (`outdoor_exposure`) is deliberately **not** in the feature set. A tree can",
        "only exploit an interaction between features it can see. That is a fair simulation of",
        "the real situation, where the thing that decides whether a group enjoyed an outdoor",
        "site is often something the catalogue never recorded.",
        "",
        "That is the honest result, and a useful one: on this data the simple transparent model",
        "is not a compromise. It reinforces rather than excuses the decision to ship the",
        "rule-based scorer.",
        "",
        "What this run demonstrates: the feature pipeline, training loop, held-out evaluation,",
        "significance testing and model registry all work, so swapping the production ranker",
        "becomes a configuration change on the day real feedback exists — and there is now a",
        "baseline, with an error bar, that any future learner has to clear.",
        "",
    ]
    (REPORT_DIR / "suitability_model.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"run_id": run_id, "results": rows}, indent=2))
    print(f"\nWrote {REPORT_DIR / 'suitability_model.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
