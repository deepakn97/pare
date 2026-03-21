"""Agreement metrics computation for annotation analysis.

Implements comprehensive metrics for measuring alignment between a ML model
and multiple human annotators on binary prediction tasks.

Metrics included:
1. Agreement with Majority Vote (accuracy, F1, precision, recall, Cohen's kappa)
2. Soft Label Alignment (cross-entropy, MAE)
3. Average Pairwise Cohen's Kappa (model vs each human)
4. Krippendorff's Alpha (model as k+1 rater)
5. Fleiss' Kappa (human-only baseline)
6. Stratified Analysis by consensus level
"""

from __future__ import annotations

import logging
import math
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)


def compute_per_model_agreement_metrics(
    evaluations_df: pl.DataFrame,
    annotations_df: pl.DataFrame,
    n_annotators: int = 2,
) -> dict[str, dict[str, Any]]:
    """Compute agreement metrics per user model from the evaluation dataframe.

    For each user_model_id in the evaluations, aggregates runs via majority vote
    and computes agreement metrics against human annotations.

    Args:
        evaluations_df: DataFrame from `pas annotation evaluate` with columns:
            sample_id, user_model_id, user_agent_decision, run, valid_response.
        annotations_df: DataFrame with human annotation data.
        n_annotators: Number of top annotators to include (by completion count).

    Returns:
        Dictionary mapping user_model_id to agreement metrics dict.
    """
    user_models = evaluations_df["user_model_id"].unique().to_list()
    results: dict[str, dict[str, Any]] = {}

    for model_id in sorted(user_models):
        model_evals = evaluations_df.filter((pl.col("user_model_id") == model_id) & pl.col("valid_response"))

        # Majority vote across runs for each sample
        majority_votes = model_evals.group_by("sample_id").agg(
            (pl.col("user_agent_decision").mean() >= 0.5).alias("user_agent_decision"),
            pl.col("scenario_id").first().alias("scenario_id"),
        )

        if len(majority_votes) == 0:
            logger.warning(f"No valid evaluations for model {model_id}")
            results[model_id] = _empty_metrics()
            continue

        # Use the existing compute_agreement_metrics with majority-voted decisions as "samples"
        results[model_id] = compute_agreement_metrics(majority_votes, annotations_df, n_annotators)

    return results


def compute_agreement_metrics(
    samples_df: pl.DataFrame,
    annotations_df: pl.DataFrame,
    n_annotators: int = 2,
) -> dict[str, Any]:
    """Compute comprehensive agreement metrics.

    Args:
        samples_df: DataFrame with sample data including user_agent_decision.
        annotations_df: DataFrame with annotation data.
        n_annotators: Number of top annotators to include (by completion count).

    Returns:
        Dictionary containing all computed metrics.
    """
    # Select top-n annotators by completion count
    filtered_annotations = _select_top_annotators(annotations_df, n_annotators)

    # Join annotations with samples
    joined = filtered_annotations.join(
        samples_df.select(["sample_id", "user_agent_decision"]),
        on="sample_id",
        how="left",
    )

    # Filter to samples that have annotations from ALL selected annotators
    selected_annotators = filtered_annotations["annotator_id"].unique().to_list()
    sample_annotator_counts = joined.group_by("sample_id").agg(pl.col("annotator_id").n_unique().alias("n_annotators"))
    complete_samples = sample_annotator_counts.filter(pl.col("n_annotators") == len(selected_annotators))[
        "sample_id"
    ].to_list()

    filtered = joined.filter(pl.col("sample_id").is_in(complete_samples))

    # Basic counts
    n_samples = len(complete_samples)
    n_annotations = len(filtered)
    actual_n_annotators = filtered["annotator_id"].n_unique() if len(filtered) > 0 else 0

    if n_samples == 0:
        logger.warning("No samples with complete annotations from selected annotators")
        return _empty_metrics()

    # Human-human agreement (baseline)
    fleiss_kappa_humans = _compute_fleiss_kappa(filtered, include_model=False)

    # Model alignment metrics
    majority_vote_metrics = _compute_majority_vote_metrics(filtered)
    soft_label_metrics = _compute_soft_label_metrics(filtered)
    avg_pairwise_kappa = _compute_avg_pairwise_model_human_kappa(filtered)
    krippendorff_alpha = _compute_krippendorff_alpha(filtered, include_model=True)
    fleiss_kappa_with_model = _compute_fleiss_kappa(filtered, include_model=True)

    # Stratified analysis
    stratified = _compute_stratified_analysis(filtered)

    # Distribution stats
    human_accept_rate = filtered["human_decision"].mean() if len(filtered) > 0 else 0
    agent_accept_rate = (
        samples_df.filter(pl.col("sample_id").is_in(complete_samples))["user_agent_decision"].mean()
        if n_samples > 0
        else 0
    )

    # Per-annotator stats
    per_annotator = _compute_per_annotator_stats(filtered)

    return {
        # Basic counts
        "n_samples": n_samples,
        "n_annotations": n_annotations,
        "n_annotators": actual_n_annotators,
        # Human-human agreement (baseline)
        "fleiss_kappa_humans": fleiss_kappa_humans,
        # Model vs majority vote
        "majority_vote_metrics": majority_vote_metrics,
        # Soft label alignment
        "soft_label_metrics": soft_label_metrics,
        # Average pairwise model-human kappa
        "avg_pairwise_model_human_kappa": avg_pairwise_kappa,
        # Krippendorff's alpha (model as k+1 rater)
        "krippendorff_alpha_with_model": krippendorff_alpha,
        # Fleiss' kappa with model as k+1 rater
        "fleiss_kappa_with_model": fleiss_kappa_with_model,
        # Stratified analysis by consensus level
        "stratified_analysis": stratified,
        # Distribution stats
        "human_accept_rate": human_accept_rate,
        "agent_accept_rate": agent_accept_rate,
        # Per-annotator stats
        "per_annotator_stats": per_annotator,
    }


