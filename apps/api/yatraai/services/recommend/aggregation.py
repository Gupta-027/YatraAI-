"""Group preference aggregation.

The hard problem this module solves: three people want temples, one wants
waterfalls. A naive average silently deletes the fourth person from the trip.

Implemented methods
-------------------
``simple_average``
    Unweighted mean member utility. Baseline; maximises total satisfaction and
    is the method most travel apps implicitly use.

``weighted_average``
    Mean weighted by member weight (a trip owner may weight a birthday
    traveller higher). Same fairness blind spot as the average.

``borda_count``
    Positional voting over each member's ranked shortlist. Rewards places that
    are broadly acceptable rather than narrowly loved, and is robust to members
    who rate everything 5.

``max_min_fairness``
    Egalitarian: an item's score is the *minimum* utility any member derives.
    Maximally protective, but can produce bland itineraries nobody loves.

``fairness_aware``
    ``alpha*weighted_mean + (1-alpha)*min_member_utility`` with alpha = 0.65,
    plus an optional *deficit boost*. Applied per item in isolation.

``select_fairly`` (**production default**)
    Iterative selection: picks one attraction at a time, recomputing every
    member's satisfaction after each pick, and maximises the marginal gain in
    ``alpha*mean + (1-alpha)*min``. Scoring an attraction in isolation cannot
    know the shortlist already has four temples and nothing for the member who
    wanted a lake; this can. **Measured**: it lifts the least-satisfied member
    by 8.5% over a simple average for a 1.1% cost in mean satisfaction, whereas
    the single-pass variant lifts it by only 0.6%. See
    ``ml/reports/aggregation_comparison.md``.

Group-level metrics
-------------------
* **Jain's fairness index** — ``(Σx)² / (n·Σx²)`` ∈ (0, 1]. 1.0 = perfectly equal
  satisfaction. Standard in resource-allocation literature and easy to explain.
* **Consensus score** — ``1 - (stdev / max_possible_stdev)``.
* **Least-satisfied score** — the minimum per-member coverage.

Every function here is pure and deterministic. See
``ml/experiments/aggregation_comparison.py`` for the measured comparison.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from yatraai.services.planner.models import AttractionCandidate, MemberProfile
from yatraai.services.recommend.taxonomy import INTERESTS, interest_vector

FAIRNESS_ALPHA = 0.65
DEFICIT_BOOST_WEIGHT = 0.25

AggregationMethod = str
METHODS: tuple[str, ...] = (
    "simple_average",
    "weighted_average",
    "borda_count",
    "max_min_fairness",
    "fairness_aware",
)


# --------------------------------------------------------------------------- #
# Per-member utility
# --------------------------------------------------------------------------- #
def member_utility(member: MemberProfile, candidate: AttractionCandidate) -> float:
    """How much this member wants this attraction, in [0, 1].

    Cosine-style match between the member's interest weights and the
    attraction's interest vector, normalised so that a member who rates
    everything 5 does not simply score every attraction 1.0.
    """
    attraction_vec = interest_vector(candidate.categories)
    numerator = 0.0
    member_norm = 0.0
    attraction_norm = 0.0
    for interest in INTERESTS:
        m = float(member.interests.get(interest, 3.0)) / 5.0
        a = attraction_vec.get(interest, 0.0)
        numerator += m * a
        member_norm += m * m
        attraction_norm += a * a
    if member_norm == 0.0 or attraction_norm == 0.0:
        return 0.0
    utility = numerator / (math.sqrt(member_norm) * math.sqrt(attraction_norm))

    # Explicit choices dominate inferred interests.
    if candidate.slug in member.must_visit_slugs:
        utility = 1.0
    elif candidate.slug in member.avoid_slugs:
        utility = 0.0
    elif candidate.slug in member.ranked_choices:
        position = member.ranked_choices.index(candidate.slug)
        boost = 0.35 * (1.0 - position / max(1, len(member.ranked_choices)))
        utility = min(1.0, utility + boost)

    return round(max(0.0, min(1.0, utility)), 6)


def utility_matrix(
    members: Sequence[MemberProfile], candidates: Sequence[AttractionCandidate]
) -> dict[str, dict[str, float]]:
    """``{attraction_slug: {member_id: utility}}``."""
    return {c.slug: {m.member_id: member_utility(m, c) for m in members} for c in candidates}


# --------------------------------------------------------------------------- #
# Aggregation methods
# --------------------------------------------------------------------------- #
def simple_average(utilities: dict[str, float]) -> float:
    return sum(utilities.values()) / len(utilities) if utilities else 0.0


def weighted_average(utilities: dict[str, float], weights: dict[str, float]) -> float:
    total_weight = sum(weights.get(m, 1.0) for m in utilities)
    if total_weight == 0:
        return 0.0
    return sum(u * weights.get(m, 1.0) for m, u in utilities.items()) / total_weight


def max_min_fairness(utilities: dict[str, float]) -> float:
    return min(utilities.values()) if utilities else 0.0


def borda_count(
    members: Sequence[MemberProfile],
    candidates: Sequence[AttractionCandidate],
    matrix: dict[str, dict[str, float]] | None = None,
) -> dict[str, float]:
    """Borda scores in [0, 1] per attraction.

    Each member ranks all candidates by their own utility; an item in position
    *i* of *n* earns ``n - 1 - i`` points. Explicit ranked shortlists are honoured
    first, with the remaining items ordered by inferred utility. Ties share the
    average of the positions they span, so arbitrary sort order cannot leak in.
    """
    if not candidates or not members:
        return {}
    matrix = matrix or utility_matrix(members, candidates)
    n = len(candidates)
    totals: dict[str, float] = dict.fromkeys((c.slug for c in candidates), 0.0)

    for member in members:
        scores = {}
        for c in candidates:
            base = matrix[c.slug][member.member_id]
            if c.slug in member.ranked_choices:
                # Shortlisted items sort above everything else, in stated order.
                position = member.ranked_choices.index(c.slug)
                base = 1.0 + (len(member.ranked_choices) - position)
            scores[c.slug] = base

        ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        i = 0
        while i < n:
            j = i
            while j + 1 < n and math.isclose(ordered[j + 1][1], ordered[i][1], abs_tol=1e-9):
                j += 1
            # Average points across the tied block.
            points = sum(n - 1 - k for k in range(i, j + 1)) / (j - i + 1)
            for k in range(i, j + 1):
                totals[ordered[k][0]] += points * member.weight
            i = j + 1

    max_points = (n - 1) * sum(m.weight for m in members)
    if max_points <= 0:
        return dict.fromkeys(totals, 0.0)
    return {slug: round(points / max_points, 6) for slug, points in totals.items()}


def fairness_aware(
    utilities: dict[str, float],
    weights: dict[str, float],
    *,
    member_deficits: dict[str, float] | None = None,
    alpha: float = FAIRNESS_ALPHA,
) -> float:
    """Production default.

    ``alpha`` trades efficiency against equality. ``member_deficits`` (how far
    below their fair share each member currently sits) makes the score adaptive:
    as the plan fills, items that serve neglected members gain weight.
    """
    if not utilities:
        return 0.0
    efficiency = weighted_average(utilities, weights)
    equality = max_min_fairness(utilities)
    score = alpha * efficiency + (1.0 - alpha) * equality

    if member_deficits:
        total_deficit = sum(max(0.0, d) for d in member_deficits.values())
        if total_deficit > 0:
            boost = (
                sum(utilities.get(m, 0.0) * max(0.0, d) for m, d in member_deficits.items())
                / total_deficit
            )
            score += DEFICIT_BOOST_WEIGHT * boost * (total_deficit / len(member_deficits))

    return round(max(0.0, min(1.5, score)), 6)


def aggregate(
    method: AggregationMethod,
    utilities: dict[str, float],
    weights: dict[str, float],
    *,
    member_deficits: dict[str, float] | None = None,
) -> float:
    if method == "simple_average":
        return simple_average(utilities)
    if method == "weighted_average":
        return weighted_average(utilities, weights)
    if method == "max_min_fairness":
        return max_min_fairness(utilities)
    if method == "fairness_aware":
        return fairness_aware(utilities, weights, member_deficits=member_deficits)
    raise ValueError(f"Unknown aggregation method: {method!r} (borda_count is set-level)")


# --------------------------------------------------------------------------- #
# Group metrics
# --------------------------------------------------------------------------- #
def jains_fairness_index(values: Sequence[float]) -> float:
    """``(Σx)² / (n · Σx²)`` ∈ (0, 1]. 1.0 means every member is equally served."""
    vals = [max(0.0, float(v)) for v in values]
    if not vals:
        return 0.0
    total = sum(vals)
    if total == 0.0:
        return 1.0  # nobody got anything: trivially equal
    sum_sq = sum(v * v for v in vals)
    return round((total * total) / (len(vals) * sum_sq), 6)


def consensus_score(values: Sequence[float]) -> float:
    """1.0 when everyone is equally satisfied, 0.0 at maximum disagreement."""
    vals = [float(v) for v in values]
    if len(vals) < 2:
        return 1.0
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    # Max stdev for values bounded in [0,1] is 0.5.
    return round(max(0.0, 1.0 - (math.sqrt(variance) / 0.5)), 6)


@dataclass
class GroupSatisfaction:
    per_member: dict[str, float]
    mean: float
    least_satisfied: float
    least_satisfied_member: str
    fairness_index: float
    consensus: float

    def to_dict(self) -> dict:
        return {
            "per_member": {k: round(v, 4) for k, v in self.per_member.items()},
            "mean": round(self.mean, 4),
            "least_satisfied": round(self.least_satisfied, 4),
            "least_satisfied_member": self.least_satisfied_member,
            "fairness_index": round(self.fairness_index, 4),
            "consensus": round(self.consensus, 4),
        }


def evaluate_selection(
    members: Sequence[MemberProfile],
    selected: Sequence[AttractionCandidate],
    matrix: dict[str, dict[str, float]] | None = None,
) -> GroupSatisfaction:
    """Score how well a chosen set of attractions serves each member.

    A member's coverage is the mean of their top-``k`` utilities among the
    selection, where ``k`` is the number of activities that member could
    realistically care about. Using the mean of the top items rather than the
    mean of *all* items prevents a large itinerary from diluting a member whose
    two favourite places are both included.
    """
    if not members:
        return GroupSatisfaction({}, 0.0, 0.0, "", 0.0, 1.0)
    if not selected:
        zero = {m.member_id: 0.0 for m in members}
        return GroupSatisfaction(zero, 0.0, 0.0, members[0].member_id, 1.0, 1.0)

    matrix = matrix or utility_matrix(members, selected)
    per_member: dict[str, float] = {}
    top_k = max(1, min(len(selected), 5))

    for member in members:
        utilities = sorted(
            (matrix[c.slug][member.member_id] for c in selected if c.slug in matrix),
            reverse=True,
        )
        top = utilities[:top_k]
        coverage = sum(top) / len(top) if top else 0.0

        # Honouring an explicit must-visit is worth an outright bonus.
        wanted = set(member.must_visit_slugs)
        if wanted:
            honoured = len(wanted & {c.slug for c in selected}) / len(wanted)
            coverage = 0.7 * coverage + 0.3 * honoured
        per_member[member.member_id] = round(min(1.0, coverage), 6)

    values = list(per_member.values())
    worst_member = min(per_member, key=lambda m: per_member[m])
    return GroupSatisfaction(
        per_member=per_member,
        mean=round(sum(values) / len(values), 6),
        least_satisfied=round(min(values), 6),
        least_satisfied_member=worst_member,
        fairness_index=jains_fairness_index(values),
        consensus=consensus_score(values),
    )


def member_deficits(satisfaction: GroupSatisfaction) -> dict[str, float]:
    """How far below the group mean each member sits (0 if at or above)."""
    return {
        member: max(0.0, satisfaction.mean - value)
        for member, value in satisfaction.per_member.items()
    }


# --------------------------------------------------------------------------- #
# Iterative fair selection
# --------------------------------------------------------------------------- #
def group_objective(satisfaction: GroupSatisfaction, alpha: float = FAIRNESS_ALPHA) -> float:
    """``α·mean + (1-α)·min`` - the quantity iterative selection maximises."""
    return alpha * satisfaction.mean + (1.0 - alpha) * satisfaction.least_satisfied


def select_fairly(
    members: Sequence[MemberProfile],
    scored: Sequence,
    k: int,
    *,
    alpha: float = FAIRNESS_ALPHA,
    item_weight: float = 0.35,
) -> list:
    """Greedily build a shortlist that maximises the fairness-regularised objective.

    Scoring an attraction *in isolation* cannot know that the group already has
    four temples and nobody has anything for the one member who wanted a lake.
    This selects **one item at a time**, recomputing every member's satisfaction
    after each pick, so the marginal value of an item depends on what is already
    chosen. That is what actually raises the floor for the least-satisfied member
    - see ``ml/reports/aggregation_comparison.md`` for the measured difference.

    ``item_weight`` retains part of the item's own suitability score (quality,
    weather, accessibility) so fairness does not select an unsuitable place
    purely because one member likes its category.

    Complexity: O(k · n · m) for k picks, n candidates, m members - a few
    milliseconds at this catalogue size.
    """
    items = list(scored)
    if not items or not members or k <= 0:
        return items[:k]

    # Mandatory items are always in, and go first.
    chosen = [s for s in items if getattr(s, "is_mandatory", False)]
    pool = [s for s in items if not getattr(s, "is_mandatory", False)]

    max_item_score = max((abs(s.total_score) for s in items), default=1.0) or 1.0
    current = evaluate_selection(members, [s.candidate for s in chosen]) if chosen else None
    current_objective = group_objective(current, alpha) if current else 0.0

    while len(chosen) < k and pool:
        best_item = None
        best_value = float("-inf")
        for item in pool:
            trial = [s.candidate for s in chosen] + [item.candidate]
            gain = group_objective(evaluate_selection(members, trial), alpha) - current_objective
            value = (1.0 - item_weight) * gain + item_weight * (item.total_score / max_item_score)
            # Deterministic tie-break on slug.
            if value > best_value or (
                value == best_value and best_item and item.candidate.slug < best_item.candidate.slug
            ):
                best_item, best_value = item, value

        if best_item is None:
            break
        chosen.append(best_item)
        pool.remove(best_item)
        current = evaluate_selection(members, [s.candidate for s in chosen])
        current_objective = group_objective(current, alpha)

    return chosen
