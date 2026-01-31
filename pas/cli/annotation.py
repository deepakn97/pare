"""Annotation CLI commands for human evaluation of proactive agent proposals."""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: TC003 - typer evaluates annotations at runtime
from typing import TYPE_CHECKING, Annotated, Any

if TYPE_CHECKING:
    import polars as pl

import typer

from pas.annotation.config import (
    get_annotations_dir,
    get_annotations_file,
    get_samples_file,
    reset_annotations_dir,
    set_annotations_dir,
)

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


@app.command()
def sample(
    traces_dir: Annotated[
        Path,
        typer.Option("--traces-dir", "-t", help="Path to the traces directory"),
    ],
    sample_size: Annotated[
        int,
        typer.Option("--sample-size", "-n", help="Number of samples to add"),
    ],
    seed: Annotated[
        int | None,
        typer.Option("--seed", "-s", help="Random seed for reproducibility"),
    ] = None,
) -> None:
    """Sample decision points from traces for annotation.

    Creates a balanced dataset of accept/reject decisions, prioritizing
    unique scenarios. Appends to existing samples if present.
    """
    from pas.annotation.sampler import load_existing_samples, sample_new_datapoints, save_samples

    # Resolve paths
    traces_dir = traces_dir.resolve()

    if not traces_dir.exists():
        typer.echo(f"Error: Traces directory not found: {traces_dir}", err=True)
        raise typer.Exit(code=1)

    # Show existing samples info
    existing_df = load_existing_samples()
    if existing_df is not None:
        existing_count = len(existing_df)
        existing_accepts = len(existing_df.filter(__import__("polars").col("user_agent_decision")))
        existing_rejects = existing_count - existing_accepts
        typer.echo(f"Existing samples: {existing_count} ({existing_accepts} accepts, {existing_rejects} rejects)")
    else:
        typer.echo("No existing samples found. Creating new sample set.")

    typer.echo(f"Sampling {sample_size} new datapoints from {traces_dir}...")
    if seed is not None:
        typer.echo(f"Using random seed: {seed}")

    try:
        samples = sample_new_datapoints(traces_dir, sample_size, seed)
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

    # Save samples
    samples_file = save_samples(samples)

    # Report statistics
    accepts = len([s for s in samples if s.user_agent_decision])
    rejects = len(samples) - accepts
    unique_scenarios = len({s.scenario_id for s in samples})

    typer.echo("\nSampling complete!")
    typer.echo(f"  New samples added: {len(samples)}")
    typer.echo(f"  Accepts: {accepts}")
    typer.echo(f"  Rejects: {rejects}")
    typer.echo(f"  Unique scenarios: {unique_scenarios}")
    typer.echo(f"\nSamples saved to: {samples_file}")


