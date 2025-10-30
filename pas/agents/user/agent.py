"""User agent wrapper that simulates realistic user behavior on a mobile phone.

Wraps a Meta-ARE BaseAgent and configured for single-action turns.
Manages notification polling, task building and tool refreshing.
Based on meta-are/are/simulation/agents/default_agent/are_simulation_main.py
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from are.simulation.agents.default_agent.base_agent import (
    DEFAULT_STEP_2_MESSAGE,
    DEFAULT_STEP_2_ROLE,
    BaseAgent,
    BaseAgentLog,
    RunningState,
)
from are.simulation.agents.llm.types import MessageRole
from are.simulation.notification_system import BaseNotificationSystem, Message, MessageType
from are.simulation.tool_utils import AppToolAdapter

from .prompts.notification_system import get_notification_system_prompt

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.agents.llm.llm_engine import LLMEngine
    from are.simulation.apps.app_tool import AppTool, Attachment
    from are.simulation.scenarios.scenario import Scenario
    from are.simulation.time_manager import TimeManager
    from are.simulation.types import MMObservation, SimulatedGenerationTimeConfig

    print("TYPE_CHECKING")

logger = logging.getLogger(__name__)

DEFAULT_USER_STEP_2_ROLE = {k: v for k, v in DEFAULT_STEP_2_ROLE.items() if k != "agent_user_interface"}
DEFAULT_USER_STEP_2_MESSAGE = {k: v for k, v in DEFAULT_STEP_2_MESSAGE.items() if k != "agent_user_interface"}

DEFAULT_USER_STEP_2_ROLE["agent_message"] = MessageRole.USER
DEFAULT_USER_STEP_2_MESSAGE["agent_message"] = "Proactive agent messages:\n***\n{content}\n***\n"


class UserAgent:
    """User agent wrapper that simulates realistic user behavior on a mobile phone.

    Wraps a Meta-ARE BaseAgent and configured for single-action turns.
    Manages notification polling, task building and tool refreshing.
    Based on meta-are/are/simulation/agents/default_agent/are_simulation_main.py
    """

    def __init__(
        self,
        log_callback: Callable[[BaseAgentLog], None],
        pause_env: Callable[[], None] | None,
        resume_env: Callable[[float], None] | None,
        llm_engine: LLMEngine,
        base_agent: BaseAgent,
        time_manager: TimeManager,
        max_iterations: int = 1,  # We want to run one agent turn per step for user
        max_turns: int | None = None,
        simulated_generation_time_config: SimulatedGenerationTimeConfig | None = None,
    ) -> None:
        """Initializes the UserAgent wrapper.

        Args:
            log_callback: Callback to log agent logs.
            pause_env: Callback to pause the environment.
            resume_env: Callback to resume the environment.
            llm_engine: LLM engine to use for the agent.
            base_agent: Base agent to wrap.
            time_manager: Time manager to use for the agent.
            max_iterations: Maximum number of iterations to run per turn.
            max_turns: Maximum number of turns to run.
            simulated_generation_time_config: Simulated generation time config to use for the agent.
        """
        # Wrapper Agent model arguments
        self.llm_engine = llm_engine
        self.time_manager = time_manager
        self.max_iterations = max_iterations
        self.max_turns = max_turns
        self.tools: list[AppTool] | None = None

        # Built React Agent arguments
        self.react_agent = base_agent
        self.react_agent.name = "user_base_agent"
        self.react_agent.llm_engine = self.llm_engine
        self.react_agent.time_manager = self.time_manager
        self.react_agent.max_iterations = self.max_iterations
        self.react_agent.log_callback = log_callback
        self.react_agent.role_dict = DEFAULT_USER_STEP_2_ROLE
        self.react_agent.message_dict = DEFAULT_USER_STEP_2_MESSAGE

        # Environment methods to handle simulation time.
        self.simulated_generation_time_config = simulated_generation_time_config
        self.pause_env = pause_env
        self.resume_env = resume_env
        self.react_agent.simulated_generation_time_config = self.simulated_generation_time_config

        # ! NO SUB-AGENTS SUPPORTED YET.

        self._initialized = False

    @property
    def agent_framework(self) -> str:
        """Name of the agent."""
        return "PASUserAgent"

    @property
    def model(self) -> str:
        """Name of the model."""
        return self.llm_engine.model_name

    def init_tools(self, tools: list[AppTool]) -> None:
        """Initialize the tools.

        Args:
            tools: Tools to initialize.
        """
        logger.info(f"Initializing {len(tools)} tools: {[tool.name for tool in tools]}")

        are_simulation_tools = [AppToolAdapter(tool) for tool in tools]
        self.tools = are_simulation_tools
        self.react_agent.tools = {tool.name: tool for tool in self.tools}

    def init_system_prompt(self, scenario: Scenario) -> None:
        """Initialize the system prompt.

        Args:
            scenario: Scenario to initialize the system prompt for.
        """
        additional_system_prompt = scenario.additional_system_prompt
        logger.info(f"Additional System Prompt: {additional_system_prompt}")

        task_description = additional_system_prompt if additional_system_prompt is not None else ""
        self.react_agent.init_system_prompts["system_prompt"] = self.react_agent.init_system_prompts[
            "system_prompt"
        ].replace("<<task_description>>", task_description)

        notification_system_prompt = get_notification_system_prompt(self.react_agent.notification_system, scenario.apps)
        self.react_agent.init_system_prompts["system_prompt"] = self.react_agent.init_system_prompts[
            "system_prompt"
        ].replace("<<notification_system_description>>", notification_system_prompt)

        date_str = datetime.fromtimestamp(scenario.start_time or 0, tz=UTC).strftime("%Y-%m-%d %H")

        self.react_agent.init_system_prompts["system_prompt"] = self.react_agent.init_system_prompts[
            "system_prompt"
        ].replace("<<curent_time_description>>", f"Today's date in 'YYYY-MM-DD HH' format is {date_str}")

        self.react_agent.init_system_prompts["system_prompt"] = self.react_agent.init_system_prompts[
            "system_prompt"
        ].replace("<<agent_reminder_description>>", "")

        logger.debug(f"Initialized system prompt: {self.react_agent.init_system_prompts['system_prompt']}")

    def init_notification_system(self, notification_system: BaseNotificationSystem) -> None:
        """Initialize the notification system.

        Args:
            notification_system: Notification system to initialize.
        """
        if notification_system is not None:
            logger.info(f"Setting notification system for User Agent to provided one {notification_system}")
            self.react_agent.notification_system = notification_system

    def prepare_user_agent_run(
        self,
        scenario: Scenario,
        notification_system: BaseNotificationSystem | None = None,
        initial_agent_logs: list[BaseAgentLog] | None = None,
    ) -> None:
        """Prepare the user agent run.

        Args:
            scenario: Scenario to run the turn for.
            notification_system: Notification system to use for the agent.
            initial_agent_logs: Initial agent logs to use for the agent.

        Raises:
            Exception: If pause and resume environment functions are not provided if simulated generation time config is set.
        """
        self.init_tools(scenario.get_user_tools())
        self.init_notification_system(notification_system)
        self.init_system_prompt(scenario)
        # ! NOTE: We don't need to replay at all for our agents.
        # Sync the base agent time manager
        if initial_agent_logs is not None and len(initial_agent_logs) > 0:
            self.react_agent.replay(initial_agent_logs)

        # Pause/resume env functions
        if self.simulated_generation_time_config is not None and (self.pause_env is None or self.resume_env is None):
            raise RuntimeError(
                "Pause and resume environment functions must be provided if simulated generation time config is set"
            )
        self.react_agent.pause_env = self.pause_env
        self.react_agent.resume_env = self.resume_env
        self._initialized = True

    def get_notifications(
        self, notification_system: BaseNotificationSystem
    ) -> tuple[list[Message], list[Message], list[Message]]:
        """Get new notifications from the notification system.

        From the User Agent perspective:
        - agent_messages: messages sent by the agent to the user.
        - environment_notifications: Environment events like incoming email, messages etc.
        - env_stop_messages: Environment stop signals

        Args:
            notification_system: Notification system to get notifications from.

        Returns:
            Tuple of (list of new agent messages, list of new environment notifications, list of environment stop messages).

        Raises:
                RuntimeError: If notification system is not set.
        """
        if notification_system is None:
            raise RuntimeError("Notification system not set")

        new_messages = notification_system.message_queue.get_by_timestamp(
            datetime.fromtimestamp(self.time_manager.time(), tz=UTC)
        )

        # Filter for AGENT_MESSAGE (ProactiveAgent proposals to UserAgent)
        # Note: We check against the string value to support both MessageType and PASMessageType
        new_agent_messages = [message for message in new_messages if message.message_type == MessageType.AGENT_MESSAGE]

        new_env_notifications = [
            message for message in new_messages if message.message_type == MessageType.ENVIRONMENT_NOTIFICATION
        ]

        for message in new_env_notifications:
            notification_system.message_queue.put(message)

        env_stop_messages = [
            message for message in new_messages if message.message_type == MessageType.ENVIRONMENT_STOP
        ]

        return new_agent_messages, new_env_notifications, env_stop_messages

    def build_task_from_notifications(self, agent_messages: list[Message]) -> str:
        """Build User Agent task from agent messages.

        Agent messages comes from Proactive Agent in the form of proposals.
        Environment notifications are handled separately by preprocessing step.

        Args:
            agent_messages: List of agent messages.

        Returns:
            Task string for the User Agent.
        """
        if len(agent_messages) > 0:
            logger.info(f"Proactive Agent made a proposal: {agent_messages}")
        task = "\n".join([message.message for message in agent_messages])
        return task

    def agent_loop(  # noqa: C901
        self,
        current_tools: list[AppTool],
        max_turns: int | None = None,
        initial_agent_logs: list[BaseAgentLog] | None = None,
    ) -> str | MMObservation | None:
        """Execute one user agent turn.

        This is completely synchronous loop where the agent runs on notifications, until it returns a result.
        The loop continues until max_turns is reached on ENVIRONMENT_STOP message is received.

        1. Refresh the internal tools list with the provided tools.
        2. Get new notifications from the notification system.
        3. If initial_task is provided, inject it as a user message into notification system.
        4. Execute the base react agent loop.

        Args:
            current_tools: Current tools to use for the turn.
            max_turns: Maximum number of turns to run.
            initial_agent_logs: Initial agent logs to use for the agent.

        Returns:
            Result from the last agent turn execution.

        Raises:
            RuntimeError: If user agent is not initialized or notification system is not set.
        """
        turn_count = 0
        result = ""

        if not self._initialized:
            raise RuntimeError("User agent must be initialized before running a turn.")

        if self.react_agent.notification_system is None:
            raise RuntimeError("Notification system not set")

        self.init_tools(current_tools)

        if initial_agent_logs:
            # ! FIXME: This is a problem, because we cannot replay the agent logs if we cannot initialize the correct tools. A problem that we can fix later.
            result = self.react_agent.replay(initial_agent_logs)
            turn_count += 1

        reset = True
        while max_turns is None or turn_count < max_turns:
            agent_messages, env_notifications, env_stop_messages = self.get_notifications(
                self.react_agent.notification_system
            )

            if len(env_stop_messages) > 0:
                logger.warning(f"Environment stop message received - Stopping User Agent: {env_stop_messages}")
                break
            if len(agent_messages) > 0 or len(env_notifications) > 0:
                task = self.build_task_from_notifications(agent_messages)

                # ? NOTE: We don't need attachments for proactive agent proposals I think. But to keep it general enough, we keep it here.
                attachments: list[Attachment] = [
                    attachment for message in agent_messages for attachment in message.attachments
                ]
                logger.debug(
                    f"Running user agent with task '{task}' at iteration {turn_count} and reset {reset} with attachments {attachments}"
                )
                result = self.react_agent.run(task=task, hint=None, reset=reset, attachments=attachments)
                reset = False
                running_state = self.react_agent.custom_state.get("running_state", None)
                if running_state == RunningState.TERMINATED:
                    turn_count += 1
                    logger.debug(f"End of turn {turn_count}")
                elif running_state == RunningState.PAUSED:
                    logger.debug("User agent paused")
                elif running_state == RunningState.FAILED:
                    agent_logs = self.react_agent.get_agent_logs()
                    error_message = (
                        f"Last User Agent log: {agent_logs[-1]}" if len(agent_logs) > 0 else "No User Agent logs"
                    )
                    raise RuntimeError(f"User agent failed. {error_message}")
                else:
                    raise RuntimeError(f"Unknown running state: {running_state}")
            else:
                # ! FIXME: Originally this was done to avoid busy looping. However, for user agent, we should allow busy looping such that the user can do other things while the agent is running, adding natural noise to the system. Maybe controlled through a cli parameter.
                logger.debug("No new messages from proactive agent or environment")
                time.sleep(1)
        if max_turns is not None and turn_count >= max_turns:
            logger.warning(f"Max turns reached - Stopping User Agent: {max_turns}")

        return result
