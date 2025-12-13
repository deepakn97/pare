"""Demo script for running two-agent proactive system scenarios.

This script demonstrates running a scenario with UserAgent and ProactiveAgent
using the TwoAgentScenarioRunner. It shows manual BaseAgent creation with
pre-step configuration for notification handling.

Usage:
    uv run python -m pas.scripts.run_two_agent_demo

Environment:
    Requires OPENAI_API_KEY environment variable (loaded via .env file).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from are.simulation.agents.are_simulation_agent_config import (
    ARESimulationReactBaseAgentConfig,
    LLMEngineConfig,
)
from are.simulation.scenario_runner import ScenarioRunnerConfig
from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig
from are.simulation.types import ToolAugmentationConfig
from dotenv import load_dotenv

from pas.cli.utils import setup_logging
from pas.scenario_runner import TwoAgentScenarioRunner
from pas.scenarios.utils.registry import registry
from pas.scenarios.utils.scenario_expander import default_weight_per_app_class

# Scenarios are auto-registered via entry points in pyproject.toml
# See: [project.entry-points."pas.scenarios"]
# PAS uses its own standalone registry, completely independent of Meta-ARE

logger = logging.getLogger(__name__)


def run_demo(
    scenario_name: str = "email_notification",
    user_model: str = "gpt-4o-mini",
    proactive_model: str = "gpt-4o-mini",
    max_turns: int | None = 10,
    output_dir: str | None = None,
    oracle_mode: bool = False,
    tool_failure_prob: float = 0.0,
    env_events_per_min: float = 0.0,
    env_events_seed: int = 42,
) -> None:
    """Run the two-agent demo with the specified configuration.

    Args:
        scenario_name: Name of the registered scenario to run.
        user_model: LLM model to use for the user agent.
        proactive_model: LLM model to use for the proactive observe and execute agents.
        max_turns: Maximum number of agent turns to run (None for unlimited).
        output_dir: Directory to export traces to (None for default).
        oracle_mode: Whether to run in oracle mode (executes OracleEvents without agents).
        tool_failure_prob: Probability (0.0-1.0) that agent tools fail.
        env_events_per_min: Average number of environmental noise events per minute.
        env_events_seed: Random seed for reproducible noise generation.
    """
    logger.info(f"Running two-agent demo with scenario: {scenario_name}")
    logger.info(f"User model: {user_model}")
    logger.info(f"Proactive model: {proactive_model}")
    logger.info(f"Max turns: {max_turns}")
    logger.info(f"Oracle mode: {oracle_mode}")
    logger.info(f"Tool failure probability: {tool_failure_prob}")
    logger.info(f"Environmental noise events per minute: {env_events_per_min}")
    logger.info(f"Environmental noise seed: {env_events_seed}")

    # Load the scenario using PAS registry
    scenario_class = registry.get_scenario(scenario_name)

    scenario = scenario_class()

    # Configure tool failure probability if requested
    if tool_failure_prob > 0:
        scenario.tool_augmentation_config = ToolAugmentationConfig(
            tool_failure_probability=tool_failure_prob,
            apply_tool_name_augmentation=False,
            apply_tool_description_augmentation=False,
        )

    if env_events_per_min > 0:
        scenario.env_events_config = EnvEventsConfig(
            num_env_events_per_minute=int(env_events_per_min),
            env_events_seed=env_events_seed,
            weight_per_app_class=default_weight_per_app_class(),
        )

    scenario.initialize(sandbox_dir=Path("sandbox"))

    # Create agent configurations
    user_config = ARESimulationReactBaseAgentConfig(
        llm_engine_config=LLMEngineConfig(model_name=user_model, provider="openai"),
        max_iterations=1,  # User agent typically takes fewer iterations per turn
        use_custom_logger=False,
    )

    proactive_observe_config = ARESimulationReactBaseAgentConfig(
        llm_engine_config=LLMEngineConfig(model_name=proactive_model, provider="openai"),
        max_iterations=10,  # Observation might need more reasoning
        use_custom_logger=False,
    )

    proactive_execute_config = ARESimulationReactBaseAgentConfig(
        llm_engine_config=LLMEngineConfig(model_name=proactive_model, provider="openai"),
        max_iterations=20,  # Execution might need multiple tool calls
        use_custom_logger=False,
    )

    # Create runner configuration
    output_path = Path(output_dir) if output_dir else Path("results/")
    output_path.mkdir(parents=True, exist_ok=True)

    # ! TODO: Support dumping agent traces as well, I think right now it is only dumping the user agent logs. We also don't use this config anywhere.
    runner_config = ScenarioRunnerConfig(
        output_dir=str(output_path),
        dump_agent_logs=True,
        dump_world_logs=True,
        use_custom_logger=False,
    )

    # Create and run the scenario runner
    runner = TwoAgentScenarioRunner()

    logger.info("Starting scenario execution...")
    validation_result = runner.run_pas_scenario(
        scenario=scenario,
        user_config=user_config,
        proactive_observe_config=proactive_observe_config,
        proactive_execute_config=proactive_execute_config,
        max_turns=max_turns,
        oracle_mode=oracle_mode,
    )

    # Display results
    logger.info("=" * 80)
    logger.info("SCENARIO EXECUTION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Validation: {'SUCCESS' if validation_result.success else 'FAILED'}")

    if validation_result.rationale:
        logger.info(f"Rationale: {validation_result.rationale}")

    if validation_result.exception:
        logger.error(f"Exception: {validation_result.exception}")

    if validation_result.export_path:
        logger.info(f"Trace exported to: {validation_result.export_path}")

    logger.info("=" * 80)


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and run the demo.

    Args:
        argv: Command-line arguments (None to use sys.argv).
    """
    parser = argparse.ArgumentParser(
        description="Run two-agent proactive system demo",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--scenario",
        default="demo_simple_contact",
        help="Name of the registered scenario to run",
    )
    parser.add_argument(
        "--user-model",
        default="gpt-4o-mini",
        help="LLM model for user agent",
    )
    parser.add_argument(
        "--proactive-model",
        default="gpt-4o-mini",
        help="LLM model for proactive agents (observe and execute)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=10,
        help="Maximum number of agent turns (0 for unlimited)",
    )
    parser.add_argument(
        "--output-dir",
        default="traces/pas",
        help="Directory to export traces to",
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
    # Logging Configuration
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level",
    )
    parser.add_argument(
        "--use-tqdm",
        action="store_true",
        help="Use tqdm for progress bars",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include logging from Meta-ARE. LiteLLM, httpx, httpcore, openai loggers are still suppressed.",
    )
    parser.add_argument(
        "--log-dir",
        default="logs",
        help="Directory to log to",
    )
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Log to file",
    )
    parser.add_argument(
        "--experiment-name",
        default="demo",
        help="Name of the experiment",
    )

    args = parser.parse_args(argv)

    # Setup logging
    setup_logging(
        scenario_id=args.scenario,
        level=args.log_level,
        log_dir=args.log_dir,
        experiment_name=args.experiment_name,
        use_tqdm=args.use_tqdm,
        log_to_file=args.log_to_file,
        verbose=args.verbose,
    )

    # Load environment variables
    load_dotenv()

    # Convert max_turns of 0 to None (unlimited)
    max_turns = args.max_turns if args.max_turns > 0 else None

    # Run the demo
    run_demo(
        scenario_name=args.scenario,
        user_model=args.user_model,
        proactive_model=args.proactive_model,
        max_turns=max_turns,
        output_dir=args.output_dir,
        oracle_mode=args.oracle,
        tool_failure_prob=args.tool_failure_prob,
        env_events_per_min=args.env_events_per_min,
        env_events_seed=args.env_events_seed,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