@app.command()
def launch(
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
    from pas.annotation.server import run_server

    data_dir = get_annotations_dir()
    samples_file = get_samples_file()

    if not samples_file.exists():
        typer.echo(f"Error: No samples found at {samples_file}", err=True)
        typer.echo("Run 'pas annotation sample' first to create samples.")
        raise typer.Exit(code=1)

    typer.echo("PAS Annotation Server")
    typer.echo("=" * 40)
    typer.echo(f"Data directory: {data_dir}")
    typer.echo(f"Samples file: {samples_file}")
    typer.echo(f"Annotators per sample: {annotators_per_sample}")
    typer.echo(f"Server URL: http://localhost:{port}")
    typer.echo("")
    typer.echo("For public access, use ngrok:")
    typer.echo(f"  ngrok http {port}")
    typer.echo("")
    typer.echo("Press Ctrl+C to stop the server.")
    typer.echo("=" * 40)

    try:
        run_server(data_dir, port, annotators_per_sample)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None
    except KeyboardInterrupt:
        typer.echo("\nServer stopped.")


@app.command()
def status() -> None:
    """Show annotation progress and statistics."""
    import polars as pl

    data_dir = get_annotations_dir()
    samples_file = get_samples_file()
    annotations_file = get_annotations_file()

    typer.echo("PAS Annotation Status")
    typer.echo("=" * 40)
    typer.echo(f"Data directory: {data_dir}")

    if not samples_file.exists():
        typer.echo("\nNo samples found. Run 'pas annotation sample' first.")
        return

    # Load samples
    samples_df = pl.read_parquet(samples_file)
    total_samples = len(samples_df)

    # Calculate balance
    accepts = len(samples_df.filter(pl.col("user_agent_decision")))
    rejects = total_samples - accepts
    accept_pct = (accepts / total_samples * 100) if total_samples > 0 else 0
    reject_pct = (rejects / total_samples * 100) if total_samples > 0 else 0

    typer.echo("\nSamples:")
    typer.echo(f"  Total: {total_samples}")
    typer.echo(f"  User agent accepts: {accepts} ({accept_pct:.1f}%)")
    typer.echo(f"  User agent rejects: {rejects} ({reject_pct:.1f}%)")

    # Load annotations if they exist
    if annotations_file.exists():
        try:
            annotations_df = pl.read_csv(annotations_file)
            total_annotations = len(annotations_df)

            if total_annotations > 0:
                # Count unique annotators
                unique_annotators = annotations_df["annotator_id"].n_unique()

                # Count annotations per sample
                sample_counts = annotations_df.group_by("sample_id").len()

                # Note: We don't have annotators_per_sample stored, so we estimate
                max_count = sample_counts["len"].max()
                complete = len(sample_counts.filter(pl.col("len") >= max_count)) if max_count else 0
                in_progress = len(sample_counts) - complete
                not_started = total_samples - len(sample_counts)

                typer.echo("\nAnnotations:")
                typer.echo(f"  Total: {total_annotations}")
                typer.echo(f"  Unique annotators: {unique_annotators}")

                typer.echo("\nProgress:")
                typer.echo(f"  Samples with annotations: {len(sample_counts)}")
                typer.echo(f"  Samples not started: {not_started}")

                # Human decision statistics
                human_accepts = len(annotations_df.filter(pl.col("human_decision")))
                human_rejects = total_annotations - human_accepts
                human_accept_pct = (human_accepts / total_annotations * 100) if total_annotations > 0 else 0

                typer.echo("\nHuman Decisions:")
                typer.echo(f"  Accepts: {human_accepts} ({human_accept_pct:.1f}%)")
                typer.echo(f"  Rejects: {human_rejects} ({100 - human_accept_pct:.1f}%)")

                # Agreement with user agent
                agreements = len(annotations_df.filter(pl.col("human_decision") == pl.col("user_agent_decision")))
                agreement_pct = (agreements / total_annotations * 100) if total_annotations > 0 else 0
                typer.echo(f"\nAgreement with user agent: {agreements}/{total_annotations} ({agreement_pct:.1f}%)")

            else:
                typer.echo("\nAnnotations: 0")
        except Exception as e:
            typer.echo(f"\nError reading annotations: {e}")
    else:
        typer.echo("\nAnnotations: 0 (file not created yet)")


@app.command("set-dir")
def set_dir(
    folder_path: Annotated[
        Path,
        typer.Argument(help="Path to the annotations directory"),
    ],
    create: Annotated[
        bool,
        typer.Option("--create", "-c", help="Create the directory if it doesn't exist"),
    ] = False,
) -> None:
    """Set the annotations directory path (persistent).

    This setting is saved to ~/.config/pas/config.json and persists across sessions.
    The PAS_ANNOTATIONS_DIR environment variable takes precedence over this setting.
    """
    import os

    try:
        set_annotations_dir(folder_path, create)
        typer.echo(f"Annotations directory set to: {folder_path.resolve()}")

        # Warn if environment variable is set
        if os.environ.get("PAS_ANNOTATIONS_DIR"):
            typer.echo(
                "\nNote: PAS_ANNOTATIONS_DIR environment variable is set and will take precedence "
                "over this config file setting."
            )
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        typer.echo("Use --create to create the directory automatically.")
        raise typer.Exit(code=1) from None
    except NotADirectoryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@app.command("reset-dir")
def reset_dir() -> None:
    """Reset annotations directory to default location.

    Removes the annotations_dir setting from the config file.
    """
    default_dir = reset_annotations_dir()
    typer.echo(f"Annotations directory reset to default: {default_dir}")


@app.command()
def invalidate(  # noqa: C901
    confirm: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
    samples_too: Annotated[
        bool,
        typer.Option("--samples", help="Also delete samples (requires re-sampling)"),
    ] = False,
) -> None:
    """Delete all annotations (and optionally samples).

    This is a destructive operation. All collected annotations will be
    permanently deleted.
    """
    annotations_file = get_annotations_file()
    samples_file = get_samples_file()

    if not annotations_file.exists() and not (samples_too and samples_file.exists()):
        typer.echo("Nothing to delete. No annotations or samples found.")
        return

    # Show what will be deleted
    typer.secho("\nWARNING: This action is irreversible!", fg=typer.colors.RED, bold=True)
    typer.echo("")

    if annotations_file.exists():
        import polars as pl

        try:
            annotations_df = pl.read_csv(annotations_file)
            n_annotations = len(annotations_df)
            n_annotators = annotations_df["annotator_id"].n_unique() if n_annotations > 0 else 0
            typer.secho(f"  Annotations to delete: {n_annotations}", fg=typer.colors.YELLOW)
            typer.secho(f"  From {n_annotators} unique annotators", fg=typer.colors.YELLOW)
        except Exception:
            typer.secho(f"  Annotations file: {annotations_file}", fg=typer.colors.YELLOW)
    else:
        typer.echo("  No annotations file found.")

    if samples_too and samples_file.exists():
        import polars as pl

        try:
            samples_df = pl.read_parquet(samples_file)
            typer.secho(f"  Samples to delete: {len(samples_df)}", fg=typer.colors.YELLOW)
        except Exception:
            typer.secho(f"  Samples file: {samples_file}", fg=typer.colors.YELLOW)

    typer.echo("")

    if not confirm:
        typer.secho(
            "Are you sure you want to delete all annotations" + (" and samples" if samples_too else "") + "?",
            fg=typer.colors.RED,
        )
        if not typer.confirm("Type 'y' to confirm"):
            typer.echo("Aborted.")
            raise typer.Exit(code=0)

    # Delete files
    deleted_annotations = False
    deleted_samples = False

    if annotations_file.exists():
        annotations_file.unlink()
        deleted_annotations = True
        typer.secho("Deleted annotations file.", fg=typer.colors.GREEN)

    if samples_too and samples_file.exists():
        samples_file.unlink()
        deleted_samples = True
        typer.secho("Deleted samples file.", fg=typer.colors.GREEN)

    if deleted_annotations or deleted_samples:
        typer.echo("\nDone. You may need to run 'pas annotation sample' to create new samples.")
    else:
        typer.echo("Nothing was deleted.")


@app.command()
def process(  # noqa: C901
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output CSV file for detailed results"),
    ] = None,
    n_annotators: Annotated[
        int,
        typer.Option("--n-annotators", "-n", help="Number of top annotators to include (by completion count)"),
    ] = 2,
) -> None:
    """Process annotations and compute agreement metrics.

    Calculates comprehensive metrics for measuring alignment between the
    ML model (user agent) and multiple human annotators.

    Metrics computed:
    - Fleiss' Kappa (human-human baseline)
    - Majority vote metrics (accuracy, F1, precision, recall, Cohen's kappa)
    - Soft label alignment (cross-entropy, MAE)
    - Average pairwise Cohen's kappa (model vs each human)
    - Krippendorff's Alpha (model as k+1 rater)
    - Stratified analysis by consensus level
    """
    import polars as pl

    from pas.annotation.metrics import compute_agreement_metrics

    samples_file = get_samples_file()
    annotations_file = get_annotations_file()

    if not samples_file.exists():
        typer.echo("Error: No samples found. Run 'pas annotation sample' first.", err=True)
        raise typer.Exit(code=1)

    if not annotations_file.exists():
        typer.echo("Error: No annotations found. Run 'pas annotation launch' to collect annotations.", err=True)
        raise typer.Exit(code=1)

    # Load data
    samples_df = pl.read_parquet(samples_file)
    annotations_df = pl.read_csv(annotations_file)

    if len(annotations_df) == 0:
        typer.echo("Error: No annotations recorded yet.", err=True)
        raise typer.Exit(code=1)

    typer.echo("Processing Annotations")
    typer.echo("=" * 60)

    # Compute metrics
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
    if mv["precision"] is not None:
        typer.echo(f"Precision:      {mv['precision']:.1%}")
    if mv["recall"] is not None:
        typer.echo(f"Recall:         {mv['recall']:.1%}")
    if mv["f1"] is not None:
        typer.echo(f"F1 Score:       {mv['f1']:.3f}")
    if mv["cohens_kappa"] is not None:
        typer.echo(f"Cohen's Kappa:  {mv['cohens_kappa']:.3f} ({_interpret_kappa(mv['cohens_kappa'])})")

    # Soft Label Alignment
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

    # Stratified Analysis
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

    typer.echo(f"Human accept rate:  {metrics['human_accept_rate']:.1%}")
    typer.echo(f"Model accept rate:  {metrics['agent_accept_rate']:.1%}")

    # Per-annotator breakdown
    if metrics["per_annotator_stats"]:
        typer.echo("\nPer-annotator statistics:")
        typer.echo(f"  {'Annotator':<12} {'Count':>6} {'Accept%':>8} {'Kappa w/Model':>14}")
        for annotator_id, stats in sorted(metrics["per_annotator_stats"].items(), key=lambda x: -x[1]["count"]):
            kappa_str = f"{stats['kappa_with_model']:.3f}" if stats["kappa_with_model"] is not None else "N/A"
            typer.echo(f"  {annotator_id[:10]:<12} {stats['count']:>6} {stats['accept_rate']:>7.1%} {kappa_str:>14}")

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
