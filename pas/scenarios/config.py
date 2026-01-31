from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig
from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig  # noqa: TC002
from are.simulation.types import ToolAugmentationConfig  # noqa: TC002
from pydantic import BaseModel, Field, model_validator

MAX_SCENARIO_DURATION = 600  # 10 minutes


class ScenarioRunnerConfig(BaseModel):
    """Configuration for running a single PAS scenario."""

    # User Agent LLM Configuration (default: gpt-5-mini)
    user_engine_config: LLMEngineConfig = Field(
        default_factory=lambda: LLMEngineConfig(
            model_name="gpt-5-mini", provider="openai", description="LLM configuration for the user agent"
        )
    )

    # Maximum number of iterations the user agent can take per turn (default: 1)
    user_max_iterations: int | None = 1

    # Agent architecture type (Default: "observe-execute")
    agent_type: str = "observe-execute"

    # User Agent Type (Default: "default")
    user_type: str = "default"

    # Proactive Observe Agent LLM configuration (default: gpt-5)
    observe_engine_config: LLMEngineConfig = Field(
        default_factory=lambda: LLMEngineConfig(
            model_name="gpt-5", provider="openai", description="LLM configuration for the observe agent"
        )
    )

    # Maximum number of iterations the observe agent can take per turn (default: 1)
    observe_max_iterations: int | None = 1

    # Proactive Execute Agent LLM configuration (default: gpt-5)
    execute_engine_config: LLMEngineConfig = Field(
        default_factory=lambda: LLMEngineConfig(
            model_name="gpt-5", provider="openai", description="LLM configuration for the execute agent"
        )
    )

    # Maximum number of iterations the execute agent can take per turn (default: 1)
    execute_max_iterations: int | None = 1

    # Flag indicating whether to run the scenarios in Oracle Mode where oracle events (i.e. user defined agent events) are ran. (default: False)
    oracle: bool = False

    # Maximum number of turns of the conversation between the user and the agent. (default: 1)
    max_turns: int | None = 10

    # Flag indicating whether to export traces to a JSON file (default: False)
    export: bool = False

    # Directory to output the scenario states, traces and logs (default: None)
    output_dir: str | None = None

    # Toggles scenario JSON export format -- must be one of "hf" or "lite" (default: "hf")
    trace_dump_format: str = "hf"

    # Whether to use the custom logger in the agent (default: True)
    use_custom_logger: bool = True

    # Simulated generation time mode (default: "measured")
    simulated_generation_time_mode: str = "measured"

    # Tool augmentation configuration for noise injection
    tool_augmentation_config: ToolAugmentationConfig | None = None

    # Environment events configuration for noise injection
    env_events_config: EnvEventsConfig | None = None

    # ! TODO: Judge mode is not fully supported yet
    # Whether to run only the judge for scenarios.
    judge_only: bool = False

    # Judge engine configuration
    judge_engine_config: LLMEngineConfig | None = None

    # Maximum scenario duration in seconds (default: 600)
    max_scenario_duration: int = MAX_SCENARIO_DURATION

    # Human-readable model aliases (used for caching, display, results)
    # These are the canonical identifiers - deployment paths may change but aliases stay consistent
    user_model_alias: str | None = None
    observe_model_alias: str | None = None
    execute_model_alias: str | None = None

    @model_validator(mode="after")
    def fill_model_aliases(self) -> ScenarioRunnerConfig:
        """Fill in model aliases from engine configs if not explicitly set."""
        if self.user_model_alias is None:
            self.user_model_alias = self.user_engine_config.model_name
        if self.observe_model_alias is None:
            self.observe_model_alias = self.observe_engine_config.model_name
        if self.execute_model_alias is None:
            self.execute_model_alias = self.execute_engine_config.model_name
        return self

    def get_config_hash(self) -> str:
        """Generate a hash of the relevant config parameters that affect scenario execution.

        Excludes parameters that only affect:
        - Parallel execution (max_concurrent_scenarios, timeout_seconds, executor_type)
        - Logging (log_level, log_to_file, logs_dir, use_custom_logger)
        - Output location (output_dir, export, trace_dump_format)
        - Caching meta-config (enable_caching)
        - Engine configs (replaced by model aliases for consistent caching)

        Uses model aliases as canonical identifiers. Aliases are always set via
        the model validator (filled from engine configs if not explicitly provided).

        This enables cache reuse across experiments with different output directories
        and when model deployments change but the logical model is the same.
        """
        exclude_fields = {
            # Parallel execution
            "max_concurrent_scenarios",
            "timeout_seconds",
            "executor_type",
            # Logging
            "log_level",
            "log_to_file",
            "logs_dir",
            "use_custom_logger",
            "experiment_name",
            # Output location
            "output_dir",
            "export",
            "trace_dump_format",
            # Caching meta-config
            "enable_caching",
            # Engine configs (we use aliases instead for consistent caching)
            "user_engine_config",
            "observe_engine_config",
            "execute_engine_config",
            "judge_engine_config",
        }

        # Use pydantic's model_dump with exclude parameter, then serialize to JSON
        # Model aliases are included and always set via the model validator
        config_dict = self.model_dump(exclude=exclude_fields)
        config_str = json.dumps(config_dict, sort_keys=True, default=str)
        return hashlib.md5(config_str.encode()).hexdigest()[:8]  # noqa: S324


