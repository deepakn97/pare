"""Benchmark CLI command for running PARE experiments."""

from __future__ import annotations

import json
import logging
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import polars as pl
import typer
from typer_config import use_yaml_config

from pare.benchmark.report_stats import (
    generate_json_stats_report,
    generate_validation_report,
)
from pare.benchmark.scenario_executor import multiply_scenarios_iterator
from pare.benchmark.scenario_loader import (
    Split,
    load_scenario_ids_from_file,
    load_scenarios_by_split,
    load_scenarios_from_registry,
)
from pare.cli.utils import probe_llm_endpoint
from pare.logging_config import configure_logging, suppress_noisy_are_loggers, suppress_noisy_loggers
from pare.multi_scenario_runner import MultiScenarioRunner
from pare.scenarios.config import MultiScenarioRunnerConfig
from pare.scenarios.validation_result import PARE_RESULT_SCHEMA

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.utils.countable_iterator import CountableIterator

    from pare.scenarios import PAREScenario
    from pare.scenarios.validation_result import PAREMultiScenarioValidationResult

logger = logging.getLogger(__name__)


class ExecutorType(StrEnum):
    """Executor type for parallel scenario execution."""

    sequential = "sequential"
    thread = "thread"
    process = "process"


class ExportFormat(StrEnum):
    """Trace export format."""

    hf = "hf"
    lite = "lite"


app = typer.Typer(
    name="benchmark",
    help="Run PARE benchmark experiments",
)


def parse_scenarios_arg(scenarios_arg: str) -> list[str]:
    """Parse scenarios argument which can be a single ID, comma-separated IDs, or a file path.

    Args:
        scenarios_arg: Either a single scenario ID, comma-separated IDs, or path to a file.

    Returns:
        List of scenario IDs.
    """
    # Check if it's a file path
    path = Path(scenarios_arg)
    if path.exists() and path.is_file():
        return load_scenario_ids_from_file(path)

    # Otherwise, parse as comma-separated IDs
    return [s.strip() for s in scenarios_arg.split(",") if s.strip()]


def build_base_dir_name(
    experiment_name: str,
    split: str,
    user_model: str,
    max_turns: int,
    user_max_iterations: int,
    observe_max_iterations: int,
    execute_max_iterations: int,
) -> str:
    """Build parent directory name with fixed params.

    Pattern: {experiment_name}_{split}_user_{user_model}_mt_{max_turns}_umi_{user_max_iterations}_omi_{observe_max_iterations}_emi_{execute_max_iterations}

    Args:
        experiment_name: Name of the experiment.
        split: The benchmark split name (e.g., 'full', 'ablation', 'custom').
        user_model: User agent model name.
        max_turns: Maximum turns per scenario.
        user_max_iterations: Max iterations for user agent.
        observe_max_iterations: Max iterations for observe agent.
        execute_max_iterations: Max iterations for execute agent.

    Returns:
        Directory name string with fixed params.
    """
    return (
        f"{experiment_name}"
        f"_{split}"
        f"_user_{user_model}"
        f"_mt_{max_turns}"
        f"_umi_{user_max_iterations}"
        f"_omi_{observe_max_iterations}"
        f"_emi_{execute_max_iterations}"
    )


def build_config_descriptor(config: MultiScenarioRunnerConfig) -> str:
    """Build config descriptor string for result file naming.

    Pattern: obs_{observe_model}_exec_{execute_model}_enmi_{env_events_per_min}_es_{env_events_seed}_tfp_{tool_failure_prob}

    Uses model aliases for human-readable names (aliases are always set via model validator).

    Args:
        config: The MultiScenarioRunnerConfig to extract params from.

    Returns:
        Config descriptor string.
    """
    obs_model = config.observe_model_alias
    exec_model = config.execute_model_alias

    tfp = 0.0
    if config.tool_augmentation_config:
        tfp = getattr(config.tool_augmentation_config, "tool_failure_probability", 0.0)

    enmi = 0
    env_seed = 42  # Default seed
    if config.env_events_config:
        enmi = getattr(config.env_events_config, "num_env_events_per_minute", 0)
        env_seed = getattr(config.env_events_config, "env_events_seed", 42)

    return f"obs_{obs_model}_exec_{exec_model}_enmi_{enmi}_es_{env_seed}_tfp_{tfp}"


