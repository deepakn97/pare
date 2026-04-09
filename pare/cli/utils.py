from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import litellm
from are.simulation.agents.are_simulation_agent_config import (
    LLMEngineConfig,
)
from are.simulation.scenario_runner import ScenarioRunnerConfig
from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig
from are.simulation.types import ToolAugmentationConfig
from litellm.exceptions import (
    APIConnectionError as LiteLLMAPIConnectionError,
)
from litellm.exceptions import (
    InternalServerError as LiteLLMInternalServerError,
)
from litellm.exceptions import (
    RateLimitError as LiteLLMRateLimitError,
)
from litellm.exceptions import (
    ServiceUnavailableError as LiteLLMServiceUnavailableError,
)
from litellm.exceptions import (
    Timeout as LiteLLMTimeout,
)
from pytz import timezone

from pare.logging_config import configure_logging, suppress_noisy_are_loggers, suppress_noisy_loggers
from pare.scenario_runner import TwoAgentScenarioRunner
from pare.scenarios.utils.registry import registry
from pare.scenarios.utils.scenario_expander import default_weight_per_app_class

if TYPE_CHECKING:
    from are.simulation.scenarios.scenario import ScenarioValidationResult


logger = logging.getLogger(__name__)


class LLMProbeError(Exception):
    """Raised when an LLM endpoint probe fails with a non-retryable error or times out."""


# Transient errors that indicate the endpoint may become available.
_RETRYABLE_PROBE_ERRORS = (
    LiteLLMServiceUnavailableError,
    LiteLLMAPIConnectionError,
    LiteLLMRateLimitError,
    LiteLLMInternalServerError,
    LiteLLMTimeout,
)


def probe_llm_endpoint(
    engine_config: LLMEngineConfig,
    *,
    timeout_seconds: int = 600,
    poll_interval: int = 30,
) -> None:
    """Probe an LLM endpoint to verify it is ready to serve requests.

    Sends a minimal completion request. Retries on transient errors (503, connection,
    rate-limit) with a fixed poll interval until the endpoint responds or the timeout
    is exceeded.

    Args:
        engine_config: The LLM engine configuration to probe.
        timeout_seconds: Maximum seconds to wait for the endpoint to become ready.
        poll_interval: Seconds between retry attempts.

    Raises:
        LLMProbeError: If the endpoint fails with a non-retryable error (e.g. auth)
            or does not become ready within the timeout.
    """
    model_name = engine_config.model_name
    provider = engine_config.provider
    endpoint = engine_config.endpoint

    logger.info(f"Probing LLM: {model_name} (provider: {provider}, endpoint: {endpoint})")
    start_time = time.monotonic()

    while True:
        try:
            litellm.completion(
                model=model_name,
                custom_llm_provider=provider if provider != "local" else None,
                messages=[{"role": "user", "content": "Reply with only the word ok"}],
                api_base=endpoint,
                num_retries=0,
            )
        except _RETRYABLE_PROBE_ERRORS as e:
            elapsed = time.monotonic() - start_time
            if elapsed + poll_interval > timeout_seconds:
                raise LLMProbeError(
                    f"LLM endpoint {model_name} not ready after {timeout_seconds}s. Last error: {type(e).__name__}: {e}"
                ) from e
            logger.warning(
                f"LLM {model_name} returned {type(e).__name__}, retrying in {poll_interval}s ({elapsed:.0f}s elapsed)"
            )
            time.sleep(poll_interval)

        except Exception as e:
            raise LLMProbeError(f"LLM {model_name} failed with non-retryable error: {type(e).__name__}: {e}") from e
        else:
            elapsed = time.monotonic() - start_time
            logger.info(f"LLM ready: {model_name} ({elapsed:.1f}s)")
            return