def _empty_metrics() -> dict[str, Any]:
    """Return empty metrics structure when no data available."""
    return {
        "n_samples": 0,
        "n_annotations": 0,
        "n_annotators": 0,
        "fleiss_kappa_humans": None,
        "majority_vote_metrics": {
            "accuracy": None,
            "precision": None,
            "recall": None,
            "f1": None,
            "cohens_kappa": None,
        },
        "soft_label_metrics": {"cross_entropy": None, "mae": None},
        "avg_pairwise_model_human_kappa": {"mean": None, "std": None},
        "krippendorff_alpha_with_model": None,
        "fleiss_kappa_with_model": None,
        "stratified_analysis": {},
        "human_accept_rate": 0,
        "agent_accept_rate": 0,
        "per_annotator_stats": {},
    }


def _select_top_annotators(
    annotations_df: pl.DataFrame,
    n_annotators: int,
) -> pl.DataFrame:
    """Select annotations from the top-n annotators by completion count.

    Args:
        annotations_df: DataFrame with all annotations.
        n_annotators: Number of top annotators to select.

    Returns:
        Filtered DataFrame with only annotations from top annotators.
    """
    # Count annotations per annotator
    annotator_counts = annotations_df.group_by("annotator_id").len().sort("len", descending=True)

    # Select top n annotators
    top_annotators = annotator_counts.head(n_annotators)["annotator_id"].to_list()

    logger.info(f"Selected top {n_annotators} annotators: {top_annotators}")
    for annotator_id in top_annotators:
        count = annotator_counts.filter(pl.col("annotator_id") == annotator_id)["len"].item()
        logger.info(f"  {annotator_id[:8]}...: {count} annotations")

    # Filter to only their annotations
    return annotations_df.filter(pl.col("annotator_id").is_in(top_annotators))


def _compute_majority_vote_metrics(df: pl.DataFrame) -> dict[str, float | None]:
    """Compute metrics comparing model predictions to human majority vote.

    Metrics: accuracy, precision, recall, F1, Cohen's kappa.
    """
    if len(df) == 0:
        return {"accuracy": None, "precision": None, "recall": None, "f1": None, "cohens_kappa": None}

    # Get majority vote per sample
    sample_votes = df.group_by("sample_id").agg([
        pl.col("human_decision").sum().alias("accepts"),
        pl.col("human_decision").count().alias("total"),
        pl.col("user_agent_decision").first().alias("agent_pred"),
    ])

    # Majority = accepts > total/2 (strict majority)
    sample_votes = sample_votes.with_columns((pl.col("accepts") > pl.col("total") / 2).alias("majority_label"))

    y_true = sample_votes["majority_label"].to_list()
    y_pred = sample_votes["agent_pred"].to_list()

    if not y_true:
        return {"accuracy": None, "precision": None, "recall": None, "f1": None, "cohens_kappa": None}

    # Calculate confusion matrix elements
    tp = sum(1 for t, p in zip(y_true, y_pred, strict=False) if t and p)
    tn = sum(1 for t, p in zip(y_true, y_pred, strict=False) if not t and not p)
    fp = sum(1 for t, p in zip(y_true, y_pred, strict=False) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred, strict=False) if t and not p)

    # Calculate metrics
    accuracy = (tp + tn) / len(y_true)
    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall and (precision + recall) > 0 else None
    kappa = _cohens_kappa(y_true, y_pred)

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "cohens_kappa": kappa,
    }


