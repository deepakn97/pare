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

from dotenv import load_dotenv

from are.simulation.agents.are_simulation_agent_config import (
    ARESimulationReactBaseAgentConfig,
    LLMEngineConfig,
)
from are.simulation.scenario_runner import ScenarioRunnerConfig
from are.simulation.scenarios.utils.registry import registry
from are.simulation.cli.utils import setup_logging, suppress_noisy_loggers

from pas.scenario_runner import TwoAgentScenarioRunner

# Import scenarios to register them
import pas.scenarios.user_scenarios.very_basic_demo  # noqa: F401

logger = logging.getLogger(__name__)


# def setup_logging() -> None:
#     """Configure logging for the demo."""
#     logging.basicConfig(
#         level=logging.INFO,
#         format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     )
#     # Set specific loggers to appropriate levels
#     logging.getLogger("pas").setLevel(logging.DEBUG)
#     logging.getLogger("are.simulation").setLevel(logging.INFO)


def run_demo(
    scenario_name: str = "demo_simple_contact",
    user_model: str = "gpt-4o-mini",
    proactive_model: str = "gpt-4o-mini",
    max_turns: int | None = 10,
    output_dir: str | None = None,
) -> None:
    """Run the two-agent demo with the specified configuration.

    Args:
        scenario_name: Name of the registered scenario to run.
        user_model: LLM model to use for the user agent.
        proactive_model: LLM model to use for the proactive observe and execute agents.
        max_turns: Maximum number of agent turns to run (None for unlimited).
        output_dir: Directory to export traces to (None for default).
    """

    logger.info(f"Running two-agent demo with scenario: {scenario_name}")
    logger.info(f"User model: {user_model}")
    logger.info(f"Proactive model: {proactive_model}")
    logger.info(f"Max turns: {max_turns}")

    # Load the scenario
    scenario_class = registry.get_scenario(scenario_name)

    scenario = scenario_class()
    scenario.initialize(sandbox_dir=Path("sandbox"))

    # Create agent configurations
    user_config = ARESimulationReactBaseAgentConfig(
        llm_engine_config=LLMEngineConfig(model_name=user_model, provider="openai"),
        max_iterations=1,  # User agent typically takes fewer iterations per turn
    )

    proactive_observe_config = ARESimulationReactBaseAgentConfig(
        llm_engine_config=LLMEngineConfig(model_name=proactive_model, provider="openai"),
        max_iterations=1,  # Observation might need more reasoning
    )

    proactive_execute_config = ARESimulationReactBaseAgentConfig(
        llm_engine_config=LLMEngineConfig(model_name=proactive_model, provider="openai"),
        max_iterations=10,  # Execution might need multiple tool calls
    )

    # Create runner configuration
    output_path = Path(output_dir) if output_dir else Path("traces/pas")
    output_path.mkdir(parents=True, exist_ok=True)

    runner_config = ScenarioRunnerConfig(
        output_dir=str(output_path),
        dump_agent_logs=True,
        dump_world_logs=True,
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

    args = parser.parse_args(argv)

    # Setup logging
    setup_logging(level="INFO", use_tqdm=True)
    suppress_noisy_loggers()

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
    )


if __name__ == "__main__":  # pragma: no cover
    main()
