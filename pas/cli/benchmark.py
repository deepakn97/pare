"""Benchmark CLI command for running PAS experiments."""

from __future__ import annotations

import itertools
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from pas.benchmark.report_stats import (
    combine_results_to_dataframe,
    generate_json_stats_report,
    generate_validation_report,
)
from pas.benchmark.scenario_executor import multiply_scenarios_iterator
from pas.benchmark.scenario_loader import (
    Split,
    load_scenario_ids_from_file,
    load_scenarios_by_split,
    load_scenarios_from_registry,
)
from pas.cli.utils import MODELS_MAP
from pas.logging_config import configure_logging, suppress_noisy_are_loggers, suppress_noisy_loggers
from pas.multi_scenario_runner import MultiScenarioRunner
from pas.scenarios.config import MultiScenarioRunnerConfig

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.utils.countable_iterator import CountableIterator

    from pas.scenarios import PASScenario
    from pas.scenarios.validation_result import PASMultiScenarioValidationResult

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="benchmark",
    help="Run PAS benchmark experiments with config sweeps",
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


def parse_model_list(models: list[str] | None) -> list[str]:
    """Parse model list, expanding comma-separated values.

    Typer list options expect repeated flags (--model a --model b), but users
    often pass comma-separated values (--model a,b). This function handles both.

    Args:
        models: List of model names, possibly with comma-separated values.

    Returns:
        Flattened list of model names.
    """
    if models is None:
        return []

    result: list[str] = []
    for model in models:
        # Split by comma and strip whitespace
        result.extend(m.strip() for m in model.split(",") if m.strip())
    return result


def build_base_dir_name(
    experiment_name: str,
    split: str,
    user_model: str,
    max_turns: int,
    user_max_iterations: int,
    observe_max_iterations: int,
    execute_max_iterations: int,
) -> str:
    """Build parent directory name with fixed params (not swept).

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
    """Build swept params string from config (varies per config in sweep).

    Pattern: obs_{observe_model}_exec_{execute_model}_enmi_{env_events_per_min}_es_{env_events_seed}_tfp_{tool_failure_prob}

    Uses model aliases for human-readable names (aliases are always set via model validator).

    Args:
        config: The MultiScenarioRunnerConfig to extract swept params from.

    Returns:
        Config descriptor string with swept params only.
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


def generate_config_sweep(
    base_config: MultiScenarioRunnerConfig,
    observe_models: list[str],
    execute_models: list[str],
    tool_failure_probs: list[float] | None,
    env_events_per_min: list[int] | None,
    env_events_seed: int,
) -> list[MultiScenarioRunnerConfig]:
    """Generate all config combinations for the sweep.

    Model pairs are zipped (not crossed). Noise values are crossed with model pairs.

    Args:
        base_config: Base configuration to use as template.
        observe_models: List of observe model names.
        execute_models: List of execute model names.
        tool_failure_probs: List of tool failure probabilities (or None).
        env_events_per_min: List of env events per minute (or None).
        env_events_seed: Seed for env events.

    Returns:
        List of configurations for each sweep combination.

    Raises:
        ValueError: If observe/execute model lists have different lengths,
                    or if both noise params are provided.
    """
    from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig
    from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig
    from are.simulation.types import ToolAugmentationConfig

    # Validate model pairs
    if len(observe_models) != len(execute_models):
        raise ValueError(
            f"observe-model and execute-model lists must have same length. "
            f"Got {len(observe_models)} observe models and {len(execute_models)} execute models."
        )

    model_pairs = list(zip(observe_models, execute_models, strict=True))

    # Noise params are treated independently - tfp and epm each produce separate configs, never combined together.
    if tool_failure_probs and env_events_per_min:
        logger.info(
            "Both tool failure probability and env events per min provided; they will be treated as separate configurations in the sweep."
        )

    # Build noise configs
    # Note: When tfp=0 or epm=0, we use None instead of creating a config object
    # to ensure cache compatibility with runs that had no noise config specified.
    noise_configs: list[tuple[ToolAugmentationConfig | None, EnvEventsConfig | None]] = []

    if tool_failure_probs:
        for tfp in tool_failure_probs:
            # tfp=0 is equivalent to no tool augmentation - use None for cache compatibility
            tool_aug = ToolAugmentationConfig(tool_failure_probability=tfp) if tfp > 0 else None
            noise_configs.append((tool_aug, None))
    if env_events_per_min:
        for epm in env_events_per_min:
            # epm=0 is equivalent to no env events - use None for cache compatibility
            env_events = (
                EnvEventsConfig(num_env_events_per_minute=epm, env_events_seed=env_events_seed) if epm > 0 else None
            )
            noise_configs.append((None, env_events))
    if not noise_configs:
        # No noise - single config with no augmentation
        noise_configs.append((None, None))

    # Generate all combinations: model_pairs x noise_configs
    configs = []
    for (obs_model, exec_model), (tool_aug, env_events) in itertools.product(model_pairs, noise_configs):
        # Create a copy of base config and update swept params
        config_dict = base_config.model_dump()

        # Update model configs - get provider from MODELS_MAP
        obs_model_info = MODELS_MAP.get(obs_model, {"model_name": obs_model, "provider": "openai"})
        exec_model_info = MODELS_MAP.get(exec_model, {"model_name": exec_model, "provider": "openai"})

        config_dict["observe_engine_config"] = LLMEngineConfig(
            model_name=obs_model_info["model_name"],
            provider=obs_model_info["provider"],
            description="LLM configuration for the observe agent",
        )
        config_dict["execute_engine_config"] = LLMEngineConfig(
            model_name=exec_model_info["model_name"],
            provider=exec_model_info["provider"],
            description="LLM configuration for the execute agent",
        )

        # Set model aliases (human-readable names for caching and display)
        config_dict["observe_model_alias"] = obs_model
        config_dict["execute_model_alias"] = exec_model

        # Update noise configs
        config_dict["tool_augmentation_config"] = tool_aug
        config_dict["env_events_config"] = env_events

        configs.append(MultiScenarioRunnerConfig(**config_dict))

    return configs