def _compute_soft_label_metrics(df: pl.DataFrame) -> dict[str, float | None]:
    """Compute alignment metrics against soft labels (proportion accepting).

    Soft labels treat the proportion of annotators choosing each class as
    a probability distribution, capturing uncertainty in human judgment.

    Metrics:
    - Cross-entropy loss: Measures how well model predictions match soft labels
    - MAE: Mean absolute error between model prediction and acceptance proportion
    """
    if len(df) == 0:
        return {"cross_entropy": None, "mae": None}

    sample_probs = df.group_by("sample_id").agg([
        pl.col("human_decision").mean().alias("soft_label"),  # proportion accepting
        pl.col("user_agent_decision").first().alias("agent_pred"),
    ])

    soft_labels = sample_probs["soft_label"].to_list()
    agent_preds = [float(p) for p in sample_probs["agent_pred"].to_list()]  # 0.0 or 1.0

    if not soft_labels:
        return {"cross_entropy": None, "mae": None}

    # Cross-entropy: -sum(y * log(p) + (1-y) * log(1-p))
    # where y is soft label (proportion) and p is prediction
    eps = 1e-15
    ce_losses = []
    for soft, pred in zip(soft_labels, agent_preds, strict=False):
        pred_clipped = max(eps, min(1 - eps, pred))
        ce = -(soft * math.log(pred_clipped) + (1 - soft) * math.log(1 - pred_clipped))
        ce_losses.append(ce)

    cross_entropy = sum(ce_losses) / len(ce_losses)

    # MAE: average absolute difference between soft label and prediction
    mae = sum(abs(s - p) for s, p in zip(soft_labels, agent_preds, strict=False)) / len(soft_labels)

    return {"cross_entropy": cross_entropy, "mae": mae}


def _compute_avg_pairwise_model_human_kappa(df: pl.DataFrame) -> dict[str, float | None]:
    """Compute Cohen's kappa between model and each human annotator.

    Returns mean and standard deviation across all human annotators.
    This reveals if the model aligns better with some annotators than others.
    """
    if len(df) == 0:
        return {"mean": None, "std": None}

    annotators = df["annotator_id"].unique().to_list()
    kappas = []

    for annotator_id in annotators:
        annotator_df = df.filter(pl.col("annotator_id") == annotator_id)
        human = annotator_df["human_decision"].to_list()
        agent = annotator_df["user_agent_decision"].to_list()
        kappa = _cohens_kappa(human, agent)
        if kappa is not None:
            kappas.append(kappa)

    if not kappas:
        return {"mean": None, "std": None}

    mean_kappa = sum(kappas) / len(kappas)
    variance = sum((k - mean_kappa) ** 2 for k in kappas) / len(kappas)
    std_kappa = math.sqrt(variance)

    return {"mean": mean_kappa, "std": std_kappa}


def _compute_fleiss_kappa(df: pl.DataFrame, *, include_model: bool = False) -> float | None:  # noqa: C901
    """Compute Fleiss' Kappa for multiple raters.

    Fleiss' Kappa measures agreement among multiple raters when each item
    is rated by a fixed number of raters.

    Args:
        df: DataFrame with annotations.
        include_model: If True, treat model as an additional rater.

    Returns:
        Fleiss' Kappa value or None if computation not possible.
    """
    if len(df) == 0:
        return None

    samples = df["sample_id"].unique().to_list()
    annotators = df["annotator_id"].unique().to_list()

    if len(annotators) < 2 and not include_model:
        return None

    # Build rating matrix: rows = samples, columns = categories (0=reject, 1=accept)
    # Each cell = number of raters who gave that rating for that sample
    ratings_matrix = []
    for sample_id in samples:
        sample_annotations = df.filter(pl.col("sample_id") == sample_id)
        human_accepts = int(sample_annotations["human_decision"].sum())
        human_rejects = len(sample_annotations) - human_accepts

        if include_model:
            # Add model as additional rater
            agent_decision = sample_annotations["user_agent_decision"].first()
            if agent_decision:
                human_accepts += 1
            else:
                human_rejects += 1

        ratings_matrix.append([human_rejects, human_accepts])

    if not ratings_matrix:
        return None

    n = len(ratings_matrix)  # number of samples

    # Calculate P_i for each sample (proportion of agreeing pairs)
    p_i_list = []
    for row in ratings_matrix:
        n_j = sum(row)
        if n_j <= 1:
            continue
        p_i = (sum(r * r for r in row) - n_j) / (n_j * (n_j - 1))
        p_i_list.append(p_i)

    if not p_i_list:
        return None

    p_bar = sum(p_i_list) / len(p_i_list)

    # Calculate P_j for each category (proportion of all ratings in that category)
    total_ratings = sum(sum(row) for row in ratings_matrix)
    p_j_list = []
    for j in range(2):  # Binary: reject (0), accept (1)
        category_total = sum(row[j] for row in ratings_matrix)
        p_j_list.append(category_total / total_ratings if total_ratings > 0 else 0)

    # Expected agreement by chance
    p_e = sum(p_j * p_j for p_j in p_j_list)

    if p_e == 1:
        return 1.0 if p_bar == 1 else 0.0

    kappa = (p_bar - p_e) / (1 - p_e)
    return kappa


