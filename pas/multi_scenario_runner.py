"""Multi-scenario runner for PAS benchmark execution."""

from __future__ import annotations

import concurrent.futures
import contextlib
import errno
import gc
import itertools
import logging
import multiprocessing
import os
import shutil
import signal
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Never

from are.simulation.utils.streaming_utils import stream_pool
from tqdm import tqdm

from pas.scenario_runner import TwoAgentScenarioRunner
from pas.scenarios.config import MultiScenarioRunnerConfig, ScenarioRunnerConfig
from pas.scenarios.validation_result import PASMultiScenarioValidationResult, PASScenarioValidationResult

if TYPE_CHECKING:
    from are.simulation.utils.countable_iterator import CountableIterator

    from pas.agents.agent_builder import ProactiveAgentBuilder, UserAgentBuilder
    from pas.agents.agent_config_builder import ProactiveAgentConfigBuilder, UserAgentConfigBuilder
    from pas.scenarios.scenario import PASScenario

logger = logging.getLogger(__name__)


class ScenarioTimeoutError(Exception):
    """Scenario exectution timed out."""

    pass


RETRYABLE_ERRNOS = {errno.EMFILE, errno.ENFILE, errno.ENOMEM}
MAX_RETRIES = 2


def _is_retryable_error(
    error: Exception | None,
    result: PASScenarioValidationResult | None,
) -> bool:
    """Check if a failure is caused by a transient OS resource error.

    Args:
        error: Exception from stream_pool error path (thrown by worker).
        result: Validation result that may contain a wrapped exception.

    Returns:
        True if the error is a retryable OS resource error.
    """
    exc = error or (result.exception if result else None)
    if exc is None:
        return False
    return isinstance(exc, OSError) and getattr(exc, "errno", None) in RETRYABLE_ERRNOS


def _create_scenario_runner_config(
    config: MultiScenarioRunnerConfig,
    scenario: PASScenario,
) -> ScenarioRunnerConfig:
    """Create a ScenarioRunnerConfig from a MultiScenarioRunnerConfig.

    Args:
        config: The multi-scenario runner config.
        scenario: The scenario (used for scenario-specific overrides like nb_turns).

    Returns:
        A ScenarioRunnerConfig for running a single scenario.
    """
    # Fields that are specific to MultiScenarioRunnerConfig (not in base)
    multi_only_fields = {
        "max_concurrent_scenarios",
        "timeout_seconds",
        "executor_type",
        "log_level",
        "log_to_file",
        "logs_dir",
        "experiment_name",
        "enable_caching",
    }

    # Get all fields from multi-config, excluding multi-scenario specific ones
    base_config_dict = config.model_dump(exclude=multi_only_fields)

    # Create ScenarioRunnerConfig from the filtered dict
    runner_config = ScenarioRunnerConfig(**base_config_dict)

    # Override with scenario-specific settings if present
    if hasattr(scenario, "nb_turns") and scenario.nb_turns is not None:
        runner_config.max_turns = scenario.nb_turns

    return runner_config


def process_scenario(
    scenario: PASScenario | str,
    config: MultiScenarioRunnerConfig,
    user_agent_config_builder: UserAgentConfigBuilder | None,
    user_agent_builder: UserAgentBuilder | None,
    proactive_agent_config_builder: ProactiveAgentConfigBuilder | None,
    proactive_agent_builder: ProactiveAgentBuilder | None,
) -> PASScenarioValidationResult:
    """Process a single scenario.

    This is the worker function passed to stream_pool for parallel execution.
    It handles logging setup, runner creation, and caching.

    Args:
        scenario: The scenario to run (or JSON string for future support).
        config: The configuration for running scenarios.
        user_agent_config_builder: Builder for user agent configs.
        user_agent_builder: Builder for user agents.
        proactive_agent_config_builder: Builder for proactive agent configs.
        proactive_agent_builder: Builder for proactive agents.

    Returns:
        The validation result for the scenario.
    """
    # Re-establish logging configuration in worker thread/process
    from are.simulation.logging_config import set_logger_scenario_id

    from pas.logging_config import configure_logging, suppress_noisy_are_loggers, suppress_noisy_loggers

    numeric_level = getattr(logging, config.log_level.upper(), logging.INFO)
    log_dir = None
    if config.executor_type != "thread" and config.log_to_file:
        log_dir = Path(config.logs_dir)

    # ! TODO: Handle JSON string scenario (future support)
    if isinstance(scenario, str):
        raise NotImplementedError("JSON scenario loading not yet supported")

    runner_config = _create_scenario_runner_config(config, scenario)

    run_number = getattr(scenario, "run_number", None)
    set_logger_scenario_id(scenario.scenario_id, run_number)

    # Reconfigure logging
    configure_logging(
        level=numeric_level,
        use_tqdm=config.executor_type != "process",
        log_dir=log_dir,
        scenario_id=scenario.scenario_id,
        run_number=run_number,
    )
    suppress_noisy_loggers()
    suppress_noisy_are_loggers()

    # Create runner with builders
    runner = TwoAgentScenarioRunner(
        user_agent_config_builder=user_agent_config_builder,
        user_agent_builder=user_agent_builder,
        proactive_agent_config_builder=proactive_agent_config_builder,
        proactive_agent_builder=proactive_agent_builder,
    )

    # Initialize the scenario if not already initialized
    if not scenario._initialized:
        scenario.initialize(sandbox_dir=Path("sandbox"))

    try:
        return maybe_run_scenario(runner, runner_config, scenario, config.enable_caching)
    except Exception as e:
        logger.exception(f"Scenario {scenario.scenario_id} failed with exception")
        raise


