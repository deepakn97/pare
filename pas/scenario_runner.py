"""TwoAgentScenarioRunner for orchestrating UserAgent and ProactiveAgent."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from are.simulation.environment import EnvironmentConfig
from are.simulation.notification_system import VerbosityLevel
from are.simulation.scenarios.scenario import ScenarioStatus
from are.simulation.types import EnvironmentState, EnvironmentType

from pas.agents.agent_builder import ProactiveAgentBuilder, UserAgentBuilder
from pas.agents.agent_config_builder import ProactiveAgentConfigBuilder, UserAgentConfigBuilder
from pas.apps import StatefulApp
from pas.data_handler.exporter import PASJsonScenarioExporter
from pas.environment import StateAwareEnvironmentWrapper
from pas.notification_system import PASNotificationSystem
from pas.scenarios.validation_result import PASScenarioValidationResult

if TYPE_CHECKING:
    from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig

    from pas.agents.pas_agent_config import ProactiveObserveExecuteAgentConfig, UserDefaultAgentConfig
    from pas.agents.proactive.agent import ProactiveAgent
    from pas.agents.user.agent import UserAgent
    from pas.scenarios.config import ScenarioRunnerConfig
    from pas.scenarios.scenario import PASScenario


logger = logging.getLogger(__name__)


class TwoAgentScenarioRunner:
    """Standalone scenario runner for two-agent proactive system.

    This runner orchestrates UserAgent and ProactiveAgent instances to execute
    PAS scenarios. It supports both normal mode (with agents) and oracle mode
    (without agents, for testing scenario validity).

    Features:
        - Agent creation via configurable builders (UserAgentBuilder, ProactiveAgentBuilder)
        - Two-agent turn-based execution loop
        - Oracle mode for automated scenario validation
        - Trace export for debugging and analysis
    """

    def __init__(
        self,
        user_agent_config_builder: UserAgentConfigBuilder | None = None,
        user_agent_builder: UserAgentBuilder | None = None,
        proactive_agent_config_builder: ProactiveAgentConfigBuilder | None = None,
        proactive_agent_builder: ProactiveAgentBuilder | None = None,
    ) -> None:
        """Initialize the TwoAgentScenarioRunner.

        Args:
            user_agent_config_builder: Builder for user agent configs. Uses default if None.
            user_agent_builder: Builder for user agents. Uses default if None.
            proactive_agent_config_builder: Builder for proactive agent configs. Uses default if None.
            proactive_agent_builder: Builder for proactive agents. Uses default if None.
        """
        self.user_agent_config_builder = user_agent_config_builder or UserAgentConfigBuilder()
        self.user_agent_builder = user_agent_builder or UserAgentBuilder()
        self.proactive_agent_config_builder = proactive_agent_config_builder or ProactiveAgentConfigBuilder()
        self.proactive_agent_builder = proactive_agent_builder or ProactiveAgentBuilder()

    def _run_without_agent(
        self,
        scenario_id: str,
        scenario: PASScenario,
        env: StateAwareEnvironmentWrapper,
    ) -> PASScenarioValidationResult:
        """Run scenario in oracle mode without agents.

        In oracle mode, the environment executes all OracleEvents automatically.
        This method waits for the environment to finish and validates the scenario.

        Args:
            scenario_id: The ID of the scenario being run.
            scenario: The scenario to run.
            env: The environment to run the scenario in.

        Returns:
            The validation result of the scenario.
        """
        logger.info(f"Running scenario {scenario_id} in oracle mode (no agents)")
        env.join()
        logger.info("Validating Scenario...")
        base_result = scenario.validate(env)
        logger.info(f"Validation Result: {base_result}")

        # Convert to PASScenarioValidationResult (no agent metrics in oracle mode)
        return PASScenarioValidationResult(
            success=base_result.success,
            exception=base_result.exception,
            export_path=base_result.export_path,
            rationale=base_result.rationale,
            duration=base_result.duration,
            # No agent metrics in oracle mode - defaults to 0
        )

    def _export_pas_trace(
        self,
        env: StateAwareEnvironmentWrapper,
        scenario: PASScenario,
        user_model: str,
        user_agent: str,
        observe_model: str,
        execute_model: str,
        proactive_agent: str,
        validation_result: PASScenarioValidationResult,
        run_duration: float,
        output_dir: str | None = None,
        export_apps: bool = True,
        trace_dump_format: str = "hf",
        runner_config: ScenarioRunnerConfig | None = None,
    ) -> str | None:
        """Export the trace of the PAS scenario.

        Args:
            env: The environment to export the trace from.
            scenario: The scenario to export the trace for.
            user_model: The model of the user agent.
            user_agent: The agent of the user agent.
            observe_model: The model of the observe agent.
            execute_model: The model of the execute agent.
            proactive_agent: The agent of the proactive agent.
            validation_result: The validation result of the scenario.
            run_duration: The duration of the scenario.
            output_dir: The directory to export the trace to.
            export_apps: Whether to export the apps or not.
            trace_dump_format: The format of the trace.
            runner_config: The configuration used to run the scenario.

        Returns:
            The path to the exported trace.
        """
        validation_decision = ScenarioStatus.Valid.value if validation_result.success else ScenarioStatus.Invalid.value
        validation_rationale = validation_result.rationale

        model_id = f"user:{user_model}|observe:{observe_model}|execute:{execute_model}"
        agent_id = f"user:{user_agent}|proactive:{proactive_agent}"

        scenario_exporter = PASJsonScenarioExporter()
        success, export_path = scenario_exporter.export_to_json_file(
            env,
            scenario,
            model_id,
            agent_id,
            validation_decision,
            validation_rationale,
            run_duration=run_duration,
            output_dir=output_dir,
            export_apps=export_apps,
            trace_dump_format=trace_dump_format,
            scenario_exception=validation_result.exception,
        )
        if success:
            logger.info(f"Trace exported to {export_path}")
        else:
            logger.error("Failed to export trace")

        return export_path

    def _run_with_two_agents(
        self,
        scenario_id: str,
        scenario: PASScenario,
        env: StateAwareEnvironmentWrapper,
        user_engine_config: LLMEngineConfig,
        observe_engine_config: LLMEngineConfig,
        execute_engine_config: LLMEngineConfig,
        max_turns: int | None = None,
        user_max_iterations: int = 1,
        observe_max_iterations: int = 5,
        execute_max_iterations: int = 10,
        use_custom_logger: bool = True,
    ) -> tuple[PASScenarioValidationResult, UserAgent | None, ProactiveAgent | None]:
        """Run scenario with two-agent turn-based loop.

        Flow:
        1. Build UserAgent and ProactiveAgent using builders
        2. Turn-based loop:
            - user_agent.agent_loop()
            - proactive_agent.agent_loop()
            - Check termination (max_turns or env stopped)
        3. Validate using scenario.validate(env) (handles OracleEvent checking)
        4. Return ScenarioValidationResult

        Args:
            scenario_id: The ID of the scenario to run.
            scenario: The scenario to run.
            env: The environment to run the scenario in.
            user_engine_config: LLM engine configuration for the user agent.
            observe_engine_config: LLM engine configuration for the observe agent.
            execute_engine_config: LLM engine configuration for the execute agent.
            max_turns: The maximum number of turns to run.
            user_max_iterations: Max iterations per turn for user agent.
            observe_max_iterations: Max iterations per turn for observe agent.
            execute_max_iterations: Max iterations per turn for execute agent.
            use_custom_logger: Whether to use custom logger in agents.

        Returns:
            A tuple containing the validation result, the user agent, and the proactive agent.
        """
        # Build user agent config
        user_agent_config: UserDefaultAgentConfig = self.user_agent_config_builder.build("default")  # type: ignore[assignment]
        user_agent_config.max_turns = max_turns
        user_agent_config.base_agent_config.llm_engine_config = user_engine_config
        user_agent_config.base_agent_config.max_iterations = user_max_iterations
        user_agent_config.base_agent_config.use_custom_logger = use_custom_logger

        # Build proactive agent config
        proactive_agent_config: ProactiveObserveExecuteAgentConfig = self.proactive_agent_config_builder.build(
            "observe-execute"
        )  # type: ignore[assignment]
        proactive_agent_config.max_turns = max_turns
        proactive_agent_config.observe_base_agent_config.llm_engine_config = observe_engine_config
        proactive_agent_config.observe_base_agent_config.max_iterations = observe_max_iterations
        proactive_agent_config.observe_base_agent_config.use_custom_logger = use_custom_logger
        proactive_agent_config.execute_base_agent_config.llm_engine_config = execute_engine_config
        proactive_agent_config.execute_base_agent_config.max_iterations = execute_max_iterations
        proactive_agent_config.execute_base_agent_config.use_custom_logger = use_custom_logger

        # Build agents using builders
        user_agent = self.user_agent_builder.build(
            agent_config=user_agent_config,
            env=env,
        )
        proactive_agent = self.proactive_agent_builder.build(
            agent_config=proactive_agent_config,
            env=env,
        )

        # Prepare both agents
        user_agent.prepare_user_agent_run(scenario, env.notification_system)
        proactive_agent.prepare_proactive_agent_run(scenario, env.notification_system)

        turn_count = 0

        # Set up proactive context getter (must be after turn_count is defined)
        env.set_proactive_context_getter(lambda: (proactive_agent.mode.value, turn_count))
        # reset on first turn, then false for subsequent turns.
        user_reset = True
        proactive_reset = True

        while (max_turns is None or turn_count < max_turns) and env.state != EnvironmentState.STOPPED:
            user_tools = env.get_user_tools()
            current_app = env.active_app
            current_state = current_app.current_state if current_app and isinstance(current_app, StatefulApp) else None

            user_result = user_agent.agent_loop(
                user_tools, current_app, current_state, reset=user_reset or not user_agent.react_agent.is_initialized()
            )
            logger.info(f"User-Agent Turn {turn_count} Output: {user_result}")
            user_reset = False

            proactive_result = proactive_agent.agent_loop(
                reset=proactive_reset or not proactive_agent.observe_agent.is_initialized()
            )
            logger.info(f"Proactive-Agent Turn {turn_count} Output: {proactive_result}")
            proactive_reset = False

            turn_count += 1

        logger.info("Validating Scenario...")
        base_result = scenario.validate(env)
        logger.info(f"Validation Result: {base_result}")

        # Extract metrics from agents
        proposal_count = proactive_agent.get_proposal_count()
        acceptance_count = user_agent.get_acceptance_count()
        read_only_actions = proactive_agent.get_read_only_actions() + user_agent.get_read_only_actions()
        write_actions = proactive_agent.get_write_actions() + user_agent.get_write_actions()

        # Convert to PASScenarioValidationResult with metrics
        validation_result = PASScenarioValidationResult(
            success=base_result.success,
            exception=base_result.exception,
            export_path=base_result.export_path,
            rationale=base_result.rationale,
            duration=base_result.duration,
            proposal_count=proposal_count,
            acceptance_count=acceptance_count,
            read_only_actions=read_only_actions,
            write_actions=write_actions,
            number_of_turns=turn_count,
        )

        return validation_result, user_agent, proactive_agent

    def _run_pas_scenario(
        self,
        config: ScenarioRunnerConfig,
        scenario: PASScenario,
    ) -> PASScenarioValidationResult:
        """Run a Proactive Agent Sandbox scenario.

        Args:
            config: The configuration for running the scenario.
            scenario: The scenario to run.

        Returns:
            PASScenarioValidationResult: The validation result of the scenario.
        """
        env_config = EnvironmentConfig(
            oracle_mode=config.oracle,
            queue_based_loop=config.oracle,
            wait_for_user_input_timeout=None,
            time_increment_in_seconds=scenario.time_increment_in_seconds,
            start_time=scenario.start_time,
            dump_dir=config.output_dir if config.oracle else None,
            exit_when_no_events=config.oracle,
        )

        if scenario.start_time and scenario.start_time > 0:
            env_config.start_time = scenario.start_time
        logger.info(f"Environment Start Time: {datetime.fromtimestamp(env_config.start_time, tz=UTC)}")
        logger.info(f"Scenario Start Time: {datetime.fromtimestamp(scenario.start_time, tz=UTC)}")

        env = StateAwareEnvironmentWrapper(
            environment_type=EnvironmentType.CLI,
            config=env_config,
            notification_system=PASNotificationSystem(verbosity_level=VerbosityLevel.HIGH),
        )

        env.run(scenario, wait_for_end=False)

        try:
            if config.oracle:
                # Oracle mode: use _run_without_agent
                # The environment will execute all OracleEvents automatically
                validation_result = self._run_without_agent(
                    scenario_id=scenario.scenario_id,
                    scenario=scenario,
                    env=env,
                )
                user_agent, proactive_agent = None, None
            else:
                # Normal mode: run with two agents
                validation_result, user_agent, proactive_agent = self._run_with_two_agents(
                    scenario_id=scenario.scenario_id,
                    scenario=scenario,
                    env=env,
                    user_engine_config=config.user_engine_config,
                    observe_engine_config=config.observe_engine_config,
                    execute_engine_config=config.execute_engine_config,
                    max_turns=config.max_turns,
                    user_max_iterations=config.user_max_iterations or 1,
                    observe_max_iterations=config.observe_max_iterations or 5,
                    execute_max_iterations=config.execute_max_iterations or 10,
                    use_custom_logger=config.use_custom_logger,
                )
        except Exception as exception:
            logger.exception("Failed to run scenario")
            validation_result, user_agent, proactive_agent = (
                PASScenarioValidationResult(success=None, exception=exception),
                None,
                None,
            )

        run_duration = env.time_manager.time_passed()

        # NOTE: ALWAYS EXPORT FOR NOW.

        # CLAUDE CODE: we need to implement the _export_pas_trace method to export everything.
        has_hf_metadata = getattr(scenario, "hf_metadata", None) is not None
        export_path = None
        if user_agent is not None and proactive_agent is not None:
            export_path = self._export_pas_trace(
                env,
                scenario,
                user_agent.model,
                user_agent.agent_framework,
                proactive_agent.observe_model,
                proactive_agent.execute_model,
                proactive_agent.agent_framework,
                validation_result,
                run_duration,
                output_dir=config.output_dir,
                export_apps=not has_hf_metadata,
                trace_dump_format=config.trace_dump_format,
                runner_config=config,
            )
        validation_result.export_path = export_path
        env.stop()
        return validation_result

    def run(
        self,
        config: ScenarioRunnerConfig,
        scenario: PASScenario,
    ) -> PASScenarioValidationResult:
        """Run a Proactive Agent Sandbox scenario.

        Args:
            config: The configuration for running the scenario.
            scenario: The scenario to run.

        Returns:
            PASScenarioValidationResult: The validation result of the scenario.

        Raises:
            NotImplementedError: If scenario loading from string is not implemented yet.
            Exception: If any other exception occurs during the scenario run.
        """
        from are.simulation.logging_config import get_logger_scenario_id, set_logger_scenario_id

        start_time = time.time()
        if isinstance(scenario, str):
            # Load the scenario
            raise NotImplementedError("Scenario loading from string is not implemented yet.")

        run_number = getattr(scenario, "run_number", None)
        if get_logger_scenario_id() != scenario.scenario_id:
            set_logger_scenario_id(scenario.scenario_id, run_number)

        try:
            result = self._run_pas_scenario(config, scenario)
        except Exception as exception:
            logger.exception("Failed to run scenario")
            result = PASScenarioValidationResult(success=None, exception=exception)

        # Log result
        logger.info(f"{'✅' if result.success is True else '❌' if result.success is False else '⚠️'} Result: {result}")

        # Convert exception into failure
        if result.success is None and result.exception is not None:
            result.success = False
        # Add run duration to result
        result.duration = time.time() - start_time
        return result
