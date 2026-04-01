"""Tests for ternary metric functions.

Tests mathematical correctness of soft labels, KL divergence, entropy,
multiclass kappa, and argmax tie-breaking using known analytical solutions.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from pare.annotation.metrics import (
    argmax_with_tiebreak,
    cohens_kappa_multiclass,
    compute_decision_entropy,
    compute_fleiss_kappa_multiclass,
    compute_kl_divergence,
    compute_krippendorff_alpha_multiclass,
    compute_soft_labels_ternary,
)


class TestComputeSoftLabelsTernary:
    """Tests for compute_soft_labels_ternary."""

    def _make_eval_df(self, decisions: list[str], model: str = "u1") -> pl.DataFrame:
        """Create an evaluation DataFrame with given decisions.

        Args:
            decisions: List of decision strings for a single sample.
            model: User model ID.

        Returns:
            DataFrame matching raw evaluation schema.
        """
        return pl.DataFrame({
            "sample_id": ["s1"] * len(decisions),
            "user_model_id": [model] * len(decisions),
            "user_agent_decision": decisions,
            "valid_response": [True] * len(decisions),
        })

    def test_unanimous_accept(self) -> None:
        """All accepts -> accept_prob=1.0, others=0.0."""
        df = self._make_eval_df(["accept", "accept", "accept"])
        result = compute_soft_labels_ternary(df)
        row = result.row(0, named=True)
        assert row["accept_count"] == 3
        assert row["reject_count"] == 0
        assert row["gather_context_count"] == 0
        assert row["accept_prob"] == pytest.approx(1.0)
        assert row["reject_prob"] == pytest.approx(0.0)
        assert row["gather_context_prob"] == pytest.approx(0.0)

    def test_uniform_distribution(self) -> None:
        """One of each -> all probs = 1/3."""
        df = self._make_eval_df(["accept", "reject", "gather_context"])
        result = compute_soft_labels_ternary(df)
        row = result.row(0, named=True)
        assert row["accept_prob"] == pytest.approx(1 / 3)
        assert row["reject_prob"] == pytest.approx(1 / 3)
        assert row["gather_context_prob"] == pytest.approx(1 / 3)

    def test_probabilities_sum_to_one(self) -> None:
        """Probabilities always sum to 1.0."""
        df = self._make_eval_df(["accept", "accept", "reject", "gather_context", "gather_context"])
        result = compute_soft_labels_ternary(df)
        row = result.row(0, named=True)
        total = row["accept_prob"] + row["reject_prob"] + row["gather_context_prob"]
        assert total == pytest.approx(1.0)

    def test_filters_invalid_responses(self) -> None:
        """Invalid responses are excluded from counts."""
        df = pl.DataFrame({
            "sample_id": ["s1", "s1", "s1"],
            "user_model_id": ["u1", "u1", "u1"],
            "user_agent_decision": ["accept", None, "reject"],
            "valid_response": [True, False, True],
        })
        result = compute_soft_labels_ternary(df)
        row = result.row(0, named=True)
        assert row["accept_count"] == 1
        assert row["reject_count"] == 1
        assert row["accept_prob"] == pytest.approx(0.5)

    def test_multiple_samples(self) -> None:
        """Groups by (sample_id, user_model_id) independently."""
        df = pl.DataFrame({
            "sample_id": ["s1", "s1", "s2", "s2"],
            "user_model_id": ["u1", "u1", "u1", "u1"],
            "user_agent_decision": ["accept", "accept", "reject", "reject"],
            "valid_response": [True, True, True, True],
        })
        result = compute_soft_labels_ternary(df).sort("sample_id")
        assert len(result) == 2
        assert result.row(0, named=True)["accept_prob"] == pytest.approx(1.0)
        assert result.row(1, named=True)["reject_prob"] == pytest.approx(1.0)


class TestComputeKlDivergence:
    """Tests for compute_kl_divergence with known analytical solutions."""

    def test_identical_distributions(self) -> None:
        """KL divergence of identical distributions is 0."""
        kl = compute_kl_divergence([0.5, 0.3, 0.2], [0.5, 0.3, 0.2])
        assert kl == pytest.approx(0.0)

    def test_positive_for_different_distributions(self) -> None:
        """KL divergence is positive for different distributions."""
        kl = compute_kl_divergence([0.8, 0.1, 0.1], [0.2, 0.4, 0.4])
        assert kl > 0

    def test_known_value(self) -> None:
        """KL([1,0,0] || [0.5,0.25,0.25]) = log(2) ~= 0.693."""
        kl = compute_kl_divergence([0.5, 0.25, 0.25], [1.0, 0.0, 0.0])
        # KL(human || model): human=[1,0,0], model=[0.5,0.25,0.25]
        # = 1 * log(1/0.5) = log(2)
        assert kl == pytest.approx(math.log(2))

    def test_handles_zero_human_prob(self) -> None:
        """Zero in human distribution contributes 0 to KL, regardless of model value.

        human=[0.5, 0.5, 0.0], model=[0.25, 0.25, 0.5]
        Term 0: 0.5 * log(0.5/0.25) = 0.5 * log(2)
        Term 1: 0.5 * log(0.5/0.25) = 0.5 * log(2)
        Term 2: 0.0 -> skipped (zero human prob, model=0.5 is irrelevant)
        KL = log(2)
        """
        kl = compute_kl_divergence([0.25, 0.25, 0.5], [0.5, 0.5, 0.0])
        assert kl == pytest.approx(math.log(2))

    def test_handles_zero_model_prob(self) -> None:
        """Zero in model distribution uses epsilon clipping."""
        # human=[0.5, 0.5, 0], model=[1.0, 0, 0]
        # KL = 0.5*log(0.5/1.0) + 0.5*log(0.5/eps)
        kl = compute_kl_divergence([1.0, 0.0, 0.0], [0.5, 0.5, 0.0])
        assert kl > 0
        assert math.isfinite(kl)


class TestComputeDecisionEntropy:
    """Tests for compute_decision_entropy."""

    def _make_soft_labels_df(
        self, probs: list[tuple[float, float, float]], model: str = "u1"
    ) -> pl.DataFrame:
        """Create soft labels DataFrame from probability tuples.

        Args:
            probs: List of (accept_prob, reject_prob, gather_context_prob) tuples.
            model: User model ID.

        Returns:
            DataFrame matching compute_soft_labels_ternary output schema.
        """
        return pl.DataFrame({
            "sample_id": [f"s{i}" for i in range(len(probs))],
            "user_model_id": [model] * len(probs),
            "accept_count": [1] * len(probs),
            "reject_count": [1] * len(probs),
            "gather_context_count": [1] * len(probs),
            "accept_prob": [p[0] for p in probs],
            "reject_prob": [p[1] for p in probs],
            "gather_context_prob": [p[2] for p in probs],
        })

    def test_deterministic_zero_entropy(self) -> None:
        """Deterministic decisions (one prob=1.0) have zero entropy."""
        df = self._make_soft_labels_df([(1.0, 0.0, 0.0)])
        result = compute_decision_entropy(df)
        assert result["u1"] == pytest.approx(0.0)

    def test_uniform_max_entropy(self) -> None:
        """Uniform distribution has maximum entropy = log(3)."""
        df = self._make_soft_labels_df([(1 / 3, 1 / 3, 1 / 3)])
        result = compute_decision_entropy(df)
        assert result["u1"] == pytest.approx(math.log(3))

    def test_binary_entropy(self) -> None:
        """50-50 between two categories has entropy = log(2)."""
        df = self._make_soft_labels_df([(0.5, 0.5, 0.0)])
        result = compute_decision_entropy(df)
        assert result["u1"] == pytest.approx(math.log(2))

    def test_average_across_samples(self) -> None:
        """Entropy is averaged across samples for a model."""
        # One deterministic (entropy=0), one uniform (entropy=log(3))
        df = self._make_soft_labels_df([
            (1.0, 0.0, 0.0),
            (1 / 3, 1 / 3, 1 / 3),
        ])
        result = compute_decision_entropy(df)
        assert result["u1"] == pytest.approx(math.log(3) / 2)

    def test_multiple_models(self) -> None:
        """Returns separate entropy values per model."""
        df = pl.concat([
            self._make_soft_labels_df([(1.0, 0.0, 0.0)], model="m1"),
            self._make_soft_labels_df([(1 / 3, 1 / 3, 1 / 3)], model="m2"),
        ])
        result = compute_decision_entropy(df)
        assert result["m1"] == pytest.approx(0.0)
        assert result["m2"] == pytest.approx(math.log(3))


class TestArgmaxWithTiebreak:
    """Tests for argmax_with_tiebreak."""

    def test_clear_winner(self) -> None:
        """No tie — returns label with highest count."""
        result = argmax_with_tiebreak([5, 2, 1], ["accept", "reject", "gather_context"], "s1")
        assert result == "accept"

    def test_tie_is_deterministic(self) -> None:
        """Same inputs always produce same result."""
        r1 = argmax_with_tiebreak([3, 3, 0], ["accept", "reject", "gather_context"], "sample_42")
        r2 = argmax_with_tiebreak([3, 3, 0], ["accept", "reject", "gather_context"], "sample_42")
        assert r1 == r2

    def test_different_seeds_can_break_differently(self) -> None:
        """Different seed strings may produce different tie-breaks."""
        results = set()
        for i in range(20):
            r = argmax_with_tiebreak([3, 3, 0], ["accept", "reject", "gather_context"], f"sample_{i}")
            results.add(r)
        # With 20 different seeds, we should see at least 2 different results
        assert len(results) >= 2

    def test_three_way_tie(self) -> None:
        """Three-way tie returns one of the tied labels."""
        result = argmax_with_tiebreak([2, 2, 2], ["accept", "reject", "gather_context"], "s1")
        assert result in ("accept", "reject", "gather_context")

    def test_single_item(self) -> None:
        """Single category always returns that category."""
        result = argmax_with_tiebreak([5], ["accept"], "s1")
        assert result == "accept"


class TestCohensKappaMulticlass:
    """Tests for cohens_kappa_multiclass with known analytical solutions."""

    def test_perfect_agreement(self) -> None:
        """Identical ratings -> kappa = 1.0."""
        y1 = ["accept", "reject", "gather_context", "accept", "reject"]
        y2 = ["accept", "reject", "gather_context", "accept", "reject"]
        kappa = cohens_kappa_multiclass(y1, y2)
        assert kappa == pytest.approx(1.0)

    def test_systematic_disagreement(self) -> None:
        """Systematic swap of categories -> kappa < 0.

        Both raters use the same categories but always swap them:
        Rater 1: [A, A, R, R]
        Rater 2: [R, R, A, A]

        p_o = 0/4 = 0
        p_A1=0.5, p_A2=0.5, p_R1=0.5, p_R2=0.5
        p_e = 0.5*0.5 + 0.5*0.5 = 0.5
        kappa = (0 - 0.5) / (1 - 0.5) = -1.0
        """
        y1 = ["accept", "accept", "reject", "reject"]
        y2 = ["reject", "reject", "accept", "accept"]
        kappa = cohens_kappa_multiclass(y1, y2)
        assert kappa is not None
        assert kappa == pytest.approx(-1.0)

    def test_partial_agreement(self) -> None:
        """Partial agreement -> 0 < kappa < 1."""
        y1 = ["accept", "reject", "gather_context", "accept"]
        y2 = ["accept", "reject", "accept", "reject"]
        kappa = cohens_kappa_multiclass(y1, y2)
        assert kappa is not None
        assert 0 < kappa < 1

    def test_empty_lists(self) -> None:
        """Empty input returns None."""
        kappa = cohens_kappa_multiclass([], [])
        assert kappa is None

    def test_unequal_lengths(self) -> None:
        """Unequal length lists return None."""
        kappa = cohens_kappa_multiclass(["accept"], ["accept", "reject"])
        assert kappa is None

    def test_known_value(self) -> None:
        """Verify against hand-computed kappa.

        Rater 1: [A, A, R, R]
        Rater 2: [A, R, R, R]

        Confusion matrix:
             A  R
        A  [ 1  1 ]
        R  [ 0  2 ]

        p_o = (1+2)/4 = 0.75
        p_A1 = 2/4 = 0.5, p_A2 = 1/4 = 0.25
        p_R1 = 2/4 = 0.5, p_R2 = 3/4 = 0.75
        p_e = 0.5*0.25 + 0.5*0.75 = 0.125 + 0.375 = 0.5
        kappa = (0.75 - 0.5) / (1 - 0.5) = 0.5
        """
        y1 = ["accept", "accept", "reject", "reject"]
        y2 = ["accept", "reject", "reject", "reject"]
        kappa = cohens_kappa_multiclass(y1, y2)
        assert kappa == pytest.approx(0.5)

    def test_three_categories_perfect(self) -> None:
        """Perfect agreement with all three ternary categories."""
        y1 = ["accept", "reject", "gather_context", "accept", "reject", "gather_context"]
        y2 = ["accept", "reject", "gather_context", "accept", "reject", "gather_context"]
        kappa = cohens_kappa_multiclass(y1, y2)
        assert kappa == pytest.approx(1.0)

    def test_three_categories_partial(self) -> None:
        """Partial agreement across three categories produces 0 < kappa < 1."""
        y1 = ["accept", "reject", "gather_context", "accept", "reject", "gather_context"]
        y2 = ["accept", "reject", "accept", "gather_context", "reject", "gather_context"]
        kappa = cohens_kappa_multiclass(y1, y2)
        assert kappa is not None
        assert 0 < kappa < 1


def _make_annotations_df(
    annotations: dict[str, list[str]],
    model_decisions: list[str] | None = None,
) -> pl.DataFrame:
    """Create a DataFrame matching the format expected by Fleiss/Krippendorff functions.

    Args:
        annotations: Dict mapping annotator_id to list of decisions (one per sample).
            All lists must be the same length.
        model_decisions: Optional list of model decisions (one per sample).
            If None, uses the first annotator's decisions as model.

    Returns:
        DataFrame with sample_id, annotator_id, human_decision, user_agent_decision.
    """
    n_samples = len(next(iter(annotations.values())))
    if model_decisions is None:
        model_decisions = next(iter(annotations.values()))

    rows = []
    for annotator_id, decisions in annotations.items():
        for i, decision in enumerate(decisions):
            rows.append({
                "sample_id": f"s{i}",
                "annotator_id": annotator_id,
                "human_decision": decision,
                "user_agent_decision": model_decisions[i],
            })
    return pl.DataFrame(rows)


class TestFleissKappaMulticlass:
    """Tests for compute_fleiss_kappa_multiclass."""

    def test_perfect_agreement(self) -> None:
        """All raters agree on every sample -> kappa = 1.0."""
        df = _make_annotations_df({
            "a1": ["accept", "reject", "gather_context"],
            "a2": ["accept", "reject", "gather_context"],
            "a3": ["accept", "reject", "gather_context"],
        })
        kappa = compute_fleiss_kappa_multiclass(df, include_model=False)
        assert kappa == pytest.approx(1.0)

    def test_complete_disagreement(self) -> None:
        """Each rater picks a different category per sample -> low kappa."""
        df = _make_annotations_df({
            "a1": ["accept", "reject", "gather_context"],
            "a2": ["reject", "gather_context", "accept"],
            "a3": ["gather_context", "accept", "reject"],
        })
        kappa = compute_fleiss_kappa_multiclass(df, include_model=False)
        assert kappa is not None
        assert kappa <= 0

    def test_partial_agreement(self) -> None:
        """Some agreement -> 0 < kappa < 1."""
        df = _make_annotations_df({
            "a1": ["accept", "reject", "gather_context", "accept"],
            "a2": ["accept", "reject", "accept", "accept"],
            "a3": ["accept", "gather_context", "gather_context", "reject"],
        })
        kappa = compute_fleiss_kappa_multiclass(df, include_model=False)
        assert kappa is not None
        assert 0 < kappa < 1

    def test_include_model_as_rater(self) -> None:
        """Including model as rater changes kappa value."""
        df = _make_annotations_df(
            annotations={
                "a1": ["accept", "reject", "gather_context"],
                "a2": ["accept", "reject", "gather_context"],
            },
            model_decisions=["reject", "reject", "reject"],
        )
        kappa_without = compute_fleiss_kappa_multiclass(df, include_model=False)
        kappa_with = compute_fleiss_kappa_multiclass(df, include_model=True)
        assert kappa_without is not None
        assert kappa_with is not None
        # Model disagrees with humans, so kappa should decrease
        assert kappa_with < kappa_without

    def test_single_annotator_returns_none(self) -> None:
        """Need at least 2 raters."""
        df = _make_annotations_df({"a1": ["accept", "reject"]})
        kappa = compute_fleiss_kappa_multiclass(df, include_model=False)
        assert kappa is None

    def test_empty_df_returns_none(self) -> None:
        """Empty DataFrame returns None."""
        df = pl.DataFrame({
            "sample_id": [],
            "annotator_id": [],
            "human_decision": [],
            "user_agent_decision": [],
        })
        kappa = compute_fleiss_kappa_multiclass(df, include_model=False)
        assert kappa is None


class TestKrippendorffAlphaMulticlass:
    """Tests for compute_krippendorff_alpha_multiclass."""

    def test_perfect_agreement(self) -> None:
        """All raters agree -> alpha = 1.0."""
        df = _make_annotations_df({
            "a1": ["accept", "reject", "gather_context"],
            "a2": ["accept", "reject", "gather_context"],
            "a3": ["accept", "reject", "gather_context"],
        })
        alpha = compute_krippendorff_alpha_multiclass(df, include_model=False)
        assert alpha == pytest.approx(1.0)

    def test_complete_disagreement(self) -> None:
        """Systematic disagreement -> alpha <= 0."""
        df = _make_annotations_df({
            "a1": ["accept", "reject", "gather_context"],
            "a2": ["reject", "gather_context", "accept"],
            "a3": ["gather_context", "accept", "reject"],
        })
        alpha = compute_krippendorff_alpha_multiclass(df, include_model=False)
        assert alpha is not None
        assert alpha <= 0

    def test_partial_agreement(self) -> None:
        """Some agreement -> 0 < alpha < 1."""
        df = _make_annotations_df({
            "a1": ["accept", "reject", "gather_context", "accept"],
            "a2": ["accept", "reject", "accept", "accept"],
            "a3": ["accept", "gather_context", "gather_context", "reject"],
        })
        alpha = compute_krippendorff_alpha_multiclass(df, include_model=False)
        assert alpha is not None
        assert 0 < alpha < 1

    def test_include_model(self) -> None:
        """Including model as rater changes alpha."""
        df = _make_annotations_df(
            annotations={
                "a1": ["accept", "reject", "gather_context"],
                "a2": ["accept", "reject", "gather_context"],
            },
            model_decisions=["reject", "reject", "reject"],
        )
        alpha_without = compute_krippendorff_alpha_multiclass(df, include_model=False)
        alpha_with = compute_krippendorff_alpha_multiclass(df, include_model=True)
        assert alpha_without is not None
        assert alpha_with is not None
        assert alpha_with < alpha_without

    def test_single_rater_returns_none(self) -> None:
        """Need at least 2 raters."""
        df = _make_annotations_df({"a1": ["accept", "reject"]})
        alpha = compute_krippendorff_alpha_multiclass(df, include_model=False)
        assert alpha is None
