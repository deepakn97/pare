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
from typing import TYPE_CHECKING

from are.simulation.agents.are_simulation_agent_config import (
    ARESimulationReactBaseAgentConfig,
    LLMEngineConfig,
)
from are.simulation.scenario_runner import ScenarioRunnerConfig
from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig
from are.simulation.types import ToolAugmentationConfig
from dotenv import load_dotenv

from pas.cli.utils import get_pst_time, setup_logging
from pas.scenario_runner import TwoAgentScenarioRunner
from pas.scenarios.utils.registry import registry
from pas.scenarios.utils.scenario_expander import default_weight_per_app_class

if TYPE_CHECKING:
    from are.simulation.scenarios.scenario import ScenarioValidationResult

# Scenarios are auto-registered via entry points in pyproject.toml
# See: [project.entry-points."pas.scenarios"]
# PAS uses its own standalone registry, completely independent of Meta-ARE

logger = logging.getLogger(__name__)

MODELS_MAP = {
    "gpt-4o-mini": {"model_name": "gpt-4o-mini", "provider": "openai"},
    "gpt-4o": {"model_name": "gpt-4o", "provider": "openai"},
    "gpt-5-mini": {"model_name": "gpt-5-mini", "provider": "openai"},
    "gpt-5": {"model_name": "gpt-5", "provider": "openai"},
    "gpt-oss-20b": {"model_name": "accounts/fireworks/models/gpt-oss-20b", "provider": "fireworks_ai"},
    "gpt-oss-120b": {"model_name": "accounts/fireworks/models/gpt-oss-120b", "provider": "fireworks_ai"},
    "claude-4.5-sonnet": {
        "model_name": "arn:aws:bedrock:us-east-1:288380904485:inference-profile/global.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "provider": "bedrock",
    },
    "claude-4.5-haiku": {
        "model_name": "arn:aws:bedrock:us-east-1:288380904485:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0",
        "provider": "bedrock",
    },
    "claude-4.5-opus": {
        "model_name": "arn:aws:bedrock:us-east-1:288380904485:inference-profile/us.anthropic.claude-opus-4-5-20251101-v1:0",
        "provider": "bedrock",
    },
    "llama-4-scout": {
        "model_name": "arn:aws:bedrock:us-east-1:288380904485:inference-profile/us.meta.llama4-scout-17b-instruct-v1:0",
        "provider": "bedrock",
    },
    "llama-4-maverick": {
        "model_name": "arn:aws:bedrock:us-east-1:288380904485:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0",
        "provider": "bedrock",
    },
    "llama-3.3-70B": {
        "model_name": "arn:aws:bedrock:us-east-1:288380904485:inference-profile/us.meta.llama3-3-70b-instruct-v1:0",
        "provider": "bedrock",
    },
    "llama-3.2-3b": {"model_name": "accounts/fireworks/models/llama-v3p2-3b-instruct", "provider": "fireworks_ai"},
    "gemma-4b-it": {"model_name": "accounts/fireworks/models/gemma-3-4b-it", "provider": "fireworks_ai"},
    "deepseek-v3.2": {"model_name": "accounts/fireworks/models/deepseek-v3p2", "provider": "fireworks_ai"},
    "qwen-3-4b-it": {"model_name": "accounts/fireworks/models/qwen3-4b-instruct-2507", "provider": "fireworks_ai"},
}


