"""Group preference aggregation: fairness is the property under test."""

from __future__ import annotations

import pytest

from yatraai.services.planner.models import AttractionCandidate, MemberProfile
from yatraai.services.recommend import aggregation
from yatraai.services.recommend.taxonomy import INTERESTS, default_preferences, interest_vector


def make_member(member_id: str, **interests) -> MemberProfile:
    profile = default_preferences()
    profile.update(interests)
    return MemberProfile(
        member_id=member_id, display_name=member_id.title(), interests=dict(profile)
    )


def make_attraction(slug: str, categories: list[str], **kw) -> AttractionCandidate:
    defaults = {
        "name": slug.replace("-", " ").title(),
        "lat": 12.97,
        "lon": 77.59,
        "typical_duration_min": 60,
        "min_duration_min": 30,
        "max_duration_min": 120,
    }
    defaults.update(kw)
    return AttractionCandidate(slug=slug, categories=categories, **defaults)


# --------------------------------------------------------------------------- #
class TestMemberUtility:
    def test_matching_interest_scores_higher_than_mismatched(self):
        temple_lover = make_member("asha", spiritual=5, heritage=1, nature=1, adventure=1)
        temple = make_attraction("temple", ["temple", "spiritual"])
        waterfall = make_attraction("falls", ["waterfall", "nature"])
        assert aggregation.member_utility(temple_lover, temple) > aggregation.member_utility(
            temple_lover, waterfall
        )

    def test_utility_is_bounded(self):
        member = make_member("m", **dict.fromkeys(INTERESTS, 5))
        for categories in (["temple"], ["waterfall"], [], ["free"]):
            u = aggregation.member_utility(member, make_attraction("x", categories))
            assert 0.0 <= u <= 1.0

    def test_must_visit_overrides_interest_mismatch(self):
        member = make_member("m", spiritual=0, nature=0, heritage=0, adventure=0)
        member.must_visit_slugs = ["fort"]
        assert aggregation.member_utility(member, make_attraction("fort", ["fort"])) == 1.0

    def test_avoid_list_zeroes_utility(self):
        member = make_member("m", spiritual=5)
        member.avoid_slugs = ["temple"]
        assert aggregation.member_utility(member, make_attraction("temple", ["temple"])) == 0.0

    def test_ranked_choice_boosts_utility(self):
        plain = make_member("a", heritage=4)
        ranked = make_member("b", heritage=4)
        ranked.ranked_choices = ["fort", "museum"]
        fort = make_attraction("fort", ["fort"])
        assert aggregation.member_utility(ranked, fort) > aggregation.member_utility(plain, fort)

    def test_rating_everything_five_does_not_score_everything_one(self):
        """Normalisation must stop an indiscriminate member dominating the group."""
        indiscriminate = make_member("m", **dict.fromkeys(INTERESTS, 5))
        u = aggregation.member_utility(indiscriminate, make_attraction("t", ["temple"]))
        assert u < 0.95


class TestAggregationMethods:
    def setup_method(self):
        self.utilities = {"a": 0.9, "b": 0.9, "c": 0.9, "d": 0.05}
        self.weights = dict.fromkeys("abcd", 1.0)

    def test_simple_average_hides_the_unhappy_member(self):
        assert aggregation.simple_average(self.utilities) == pytest.approx(0.6875)

    def test_max_min_reports_the_unhappy_member(self):
        assert aggregation.max_min_fairness(self.utilities) == pytest.approx(0.05)

    def test_fairness_aware_sits_between_average_and_min(self):
        score = aggregation.fairness_aware(self.utilities, self.weights)
        assert aggregation.max_min_fairness(self.utilities) < score
        assert score < aggregation.simple_average(self.utilities)

    def test_fairness_aware_prefers_the_inclusive_option(self):
        """The core requirement: a majority must not simply overrule one member."""
        inclusive = {"a": 0.65, "b": 0.65, "c": 0.65, "d": 0.62}
        majority = {"a": 0.95, "b": 0.95, "c": 0.95, "d": 0.02}
        w = self.weights
        assert aggregation.simple_average(majority) > aggregation.simple_average(inclusive)
        assert aggregation.fairness_aware(inclusive, w) > aggregation.fairness_aware(majority, w)

    def test_weighted_average_respects_weights(self):
        weights = {"a": 3.0, "b": 1.0, "c": 1.0, "d": 1.0}
        assert aggregation.weighted_average(self.utilities, weights) > aggregation.simple_average(
            self.utilities
        )

    def test_deficit_boost_lifts_items_serving_neglected_members(self):
        base = aggregation.fairness_aware(self.utilities, self.weights)
        boosted = aggregation.fairness_aware(
            self.utilities, self.weights, member_deficits={"d": 0.6}
        )
        assert boosted > base

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError):
            aggregation.aggregate("not_a_method", self.utilities, self.weights)

    def test_empty_utilities_are_safe(self):
        assert aggregation.simple_average({}) == 0.0
        assert aggregation.max_min_fairness({}) == 0.0
        assert aggregation.fairness_aware({}, {}) == 0.0