def maybe_run_scenario(
    runner: TwoAgentScenarioRunner,
    config: ScenarioRunnerConfig,
    scenario: PASScenario,
    enable_caching: bool = True,
) -> PASScenarioValidationResult:
    """Run a scenario with caching support.

    Args:
        runner: The scenario runner instance.
        config: The configuration for running scenario.
        scenario: The scenario to run.
        enable_caching: Whether to use caching for scenario results.

    Returns:
        The validation result for the scenario.
    """
    # Check cache if enabled
    if enable_caching:
        from pas.scenarios.utils.caching import maybe_load_cached_result

        cached_result = maybe_load_cached_result(config, scenario)
        if cached_result is not None:
            # Cached result found
            if config.export and config.output_dir:
                # Check if cached export exists
                run_number = getattr(scenario, "run_number", None)
                suffix = f"_run_{run_number}" if run_number is not None else ""
                expected_path = Path(config.output_dir) / f"{scenario.scenario_id}{suffix}.json"

                if not expected_path.exists():
                    # Trace doesn't exist in the output dir, check export path in cache
                    cached_export = cached_result.export_path
                    if cached_export and Path(cached_export).exists():
                        # Copy from cached trace to expected output directory
                        Path(expected_path).parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(cached_export, expected_path)
                        logger.warning(f"Copied trace from {cached_export} to {expected_path}")
                        return cached_result
                    else:
                        # Trace not found anywhere, run scenario again to regenerate trace
                        log_msg = f"Cache hit but trace missing, running scenario {scenario.scenario_id}"
                        if run_number is not None:
                            log_msg += f", run: {run_number}"
                        logger.warning(log_msg)
                else:
                    log_msg = f"Found cached result and trace, skipping scenario {scenario.scenario_id}"
                    if run_number is not None:
                        log_msg += f", run: {run_number}"
                    logger.warning(log_msg)
                    return cached_result
            else:
                run_number = getattr(scenario, "run_number", None)
                log_msg = f"Found cached result and export disabled, skipping scenario {scenario.scenario_id}"
                if run_number is not None:
                    log_msg += f", run: {run_number}"
                logger.warning(log_msg)
                return cached_result

    # Run the scenario
    result = runner.run(config, scenario)

    # Cache the result if enabled
    if enable_caching:
        from pas.scenarios.utils.caching import write_cached_result

        write_cached_result(config, scenario, result)

    return result


