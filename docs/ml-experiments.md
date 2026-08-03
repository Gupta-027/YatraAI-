# ML experiments

## The honest position

**There is no genuine labelled data for this problem.** Nobody has told us which itineraries
groups actually enjoyed. That single fact determines everything below.

A learned ranker trained on labels we invented would produce an impressive-looking accuracy
number that measures only *how well it reproduced our own heuristic*. Reporting that as "ML
performance" would be dishonest. So:

- **Production uses the transparent rule-based ranker.** Nine components, fixed weights, every
  number stored and rendered in the UI.
- **`ml/` contains a real, reproducible training pipeline** against clearly-labelled synthetic
  data. It exists to show the pipeline works and to be ready the day feedback exists.
- **Every run records `data_kind="synthetic"`** on its `model_runs` row. The label travels with
  the result and cannot be lost.

## Experiment 1 — group aggregation (real, not synthetic)

This is a genuine measurement, because it needs no labels: it compares aggregation methods
against *fairness metrics computed from the group's own stated preferences*.

```bash
python ml/experiments/aggregation_comparison.py
```

**Design.** Five reproducible group profiles across real seed destinations, each constructed so a
simple average would steamroll a minority — that is the situation the method exists to handle, so
that is the situation measured. Evaluated at K = 5, 8 and 12.

**Result** ([full report](../ml/reports/aggregation_comparison.md)):

| Method | Mean satisfaction | Least satisfied | Fairness | Spread |
|---|---|---|---|---|
| `simple_average` | 0.604 | 0.481 | 0.979 | 0.172 |
| `weighted_average` | 0.604 | 0.481 | 0.979 | 0.172 |
| `borda_count` | 0.618 | 0.478 | 0.975 | 0.197 |
| `max_min_fairness` | 0.582 | **0.545** | 0.996 | 0.069 |
| `fairness_aware` (single pass) | 0.603 | 0.484 | 0.981 | 0.167 |
| **`select_fairly` (production)** | 0.597 | 0.522 | 0.991 | 0.115 |

**Two findings worth stating plainly.**

1. The single-pass blend improves the floor by **0.6%** over an average — essentially nothing.
   Without measuring, it would have looked principled and shipped while doing nothing. This null
   result is why the iterative selector exists.
2. Method choice stops mattering as K approaches the pool size. Reporting one large K would have
   hidden every difference. The report shows the sensitivity table rather than the flattering
   number.

## Experiment 2 — optimiser vs baseline (real)

Also label-free: it compares two schedulers on objective quantities.

```bash
python ml/experiments/planner_comparison.py
```

**Design.** Six scenarios across six clusters (varying pace, group size, accessibility needs,
must-visits), three timing repeats each. Both planners get identical scored candidates and
identical hard constraints, so the difference isolates *scheduling quality*.

**Result** ([full report](../ml/reports/planner_comparison.md)):

| Metric | Greedy | OR-Tools | Δ |
|---|---|---|---|
| Total travel distance | 149.8 km | **64.0 km** | −57% |
| Total travel time | 487 min | **275 min** | −43% |
| Travel km per activity | 15.61 | **6.01** | −61% |
| Activities scheduled | 9.8 | 10.3 | +0.5 |
| Satisfied preference dimensions | 6.8 | 7.2 | — |
| Constraint violations | 0.0 | 0.0 | — |
| Fairness index | 0.996 | 0.996 | — |
| Computation (median) | 8.8 ms | 48.2 ms | +39 ms |

Fairness being identical is the expected and desirable outcome: fairness is decided in scoring,
not scheduling. That separation means changing the scheduler cannot accidentally make a plan less
fair — a property worth having.

## Experiment 3 — attraction suitability model (synthetic, and labelled as such)

```bash
python ml/train_suitability.py
```

**What it does.** Generates synthetic (group, attraction, outcome) triples using a noisy
generative process *deliberately different in form* from the production scorer, so a model cannot
trivially memorise our heuristic. Trains and compares:

- Logistic regression (interpretable baseline)
- Random forest
- Gradient boosting
- The production rule-based scorer, as a control

**Result** ([full report](../ml/reports/suitability_model.md)):

| Model | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|
| `logistic_regression` | 0.6711 | 0.8341 | 0.1826 |
| `random_forest` | 0.6404 | 0.8190 | 0.1863 |
| `gradient_boosting` | 0.6404 | 0.8147 | 0.1874 |
| **`rule_based_production_control`** | **0.6676** | **0.8278** | — |