class TestBordaCount:
    def test_broadly_acceptable_beats_narrowly_loved(self):
        members = [
            make_member("a", heritage=5, nature=1, spiritual=3),
            make_member("b", heritage=5, nature=1, spiritual=3),
            make_member("c", nature=5, heritage=1, spiritual=3),
        ]
        candidates = [
            make_attraction("fort", ["fort", "heritage"]),
            make_attraction("falls", ["waterfall", "nature"]),
            make_attraction("temple", ["temple", "spiritual"]),
        ]
        scores = aggregation.borda_count(members, candidates)
        assert set(scores) == {"fort", "falls", "temple"}
        assert all(0.0 <= v <= 1.0 for v in scores.values())
        # The middle option should not finish last despite nobody ranking it first.
        assert scores["temple"] > min(scores["fort"], scores["falls"])

    def test_ranked_shortlists_dominate(self):
        members = [make_member("a", heritage=1, nature=1)]
        members[0].ranked_choices = ["museum"]
        candidates = [
            make_attraction("fort", ["fort", "heritage"]),
            make_attraction("museum", ["museum"]),
        ]
        scores = aggregation.borda_count(members, candidates)
        assert scores["museum"] > scores["fort"]

    def test_ties_share_points_so_sort_order_cannot_leak(self):
        members = [make_member("a")]
        candidates = [
            make_attraction("x", ["museum"]),
            make_attraction("y", ["museum"]),
        ]
        scores = aggregation.borda_count(members, candidates)
        assert scores["x"] == pytest.approx(scores["y"])

    def test_empty_inputs(self):
        assert aggregation.borda_count([], []) == {}


class TestFairnessMetrics:
    def test_jains_index_is_one_for_equal_allocation(self):
        assert aggregation.jains_fairness_index([0.5, 0.5, 0.5]) == pytest.approx(1.0)

    def test_jains_index_falls_with_inequality(self):
        equal = aggregation.jains_fairness_index([0.6, 0.6, 0.6])
        skewed = aggregation.jains_fairness_index([0.9, 0.9, 0.05])
        assert skewed < equal

    def test_jains_index_lower_bound(self):
        # One member served, n-1 ignored -> index approaches 1/n.
        assert aggregation.jains_fairness_index([1.0, 0.0, 0.0, 0.0]) == pytest.approx(0.25)

    def test_all_zero_allocation_is_trivially_equal(self):
        assert aggregation.jains_fairness_index([0.0, 0.0]) == 1.0

    def test_consensus_is_one_for_identical_values(self):
        assert aggregation.consensus_score([0.4, 0.4, 0.4]) == pytest.approx(1.0)

    def test_consensus_drops_with_spread(self):
        assert aggregation.consensus_score([1.0, 0.0]) < 0.1

    def test_single_member_has_full_consensus(self):
        assert aggregation.consensus_score([0.3]) == 1.0


class TestSelectionEvaluation:
    def setup_method(self):
        self.members = [
            make_member("asha", spiritual=5, heritage=2, nature=1, adventure=1),
            make_member("ben", nature=5, adventure=4, spiritual=1, heritage=1),
            make_member("chi", museums=5, heritage=4, nature=1, spiritual=1),
        ]

    def test_balanced_selection_scores_higher_fairness(self):
        balanced = [
            make_attraction("temple", ["temple", "spiritual"]),
            make_attraction("falls", ["waterfall", "nature"]),
            make_attraction("museum", ["museum"]),
        ]
        skewed = [
            make_attraction("temple", ["temple", "spiritual"]),
            make_attraction("temple2", ["temple", "spiritual"]),
            make_attraction("temple3", ["temple", "spiritual"]),
        ]
        assert (
            aggregation.evaluate_selection(self.members, balanced).fairness_index
            > aggregation.evaluate_selection(self.members, skewed).fairness_index
        )

    def test_identifies_the_least_satisfied_member(self):
        temples_only = [
            make_attraction("t1", ["temple", "spiritual"]),
            make_attraction("t2", ["temple", "spiritual"]),
        ]
        result = aggregation.evaluate_selection(self.members, temples_only)
        assert result.least_satisfied_member in {"ben", "chi"}
        assert result.per_member["asha"] > result.least_satisfied

    def test_honouring_a_must_visit_raises_that_member(self):
        self.members[1].must_visit_slugs = ["falls"]
        without = aggregation.evaluate_selection(
            self.members, [make_attraction("temple", ["temple", "spiritual"])]
        )
        with_it = aggregation.evaluate_selection(
            self.members,
            [
                make_attraction("temple", ["temple", "spiritual"]),
                make_attraction("falls", ["waterfall", "nature"]),
            ],
        )
        assert with_it.per_member["ben"] > without.per_member["ben"]

    def test_empty_selection_is_handled(self):
        result = aggregation.evaluate_selection(self.members, [])
        assert result.mean == 0.0
        assert all(v == 0.0 for v in result.per_member.values())

    def test_deficits_are_non_negative_and_target_the_worst_off(self):
        result = aggregation.evaluate_selection(
            self.members, [make_attraction("t", ["temple", "spiritual"])]
        )
        deficits = aggregation.member_deficits(result)
        assert all(d >= 0 for d in deficits.values())
        assert deficits[result.least_satisfied_member] > 0


class TestTaxonomy:
    def test_interest_vector_is_bounded_and_complete(self):
        vector = interest_vector(["temple", "heritage", "photo-spot"])
        assert set(vector) == set(INTERESTS)
        assert all(0.0 <= v <= 1.0 for v in vector.values())

    def test_unknown_category_is_ignored_not_fatal(self):
        assert interest_vector(["not-a-real-category"]) == dict.fromkeys(INTERESTS, 0.0)

    def test_every_seed_category_is_mapped(self):
        """A new category tag in the data must not silently score zero everywhere."""
        from yatraai.seed.loader import read_seed_files
        from yatraai.services.recommend.taxonomy import CATEGORY_TO_INTERESTS

        used = {
            c
            for payload in read_seed_files()
            for a in payload["attractions"]
            for c in a.get("categories", [])
        }
        unmapped = sorted(used - set(CATEGORY_TO_INTERESTS))
        assert not unmapped, f"categories missing from the taxonomy: {unmapped}"