class MultiScenarioRunner:
    """Runner for executing multiple PAS scenarios with shared configuration."""

    def __init__(
        self,
        user_agent_config_builder: UserAgentConfigBuilder | None = None,
        user_agent_builder: UserAgentBuilder | None = None,
        proactive_agent_config_builder: ProactiveAgentConfigBuilder | None = None,
        proactive_agent_builder: ProactiveAgentBuilder | None = None,
    ) -> None:
        """Initialize the MultiScenarioRunner with agent builders.

        Args:
            user_agent_config_builder: Builder for user agent configs.
            user_agent_builder: Builder for user agents.
            proactive_agent_config_builder: Builder for proactive agent configs.
            proactive_agent_builder: Builder for proactive agents.

        """
        self.user_agent_config_builder = user_agent_config_builder
        self.user_agent_builder = user_agent_builder
        self.proactive_agent_config_builder = proactive_agent_config_builder
        self.proactive_agent_builder = proactive_agent_builder
        self._interrupted = False
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers to handle Ctrl+C gracefully."""

        def signal_handler(signum: int, frame: object) -> None:
            logger.info("Received interrupt signal. Stopping scenario execution...")
            self._interrupted = True
            raise KeyboardInterrupt("Execution interrupted by user")

        signal.signal(signal.SIGINT, signal_handler)

    def run(self, config: MultiScenarioRunnerConfig, scenarios: list[PASScenario]) -> PASMultiScenarioValidationResult:
        """Run multiple scenarios with the given configuration.

        Args:
            config: The configuration for running scenarios.
            scenarios: The list of scenarios to run.

        Returns:
            The combined validation result for all scenarios.
        """
        if len(scenarios) == 0:
            raise ValueError("No scenarios provided to run.")
        return self.run_with_scenarios(config, itertools.zip_longest(scenarios, [], fillvalue=None))

    def _run_phase(
        self,
        scenarios: CountableIterator[PASScenario] | list[PASScenario],
        config: MultiScenarioRunnerConfig,
        max_workers: int,
        multi_result: PASMultiScenarioValidationResult,
        progress_bar: tqdm[Never],
        retry_attempts: dict[str, int],
    ) -> list[PASScenario]:
        """Run a single phase of scenario execution, collecting retryable failures.

        Processes all scenarios via stream_pool. Scenarios that fail with retryable
        OS errors (EMFILE, ENFILE, ENOMEM) and have retry budget remaining are
        collected into a retry queue instead of being finalized.

        Args:
            scenarios: Iterator or list of scenarios to run in this phase.
            config: The multi-scenario runner config.
            max_workers: Number of parallel workers for this phase.
            multi_result: The accumulator for finalized results.
            progress_bar: Shared progress bar (updated only on finalized results).
            retry_attempts: Dict tracking retry count per scenario key.

        Returns:
            List of scenarios to retry in the next phase.
        """
        retry_queue: list[PASScenario] = []

        with stream_pool(
            iter(scenarios) if isinstance(scenarios, list) else scenarios,
            process_scenario,
            max_workers=max_workers,
            timeout_seconds=config.timeout_seconds,
            executor_type=config.executor_type,
            config=config,
            user_agent_config_builder=self.user_agent_config_builder,
            user_agent_builder=self.user_agent_builder,
            proactive_agent_config_builder=self.proactive_agent_config_builder,
            proactive_agent_builder=self.proactive_agent_builder,
        ) as stream:
            for scenario, result, error in stream:
                if self._interrupted:
                    logger.info("Execution interrupted, stopping...")
                    break

                scenario_id = scenario.scenario_id if hasattr(scenario, "scenario_id") else str(scenario)
                run_number = getattr(scenario, "run_number", None)

                # Handle errors from stream_pool (exceptions thrown by worker)
                if error:
                    if isinstance(error, (TimeoutError, concurrent.futures.TimeoutError)):
                        logger.error(f"Scenario {scenario_id} timed out after {config.timeout_seconds} seconds")
                        result = PASScenarioValidationResult(
                            success=False,
                            exception=ScenarioTimeoutError(
                                f"Scenario {scenario_id} timed out after {config.timeout_seconds} seconds"
                            ),
                            duration=float(config.timeout_seconds) if config.timeout_seconds else 0.0,
                        )
                    else:
                        logger.error(f"Scenario {scenario_id} failed with exception: {error}")
                        result = PASScenarioValidationResult(
                            success=False,
                            exception=error,
                            duration=None,
                        )

                if result is None:
                    result = PASScenarioValidationResult(
                        success=False,
                        exception=Exception(f"Unknown error for scenario {scenario_id}"),
                        duration=None,
                    )

                # Check if this is a retryable error with budget remaining
                key = f"{scenario_id}_run_{run_number}" if run_number is not None else scenario_id
                attempts = retry_attempts.get(key, 0)
                if _is_retryable_error(error, result) and attempts < MAX_RETRIES:
                    retry_attempts[key] = attempts + 1
                    retry_queue.append(scenario)
                    logger.warning(
                        f"Scenario {scenario_id} hit retryable error, queued for retry "
                        f"(attempt {attempts + 1}/{MAX_RETRIES})"
                    )
                    continue

                # Final result -- add to multi_result and update progress
                multi_result.add_result(result, scenario_id, run_number)
                progress_bar.update(1)
                success_rate = multi_result.success_rate_updated()
                progress_bar.set_postfix({"Success": f"{success_rate:.1f}%"})

        return retry_queue

    def run_with_scenarios(  # noqa: C901
        self,
        config: MultiScenarioRunnerConfig,
        scenarios: CountableIterator[PASScenario],
        progress_description: str | None = None,
    ) -> PASMultiScenarioValidationResult:
        """Run multiple scenarios with retry for transient OS errors.

        Executes scenarios in up to 3 phases:
        - Phase 1: Run all scenarios with full worker count.
        - Phase 2: Retry scenarios that failed with retryable OS errors, using half the workers.
        - Phase 3: Final retry attempt for any remaining retryable failures.

        Args:
            config: The configuration for running scenarios.
            scenarios: An iterator of scenarios to run.
            progress_description: Optional description for progress bar.

        Returns:
            The combined validation result for all scenarios.
        """
        multi_result = PASMultiScenarioValidationResult(run_config=config)

        # Setup output directory
        if config.output_dir is None:
            config.output_dir = tempfile.gettempdir()
        if not os.path.isabs(config.output_dir):
            config.output_dir = os.path.abspath(config.output_dir)
        os.makedirs(config.output_dir, exist_ok=True)

        start_time = time.time()

        # Determine max workers
        max_workers = config.max_concurrent_scenarios
        if max_workers is None:
            max_workers = multiprocessing.cpu_count()

        if max_workers == 1:
            logger.info("Running scenarios sequentially (max_concurrent_scenarios=1)")
        else:
            logger.info(f"Running scenarios in parallel with {max_workers} workers")

        # Print config details before progress bar
        config_info = (
            f"Config: user={config.user_model_alias} | "
            f"observe={config.observe_model_alias} | "
            f"execute={config.execute_model_alias} | "
            f"max_turns={config.max_turns}"
        )
        if config.tool_augmentation_config:
            tfp = config.tool_augmentation_config.tool_failure_probability
            config_info += f" | tfp={tfp}"
        if config.env_events_config:
            epm = config.env_events_config.num_env_events_per_minute
            config_info += f" | epm={epm}"
        if config.experiment_name:
            config_info = f"[{config.experiment_name}] {config_info}"
        tqdm.write(config_info)

        # Get total count for progress bar
        total = None
        with contextlib.suppress(TypeError, AttributeError):
            total = len(scenarios)

        # Create progress bar once, reuse across all phases
        desc = progress_description or "Running scenarios"
        progress_bar = tqdm(
            total=total,
            desc=desc,
            position=0,
            leave=True,
            mininterval=0.1,
            maxinterval=1.0,
            smoothing=0.3,
            dynamic_ncols=True,
            file=sys.stdout,
        )
        progress_bar.set_postfix({"Success": "0.0%"})

        retry_attempts: dict[str, int] = {}

        try:
            # Phase 1: Run all scenarios with full worker count
            retry_queue = self._run_phase(
                scenarios,
                config,
                max_workers,
                multi_result,
                progress_bar,
                retry_attempts,
            )

            # Phase 2 and 3: Retry with reduced workers
            retry_workers = max(1, max_workers // 2)
            for phase in range(2, 4):
                if not retry_queue or self._interrupted:
                    break

                gc.collect()
                tqdm.write(
                    f"Retrying {len(retry_queue)} scenarios with transient errors "
                    f"(attempt {phase}/3, {retry_workers} workers)"
                )
                progress_bar.set_description(f"Retrying scenarios (attempt {phase}/3)")

                retry_queue = self._run_phase(
                    retry_queue,
                    config,
                    retry_workers,
                    multi_result,
                    progress_bar,
                    retry_attempts,
                )

        except KeyboardInterrupt:
            logger.info("Received interrupt signal, stopping scenario execution...")
            self._interrupted = True
            raise
        finally:
            progress_bar.close()

        if len(multi_result.scenario_results) == 0:
            raise RuntimeError("No scenarios processed")

        multi_result.duration = time.time() - start_time
        return multi_result