def build_base_config(
    user_model_info: dict[str, str],
    user_model_alias: str,
    user_max_iterations: int,
    observe_max_iterations: int,
    execute_max_iterations: int,
    max_turns: int,
    export: bool,
    export_format: str,
    max_concurrent: int | None,
    timeout: int | None,
    executor_type: str,
    log_level: str,
    no_cache: bool,
    experiment_name: str,
    oracle: bool = False,
) -> MultiScenarioRunnerConfig:
    """Build the base MultiScenarioRunnerConfig with fixed parameters.

    Args:
        user_model_info: User model info dict with model_name and provider.
        user_model_alias: Human-readable alias for the user model.
        user_max_iterations: Max iterations for user agent per turn.
        observe_max_iterations: Max iterations for observe agent per turn.
        execute_max_iterations: Max iterations for execute agent per turn.
        max_turns: Maximum turns per scenario.
        export: Whether to export traces.
        export_format: Trace export format (hf or lite).
        max_concurrent: Max concurrent scenarios.
        timeout: Timeout per scenario in seconds.
        executor_type: Executor type (sequential, thread, process).
        log_level: Logging level.
        no_cache: Whether to disable caching.
        experiment_name: Name for this experiment.
        oracle: Whether to run in oracle mode (no agents).

    Returns:
        Base MultiScenarioRunnerConfig with fixed params.
    """
    from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig

    return MultiScenarioRunnerConfig(
        user_engine_config=LLMEngineConfig(
            model_name=user_model_info["model_name"],
            provider=user_model_info["provider"],
            description="LLM configuration for the user agent",
        ),
        user_model_alias=user_model_alias,
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
    )


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
    scenario_iterator_factory: Callable[[], CountableIterator[PASScenario]],
    runs: int,
    split_name: str,
    base_dir_name: str,
    results_dir: Path,
    output_dir: Path | None,
) -> tuple[str, PASMultiScenarioValidationResult]:
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