**The tree models lost.** I expected them to exploit the interaction and saturating distance
effect that the linear production scorer lacks. Both land at 0.6404, *below* the hand-weighted
control at 0.6676.

The only learner that edges the control is logistic regression, at +0.0035 ROC-AUC — the same
linear model class the production scorer already is. That margin is too small to read off a point
estimate, so the script measures it with a **paired bootstrap** over 2,000 resamples of the same
held-out rows:

```
ROC-AUC(logistic_regression) − ROC-AUC(rule_based_control)
  = +0.0035,  95% CI [−0.0100, +0.0173]
```

The interval straddles zero. On this data the two are **statistically indistinguishable**, and
the report says so because the bootstrap said so, not because it is a comfortable conclusion.

Why the extra capacity does not pay: 12% label noise, plus the variable driving the interaction
(`outdoor_exposure`) is deliberately **not** in the feature set. A tree can only exploit an
interaction between features it can see. That is a fair simulation of the real problem, where
whatever actually decided if a group enjoyed an outdoor site is often something the catalogue
never recorded.

That is the honest result and a useful one — on this data the simple transparent model is not a
compromise. It reinforces the decision to ship the rule-based scorer rather than merely excusing
it, and it establishes a baseline *with an error bar* that a future learner has to clear.

**What is not claimed.** That any of these numbers predicts real-world satisfaction. They cannot.
The experiment demonstrates that the feature pipeline, training loop, evaluation and model
registry work — so when feedback data arrives, swapping the ranker is a configuration change
rather than a project — and it establishes a baseline any future learner must beat.

**The guard.** Every row written to `model_runs` carries `data_kind="synthetic"`. The analytics
dashboard displays that field. There is no path by which a synthetic result can be presented as a
real one.

## Experiment 4 — cost estimation

The estimator returns a **range across five components** (accommodation, food, local transport,
entry charges, contingency), with every assumption returned alongside the number:

> "Expected cost: ₹18,500–₹21,300 per person"

**No accuracy figure is reported, because none has been measured.** The dashboard says so
explicitly:

> "No actual-spend feedback recorded yet, so no prediction error is reported. We do not publish an
> accuracy figure we have not measured."

The capture path exists — `POST /api/v1/feedback` accepts `actual_spend_inr`, and
`_spend_accuracy` computes within-range rate and MAPE the moment there are samples. It simply has
no data yet, and inventing one would be the exact failure this project is designed to avoid.

## Reproducibility

| Concern | Handling |
|---|---|
| Random seeds | Fixed in settings; `planner_random_seed` also seeds CP-SAT |
| Solver determinism | `num_workers = 1` — slower, reproducible |
| Data versioning | Seed files committed; Bronze content-hashed |
| Run tracking | `model_runs` records params, metrics, dataset fingerprint, `data_kind` |
| Environment | `pyproject.toml` with pinned minimums; CI runs the same commands |
| Input fingerprint | Every itinerary stores a hash of its planner inputs |

`test_identical_inputs_give_identical_plans` and
`test_candidate_order_does_not_change_the_result` assert determinism in CI.

## What the experiments actually caught

The point of building these was not the tables. It was the three defects they exposed, none of
which was visible from reading the code:

1. **Greedy scheduled meal breaks with a zero travel gap**, producing invalid plans — caught by
   the validator once the comparison ran both planners through it.
2. **A 401 km Delhi–Agra itinerary.** Size-balancing was dragging Delhi sites into the Agra day.
   Fixed with a maximum-move-distance guard; the same scenario now plans at 54 km.
3. **Every Delhi–Agra day infeasible.** A single trip-wide base sat 115 km from everything. Fixed
   with a per-day base plus an explicit relocation note.

A fourth came from the RAG harness: **topic classification measured at 0.50** because
`\b(histor)\b` can never match "history" — the trailing word boundary forbids it. Fixed to 0.94.

## Next steps, in order of value

1. **Collect real feedback.** Acceptance, removals and actual spend are already captured; they are
   the first genuine training signal.
2. **Cost model error.** The first metric that can be honestly reported once data exists.
3. **Learning-to-rank on real labels** — LambdaMART over the existing Gold features.
4. **Counterfactual evaluation.** Recommendation feedback is biased by what was shown; IPS or
   doubly-robust estimation would be needed before trusting any offline number.
