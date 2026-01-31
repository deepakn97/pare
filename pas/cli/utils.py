from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from are.simulation.agents.are_simulation_agent_config import (
    LLMEngineConfig,
)
from are.simulation.scenario_runner import ScenarioRunnerConfig
from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig
from are.simulation.types import ToolAugmentationConfig
from pytz import timezone

from pas.logging_config import configure_logging, suppress_noisy_are_loggers, suppress_noisy_loggers
from pas.scenario_runner import TwoAgentScenarioRunner
from pas.scenarios.utils.registry import registry
from pas.scenarios.utils.scenario_expander import default_weight_per_app_class

if TYPE_CHECKING:
    from are.simulation.scenarios.scenario import ScenarioValidationResult


logger = logging.getLogger(__name__)

MODELS_MAP = {
    "gpt-4o-mini": {"model_name": "gpt-4o-mini", "provider": "openai"},
    "gpt-4o": {"model_name": "gpt-4o", "provider": "openai"},
    "gpt-5-mini": {"model_name": "gpt-5-mini", "provider": "openai"},
    "gpt-5": {"model_name": "gpt-5", "provider": "openai"},
    "gpt-oss-20b": {"model_name": "accounts/fireworks/models/gpt-oss-20b", "provider": "fireworks_ai"},
    "gpt-oss-120b": {"model_name": "accounts/fireworks/models/gpt-oss-120b", "provider": "fireworks_ai"},
    # BEDROCK Models
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
    # FIREWORKS Models
    "deepseek-v3.2": {"model_name": "accounts/fireworks/models/deepseek-v3p2", "provider": "fireworks_ai"},
    "qwen-3-8B-base": {"model_name": "accounts/fireworks/models/qwen3-8b", "provider": "fireworks_ai"},
    # These models do not support serverless so we use a autoscaled deployment.
    "llama-3.2-3b-it": {
        "model_name": "accounts/eric-lab/deployments/zxezvdmp",
        "provider": "fireworks_ai",
    },
    "gemma-3-4b-it": {
        "model_name": "accounts/eric-lab/deployments/pmewm76x",
        "provider": "fireworks_ai",
    },
    "qwen-3-4b-it": {
        "model_name": "accounts/eric-lab/deployments/y4tn93dp",
        "provider": "fireworks_ai",
    },
    "ministral-3-3b-it": {"model_name": "accounts/eric-lab/deployments/ncvfom3m", "provider": "fireworks_ai"},
}


def get_pst_time() -> str:
    """Get the current time in PST."""
    date_format = "%Y%m%d_%H%M%S"
    date = datetime.now(tz=UTC)
    date = date.astimezone(timezone("US/Pacific"))
    return date.strftime(date_format)


def setup_logging(
    level: str = "INFO",
    log_dir: str | Path = "logs",
    use_tqdm: bool = True,
    log_to_file: bool = False,
    verbose: bool = False,
) -> None:
    """Configure logging for PAS."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise TypeError(f"Invalid log level: {level}")

    if isinstance(log_dir, str):
        log_dir = Path(log_dir)

    # Configure logging with the specified level
    configure_logging(level=numeric_level, use_tqdm=use_tqdm, log_dir=log_dir)
    suppress_noisy_loggers()
    if not verbose:
        suppress_noisy_are_loggers()


def run_scenario_by_id(
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

    # Create runner configuration
    runner_config = ScenarioRunnerConfig(
        user_engine_config=LLMEngineConfig(model_name=user_model, provider=user_model_provider),
        user_max_iterations=user_max_iterations,
        observe_engine_config=LLMEngineConfig(model_name=proactive_model, provider=proactive_model_provider),
        observe_max_iterations=observe_max_iterations,
        execute_engine_config=LLMEngineConfig(model_name=proactive_model, provider=proactive_model_provider),
        execute_max_iterations=execute_max_iterations,
        max_turns=max_turns,
        oracle=oracle_mode,
        output_dir=traces_dir,
        export=True,
        use_custom_logger=False,
    )

    # Create and run the scenario runner
    runner = TwoAgentScenarioRunner()

    logger.info("Starting scenario execution...")
    validation_result = runner.run(runner_config, scenario)

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
