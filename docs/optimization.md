# Itinerary optimisation: the CP-SAT formulation

## The problem

Each day is a **prize-collecting travelling-salesman problem with time windows** (PC-TSPTW).
"Prize-collecting" because we choose *which* attractions to visit as well as in what order —
there are always more candidates than fit in a day.

Solved per day rather than as one trip-wide problem. Two reasons:

1. **Real travellers plan by area.** A single global model happily produces a day that zig-zags
   across a city because the objective only sees total distance.
2. **Model size.** Trip-wide is `O((k·days)²)` arcs. Per day it is `days · O(k²)`. With k = 9 and
   4 days: 1,296 arcs vs 324. That is what keeps median solve time at 48 ms.

## Formal model

### Sets

- `N = {0, 1, …, n}` — node 0 is the depot (that day's base); 1..k are attractions;
  the remaining indices are the mandatory meal break and an optional rest break.

### Parameters

| Symbol | Meaning |
|---|---|
| `sᵢ` | service duration at node *i* (minutes) |
| `tᵢⱼ` | travel time from *i* to *j* (minutes) |
| `dᵢⱼ` | travel distance from *i* to *j* (km) |
| `[eᵢ, lᵢ]` | earliest / latest feasible service start at *i* |
| `pᵢ` | score ("prize") of visiting *i* |
| `cᵢ` | entry cost of *i* |
| `[D_start, D_end]` | the group's day window |
| `A_max` | maximum activities for the chosen pace |
| `T_max` | maximum daily travel minutes for the chosen pace |
| `B` | daily activity budget |

### Decision variables

```
x[i][j] ∈ {0,1}    the tour goes directly from i to j          (i ≠ j)
x[i][i] ∈ {0,1}    node i is SKIPPED (self-loop)               (i ≠ 0)
v[i]    ∈ {0,1}    node i is visited;  v[i] = 1 − x[i][i]
u[i]    ∈ ℤ        service start time at i, in minutes from midnight
```

### Constraints

**(C1) Single tour with optional nodes**

```
AddCircuit({ (i, j, x[i][j]) : i, j ∈ N })
```

OR-Tools' `AddCircuit` enforces exactly one Hamiltonian circuit over the nodes whose self-loop
literal is false. A node opts out by setting its self-loop true. This is the key modelling
choice: sequencing *and* selection fall out of one constraint, with no subtour-elimination
family and no big-M.

**(C2) Time propagation**

```
x[i][j] = 1  ⟹  u[j] ≥ u[i] + sᵢ + tᵢⱼ            ∀ i ∈ N, j ∈ N\{0}
```

Expressed with `OnlyEnforceIf`, so it is a genuine implication rather than a linearised one.

**(C3) Opening hours and the day window**

```
eᵢ ≤ u[i] ≤ lᵢ                                     (variable domain)
v[i] = 1  ⟹  u[i] ≥ D_start  ∧  u[i] + sᵢ ≤ D_end
```

`[eᵢ, lᵢ]` is the widest opening window on that weekday intersected with the day window. An
attraction closed that weekday has no window and is excluded before the model is built.

**(C4) Pinning skipped nodes**

```
x[i][i] = 1  ⟹  u[i] = eᵢ
```

Without this an unvisited node's start time floats freely and creates spurious propagation
pressure through (C2), which measurably slows the solve.

**(C5) Mandatory nodes**

```
v[i] = 1        ∀ i ∈ must_visit ∪ {meal}  (∪ {rest} when pace = relaxed or seniors present)
```

**(C6) Capacity**

```
Σ v[i]                    ≤ A_max          (attractions only)
Σ tᵢⱼ · x[i][j]           ≤ T_max
Σ cᵢ · v[i]               ≤ B
```

### Objective

```
maximise   Σ ⌈(pᵢ − shift + 0.05) · 1000⌉ · v[i]  −  4 · Σ tᵢⱼ · x[i][j]
```

Notes:

- **Integer scaling** — CP-SAT is an integer solver, so scores are scaled by 1000.
- **The shift** guarantees every prize is strictly positive. Scores can go negative after
  distance and crowd penalties; a negative prize would make skipping *rewarding*, and the
  solver would return an empty day.
- **`TRAVEL_WEIGHT = 4`** per travel-minute. This is what stops the optimiser choosing two
  high-scoring places at opposite ends of the city over three good ones in a cluster. It is the
  single most consequential tuning constant in the model.

## Determinism

```python
solver.parameters.num_workers = 1  # multi-threaded search is non-deterministic
solver.parameters.random_seed = settings.planner_random_seed
solver.parameters.max_time_in_seconds = settings.ortools_time_limit_seconds
```

Single-worker search costs some speed and buys reproducibility. `test_planner.py` asserts that
identical inputs give identical plans, and that candidate *ordering* does not change the result.

## Infeasibility: the relaxation ladder

A hard "no plan" is a terrible user experience, but so is silently producing a six-hour driving
day. The solver retries in a fixed order, least-harmful first, and **records what it relaxed**:

| Attempt | What changes |
|---|---|
| 1 | Full model |
| 2 | `A_max − 1` — schedule fewer stops |
| 3 | `T_max × 1.25` |
| 4 | Drop the budget cap; `A_max − 1`; `T_max × 1.4` |
| 5 | `A_max = 2`; `T_max × 1.5` |

Travel is relaxed *last and least*. A day that drives for six hours is technically feasible and
practically useless, so we would rather schedule fewer stops. If every attempt fails the day is
returned empty with `status = INFEASIBLE` and the validator reports it.

## The validator

**No itinerary is displayed unless it passes.** The validator re-derives every constraint from
the persisted rows, independently of the solver, so a modelling bug surfaces as a failed
validation rather than an impossible plan.

| # | Check | Severity |
|---|---|---|
| 1 | Activities ordered and non-overlapping | error |
| 2 | Every visit inside a real opening window for that weekday | error |
| 3 | Nothing before day start or after day end | error |
| 4 | Visit duration within the attraction's min/max | error |
| 5 | Travel time between consecutive stops is actually available | error |
| 6 | No attraction appears twice across the whole trip | error |
| 7 | Every mandatory attraction is scheduled | error |
| 8 | Daily travel within the pace guideline | warning |
| 9 | Activities per day within the pace guideline | warning |
| 10 | A meal break exists on any day longer than 6 h | warning |
| 11 | Total estimated cost within budget | warning |
| 12 | Accessibility requirements respected | error |
| 13 | Nothing scheduled on a day the attraction is closed | error |
| 14 | Weather-unsuitable outdoor activities flagged | warning |
| 15 | The trip has at least one activity | error |

Budget is a **warning**, not an error: exceeding a budget is information the traveller should
act on, not a reason to withhold the plan.

## Geographic clustering

Balanced k-means on an equirectangular projection, with deterministic farthest-point seeding
(no RNG, so results are reproducible).

The balancing pass moves points from over-full to under-full clusters — but **refuses any move
that would strand a point more than 25 km from where it belongs**. This guard exists because of
a measured failure: in the 230 km-wide Delhi–Agra cluster, size balancing was dragging Delhi
sites into the Agra day, producing a 401 km itinerary. With the guard, the same scenario plans
at 54 km.

## Per-day base

A single trip-wide base breaks on genuinely multi-city clusters. In Delhi–Agra the centroid sits
~115 km from everything, so *every* day exceeded the travel cap and the trip was infeasible.

Each day now starts and ends at a base within its own area. When that base is more than 60 km
from the stated origin, the day carries an explicit note telling the traveller the plan assumes
they move accommodation. Silently generating a 200 km round trip would have been worse than
either failing or explaining.

## Measured results

`python ml/experiments/planner_comparison.py` — 6 scenarios, 6 clusters, 3 repeats:

| Metric | Greedy | OR-Tools | Δ |
|---|---|---|---|
| Total travel distance | 149.8 km | **64.0 km** | −57% |
| Total travel time | 487 min | **275 min** | −43% |
| Travel km per activity | 15.61 | **6.01** | −61% |
| Activities scheduled | 9.8 | 10.3 | +0.5 |
| Constraint violations | 0.0 | 0.0 | — |
| Fairness index | 0.996 | 0.996 | — |
| Computation (median) | 8.8 ms | 48.2 ms | +39 ms |

**Fairness being identical is expected and desirable.** Fairness is decided in the scoring
stage, not the scheduling stage. That separation means swapping the scheduler cannot
accidentally make an itinerary less fair.

## The greedy baseline is not a strawman

It sorts by score, walks the list, and inserts each candidate at its earliest feasible start
given travel from the previous stop — respecting the same opening hours, budget, activity cap
and travel cap. That is what a competent hand-rolled itinerary builder does. The 57% gap
measures *sequencing quality*, not constraint handling.

Building it also paid for itself directly: it exposed a meal-break bug (breaks scheduled with a
zero travel gap) that the validator then caught, in code the CP-SAT path shared.

## Travel-time model

When OSRM is unavailable:

```
road_km      = haversine_km × detour_factor[mode]
travel_min   = (road_km / speed_kmph[mode]) × 60 + fixed_overhead[mode]
```

| Mode | Speed (km/h) | Detour factor | Fixed overhead (min) |
|---|---|---|---|
| walk | 4.2 | 1.25 | 2 |
| car / taxi | 24.0 | 1.35 | 8 / 10 |
| public | 16.0 | 1.45 | 14 |
| mixed | 21.0 | 1.35 | 9 |

Speeds are deliberately conservative for Indian urban traffic. Underestimating travel is the
failure mode that produces itineraries which cannot actually be walked, so the fallback errs
slow. The fixed overhead captures parking, walking to the entrance and waiting for a taxi —
things a pure distance/speed model misses entirely on short hops.
