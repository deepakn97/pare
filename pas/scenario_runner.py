"""TwoAgentScenarioRunner for orchestrating UserAgent and ProactiveAgent."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from are.simulation.agents.default_agent.base_agent import BaseAgent
from are.simulation.agents.llm.llm_engine_builder import LLMEngineBuilder
from are.simulation.data_handler.exporter import JsonScenarioExporter
from are.simulation.environment import EnvironmentConfig
from are.simulation.scenario_runner import ScenarioRunner
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import EnvironmentState, EnvironmentType

from pas.agents import ProactiveAgent, UserAgent
from pas.environment import StateAwareEnvironmentWrapper
from pas.notification_system import PASNotificationSystem

if TYPE_CHECKING:
    from are.simulation.agents.are_simulation_agent_config import ARESimulationReactBaseAgentConfig
    from are.simulation.scenarios import Scenario


logger = logging.getLogger(__name__)


class TwoAgentScenarioRunner(ScenarioRunner):
    """Extends Meta-ARE's ScenarioRunner for two-agent proactive system.

    Inherits:
        - Scenario parsing (JSON → Scenario object)
        - Oracle validation (OracleEvent checking via scenario.validate())
        - Trace export
        - Environment setup and teardown
        - Agent configuration infrastructure

    Implements:
        - Custom two-agent turn-based loop (_run_with_two_agents)
        - UserAgent and ProactiveAgent orchestration
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the TwoAgentScenarioRunner.

        Args:
            *args: The arguments to pass to the ScenarioRunner.
            **kwargs: The keyword arguments to pass to the ScenarioRunner.
        """
        super().__init__(*args, **kwargs)

    def _export_pas_trace(
        self,
        env: StateAwareEnvironmentWrapper,
        scenario: Scenario,
        user_model: str,
        user_agent: str,
        observe_model: str,
        execute_model: str,
        proactive_agent: str,
        validation_result: ScenarioValidationResult,
        run_duration: float,
        output_dir: str | None = None,
        export_apps: bool = True,
        trace_dump_format: str = "hf",
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

        Returns:
            The path to the exported trace.
        """
        validation_decision = ScenarioStatus.Valid.value if validation_result.success else ScenarioStatus.Invalid.value
        validation_rationale = validation_result.rationale

        model_id = f"user:{user_model}|observe:{observe_model}|execute:{execute_model}"
        agent_id = f"user:{user_agent}|proactive:{proactive_agent}"

        scenario_exporter = JsonScenarioExporter()
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
            runner_config=self.config,
        )
        if success:
            logger.info(f"Trace exported to {export_path}")
        else:
            logger.error("Failed to export trace")

        return export_path

    def _run_with_two_agents(
        self,
        scenario_id: str,
        scenario: Scenario,
        env: StateAwareEnvironmentWrapper,
        user_config: ARESimulationReactBaseAgentConfig,
        proactive_observe_config: ARESimulationReactBaseAgentConfig,
        proactive_execute_config: ARESimulationReactBaseAgentConfig,
        max_turns: int | None = None,
    ) -> tuple[ScenarioValidationResult, UserAgent | None, ProactiveAgent | None]:
        """Run scenario with two-agent turn-based loop.

        Flow:
        1. Build three BaseAgent instances (user, observe, execute)
        2. Wrap in UserAgent and ProactiveAgent
        3. Turn-based loop:
            - user_agent.agent_loop()
            - proactive_agent.agent_loop()
            - Check termination (max_turns or env stopped)
        4. Validate using scenario.validate(env) (handles OracleEvent checking)
        5. Return ScenarioValidationResult

        Args:
            scenario_id: The ID of the scenario to run.
            scenario: The scenario to run.
            env: The environment to run the scenario in.
            user_config: The configuration for the user agent.
            proactive_observe_config: The configuration for the proactive observe agent.
            proactive_execute_config: The configuration for the proactive execute agent.
            max_turns: The maximum number of turns to run.

        Returns:
            A tuple containing the validation result, the user agent, and the proactive agent.
        """
        # ! TODO: Will be replaced by an agent builder class.
        user_llm_engine = LLMEngineBuilder().create_engine(user_config.llm_engine_config)
        user_base_agent = BaseAgent(
            llm_engine=user_llm_engine,
            tools={},  # Will be set by the UsetAgent.init_tools()
            max_iterations=user_config.max_iterations,
        )

        observe_llm_engine = LLMEngineBuilder().create_engine(proactive_observe_config.llm_engine_config)
        observe_base_agent = BaseAgent(
            llm_engine=observe_llm_engine,
            tools={},  # Will be set by the ProactiveAgent.init_tools()
            max_iterations=proactive_observe_config.max_iterations,
        )

        execute_llm_engine = LLMEngineBuilder().create_engine(proactive_execute_config.llm_engine_config)
        execute_base_agent = BaseAgent(
            llm_engine=execute_llm_engine,
            tools={},  # Will be set by the ProactiveAgent.init_tools()
            max_iterations=proactive_execute_config.max_iterations,
        )

        user_agent = UserAgent(
            log_callback=env.append_to_world_logs,
            pause_env=env.pause,
            resume_env=env.resume_with_offset,
            llm_engine=user_llm_engine,
            base_agent=user_base_agent,
            time_manager=env.time_manager,
            max_iterations=user_config.max_iterations,
            max_turns=max_turns,
            simulated_generation_time_config=user_config.simulated_generation_time_config,
        )

        proactive_agent = ProactiveAgent(
            log_callback=env.append_to_world_logs,
            pause_env=env.pause,
            resume_env=env.resume_with_offset,
            observe_llm_engine=observe_llm_engine,
            observe_agent=observe_base_agent,
            execute_llm_engine=execute_llm_engine,
            execute_agent=execute_base_agent,
            time_manager=env.time_manager,
            tools=[],
            observe_max_iterations=proactive_observe_config.max_iterations,
            execute_max_iterations=proactive_execute_config.max_iterations,
            max_turns=max_turns,
            simulated_generation_time_config=proactive_observe_config.simulated_generation_time_config,
        )

        # Prepare both agents
        user_agent.prepare_user_agent_run(scenario, env.notification_system)
        proactive_agent.prepare_proactive_agent_run(scenario, env.notification_system)

        turn_count = 0
        while (max_turns is None or turn_count < max_turns) and env.state != EnvironmentState.STOPPED:
            user_tools = env.get_user_tools()
            # ! TODO: Check if setting the max_turns to 1 is correct.
            user_result = user_agent.agent_loop(user_tools, max_turns=1)
            logger.info(f"Turn {turn_count} - User Agent Output: {user_result}")

            proactive_result = proactive_agent.agent_loop()
            logger.info(f"Turn {turn_count} - Proactive Agent Output: {proactive_result}")

            turn_count += 1

        logger.info("Validating Scenario...")
        validation_result = scenario.validate(env)
        logger.info(f"Validation Result: {validation_result}")

        return validation_result, user_agent, proactive_agent

    def _run_pas_scenario(
        self,
        scenario: Scenario,
        user_config: ARESimulationReactBaseAgentConfig,
        proactive_observe_config: ARESimulationReactBaseAgentConfig,
        proactive_execute_config: ARESimulationReactBaseAgentConfig,
        max_turns: int | None = None,
    ) -> ScenarioValidationResult:
        """Run a Proactive Agent Sandbox scenario.

        Args:
            scenario: The scenario to run.
            user_config: The configuration for the user agent.
            proactive_observe_config: The configuration for the proactive observe agent.
            proactive_execute_config: The configuration for the proactive execute agent.
            max_turns: The maximum number of turns to cycles.

        Returns:
            The validation result of the scenario.
        """
        env_config = EnvironmentConfig(
            oracle_mode=False,
            queue_based_loop=False,
            wait_for_user_input_timeout=None,
            time_increment_in_seconds=scenario.time_increment_in_seconds,
            start_time=scenario.start_time,
            dump_dir=None,
            exit_when_no_events=False,
        )

        if scenario.start_time and scenario.start_time > 0:
            env_config.start_time = scenario.start_time

        env = StateAwareEnvironmentWrapper(
            environment_type=EnvironmentType.CLI,
            config=env_config,
            notification_system=PASNotificationSystem(),
        )

        env.run(scenario, wait_for_end=False)

        try:
            # ! TODO: Running without an agent is not implemented yet. This can be useful when evaluating the user simulator agent.
            validation_result, user_agent, proactive_agent = self._run_with_two_agents(
                scenario_id=scenario.scenario_id,
                scenario=scenario,
                env=env,
                user_config=user_config,
                proactive_observe_config=proactive_observe_config,
                proactive_execute_config=proactive_execute_config,
                max_turns=max_turns,
            )
        except Exception as exception:
            logger.exception("Failed to run scenario")
            validation_result, user_agent, proactive_agent = (
                ScenarioValidationResult(success=None, exception=exception),
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
                output_dir=self.config.output_dir,
                export_apps=not has_hf_metadata,
                trace_dump_format="hf",
            )
        validation_result.export_path = export_path
        env.stop()
        return validation_result

    def run_pas_scenario(
        self,
        scenario: Scenario,
        user_config: ARESimulationReactBaseAgentConfig,
        proactive_observe_config: ARESimulationReactBaseAgentConfig,
        proactive_execute_config: ARESimulationReactBaseAgentConfig,
        max_turns: int | None = None,
    ) -> ScenarioValidationResult:
        """Run a Proactive Agent Sandbox scenario.

        Args:
            scenario: The scenario to run.
            user_config: The configuration for the user agent.
            proactive_observe_config: The configuration for the proactive observe agent.
            proactive_execute_config: The configuration for the proactive execute agent.
            max_turns: The maximum number of turns to cycles.

        Returns:
            The validation result of the scenario.

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
            # ! TODO: Judge only mode is not implemented yet.
            result = self._run_pas_scenario(
                scenario, user_config, proactive_observe_config, proactive_execute_config, max_turns
            )
        except Exception as exception:
            logger.exception("Failed to run scenario")
            result = ScenarioValidationResult(success=None, exception=exception)

        # Log result
        logger.info(f"{'✅' if result.success is True else '❌' if result.success is False else '⚠️'} Result: {result}")

        # Convert exception into failure
        if result.success is None and result.exception is not None:
            result.success = False
        # Add run duration to result
        result.duration = time.time() - start_time
        return result
