# Recommendation methodology

## The problem this solves

Three people want temples. One wants waterfalls. A simple average silently deletes the fourth
person from the trip — and does so invisibly, because the average *looks* reasonable.

## Two-stage design

### Stage 1 — hard eligibility (removal, not down-weighting)

Anything that fails here is **removed from consideration**, so everything that survives is
genuinely feasible. Down-weighting an inaccessible place still lets a strong interest match pull
it into the plan; removing it cannot.

| Reason | Trigger |
|---|---|
| `excluded_by_group` | On the trip's avoid list |
| `closed_for_entire_trip` | Closed on every day of the trip |
| `cannot_fit_in_daily_window` | Minimum visit does not fit any opening window ∩ day window |
| `not_wheelchair_accessible` | Group requires step-free access |
| `member_requires_step_free_access` | Any member is a wheelchair user |
| `too_physically_demanding_for_a_member` | A member has limited walking and intensity is 5/5 |
| `entry_fee_exceeds_budget` | Single entry fee exceeds the daily activity budget |
| **`vetoed_by_member`** | **Any single member listed it as avoid** |

That last one is the brief's requirement made concrete: **one member's veto is absolute**. A
majority cannot overrule it.

A must-visit place that fails eligibility is *reported*, never silently dropped.

### Stage 2 — weighted scoring

Nine components, each in [0, 1], with fixed inspectable weights:

| Component | Weight | Meaning |
|---|---|---|
| `interest_match` | 0.30 | Aggregated group utility (method-dependent) |
| `group_fairness` | 0.15 | Minimum utility across members |
| `attraction_quality` | 0.12 | Curated quality score |
| `weather_suitability` | 0.12 | Forecast fit, scaled by exposure and sensitivity |
| `seasonal_suitability` | 0.10 | Travel month within suitable months |
| `accessibility_suitability` | 0.09 | Step-free access, senior/child fit, physical demand |
| `budget_suitability` | 0.08 | Entry fee against the daily activity budget |
| `evidence_quality` | 0.04 | Source authority, count, confidence, content completeness |

Penalties subtracted:

| Penalty | Weight |
|---|---|
| `distance_penalty` | 0.10 |
| `crowd_penalty` | 0.06 |

Plus `mandatory_bonus = 1.0` for must-visit places, which dominates everything else by design.

Every component is persisted on `recommendation_scores` and rendered in the "Why recommended?"
panel. The UI does not re-derive anything — it displays the numbers the optimiser actually used.

## Per-member utility

Cosine-style similarity between a member's interest weights and the attraction's interest
vector, **normalised**:

```
u(m, a) = Σᵢ (mᵢ/5 · aᵢ) / (‖m/5‖ · ‖a‖)
```

Normalisation matters: without it, a member who rates everything 5 scores 1.0 on every
attraction and silently dominates the group. `test_rating_everything_five_does_not_score_everything_one`
guards this.

Explicit choices override inferred interests: must-visit → 1.0, avoid → 0.0, ranked shortlist →
positional boost.

## Aggregation methods

| Method | Formula | Character |
|---|---|---|
| `simple_average` | `mean(u)` | Maximises total satisfaction; blind to who loses |
| `weighted_average` | `Σ wₘuₘ / Σ wₘ` | Same blind spot, with member weights |
| `borda_count` | Positional voting, ties share points | Rewards broad acceptability |
| `max_min_fairness` | `min(u)` | Maximally protective; produces bland plans |
| `fairness_aware` | `α·mean + (1−α)·min`, α = 0.65 | Per-item blend |
| **`select_fairly`** | Iterative, group-aware | **Production default** |

### Group metrics

**Jain's fairness index** — standard in resource allocation, bounded and easy to explain:

```
J(x) = (Σxᵢ)² / (n · Σxᵢ²)      ∈ (0, 1]
```

1.0 = perfectly equal satisfaction; 1/n = one member served, the rest ignored.

**Consensus** = `1 − stdev/0.5` (0.5 is the maximum stdev for values in [0,1]).
**Least-satisfied** = `min` per-member coverage — the metric the brief actually cares about.

## Why iterative selection

Scoring each attraction *in isolation* cannot know that the shortlist already contains four
temples and nothing for the one member who wanted a lake. `select_fairly` picks one item at a
time, recomputing every member's satisfaction after each pick, and maximises the marginal gain
in:

```
objective(S) = α · mean_coverage(S) + (1−α) · min_coverage(S)
```

with a retained weight on the item's own suitability so fairness cannot select an unsuitable
place purely because one member likes its category.

Complexity `O(k · n · m)` — a few milliseconds at this catalogue size.

## Measured comparison

`python ml/experiments/aggregation_comparison.py` — 5 group profiles, K = 5 (a realistic
two-day itinerary):

| Method | Mean satisfaction | **Least satisfied** | Fairness | Spread |
|---|---|---|---|---|
| `simple_average` | 0.604 | 0.481 | 0.979 | 0.172 |
| `weighted_average` | 0.604 | 0.481 | 0.979 | 0.172 |
| `borda_count` | 0.618 | 0.478 | 0.975 | 0.197 |
| `max_min_fairness` | 0.582 | **0.545** | 0.996 | 0.069 |
| `fairness_aware` (single pass) | 0.603 | 0.484 | 0.981 | 0.167 |
| **`select_fairly` (production)** | 0.597 | **0.522** | 0.991 | 0.115 |

### The trade-off, stated explicitly

| | Floor gain vs average | Mean-satisfaction cost |
|---|---|---|
| `max_min_fairness` | **+13.3%** | −3.6% |
| `select_fairly` | +8.5% | **−1.1%** |

Pure max-min raises the floor most but flattens the itinerary — it keeps choosing the option
nobody objects to rather than the option most people want. The iterative method captures **64%
of the fairness gain for 30% of the cost**, which is why it ships.

### A null result worth reporting

Single-pass `fairness_aware` improves the floor by only **+0.6%** over a simple average. Almost
nothing. That finding is precisely why the iterative selector exists — without measuring it, the
blend would have looked principled and shipped while doing essentially nothing.

### Sensitivity to itinerary size

| Method | K=5 | K=8 | K=12 |
|---|---|---|---|
| `simple_average` | 0.481 | 0.514 | 0.562 |
| `max_min_fairness` | 0.545 | 0.558 | 0.598 |
| `select_fairly` | 0.522 | 0.568 | 0.594 |

As the selection approaches the pool size every method converges — they all pick nearly
everything. Reporting a single large K would have hidden the differences entirely, which is why
the headline uses a realistic K.

## Interest taxonomy

Members express preferences over **10 stable dimensions** rather than the ~60 free-form category
tags in the catalogue. New attractions can introduce new tags without invalidating stored
preference profiles, and the aggregation maths operates on a fixed-width vector.

`test_every_seed_category_is_mapped` fails the build if a category tag appears in the data
without a taxonomy mapping — otherwise it would silently score zero everywhere.

## Why not a learned ranker in production

There is **no genuine labelled data**: no record of which itineraries groups actually enjoyed. A
learned model would be fitted to invented labels and its apparent accuracy would measure how
well it reproduced our own heuristic.

`ml/` contains a reproducible pipeline that trains logistic regression, random forest and
gradient boosting on **clearly-labelled synthetic** data — recorded with `data_kind="synthetic"`
on every `model_runs` row. It exists to show the pipeline is real and to be ready the moment
feedback data exists. It is **not** promoted to production. See [ml-experiments.md](ml-experiments.md).
