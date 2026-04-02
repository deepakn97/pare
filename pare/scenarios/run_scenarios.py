"""Helpers and CLI entrypoint for running PARE scenarios."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from pare.cli.utils import get_pst_time, run_scenario_by_id, setup_logging
from pare.scenarios.utils.registry import registry

logger = logging.getLogger(__name__)


@dataclass
class ScenarioResult:
    """Result of running a single scenario."""

    scenario_name: str
    success: bool
    rationale: str | None = None
    exception: Exception | None = None
    duration_seconds: float = 0.0
    export_path: str | None = None


@dataclass
class ResultsSummary:
    """Summary of all scenario runs."""

    timestamp: str
    config: dict[str, Any] = field(default_factory=dict)
    total_scenarios: int = 0
    passed: int = 0
    failed: int = 0
    results: list[ScenarioResult] = field(default_factory=list)


def run_scenarios(
    scenario_names: list[str],
    user_model: str = "gpt-4o-mini",
    user_model_provider: str = "openai",
    proactive_model: str = "gpt-4o-mini",
    proactive_model_provider: str = "openai",
    max_turns: int | None = 10,
    user_max_iterations: int = 1,
    observe_max_iterations: int = 10,
    execute_max_iterations: int = 10,
    traces_dir: str = "traces",
    logs_dir: str = "logs",
    oracle_mode: bool = False,
    tool_failure_prob: float = 0.0,
    env_events_per_min: float = 0.0,
    env_events_seed: int = 42,
    stop_on_failure: bool = False,
    log_level: str = "WARNING",
) -> ResultsSummary:
    """Run specified scenarios and collect results."""
    logger.info(f"Running {len(scenario_names)} scenarios: {scenario_names}")

    summary = ResultsSummary(
        timestamp=datetime.now(UTC).isoformat(),
        config={
            "user_model": user_model,
            "user_model_provider": user_model_provider,
            "proactive_model": proactive_model,
            "proactive_model_provider": proactive_model_provider,
            "max_turns": max_turns,
            "user_max_iterations": user_max_iterations,
            "observe_max_iterations": observe_max_iterations,
            "execute_max_iterations": execute_max_iterations,
            "oracle_mode": oracle_mode,
            "tool_failure_prob": tool_failure_prob,
            "env_events_per_min": env_events_per_min,
            "env_events_seed": env_events_seed,
        },
        total_scenarios=len(scenario_names),
    )

    green = "\033[92m"
    reset = "\033[0m"

    for idx, scenario_name in enumerate(scenario_names, start=1):
        print("*" * 80)
        print(f"{green}Running Scenario {idx}/{len(scenario_names)}: {scenario_name}{reset}")
        print("*" * 80)

        current_logs_dir = Path(logs_dir) / scenario_name
        current_logs_dir.mkdir(parents=True, exist_ok=True)

        setup_logging(
            level=log_level,
            log_dir=current_logs_dir,
            use_tqdm=True,
            log_to_file=True,
            verbose=False,
        )

        start_time = time.time()
        result = ScenarioResult(scenario_name=scenario_name, success=False)

        try:
            validation_result = run_scenario_by_id(
                scenario_name=scenario_name,
                user_model=user_model,
                user_model_provider=user_model_provider,
                proactive_model=proactive_model,
                proactive_model_provider=proactive_model_provider,
                max_turns=max_turns,
                user_max_iterations=user_max_iterations,
                observe_max_iterations=observe_max_iterations,
                execute_max_iterations=execute_max_iterations,
                traces_dir=traces_dir,
                oracle_mode=oracle_mode,
                tool_failure_prob=tool_failure_prob,
                env_events_per_min=env_events_per_min,
                env_events_seed=env_events_seed,
            )

            result.success = validation_result.success
            result.rationale = validation_result.rationale
            result.export_path = validation_result.export_path

            if validation_result.exception:
                result.exception = validation_result.exception

        except Exception as exc:
            result.success = False
            result.exception = exc
            logger.exception(f"Exception while running scenario {scenario_name}")

        result.duration_seconds = time.time() - start_time

        summary.results.append(result)
        if result.success:
            summary.passed += 1
        else:
            summary.failed += 1

        status = "SUCCESS" if result.success else "FAILED"
        logger.info(f"Completed {scenario_name}: {status} (took {result.duration_seconds:.2f}s)")

        if stop_on_failure and not result.success:
            logger.warning(f"Stopping due to --stop-on-failure flag after {scenario_name}")
            break

    return summary


def save_results_summary(summary: ResultsSummary, output_path: Path) -> None:
    """Save results summary to JSON file."""
    summary_dict = asdict(summary)

    with open(output_path, "w") as file:
        json.dump(summary_dict, file, indent=2)

    logger.info(f"Results summary saved to: {output_path}")


def print_summary_table(summary: ResultsSummary) -> None:
    """Print a summary table to console."""
    print("\n" + "=" * 80)
    print("SCENARIO RUN SUMMARY")
    print("=" * 80)
    print(f"Total: {summary.total_scenarios} | Passed: {summary.passed} | Failed: {summary.failed}")
    print("-" * 80)
    print(f"{'Scenario':<40} {'Status':<10} {'Duration':<12} {'Rationale'}")
    print("-" * 80)

    for result in summary.results:
        status = "PARES" if result.success else "FAIL"
        duration = f"{result.duration_seconds:.2f}s"
        rationale = (
            result.rationale[:30] + "..."
            if result.rationale and len(result.rationale) > 30
            else (result.rationale or "")
        )
        print(f"{result.scenario_name:<40} {status:<10} {duration:<12} {rationale}")

    print("=" * 80)


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and run scenarios."""
    parser = argparse.ArgumentParser(
        description="Run PARE scenarios",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--scenarios",
        nargs="*",
        default=None,
        help="Scenario IDs to run. If not specified, runs all registered scenarios.",
    )
    parser.add_argument(
        "--user-model",
        default="gpt-4o-mini",
        help="LLM model for user agent",
    )
    parser.add_argument(
        "--user-model-provider",
        default="openai",
        help="Provider for user model",
    )
    parser.add_argument(
        "--proactive-model",
        default="gpt-4o-mini",
        help="LLM model for proactive agents (observe and execute)",
    )
    parser.add_argument(
        "--proactive-model-provider",
        default="openai",
        help="Provider for proactive model",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=10,
        help="Maximum number of agent turns (0 for unlimited)",
    )
    parser.add_argument(
        "--user-max-iterations",
        type=int,
        default=1,
        help="Maximum number of iterations for the user agent",
    )
    parser.add_argument(
        "--observe-max-iterations",
        type=int,
        default=10,
        help="Maximum number of iterations for the proactive observe agent",
    )
    parser.add_argument(
        "--execute-max-iterations",
        type=int,
        default=10,
        help="Maximum number of iterations for the proactive execute agent",
    )
    parser.add_argument(
        "--traces-dir",
        default="traces",
        help="Base directory to export traces to",
    )
    parser.add_argument(
        "--tool-failure-prob",
        type=float,
        default=0.0,
        help="Probability (0.0-1.0) that agent tools fail",
    )
    parser.add_argument(
        "--env-events-per-min",
        type=float,
        default=0.0,
        help="Average number of environmental noise events per minute",
    )
    parser.add_argument(
        "--env-events-seed",
        type=int,
        default=42,
        help="Random seed for reproducible noise generation",
    )
    parser.add_argument(
        "--oracle",
        action="store_true",
        help="Run in oracle mode (executes predefined oracle events without agents)",
    )
    parser.add_argument(
        "--experiment-name",
        default="experiment",
        help="Name of the experiment",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop execution on first scenario failure",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        help="Logging level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    args = parser.parse_args(argv)

    load_dotenv()

    all_scenarios = registry.get_all_scenarios()

    if args.scenarios is None or len(args.scenarios) == 0:
        scenario_names = sorted(all_scenarios.keys())
        print(f"Running all {len(scenario_names)} registered scenarios")
    else:
        if len(args.scenarios) == 1 and Path(args.scenarios[0]).is_file():
            scenarios_file = Path(args.scenarios[0])
            scenario_names = []
            with open(scenarios_file) as file:
                for line in file:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    scenario_names.append(line)
            print(f"Loaded {len(scenario_names)} scenarios from {scenarios_file}")
        else:
            scenario_names = args.scenarios

        for name in scenario_names:
            if name not in all_scenarios:
                print(f"Error: Unknown scenario '{name}'")
                print(f"Available scenarios: {sorted(all_scenarios.keys())}")
                sys.exit(1)
        print(f"Running {len(scenario_names)} scenarios: {scenario_names}")

    config_suffix = (
        f"{args.experiment_name}_user_{args.user_model}"
        f"_mt_{args.max_turns}_umi_{args.user_max_iterations}_omi_{args.observe_max_iterations}"
        f"_emi_{args.execute_max_iterations}_enmi_{args.env_events_per_min}_es_{args.env_events_seed}"
        f"_tfp_{args.tool_failure_prob}"
    )

    run_timestamp = get_pst_time()

    traces_base = Path(args.traces_dir) if Path(args.traces_dir).is_absolute() else (Path.cwd() / args.traces_dir)
    traces_dir = traces_base / config_suffix / f"{args.proactive_model}"
    traces_dir.mkdir(parents=True, exist_ok=True)
    print(f"Traces directory: {traces_dir}")

    logs_dir = Path("logs") / config_suffix / f"{args.proactive_model}_{run_timestamp}"
    logs_dir.mkdir(parents=True, exist_ok=True)
    print(f"Logs directory: {logs_dir}")

    max_turns = args.max_turns if args.max_turns > 0 else None

    summary = run_scenarios(
        scenario_names=scenario_names,
        user_model=args.user_model,
        user_model_provider=args.user_model_provider,
        proactive_model=args.proactive_model,
        proactive_model_provider=args.proactive_model_provider,
        max_turns=max_turns,
        user_max_iterations=args.user_max_iterations,
        observe_max_iterations=args.observe_max_iterations,
        execute_max_iterations=args.execute_max_iterations,
        traces_dir=str(traces_dir),
        logs_dir=str(logs_dir),
        oracle_mode=args.oracle,
        tool_failure_prob=args.tool_failure_prob,
        env_events_per_min=args.env_events_per_min,
        env_events_seed=args.env_events_seed,
        stop_on_failure=args.stop_on_failure,
        log_level=args.log_level,
    )

    results_path = traces_dir / "result_summary.json"
    save_results_summary(summary, results_path)
    print_summary_table(summary)


if __name__ == "__main__":  # pragma: no cover
    main()