def run_demo(
    scenario_name: str = "email_notification",
    user_model: str = "gpt-4o-mini",
    user_model_provider: str = "openai",
    proactive_model: str = "gpt-4o-mini",
    proactive_model_provider: str = "openai",
    max_turns: int | None = 10,
    user_max_iterations: int = 1,
    observe_max_iterations: int = 10,
    execute_max_iterations: int = 10,
    traces_dir: str = "traces/demo",
    oracle_mode: bool = False,
    tool_failure_prob: float = 0.0,
    env_events_per_min: float = 0.0,
    env_events_seed: int = 42,
) -> ScenarioValidationResult:
    """Run the two-agent demo with the specified configuration.

    Args:
        scenario_name: Name of the registered scenario to run.
        user_model: LLM model to use for the user agent.
        user_model_provider: Provider for user model.
        proactive_model: LLM model to use for the proactive observe and execute agents.
        proactive_model_provider: Provider for proactive model.
        max_turns: Maximum number of agent turns to run (None for unlimited).
        user_max_iterations: Maximum number of iterations for the user agent.
        observe_max_iterations: Maximum number of iterations for the proactive observe agent.
        execute_max_iterations: Maximum number of iterations for the proactive execute agent.
        traces_dir: Directory to export traces to.
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
    logger.info(f"Traces directory: {traces_dir}")

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

    user_model_data = MODELS_MAP.get(user_model, {})
    proactive_model_data = MODELS_MAP.get(proactive_model, {})

    if user_model_data:
        user_model = user_model_data["model_name"]
        user_model_provider = user_model_data["provider"]
    else:
        logger.warning(
            f"Provided user model {user_model} not found in MODELS_MAP. Provider information may be incorrect."
        )
    if proactive_model_data:
        proactive_model = proactive_model_data["model_name"]
        proactive_model_provider = proactive_model_data["provider"]
    else:
        logger.warning(
            f"Provided proactive model {proactive_model} not found in MODELS_MAP. Provider information may be incorrect."
        )

    # Create agent configurations
    user_config = ARESimulationReactBaseAgentConfig(
        llm_engine_config=LLMEngineConfig(model_name=user_model, provider=user_model_provider),
        max_iterations=user_max_iterations,  # User agent typically takes fewer iterations per turn
        use_custom_logger=False,
    )

    proactive_observe_config = ARESimulationReactBaseAgentConfig(
        llm_engine_config=LLMEngineConfig(model_name=proactive_model, provider=proactive_model_provider),
        max_iterations=observe_max_iterations,  # Observation might need more reasoning
        use_custom_logger=False,
    )

    proactive_execute_config = ARESimulationReactBaseAgentConfig(
        llm_engine_config=LLMEngineConfig(model_name=proactive_model, provider=proactive_model_provider),
        max_iterations=execute_max_iterations,  # Execution might need multiple tool calls
        use_custom_logger=False,
    )

    # Create runner configuration
    output_path = Path(traces_dir) if traces_dir else Path("results/")
    output_path.mkdir(parents=True, exist_ok=True)

    # ! TODO: Support dumping agent traces as well, I think right now it is only dumping the user agent logs. We also don't use this config anywhere.
    runner_config = ScenarioRunnerConfig(
        output_dir=str(output_path),
        export=True,
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
        traces_dir=traces_dir,
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

    # Return the validation result so callers (e.g., the multi-step scenario
    # generator) can programmatically inspect success/failure instead of only
    # relying on logs.
    return validation_result


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
        help="Include logging from Meta-ARE Default Agent. LiteLLM, httpx, httpcore, openai, and Meta-ARE Noisy (environment, apps, validation.judge) loggers are still suppressed.",
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
    current_timestamp = get_pst_time()

    # Make log directory if it doesn't exist
    if args.log_to_file:
        log_dir = Path(args.log_dir) if Path(args.log_dir).is_absolute() else (Path.cwd() / args.log_dir)
        log_dir = (
            log_dir
            / f"{args.experiment_name}_user_{args.user_model}_proactive_{args.proactive_model}_mt_{args.max_turns}_umi_{args.user_max_iterations}_omi_{args.observe_max_iterations}_emi_{args.execute_max_iterations}_enmi_{args.env_events_per_min}_es_{args.env_events_seed}_tfp_{args.tool_failure_prob}"
            / f"{args.scenario}_{current_timestamp}"
        )
        print(f"Log directory: {log_dir}")
        log_dir.mkdir(parents=True, exist_ok=True)

    # Make traces directory if it doesn't exist
    traces_dir = Path(args.traces_dir) if Path(args.traces_dir).is_absolute() else (Path.cwd() / args.traces_dir)
    traces_dir = (
        traces_dir
        / f"{args.experiment_name}_user_{args.user_model}_proactive_{args.proactive_model}_mt_{args.max_turns}_umi_{args.user_max_iterations}_omi_{args.observe_max_iterations}_emi_{args.execute_max_iterations}_enmi_{args.env_events_per_min}_es_{args.env_events_seed}_tfp_{args.tool_failure_prob}"
    )
    print(f"Traces directory: {traces_dir}")
    traces_dir.mkdir(parents=True, exist_ok=True)

    # Setup logging
    setup_logging(
        scenario_id=args.scenario,
        level=args.log_level,
        log_dir=log_dir,
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
        user_model_provider=args.user_model_provider,
        proactive_model=args.proactive_model,
        proactive_model_provider=args.proactive_model_provider,
        max_turns=max_turns,
        user_max_iterations=args.user_max_iterations,
        observe_max_iterations=args.observe_max_iterations,
        execute_max_iterations=args.execute_max_iterations,
        traces_dir=traces_dir,
        oracle_mode=args.oracle,
        tool_failure_prob=args.tool_failure_prob,
        env_events_per_min=args.env_events_per_min,
        env_events_seed=args.env_events_seed,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