def _compute_krippendorff_alpha(df: pl.DataFrame, *, include_model: bool = True) -> float | None:  # noqa: C901
    """Compute Krippendorff's Alpha for nominal data.

    Krippendorff's Alpha is a robust measure of inter-rater reliability that:
    - Handles any number of raters
    - Works with missing data
    - For nominal data, is equivalent to Fleiss' Kappa

    Args:
        df: DataFrame with annotations.
        include_model: If True, treat model as an additional rater.

    Returns:
        Krippendorff's Alpha value or None if computation not possible.
    """
    if len(df) == 0:
        return None

    samples = df["sample_id"].unique().to_list()
    annotators = df["annotator_id"].unique().to_list()

    # Build reliability data: dict of (rater, sample) -> value
    ratings: dict[tuple[str, str], int] = {}
    for row in df.iter_rows(named=True):
        ratings[(row["annotator_id"], row["sample_id"])] = int(row["human_decision"])

    # Add model as additional rater if requested
    if include_model:
        model_id = "__MODEL__"
        for row in df.iter_rows(named=True):
            ratings[(model_id, row["sample_id"])] = int(row["user_agent_decision"])
        all_raters = [*annotators, model_id]
    else:
        all_raters = annotators

    if len(all_raters) < 2:
        return None

    # For nominal data, Krippendorff's Alpha uses coincidence matrix
    # Values are 0 (reject) and 1 (accept)
    values = [0, 1]

    # Count coincidences: for each pair of raters rating the same item
    # Build observed coincidence matrix
    o_matrix = {(v1, v2): 0.0 for v1 in values for v2 in values}

    for sample_id in samples:
        # Get all ratings for this sample
        sample_ratings = [(r, ratings[(r, sample_id)]) for r in all_raters if (r, sample_id) in ratings]

        n_raters = len(sample_ratings)
        if n_raters < 2:
            continue

        # For each pair of raters, count coincidences
        for i, (_, v1) in enumerate(sample_ratings):
            for j, (_, v2) in enumerate(sample_ratings):
                if i != j:
                    o_matrix[(v1, v2)] += 1.0 / (n_raters - 1)

    # Total number of pairable values
    n_total = sum(o_matrix.values())
    if n_total == 0:
        return None

    # Calculate observed disagreement
    d_o = 0.0
    for v1 in values:
        for v2 in values:
            if v1 != v2:  # Nominal: disagreement = 1 if different, 0 if same
                d_o += o_matrix[(v1, v2)]
    d_o /= n_total

    # Calculate expected disagreement
    # Marginal frequencies
    n_c = {v: sum(o_matrix[(v, v2)] for v2 in values) for v in values}
    n_total_marginal = sum(n_c.values())

    if n_total_marginal <= 1:
        return None

    d_e = 0.0
    for v1 in values:
        for v2 in values:
            if v1 != v2:
                d_e += n_c[v1] * n_c[v2]
    d_e /= n_total_marginal * (n_total_marginal - 1)

    if d_e == 0:
        return 1.0 if d_o == 0 else 0.0

    alpha = 1 - d_o / d_e
    return alpha


