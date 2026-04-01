"""Annotation CLI commands for human evaluation of proactive agent proposals."""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: TC003 - typer evaluates annotations at runtime
from typing import TYPE_CHECKING, Annotated, Any

if TYPE_CHECKING:
    import polars as pl

    from pare.trajectory.models import DecisionPoint as TernaryDecisionPoint

import typer

from pare.annotation.config import ensure_extension

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="annotation",
    help="Human annotation interface for evaluating proactive agent proposals",
)


def _format_size(size_bytes: int) -> str:
    """Format size in bytes to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def _validate_sample_args(
    sample_size: int | None,
    per_model: str | None,
    target_models: str | None,
) -> tuple[dict[str, int] | None, list[str] | None]:
    """Validate and parse sample command arguments.

    Returns:
        Tuple of (per_model_count, target_model_list).
    """
    per_model_count: dict[str, int] | None = _parse_per_model_arg(per_model) if per_model else None
    target_model_list: list[str] | None = (
        [m.strip() for m in target_models.split(",") if m.strip()] if target_models else None
    )

    if sample_size is not None and per_model_count is not None:
        typer.echo("Error: --sample-size and --per-model are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    if per_model_count is not None and target_model_list is not None:
        typer.echo("Error: --per-model and --target-models are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    if sample_size is None and per_model_count is None:
        typer.echo("Error: Either --sample-size or --per-model must be provided.", err=True)
        raise typer.Exit(code=1)

    return per_model_count, target_model_list


def _parse_per_model_arg(per_model: str) -> dict[str, int]:
    """Parse --per-model argument into a dict of model:count pairs."""
    result: dict[str, int] = {}
    for pair in per_model.split(","):
        parts = pair.strip().split(":")
        if len(parts) != 2:
            raise typer.BadParameter(f"Invalid --per-model format: '{pair}'. Expected 'model:count'.")
        result[parts[0].strip()] = int(parts[1].strip())
    return result


def _print_sample_stats(samples: list[TernaryDecisionPoint], output_file: Path) -> None:
    """Print sampling statistics to console.

    Args:
        samples: List of TernaryDecisionPoint objects.
        output_file: Path where samples were saved.
    """
    from collections import Counter

    accepts = len([s for s in samples if s.user_agent_decision == "accept"])
    rejects = len([s for s in samples if s.user_agent_decision == "reject"])
    gather_context = len([s for s in samples if s.user_agent_decision == "gather_context"])
    unique_scenarios = len({s.scenario_id for s in samples})
    model_counts = Counter(s.proactive_model_id for s in samples)

    typer.echo("\nSampling complete!")
    typer.echo(f"  New samples added: {len(samples)}")
    typer.echo(f"  Accepts: {accepts}")
    typer.echo(f"  Rejects: {rejects}")
    typer.echo(f"  Gather context: {gather_context}")
    if len(model_counts) > 1:
        typer.echo("  Per model:")
        for model_id, count in sorted(model_counts.items()):
            typer.echo(f"    {model_id}: {count}")
    typer.echo(f"  Unique scenarios: {unique_scenarios}")
    typer.echo(f"\nSamples saved to: {output_file}")


def _copy_tutorial_examples(tutorial_path: Path, output_file: Path) -> None:
    """Copy tutorial examples into the output parquet file.

    If the output file already exists, removes any existing tutorial rows
    before appending to avoid duplication.

    Args:
        tutorial_path: Path to the tutorial_samples.parquet file.
        output_file: Path to the output samples.parquet file.
    """
    import polars as pl

    tutorial_df = pl.read_parquet(tutorial_path)
    if len(tutorial_df) == 0:
        typer.echo("Tutorial file is empty, skipping tutorial examples.")
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        existing_df = pl.read_parquet(output_file)

        # Check for incompatible old schema
        if "tutorial" not in existing_df.columns:
            typer.echo(
                f"Error: Existing parquet {output_file} is missing the 'tutorial' column. "
                "Delete it and re-sample with the ternary pipeline.",
                err=True,
            )
            raise typer.Exit(code=1)

        existing_non_tutorial = existing_df.filter(pl.col("tutorial") == False)  # noqa: E712
        combined = pl.concat([existing_non_tutorial, tutorial_df])
        combined.write_parquet(output_file)
        typer.echo(f"Added {len(tutorial_df)} tutorial examples to {output_file}")
    else:
        tutorial_df.write_parquet(output_file)
        typer.echo(f"Created {output_file} with {len(tutorial_df)} tutorial examples")


@app.command()
def sample(  # noqa: C901
    traces_dir: Annotated[
        Path,
        typer.Option("--traces-dir", "-t", help="Path to the traces directory"),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output path for samples (extension auto-corrected to .parquet)"),
    ],
    sample_size: Annotated[
        int | None,
        typer.Option("--sample-size", "-n", help="Number of samples to add (optional if --per-model is used)"),
    ] = None,
    seed: Annotated[
        int | None,
        typer.Option("--seed", "-s", help="Random seed for reproducibility"),
    ] = None,
    target_models: Annotated[
        str | None,
        typer.Option(
            "--target-models", help="Comma-separated proactive models; used with --sample-size to distribute equally"
        ),
    ] = None,
    per_model: Annotated[
        str | None,
        typer.Option(
            "--per-model", help="Comma-separated model:count pairs (e.g., 'claude-4.5-sonnet:50,qwen-3-4b-it:50')"
        ),
    ] = None,
    user_model: Annotated[
        str,
        typer.Option("--user-model", "-um", help="User model that generated the traces"),
    ] = "gpt-5-mini",
    add_tutorial_examples: Annotated[
        Path | None,
        typer.Option("--add-tutorial-examples", help="Path to tutorial_samples.parquet to copy into output"),
    ] = None,
) -> None:
    """Sample ternary decision points from traces for annotation.

    Creates a balanced dataset of accept/reject/gather_context decisions
    using three-way balanced sampling. Writes parquet with ternary schema.
    Appends to existing samples if output file already exists.
    """
    from pare.annotation.sampler import sample_new_datapoints_ternary

    per_model_count, target_model_list = _validate_sample_args(sample_size, per_model, target_models)

    # Resolve paths
    traces_dir = traces_dir.resolve()
    output_file = ensure_extension(output.resolve(), ".parquet")

    if not traces_dir.exists():
        typer.echo(f"Error: Traces directory not found: {traces_dir}", err=True)
        raise typer.Exit(code=1)

    # Copy tutorial examples if requested
    if add_tutorial_examples:
        tutorial_path = add_tutorial_examples.resolve()
        if not tutorial_path.exists():
            typer.echo(f"Error: Tutorial file not found: {tutorial_path}", err=True)
            raise typer.Exit(code=1)
        _copy_tutorial_examples(tutorial_path, output_file)

    # Show existing samples info
    if output_file.exists():
        import polars as pl

        existing_df = pl.read_parquet(output_file)
        typer.echo(f"Existing samples in {output_file}: {len(existing_df)}")
    else:
        typer.echo(f"No existing samples at {output_file}. Creating new sample set.")

    effective_size = sum(per_model_count.values()) if per_model_count else sample_size
    typer.echo(f"Sampling {effective_size} new datapoints from {traces_dir}...")
    if per_model_count:
        for model, count in per_model_count.items():
            typer.echo(f"  {model}: {count}")
    if target_model_list:
        typer.echo(f"Target models: {target_model_list} (distributing {sample_size} equally)")

    try:
        samples = sample_new_datapoints_ternary(
            traces_dir=traces_dir,
            samples_file=output_file,
            user_model_id=user_model,
            sample_size=effective_size,  # type: ignore[arg-type]
            seed=seed,
            target_models=target_model_list,
        )
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None
    except Exception as e:
        typer.echo(f"Error during sampling: {e}", err=True)
        logger.exception("Sampling failed")
        raise typer.Exit(code=1) from None

    if not samples:
        typer.echo("No new samples could be created. All candidates may already be sampled.", err=True)
        raise typer.Exit(code=1)

    _print_sample_stats(samples, output_file)


@app.command()
def launch(
    samples: Annotated[
        Path,
        typer.Option("--samples", help="Path to the samples parquet file"),
    ],
    annotations: Annotated[
        Path,
        typer.Option("--annotations", help="Path to the annotations CSV file (created if not exists)"),
    ],
    annotators_per_sample: Annotated[
        int,
        typer.Option("--annotators-per-sample", "-k", help="Number of annotations required per sample"),
    ] = 2,
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port to run the server on"),
    ] = 8000,
) -> None:
    """Launch the annotation web interface.

    Starts a FastAPI server that serves the annotation UI. Share the URL
    with annotators (use ngrok for public access).
    """
    from pare.annotation.server import run_server

    samples_file = ensure_extension(samples.resolve(), ".parquet")
    annotations_file = ensure_extension(annotations.resolve(), ".csv")

    if not samples_file.exists():
        typer.echo(f"Error: No samples found at {samples_file}", err=True)
        typer.echo("Run 'pare annotation sample' first to create samples.")
        raise typer.Exit(code=1)

    typer.echo("PARE Annotation Server")
    typer.echo("=" * 40)
    typer.echo(f"Samples: {samples_file}")
    typer.echo(f"Annotations: {annotations_file}")
    typer.echo(f"Annotators per sample: {annotators_per_sample}")
    typer.echo(f"Server URL: http://localhost:{port}")
    typer.echo("")
    typer.echo("For public access, use ngrok:")
    typer.echo(f"  ngrok http {port}")
    typer.echo("")
    typer.echo("Press Ctrl+C to stop the server.")
    typer.echo("=" * 40)

    try:
        run_server(samples_file, annotations_file, port, annotators_per_sample)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None
    except KeyboardInterrupt:
        typer.echo("\nServer stopped.")


@app.command()
def status(
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port of the running annotation server"),
    ] = 8000,
) -> None:
    """Show annotation progress from a running annotation server."""
    import json
    import urllib.error
    import urllib.request

    url = f"http://localhost:{port}/api/stats"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
            stats = json.loads(response.read().decode())
    except urllib.error.URLError as e:
        if "Connection refused" in str(e):
            typer.echo(f"Error: No server running on port {port}", err=True)
            typer.echo(f"Start the server with: pare annotation launch -p {port}")
        else:
            typer.echo(f"Error: Could not connect to server: {e}", err=True)
        raise typer.Exit(code=1) from None
    except TimeoutError:
        typer.echo(f"Error: Server at localhost:{port} is not responding (timeout)", err=True)
        raise typer.Exit(code=1) from None
    except json.JSONDecodeError as e:
        typer.echo(f"Error: Server returned invalid response: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo("PARE Annotation Status")
    typer.echo("=" * 40)
    typer.echo(f"Total samples: {stats.get('total_samples', 'N/A')}")
    typer.echo(f"Complete: {stats.get('complete', 'N/A')}")
    typer.echo(f"In progress: {stats.get('in_progress', 'N/A')}")
    typer.echo(f"Not started: {stats.get('not_started', 'N/A')}")
    typer.echo(f"Total annotations: {stats.get('total_annotations', 'N/A')}")
    typer.echo(f"Unique annotators: {stats.get('unique_annotators', 'N/A')}")


@app.command()
def process(  # noqa: C901
    samples: Annotated[
        Path,
        typer.Option("--samples", help="Path to the samples parquet file"),
    ],
    annotations: Annotated[
        Path,
        typer.Option("--annotations", help="Path to the annotations CSV file"),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output CSV file for detailed results"),
    ] = None,
    n_annotators: Annotated[
        int,
        typer.Option("--n-annotators", "-n", help="Number of top annotators to include (by completion count)"),
    ] = 2,
    evaluations_file: Annotated[
        Path | None,
        typer.Option("--evaluations-file", help="Path to evaluation results parquet (from 'pare annotation evaluate')"),
    ] = None,
) -> None:
    """Process annotations and compute agreement metrics.

    Calculates comprehensive metrics for measuring alignment between the
    ML model (user agent) and multiple human annotators.

    When --evaluations-file is provided, computes metrics per user_model_id
    from the evaluation dataframe instead of from the original samples.

    Metrics computed:
    - Fleiss' Kappa (human-human baseline)
    - Majority vote metrics (accuracy, F1, precision, recall, Cohen's kappa)
    - Soft label alignment (cross-entropy, MAE)
    - Average pairwise Cohen's kappa (model vs each human)
    - Krippendorff's Alpha (model as k+1 rater)
    - Stratified analysis by consensus level
    """
    import polars as pl

    from pare.annotation.metrics import (
        compute_agreement_metrics,
        compute_agreement_metrics_ternary,
        compute_per_model_agreement_metrics,
        compute_per_model_agreement_metrics_ternary,
    )

    samples_file = ensure_extension(samples.resolve(), ".parquet")
    annotations_file = ensure_extension(annotations.resolve(), ".csv")

    if not samples_file.exists():
        typer.echo(f"Error: No samples found at {samples_file}", err=True)
        raise typer.Exit(code=1)

    if not annotations_file.exists():
        typer.echo(f"Error: No annotations found at {annotations_file}", err=True)
        raise typer.Exit(code=1)

    # Load data
    samples_df = pl.read_parquet(samples_file)
    annotations_df = pl.read_csv(annotations_file)

    if len(annotations_df) == 0:
        typer.echo("Error: No annotations recorded yet.", err=True)
        raise typer.Exit(code=1)

    typer.echo("Processing Annotations")
    typer.echo("=" * 60)

    # Detect schema: ternary if user_agent_decision is string type
    is_ternary = samples_df["user_agent_decision"].dtype == pl.String

    # Compute metrics
    # Per-model metrics from evaluation dataframe
    if evaluations_file is not None:
        if not evaluations_file.exists():
            typer.echo(f"Error: Evaluations file not found: {evaluations_file}", err=True)
            raise typer.Exit(code=1)

        evaluations_df = pl.read_parquet(evaluations_file)

        if is_ternary:
            per_model_metrics = compute_per_model_agreement_metrics_ternary(
                evaluations_df, annotations_df, n_annotators
            )
        else:
            per_model_metrics = compute_per_model_agreement_metrics(evaluations_df, annotations_df, n_annotators)

        typer.echo("\n=== Per-Model Agreement Metrics ===")
        for model_id, model_metrics in per_model_metrics.items():
            typer.echo(f"\n--- {model_id} ---")
            typer.echo(f"  Samples: {model_metrics['n_samples']}")
            mv = model_metrics.get("majority_vote_metrics", {})
            typer.echo(f"  Accuracy: {mv.get('accuracy', 'N/A')}")
            typer.echo(f"  Cohen's Kappa: {mv.get('cohens_kappa', 'N/A')}")
            if "f1" in mv:
                typer.echo(f"  F1: {mv.get('f1', 'N/A')}")
        return

    if is_ternary:
        metrics = compute_agreement_metrics_ternary(samples_df, annotations_df, n_annotators)
    else:
        metrics = compute_agreement_metrics(samples_df, annotations_df, n_annotators)

    # Display basic counts
    typer.echo(f"\nSamples analyzed: {metrics['n_samples']}")
    typer.echo(f"Total annotations: {metrics['n_annotations']}")
    typer.echo(f"Annotators included: {metrics['n_annotators']}")

    # Human-human agreement (baseline)
    typer.echo("\n" + "-" * 60)
    typer.echo("HUMAN-HUMAN AGREEMENT (Baseline)")
    typer.echo("-" * 60)

    if metrics["fleiss_kappa_humans"] is not None:
        typer.echo(
            f"Fleiss' Kappa: {metrics['fleiss_kappa_humans']:.3f} ({_interpret_kappa(metrics['fleiss_kappa_humans'])})"
        )
    else:
        typer.echo("Fleiss' Kappa: N/A (need >= 2 annotators)")

    # Model vs Majority Vote
    typer.echo("\n" + "-" * 60)
    typer.echo("MODEL vs MAJORITY VOTE")
    typer.echo("-" * 60)

    mv = metrics["majority_vote_metrics"]
    if mv["accuracy"] is not None:
        typer.echo(f"Accuracy:       {mv['accuracy']:.1%}")
    if mv.get("precision") is not None:
        typer.echo(f"Precision:      {mv['precision']:.1%}")
    if mv.get("recall") is not None:
        typer.echo(f"Recall:         {mv['recall']:.1%}")
    if mv.get("f1") is not None:
        typer.echo(f"F1 Score:       {mv['f1']:.3f}")
    if mv["cohens_kappa"] is not None:
        typer.echo(f"Cohen's Kappa:  {mv['cohens_kappa']:.3f} ({_interpret_kappa(mv['cohens_kappa'])})")

    # Soft Label Alignment (binary only)
    if not is_ternary and "soft_label_metrics" in metrics:
        typer.echo("\n" + "-" * 60)
        typer.echo("SOFT LABEL ALIGNMENT")
        typer.echo("-" * 60)

        sl = metrics["soft_label_metrics"]
        if sl["cross_entropy"] is not None:
            typer.echo(f"Cross-Entropy:  {sl['cross_entropy']:.3f}")
        if sl["mae"] is not None:
            typer.echo(f"MAE:            {sl['mae']:.3f}")

    # Average Pairwise Model-Human Kappa
    typer.echo("\n" + "-" * 60)
    typer.echo("MODEL-HUMAN PAIRWISE AGREEMENT")
    typer.echo("-" * 60)

    pw = metrics["avg_pairwise_model_human_kappa"]
    if pw["mean"] is not None:
        typer.echo(f"Avg Cohen's Kappa: {pw['mean']:.3f} (+/- {pw['std']:.3f})")
        typer.echo(f"  Interpretation: {_interpret_kappa(pw['mean'])}")

    # Krippendorff's Alpha and Fleiss' Kappa with Model
    typer.echo("\n" + "-" * 60)
    typer.echo("OVERALL AGREEMENT (Model as k+1 Rater)")
    typer.echo("-" * 60)

    if metrics["krippendorff_alpha_with_model"] is not None:
        typer.echo(
            f"Krippendorff's Alpha: {metrics['krippendorff_alpha_with_model']:.3f} ({_interpret_kappa(metrics['krippendorff_alpha_with_model'])})"
        )

    if metrics["fleiss_kappa_with_model"] is not None:
        typer.echo(
            f"Fleiss' Kappa:        {metrics['fleiss_kappa_with_model']:.3f} ({_interpret_kappa(metrics['fleiss_kappa_with_model'])})"
        )

    # Stratified Analysis (binary only)
    if not is_ternary and "stratified_analysis" in metrics:
        typer.echo("\n" + "-" * 60)
        typer.echo("STRATIFIED ANALYSIS (by Human Consensus)")
        typer.echo("-" * 60)

        strat = metrics["stratified_analysis"]
        if strat:
            typer.echo(f"  {'Consensus Level':<16} {'Samples':>8} {'Accuracy':>10} {'Model Accept':>13}")
            for level in ["unanimous", "high_agreement", "low_agreement"]:
                if level in strat:
                    s = strat[level]
                    acc_str = f"{s['accuracy']:.1%}" if s["accuracy"] is not None else "N/A"
                    mar_str = f"{s['model_accept_rate']:.1%}" if s["model_accept_rate"] is not None else "N/A"
                    typer.echo(f"  {level:<16} {s['n_samples']:>8} {acc_str:>10} {mar_str:>13}")

    # Decision Distribution
    typer.echo("\n" + "-" * 60)
    typer.echo("DECISION DISTRIBUTION")
    typer.echo("-" * 60)

    if is_ternary and "category_rates" in metrics:
        cat_rates = metrics["category_rates"]
        if "human" in cat_rates:
            typer.echo("Human rates:")
            typer.echo(f"  Accept:         {cat_rates['human']['accept']:.1%}")
            typer.echo(f"  Reject:         {cat_rates['human']['reject']:.1%}")
            typer.echo(f"  Gather Context: {cat_rates['human']['gather_context']:.1%}")
        if "model" in cat_rates:
            typer.echo("\nModel rates:")
            typer.echo(f"  Accept:         {cat_rates['model']['accept']:.1%}")
            typer.echo(f"  Reject:         {cat_rates['model']['reject']:.1%}")
            typer.echo(f"  Gather Context: {cat_rates['model']['gather_context']:.1%}")
    else:
        typer.echo(f"Human accept rate:  {metrics.get('human_accept_rate', 0):.1%}")
        typer.echo(f"Model accept rate:  {metrics.get('agent_accept_rate', 0):.1%}")

    # Per-annotator breakdown
    if metrics["per_annotator_stats"]:
        typer.echo("\nPer-annotator statistics:")
        if is_ternary:
            typer.echo(
                f"  {'Annotator':<12} {'Count':>6} {'Accept%':>8} {'Reject%':>8} {'Gather%':>8} {'Kappa w/Model':>14}"
            )
            for annotator_id, stats in sorted(metrics["per_annotator_stats"].items(), key=lambda x: -x[1]["count"]):
                kappa_str = f"{stats['kappa_with_model']:.3f}" if stats["kappa_with_model"] is not None else "N/A"
                typer.echo(
                    f"  {annotator_id[:10]:<12} {stats['count']:>6} "
                    f"{stats['accept_rate']:>7.1%} {stats['reject_rate']:>7.1%} "
                    f"{stats['gather_context_rate']:>7.1%} {kappa_str:>14}"
                )
        else:
            typer.echo(f"  {'Annotator':<12} {'Count':>6} {'Accept%':>8} {'Kappa w/Model':>14}")
            for annotator_id, stats in sorted(metrics["per_annotator_stats"].items(), key=lambda x: -x[1]["count"]):
                kappa_str = f"{stats['kappa_with_model']:.3f}" if stats["kappa_with_model"] is not None else "N/A"
                typer.echo(
                    f"  {annotator_id[:10]:<12} {stats['count']:>6} {stats['accept_rate']:>7.1%} {kappa_str:>14}"
                )

    # Save detailed results if output specified
    if output:
        _save_detailed_results(output, samples_df, annotations_df, metrics)
        typer.echo(f"\nDetailed results saved to: {output}")


def _interpret_kappa(kappa: float) -> str:
    """Interpret Kappa value according to Landis & Koch (1977)."""
    if kappa < 0:
        return "Poor"
    elif kappa < 0.20:
        return "Slight"
    elif kappa < 0.40:
        return "Fair"
    elif kappa < 0.60:
        return "Moderate"
    elif kappa < 0.80:
        return "Substantial"
    else:
        return "Almost Perfect"


def _save_detailed_results(
    output_path: Path,
    samples_df: pl.DataFrame,
    annotations_df: pl.DataFrame,
    metrics: dict[str, Any],
) -> None:
    """Save detailed per-sample results to CSV."""
    import polars as pl

    # Join annotations with samples to get user_agent_decision
    joined = annotations_df.join(
        samples_df.select(["sample_id", "user_agent_decision", "scenario_id"]),
        on="sample_id",
        how="left",
    )

    # Aggregate per sample
    sample_stats = (
        joined.group_by("sample_id")
        .agg([
            pl.col("scenario_id").first().alias("scenario_id"),
            pl.col("user_agent_decision").first().alias("user_agent_decision"),
            pl.col("human_decision").sum().alias("human_accepts"),
            pl.col("human_decision").count().alias("n_annotations"),
            (pl.col("human_decision") == pl.col("user_agent_decision")).sum().alias("agrees_with_agent"),
        ])
        .with_columns([
            (pl.col("human_accepts") / pl.col("n_annotations")).alias("human_accept_rate"),
            (pl.col("agrees_with_agent") / pl.col("n_annotations")).alias("agent_agreement_rate"),
            (pl.col("human_accepts") > pl.col("n_annotations") / 2).alias("majority_accepts"),
        ])
    )

    sample_stats.write_csv(output_path)
    logger.info(f"Saved detailed results to {output_path}")


@app.command()
def evaluate(
    samples: Annotated[
        Path,
        typer.Option("--samples", help="Path to the samples parquet file"),
    ],
    user_models: Annotated[
        str,
        typer.Option("--user-models", help="Comma-separated user model aliases to evaluate"),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o", help="Output path for evaluation results (extension auto-corrected to .parquet)"
        ),
    ],
    target_models: Annotated[
        str | None,
        typer.Option("--target-models", help="Comma-separated proactive model IDs to filter samples"),
    ] = None,
    runs: Annotated[
        int,
        typer.Option("--runs", "-r", help="Number of runs per (sample, user_model) pair"),
    ] = 3,
    smoke_test: Annotated[
        bool,
        typer.Option("--smoke-test", help="Only process 10 samples for quick validation"),
    ] = False,
    max_workers: Annotated[
        int | None,
        typer.Option(
            "--max-workers", help="Number of parallel worker threads (default: min(len(user_models), cpu_count))"
        ),
    ] = None,
) -> None:
    """Evaluate user models on sampled decision points via single-shot queries.

    Loads llm_input from samples parquet, fires it at each candidate user model,
    and records ternary decisions (accept/reject/gather_context). Outputs both
    raw evaluation results and aggregated soft labels.
    """
    import polars as pl

    from pare.annotation.evaluator import (
        aggregate_evaluations,
        evaluate_samples_ternary,
        print_evaluation_summary_ternary,
    )
    from pare.cli.utils import MODELS_MAP

    # Load samples
    samples_file = ensure_extension(samples.resolve(), ".parquet")
    if not samples_file.exists():
        typer.echo(f"Error: No samples found at {samples_file}", err=True)
        raise typer.Exit(code=1)

    samples_df = pl.read_parquet(samples_file)

    # Parse arguments
    user_model_list = [m.strip() for m in user_models.split(",") if m.strip()]
    target_model_list = [m.strip() for m in target_models.split(",") if m.strip()] if target_models else None

    # Validate user models exist in MODELS_MAP
    for model in user_model_list:
        if model not in MODELS_MAP:
            typer.echo(f"Warning: {model} not found in MODELS_MAP, will use as raw model name with openai provider")

    typer.echo(f"Evaluating {len(user_model_list)} user models on {len(samples_df)} samples")
    typer.echo(f"User models: {user_model_list}")
    if target_model_list:
        typer.echo(f"Filtering to proactive models: {target_model_list}")
    typer.echo(f"Runs per sample: {runs}")
    if max_workers:
        typer.echo(f"Max workers: {max_workers}")
    if smoke_test:
        typer.echo("Smoke test mode: using only 10 samples")

    # Run evaluation
    eval_df = evaluate_samples_ternary(
        samples_df=samples_df,
        user_models=user_model_list,
        models_map=MODELS_MAP,
        runs=runs,
        target_models=target_model_list,
        smoke_test=smoke_test,
        max_workers=max_workers,
    )

    # Save raw results
    output_file = ensure_extension(output.resolve(), ".parquet")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    eval_df.write_parquet(output_file)
    typer.echo(f"\nRaw results saved to {output_file}")

    # Aggregate and save soft labels
    aggregated_df = aggregate_evaluations(eval_df)
    aggregated_file = output_file.with_name(output_file.stem + "_aggregated.parquet")
    aggregated_df.write_parquet(aggregated_file)
    typer.echo(f"Aggregated results saved to {aggregated_file}")

    # Print summary
    print_evaluation_summary_ternary(eval_df, original_samples_df=samples_df)