class MultiScenarioRunnerConfig(ScenarioRunnerConfig):
    """Configuration for running multiple PAS scenarios in parallel."""

    # Maximum number of concurrent scenarios to run. If not specified, automatically sets based on the number of CPUs.
    max_concurrent_scenarios: int | None = None

    # Timeout for individual scenarios in seconds. If not specified, no timeout is applied.
    timeout_seconds: int | None = None

    # Type of executor to use for running scenarios, options: "sequential", "thread", "process"
    executor_type: str = "thread"

    # Logging Level to use for the runner and worker threads
    log_level: str = "INFO"

    # Whether to log to file
    log_to_file: bool = True

    # Directory for logs files. This is parent level logs directory.
    logs_dir: str = "logs"

    # Enable scenario result caching to skip re-running identical scenarios
    enable_caching: bool = True

    # Experiment name for organizing logs and outputs
    experiment_name: str = "default"

    @model_validator(mode="after")
    def maybe_build_logs_dir(self) -> MultiScenarioRunnerConfig:
        """Maybe build the full logs directory after validation."""
        if self.log_to_file and self.executor_type == "thread":
            import warnings

            warnings.warn(
                "log_to_file is True but executor_type is 'thread' - skipping log directory build", stacklevel=2
            )
            return self
        self._build_logs_dir_internal()
        return self

    def _build_logs_dir_internal(self) -> None:
        """Build the full logs directory based on experiment name.

        Structure: {logs_dir}/{experiment_name}_{config_params}/{proactive_model}_{timestamp}
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # build config suffix from relevant params - use aliases for human-readable names
        config_suffix = f"{self.experiment_name}_user_{self.user_type}_{self.user_model_alias}_proactive_{self.agent_type}_mt_{self.max_turns}_umi_{self.user_max_iterations}_ome_{self.observe_max_iterations}_exe_{self.execute_max_iterations}"

        # Add noise params if set
        if self.tool_augmentation_config is not None:
            tfp = getattr(self.tool_augmentation_config, "tool_failure_probability", 0.0)
            config_suffix += f"_tfp_{tfp}"

        if self.env_events_config is not None:
            enmi = getattr(self.env_events_config, "num_env_events_per_min", 0.0)
            config_suffix += f"_enmi_{enmi}"

        # ! TODO: Make it general, get the proactive model identifier from registry and should depend on agent_type
        # Proactive model identifier - use aliases for human-readable names
        proactive_model = f"obs_{self.observe_model_alias}_exec_{self.execute_model_alias}"

        # Build full path
        base_dir = Path(self.logs_dir)
        full_path = base_dir / f"{config_suffix}" / f"{proactive_model}_{timestamp}"
        self.logs_dir = str(full_path)

    def build_logs_dir(self, experiment_name: str | None = None) -> None:
        """Explicitly build the full logs directory path with a new experiment name. Should be called before running scenarios.

        Args:
            experiment_name: The experiment name to use. If None, uses the existing experiment_name in the config.
        """
        if self.log_to_file and self.executor_type == "thread":
            import warnings

            warnings.warn(
                "log_to_file is True but executor_type is 'thread' - skipping log directory build", stacklevel=2
            )
            return
        if experiment_name is not None:
            self.experiment_name = experiment_name
        self._build_logs_dir_internal()