def save_json_result(result_path: Path, data: dict[str, object] | list[dict[str, object]]) -> None:
    """Save data to a JSON file.

    Args:
        result_path: Path to save the JSON file.
        data: Data to save (dict or list).
    """
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with open(result_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"Saved JSON to {result_path}")


def save_text_report(report_path: Path, content: str) -> None:
    """Save text content to a file.

    Args:
        report_path: Path to save the text file.
        content: Text content to save.
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(content)
    logger.info(f"Saved report to {report_path}")


def build_result_key(config: MultiScenarioRunnerConfig) -> tuple[str, str, float, int]:
    """Build the result key tuple for combine_results_to_dataframe.

    Uses model aliases for human-readable names (aliases are always set via model validator).

    Args:
        config: The MultiScenarioRunnerConfig to build key from.

    Returns:
        Tuple of (user_model, proactive_model, tool_failure_prob, env_events_per_min).
    """
    tfp = 0.0
    if config.tool_augmentation_config:
        tfp = getattr(config.tool_augmentation_config, "tool_failure_probability", 0.0)
    enmi = 0
    if config.env_events_config:
        enmi = getattr(config.env_events_config, "num_env_events_per_minute", 0)

    # Aliases are always set by the model validator, but we check for type safety
    user_alias = config.user_model_alias or config.user_engine_config.model_name
    observe_alias = config.observe_model_alias or config.observe_engine_config.model_name
    execute_alias = config.execute_model_alias or config.execute_engine_config.model_name

    return (
        user_alias,
        f"{observe_alias}_{execute_alias}",
        tfp,
        enmi,
    )


def run_single_config(
    config: MultiScenarioRunnerConfig,
    scenario_iterator_factory: Callable[[], CountableIterator[PAREScenario]],
    runs: int,
    split_name: str,
    base_dir_name: str,
    results_dir: Path,
    output_dir: Path | None,
) -> tuple[str, PAREMultiScenarioValidationResult]:
    """Run scenarios for a single configuration.

    Args:
        config: The MultiScenarioRunnerConfig for this run.
        scenario_iterator_factory: Factory function that returns a fresh scenario iterator.
        runs: Number of runs per scenario.
        split_name: The benchmark split name (for report generation).
        base_dir_name: Base directory name for results.
        results_dir: Directory for JSON result files.
        output_dir: Directory for trace exports (if exporting).

    Returns:
        Tuple of (config_descriptor, validation_result).
    """
    config_descriptor = build_config_descriptor(config)
    logger.info(f"Running config: {config_descriptor}")

    # Set output directory if exporting
    if config.export and output_dir:
        config.output_dir = str(output_dir / base_dir_name / config_descriptor)
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)

    # Get fresh scenario iterator from factory
    scenarios_iterator = scenario_iterator_factory()

    # Multiply scenarios for multiple runs
    if runs > 1:
        scenarios_iterator = multiply_scenarios_iterator(scenarios_iterator, runs)

    # Create runner and run scenarios
    runner = MultiScenarioRunner()
    result = runner.run_with_scenarios(config, scenarios_iterator)

    # Save individual result as JSON and text report
    config_results_dir = results_dir / base_dir_name
    save_json_result(config_results_dir / f"{config_descriptor}_result.json", result.to_polars().to_dicts())
    save_text_report(config_results_dir / f"{config_descriptor}_report.txt", result.description(split_name))

    return config_descriptor, result


def _print_config_result(
    config_key: tuple[str, str, float, int],
    config_result_obj: PAREMultiScenarioValidationResult,
    *,
    prefix: str = "  ",
) -> None:
    """Print summary stats for a single config result.

    Args:
        config_key: Tuple of (user_model, proactive_model, tfp, enmi).
        config_result_obj: Validation results for this config.
        prefix: String prefix for each output line.
    """
    _user_model, proactive_model, tfp, enmi = config_key
    result_df = config_result_obj.to_polars()
    total = len(result_df)
    success = result_df.filter(result_df["status"] == "success").height
    failed = result_df.filter(result_df["status"] == "failed").height
    exception_df = result_df.filter(result_df["has_exception"] == True)  # noqa: E712
    exceptions = exception_df.height

    noise_info = ""
    if tfp > 0:
        noise_info += f" tfp={tfp}"
    if enmi > 0:
        noise_info += f" epm={enmi}"

    typer.echo(
        f"{prefix}{proactive_model}{noise_info}: "
        f"{total} total | {success} success | {failed} failed | {exceptions} exceptions"
    )

    if exceptions > 0:
        exc_groups = (
            exception_df.group_by("exception_type")
            .agg(
                pl.col("exception_message").first().alias("sample_message"),
                pl.len().alias("count"),
            )
            .sort("count", descending=True)
        )
        for row in exc_groups.iter_rows(named=True):
            msg = row["sample_message"] or "no message"
            if len(msg) > 100:
                msg = msg[:100] + "..."
            typer.echo(f"{prefix}  [{row['exception_type']}] x{row['count']}: {msg}")


@app.command()
@use_yaml_config()
def run(
    # Scenario selection (mutually exclusive)
    scenarios: Annotated[
        str | None,
        typer.Option("--scenarios", "-s", help="Scenario IDs: single ID, comma-separated, or file path"),
    ] = None,
    split: Annotated[
        Split | None,
        typer.Option("--split", help="Benchmark split: full or ablation"),
    ] = None,
    # Observe model configuration
    observe_model: Annotated[
        str,
        typer.Option("--observe-model", "-om", help="Observe model name"),
    ] = "gpt-5",
    observe_provider: Annotated[
        str,
        typer.Option("--observe-provider", "-op", help="Observe model provider"),
    ] = "openai",
    observe_endpoint: Annotated[
        str | None,
        typer.Option("--observe-endpoint", "-oe", help="Observe model endpoint URL"),
    ] = None,
    # Execute model configuration
    execute_model: Annotated[
        str,
        typer.Option("--execute-model", "-em", help="Execute model name"),
    ] = "gpt-5",
    execute_provider: Annotated[
        str,
        typer.Option("--execute-provider", "-ep", help="Execute model provider"),
    ] = "openai",
    execute_endpoint: Annotated[
        str | None,
        typer.Option("--execute-endpoint", "-ee", help="Execute model endpoint URL"),
    ] = None,
    # User model configuration
    user_model: Annotated[
        str,
        typer.Option("--user-model", "-um", help="User agent model name"),
    ] = "gpt-5-mini",
    user_provider: Annotated[
        str,
        typer.Option("--user-provider", "-up", help="User agent model provider"),
    ] = "openai",
    user_endpoint: Annotated[
        str | None,
        typer.Option("--user-endpoint", "-ue", help="User agent model endpoint URL"),
    ] = None,
    # Iteration limits
    max_turns: Annotated[
        int,
        typer.Option("--max-turns", "-mt", help="Maximum turns per scenario"),
    ] = 10,
    observe_max_iterations: Annotated[
        int,
        typer.Option("--observe-max-iterations", "-omi", help="Max iterations for observe agent per turn"),
    ] = 1,
    execute_max_iterations: Annotated[
        int,
        typer.Option("--execute-max-iterations", "-emi", help="Max iterations for execute agent per turn"),
    ] = 1,
    user_max_iterations: Annotated[
        int,
        typer.Option("--user-max-iterations", "-umi", help="Max iterations for user agent per turn"),
    ] = 1,
    # Noise configuration
    tool_failure_probability: Annotated[
        float | None,
        typer.Option("--tool-failure-probability", "-tfp", help="Tool failure probability"),
    ] = None,
    env_events_per_min: Annotated[
        int | None,
        typer.Option("--env-events-per-min", "-epm", help="Environmental events per minute"),
    ] = None,
    env_events_seed: Annotated[
        int,
        typer.Option("--env-events-seed", help="Seed for env events generation"),
    ] = 42,
    # Execution configuration
    runs: Annotated[
        int,
        typer.Option("--runs", "-r", help="Number of runs per scenario"),
    ] = 1,
    max_concurrent: Annotated[
        int | None,
        typer.Option("--max-concurrent", "-c", help="Max concurrent scenarios (default: CPU count)"),
    ] = None,
    timeout: Annotated[
        int | None,
        typer.Option("--timeout", "-t", help="Timeout per scenario in seconds"),
    ] = None,
    executor_type: Annotated[
        ExecutorType,
        typer.Option("--executor-type", help="Executor: sequential, thread, or process"),
    ] = ExecutorType.thread,
    # Output configuration
    results_dir: Annotated[
        Path,
        typer.Option("--results-dir", help="Directory for JSON result files"),
    ] = Path("results"),
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Directory for trace exports"),
    ] = None,
    export: Annotated[
        bool,
        typer.Option("--export/--no-export", help="Export scenario traces"),
    ] = False,
    export_format: Annotated[
        ExportFormat,
        typer.Option("--export-format", help="Trace export format: hf or lite"),
    ] = ExportFormat.hf,
    experiment_name: Annotated[
        str,
        typer.Option("--experiment-name", "-n", help="Name for this experiment"),
    ] = "benchmark",
    # Misc
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level: DEBUG, INFO, WARNING, ERROR"),
    ] = "INFO",
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable result caching"),
    ] = False,
    oracle: Annotated[
        bool,
        typer.Option("--oracle", help="Run in oracle mode (no agents, execute oracle events only)"),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-l", help="Limit number of scenarios to load"),
    ] = None,
) -> None:
    """Run benchmark experiments with a single model configuration."""
    from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig
    from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig
    from are.simulation.types import ToolAugmentationConfig

    # Setup logging
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    configure_logging(level=numeric_level, use_tqdm=True)
    suppress_noisy_loggers()
    suppress_noisy_are_loggers()

    # Validate scenario selection: exactly one of --scenarios or --split must be provided
    if (scenarios is None) == (split is None):
        msg = (
            "--scenarios and --split are mutually exclusive"
            if scenarios is not None
            else "Either --scenarios or --split must be provided"
        )
        raise typer.BadParameter(msg)

    # Build scenario iterator factory
    if scenarios is not None:
        scenario_ids = parse_scenarios_arg(scenarios)
        split_name = "custom"

        def scenario_factory() -> CountableIterator[PAREScenario]:
            return load_scenarios_from_registry(scenario_ids=scenario_ids, limit=limit)

    elif split is not None:
        split_name = split.value

        def scenario_factory() -> CountableIterator[PAREScenario]:
            return load_scenarios_by_split(split, limit=limit)

    # Build engine configs with endpoint support
    observe_engine_config = LLMEngineConfig(
        model_name=observe_model,
        provider=observe_provider,
        endpoint=observe_endpoint,
    )
    execute_engine_config = LLMEngineConfig(
        model_name=execute_model,
        provider=execute_provider,
        endpoint=execute_endpoint,
    )
    user_engine_config = LLMEngineConfig(
        model_name=user_model,
        provider=user_provider,
        endpoint=user_endpoint,
    )

    # Build noise configs
    tool_augmentation_config = None
    if tool_failure_probability is not None and tool_failure_probability > 0:
        tool_augmentation_config = ToolAugmentationConfig(
            tool_failure_probability=tool_failure_probability,
        )

    env_events_config = None
    if env_events_per_min is not None and env_events_per_min > 0:
        env_events_config = EnvEventsConfig(
            num_env_events_per_minute=env_events_per_min,
            env_events_seed=env_events_seed,
        )

    # Build the full config
    config = MultiScenarioRunnerConfig(
        user_engine_config=user_engine_config,
        observe_engine_config=observe_engine_config,
        execute_engine_config=execute_engine_config,
        user_max_iterations=user_max_iterations,
        observe_max_iterations=observe_max_iterations,
        execute_max_iterations=execute_max_iterations,
        max_turns=max_turns,
        oracle=oracle,
        export=export,
        trace_dump_format=export_format,
        max_concurrent_scenarios=max_concurrent,
        timeout_seconds=timeout,
        executor_type=executor_type,
        log_level=log_level,
        enable_caching=not no_cache,
        experiment_name=experiment_name,
        use_custom_logger=False,
        tool_augmentation_config=tool_augmentation_config,
        env_events_config=env_events_config,
    )

    # Probe all unique LLM endpoints before running scenarios
    probed: set[tuple[str, str | None, str | None]] = set()
    for engine in (user_engine_config, observe_engine_config, execute_engine_config):
        engine_key = (engine.model_name, engine.provider, engine.endpoint)
        if engine_key not in probed:
            probe_llm_endpoint(engine)
            probed.add(engine_key)

    # Build directory names
    base_dir_name = build_base_dir_name(
        experiment_name=experiment_name,
        split=split_name,
        user_model=user_model,
        max_turns=max_turns,
        user_max_iterations=user_max_iterations,
        observe_max_iterations=observe_max_iterations,
        execute_max_iterations=execute_max_iterations,
    )

    # Run the config
    _config_descriptor, result = run_single_config(
        config=config,
        scenario_iterator_factory=scenario_factory,
        runs=runs,
        split_name=split_name,
        base_dir_name=base_dir_name,
        results_dir=results_dir,
        output_dir=output_dir,
    )

    # Print results
    config_key = build_result_key(config)
    typer.echo("\nBenchmark complete:")
    _print_config_result(config_key, result)


@app.command()
def report(
    results_dir: Annotated[
        Path,
        typer.Option("--results-dir", "-d", help="Path to results directory containing *_result.json files"),
    ],
    split: Annotated[
        str,
        typer.Option("--split", "-s", help="Dataset split name for report header"),
    ] = "full",
) -> None:
    """Generate combined report from existing per-model result files.

    Reads all *_result.json files from the given directory, combines them
    into a single DataFrame, and generates combined JSON and text reports.
    """
    results_dir = results_dir.resolve()
    if not results_dir.exists():
        typer.echo(f"Error: Results directory not found: {results_dir}", err=True)
        raise typer.Exit(code=1)

    # Find all individual result files (exclude combined_result.json)
    result_files = sorted(results_dir.glob("*_result.json"))
    result_files = [f for f in result_files if f.name != "combined_result.json"]

    if not result_files:
        typer.echo(f"Error: No result files found in {results_dir}", err=True)
        raise typer.Exit(code=1)

    # Load and combine
    dataframes = []
    for f in result_files:
        with open(f) as fh:
            data = json.load(fh)
        df = pl.DataFrame(data, schema=PARE_RESULT_SCHEMA)
        dataframes.append(df)
        typer.echo(f"  Loaded {f.name}: {len(df)} rows")

    combined_df = pl.concat(dataframes, how="vertical")
    typer.echo(f"\nCombined: {len(combined_df)} total rows from {len(result_files)} files")

    # Generate reports
    json_report = generate_json_stats_report(combined_df, split)
    text_report = generate_validation_report(combined_df, split)

    # Save
    save_json_result(results_dir / "combined_result.json", json_report)
    save_text_report(results_dir / "combined_report.txt", text_report)

    typer.echo(f"\nSaved combined_result.json and combined_report.txt to {results_dir}")
    typer.echo(f"\n{text_report}")