MODELS_MAP = {
    "gpt-4o-mini": {"model_name": "gpt-4o-mini", "provider": "openai"},
    "gpt-4o": {"model_name": "gpt-4o", "provider": "openai"},
    "gpt-5-mini": {"model_name": "gpt-5-mini", "provider": "openai"},
    "gpt-5": {"model_name": "gpt-5", "provider": "openai"},
    "gpt-oss-20b": {"model_name": "accounts/fireworks/models/gpt-oss-20b", "provider": "fireworks_ai"},
    "gpt-oss-120b": {"model_name": "accounts/fireworks/models/gpt-oss-120b", "provider": "fireworks_ai"},
    # ANTHROPIC Models
    "claude-4.5-sonnet": {"model_name": "claude-sonnet-4-5-20250929", "provider": "anthropic"},
    "claude-4.5-haiku": {"model_name": "claude-haiku-4-5-20251001", "provider": "anthropic"},
    "claude-4.5-opus": {"model_name": "claude-opus-4-5-20251101", "provider": "anthropic"},
    # BEDROCK Models
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
    "minimax-2.5": {"model_name": "accounts/fireworks/models/minimax-m2p5", "provider": "fireworks_ai"},
    # GEMINI Models
    "gemini-3-pro": {"model_name": "gemini/gemini-3-pro-preview", "provider": "gemini"},
    "gemini-3-flash": {"model_name": "gemini/gemini-3-flash-preview", "provider": "gemini"},
}


def resolve_model_config(
    model: str,
    provider: str | None,
    endpoint: str | None,
) -> tuple[LLMEngineConfig, str]:
    """Resolve model parameters into an LLMEngineConfig and alias.

    Resolution order:
    1. If model is in MODELS_MAP, use its values as defaults for model_name, provider, endpoint.
    2. CLI provider/endpoint override MODELS_MAP values if provided.
    3. If provider is still None after resolution, raise ValueError.

    Alias is the MODELS_MAP key if matched, otherwise the last segment after '/' in model name.

    Args:
        model: Model name or MODELS_MAP alias.
        provider: Provider override (None to use MODELS_MAP or fail).
        endpoint: Endpoint override (None to use MODELS_MAP or omit).

    Returns:
        Tuple of (LLMEngineConfig, alias).

    Raises:
        ValueError: If provider cannot be resolved.
    """
    map_entry = MODELS_MAP.get(model)

    if map_entry:
        resolved_model = map_entry.get("model_name", model)
        resolved_provider = provider or map_entry.get("provider")
        resolved_endpoint = endpoint or map_entry.get("endpoint")
        alias = model
    else:
        resolved_model = model
        resolved_provider = provider
        resolved_endpoint = endpoint
        alias = model.rsplit("/", 1)[-1]

    if not resolved_provider:
        msg = f"Provider is required for model '{model}'. Use --<role>-provider or add the model to MODELS_MAP."
        raise ValueError(msg)

    engine_config = LLMEngineConfig(
        model_name=resolved_model,
        provider=resolved_provider,
        endpoint=resolved_endpoint,
    )
    return engine_config, alias


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
    """Configure logging for PARE."""
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
    user_model_endpoint: str | None = None,
    proactive_model: str = "gpt-4o-mini",
    proactive_model_provider: str = "openai",
    proactive_model_endpoint: str | None = None,
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
        user_model: LLM model name for the user agent.
        user_model_provider: Provider for user model.
        user_model_endpoint: Endpoint URL for user model (for locally hosted models).
        proactive_model: LLM model name for the proactive observe and execute agents.
        proactive_model_provider: Provider for proactive model.
        proactive_model_endpoint: Endpoint URL for proactive model (for locally hosted models).
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

    # Load the scenario using PARE registry
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

    # Create runner configuration
    runner_config = ScenarioRunnerConfig(
        user_engine_config=LLMEngineConfig(
            model_name=user_model,
            provider=user_model_provider,
            endpoint=user_model_endpoint,
        ),
        user_max_iterations=user_max_iterations,
        observe_engine_config=LLMEngineConfig(
            model_name=proactive_model,
            provider=proactive_model_provider,
            endpoint=proactive_model_endpoint,
        ),
        observe_max_iterations=observe_max_iterations,
        execute_engine_config=LLMEngineConfig(
            model_name=proactive_model,
            provider=proactive_model_provider,
            endpoint=proactive_model_endpoint,
        ),
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