@app.command()
def sweep(
    # Scenario selection (mutually exclusive)
    scenarios: Annotated[
        str | None,
        typer.Option("--scenarios", "-s", help="Scenario IDs: single ID, comma-separated, or file path"),
    ] = None,
    split: Annotated[
        Split | None,
        typer.Option("--split", help="Benchmark split: full or ablation"),
    ] = None,
    # Model configuration
    observe_model: Annotated[
        list[str] | None,
        typer.Option("--observe-model", "-om", help="Observe model(s) for sweep (zipped with --execute-model)"),
    ] = None,
    execute_model: Annotated[
        list[str] | None,
        typer.Option("--execute-model", "-em", help="Execute model(s) for sweep (zipped with --observe-model)"),
    ] = None,
    user_model: Annotated[
        str,
        typer.Option("--user-model", "-um", help="User agent model"),
    ] = "gpt-5-mini",
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
    # Noise configuration (mutually exclusive)
    tool_failure_probability: Annotated[
        list[float] | None,
        typer.Option("--tool-failure-probability", "-tfp", help="Tool failure prob(s) for sweep"),
    ] = None,
    env_events_per_min: Annotated[
        list[int] | None,
        typer.Option("--env-events-per-min", "-epm", help="Env events per min for sweep"),
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
        str,
        typer.Option("--executor-type", help="Executor: sequential, thread, or process"),
    ] = "thread",
    # Output configuration
    results_dir: Annotated[
        Path,
        typer.Option("--results-dir", help="Directory for JSON result files"),
    ] = Path("results"),
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Directory for trace exports (requires --export)"),
    ] = None,
    export: Annotated[
        bool,
        typer.Option("--export/--no-export", help="Export scenario traces"),
    ] = False,
    export_format: Annotated[
        str,
        typer.Option("--export-format", help="Trace export format: hf or lite"),
    ] = "hf",
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
    """Run benchmark experiments with optional config sweeps."""
    # Setup logging
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    configure_logging(level=numeric_level, use_tqdm=True)
    suppress_noisy_loggers()
    suppress_noisy_are_loggers()

    # Parse model lists (supports both repeated flags and comma-separated values)
    observe_models = parse_model_list(observe_model) or ["gpt-5"]
    execute_models = parse_model_list(execute_model) or ["gpt-5"]

    # Validate mutually exclusive scenario selection
    if scenarios is not None and split is not None:
        raise typer.BadParameter("--scenarios and --split are mutually exclusive")

    # Build scenario iterator factory based on mutually exclusive options
    if scenarios is not None:
        scenario_ids = parse_scenarios_arg(scenarios)
        split_name = "custom"

        def scenario_factory() -> CountableIterator[PASScenario]:
            return load_scenarios_from_registry(scenario_ids=scenario_ids, limit=limit)

    elif split is not None:
        split_name = split.value
        split_for_factory = split  # Capture for closure

        def scenario_factory() -> CountableIterator[PASScenario]:
            return load_scenarios_by_split(split_for_factory, limit=limit)

    else:
        raise typer.BadParameter("Either --scenarios or --split must be provided")

    # Get user model info from MODELS_MAP
    user_model_info = MODELS_MAP.get(user_model, {"model_name": user_model, "provider": "openai"})

    # Build base config with fixed params
    base_config = build_base_config(
        user_model_info=user_model_info,
        user_model_alias=user_model,
        user_max_iterations=user_max_iterations,
        observe_max_iterations=observe_max_iterations,
        execute_max_iterations=execute_max_iterations,
        max_turns=max_turns,
        export=export,
        export_format=export_format,
        max_concurrent=max_concurrent,
        timeout=timeout,
        executor_type=executor_type,
        log_level=log_level,
        no_cache=no_cache,
        experiment_name=experiment_name,
        oracle=oracle,
    )

    # Generate config sweep
    configs = generate_config_sweep(
        base_config=base_config,
        observe_models=observe_models,
        execute_models=execute_models,
        tool_failure_probs=tool_failure_probability,
        env_events_per_min=env_events_per_min,
        env_events_seed=env_events_seed,
    )

    logger.info(f"Running {len(configs)} config combinations")

    # Build base directory name (same for all configs - uses fixed params)
    base_dir_name = build_base_dir_name(
        experiment_name=experiment_name,
        split=split_name,
        user_model=user_model,
        max_turns=max_turns,
        user_max_iterations=user_max_iterations,
        observe_max_iterations=observe_max_iterations,
        execute_max_iterations=execute_max_iterations,
    )

    # Run each config and collect results
    all_results: dict[tuple[str, str, float, int], PASMultiScenarioValidationResult] = {}
    for i, config in enumerate(configs, 1):
        logger.info(f"Running config {i}/{len(configs)}")
        _, result = run_single_config(
            config=config,
            scenario_iterator_factory=scenario_factory,
            runs=runs,
            split_name=split_name,
            base_dir_name=base_dir_name,
            results_dir=results_dir,
            output_dir=output_dir,
        )
        all_results[build_result_key(config)] = result

    # Combine results and generate reports
    combined_df = combine_results_to_dataframe(all_results)
    json_report = generate_json_stats_report(combined_df, split_name)
    text_report = generate_validation_report(combined_df, split_name)

    # Save reports
    save_json_result(results_dir / base_dir_name / "combined_result.json", json_report)
    save_text_report(results_dir / base_dir_name / "combined_report.txt", text_report)

    # Print summary
    typer.echo(f"\nBenchmark complete: {len(configs)} configs")
    for config_result in json_report.get("per_config_results", []):
        typer.echo(f"  {config_result['proactive_model']}: {config_result['success_rate']:.1f}% success")