def _compute_stratified_analysis(df: pl.DataFrame) -> dict[str, dict[str, Any]]:
    """Compute model performance stratified by human consensus level.

    Categorizes samples into:
    - unanimous: All humans agreed (100% or 0% acceptance)
    - high_agreement: Strong consensus (>=75% or <=25% acceptance)
    - low_agreement: Split decisions (between 25% and 75%)

    This reveals whether the model performs better on clear-cut vs ambiguous cases.
    """
    if len(df) == 0:
        return {}

    sample_consensus = df.group_by("sample_id").agg([
        pl.col("human_decision").mean().alias("agreement_ratio"),
        pl.col("human_decision").sum().alias("accepts"),
        pl.col("human_decision").count().alias("total"),
        pl.col("user_agent_decision").first().alias("agent_pred"),
    ])

    # Categorize by consensus level
    sample_consensus = sample_consensus.with_columns([
        pl.when((pl.col("agreement_ratio") == 0) | (pl.col("agreement_ratio") == 1))
        .then(pl.lit("unanimous"))
        .when((pl.col("agreement_ratio") >= 0.75) | (pl.col("agreement_ratio") <= 0.25))
        .then(pl.lit("high_agreement"))
        .otherwise(pl.lit("low_agreement"))
        .alias("consensus_level"),
        # Majority label (for comparison with model)
        (pl.col("agreement_ratio") > 0.5).alias("majority_label"),
    ])

    results: dict[str, dict[str, Any]] = {}
    for level in ["unanimous", "high_agreement", "low_agreement"]:
        subset = sample_consensus.filter(pl.col("consensus_level") == level)
        n_subset = len(subset)

        if n_subset == 0:
            results[level] = {"n_samples": 0, "accuracy": None, "model_accept_rate": None}
            continue

        # Accuracy vs majority vote
        correct = subset.filter(pl.col("majority_label") == pl.col("agent_pred"))
        accuracy = len(correct) / n_subset

        # Model's accept rate in this stratum
        model_accept_rate = subset["agent_pred"].mean()

        # Human accept rate in this stratum
        human_accept_rate = subset["agreement_ratio"].mean()

        results[level] = {
            "n_samples": n_subset,
            "accuracy": accuracy,
            "model_accept_rate": model_accept_rate,
            "human_accept_rate": human_accept_rate,
        }

    return results


def _compute_per_annotator_stats(df: pl.DataFrame) -> dict[str, dict[str, Any]]:
    """Compute statistics for each annotator."""
    if len(df) == 0:
        return {}

    annotators = df["annotator_id"].unique().to_list()
    stats = {}

    for annotator_id in annotators:
        annotator_df = df.filter(pl.col("annotator_id") == annotator_id)
        count = len(annotator_df)
        accept_rate = annotator_df["human_decision"].mean() if count > 0 else 0

        # Agreement with model
        agrees = annotator_df.filter(pl.col("human_decision") == pl.col("user_agent_decision"))
        model_agreement = len(agrees) / count if count > 0 else 0

        # Cohen's kappa with model
        human = annotator_df["human_decision"].to_list()
        agent = annotator_df["user_agent_decision"].to_list()
        kappa_with_model = _cohens_kappa(human, agent)

        stats[annotator_id] = {
            "count": count,
            "accept_rate": accept_rate,
            "model_agreement": model_agreement,
            "kappa_with_model": kappa_with_model,
        }

    return stats


def _cohens_kappa(y1: list[bool], y2: list[bool]) -> float | None:
    """Compute Cohen's Kappa between two raters.

    Cohen's Kappa measures agreement between two raters, accounting for
    agreement that would be expected by chance.

    Args:
        y1: First rater's decisions.
        y2: Second rater's decisions.

    Returns:
        Cohen's Kappa value or None if computation not possible.
    """
    if len(y1) != len(y2) or len(y1) == 0:
        return None

    n = len(y1)

    # Build confusion matrix
    both_true = sum(1 for a, b in zip(y1, y2, strict=False) if a and b)
    both_false = sum(1 for a, b in zip(y1, y2, strict=False) if not a and not b)
    a1_true_a2_false = sum(1 for a, b in zip(y1, y2, strict=False) if a and not b)
    a1_false_a2_true = sum(1 for a, b in zip(y1, y2, strict=False) if not a and b)

    # Observed agreement
    p_o = (both_true + both_false) / n

    # Expected agreement by chance
    p_a1_true = (both_true + a1_true_a2_false) / n
    p_a2_true = (both_true + a1_false_a2_true) / n
    p_a1_false = 1 - p_a1_true
    p_a2_false = 1 - p_a2_true

    p_e = p_a1_true * p_a2_true + p_a1_false * p_a2_false

    if p_e == 1:
        return 1.0 if p_o == 1 else 0.0

    kappa = (p_o - p_e) / (1 - p_e)
    return kappa
