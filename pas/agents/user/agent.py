"""User agent wrapper that simulates realistic user behavior on a mobile phone.

Wraps a Meta-ARE BaseAgent and configured for single-action turns.
Manages notification polling, task building and tool refreshing.
Based on meta-are/are/simulation/agents/default_agent/are_simulation_main.py
"""

from __future__ import annotations

import logging
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
from are.simulation.tool_utils import AppToolAdapter

from pas.notification_system import PASMessageType

from .prompts.apps import format_available_apps
from .prompts.notification_system import get_notification_system_prompt

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.agents.llm.llm_engine import LLMEngine
    from are.simulation.agents.multimodal import Attachment
    from are.simulation.notification_system import BaseNotificationSystem, Message
    from are.simulation.scenarios.scenario import Scenario
    from are.simulation.time_manager import TimeManager
    from are.simulation.tool_utils import AppTool
    from are.simulation.types import MMObservation, SimulatedGenerationTimeConfig

    from pas.apps import App, AppState

    print("TYPE_CHECKING")

logger = logging.getLogger(__name__)

DEFAULT_USER_STEP_2_ROLE = {k: v for k, v in DEFAULT_STEP_2_ROLE.items() if k != "agent_user_interface"}
DEFAULT_USER_STEP_2_MESSAGE = {k: v for k, v in DEFAULT_STEP_2_MESSAGE.items() if k != "agent_user_interface"}

DEFAULT_USER_STEP_2_ROLE["agent_message"] = MessageRole.USER
DEFAULT_USER_STEP_2_ROLE["current_app_state"] = MessageRole.USER
DEFAULT_USER_STEP_2_ROLE["available_tools"] = MessageRole.USER
DEFAULT_USER_STEP_2_MESSAGE["agent_message"] = "Proactive agent messages:\n***\n{content}\n***\n"
DEFAULT_USER_STEP_2_MESSAGE["current_app_state"] = "Current app state:\n***\n{content}\n***\n"
DEFAULT_USER_STEP_2_MESSAGE["available_tools"] = "Available Actions from current state:\n***\n{content}\n***\n"


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
        user_tools = self.remove_aui_irrelevant_tools(tools)
        are_simulation_tools = [AppToolAdapter(tool) for tool in user_tools]
        self.tools = are_simulation_tools
        self.react_agent.tools = {tool.name: tool for tool in self.tools}
        self.react_agent.init_tools()
        logger.debug(f"Initialized {len(self.tools)} tools: {[tool.name for tool in self.tools]}")

    def remove_aui_irrelevant_tools(self, tools: list[AppTool]) -> list[AppTool]:
        """Remove irrelevant tools from the tools.

        Args:
            tools: Tools to remove irrelevant tools from.

        Returns:
            List of tools.
        """
        return [
            tool
            for tool in tools
            if tool.name
            not in [
                "PASAgentUserInterface__send_message_to_agent",
            ]
        ]

    def init_system_prompt(self, scenario: Scenario) -> None:
        """Initialize the system prompt.

        Args:
            scenario: Scenario to initialize the system prompt for.
        """
        additional_system_prompt = scenario.additional_system_prompt
        logger.debug(f"Additional System Prompt: {additional_system_prompt}")

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

        available_apps = format_available_apps(scenario.apps)
        self.react_agent.init_system_prompts["system_prompt"] = self.react_agent.init_system_prompts[
            "system_prompt"
        ].replace("<<available_apps>>", available_apps)

    def init_notification_system(self, notification_system: BaseNotificationSystem) -> None:
        """Initialize the notification system.

        Args:
            notification_system: Notification system to initialize.
        """
        if notification_system is not None:
            logger.debug(f"Setting notification system for User Agent to provided one {notification_system}")
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

    def get_notifications(self) -> tuple[list[Message], list[Message], list[Message]]:
        """Get ENVIRONMENT_STOP notifications from the notification system.

        Returns:
            Tuple of (list of agent messages, list of environment notifications, list of environment stop messages).
        """
        # new_messages = self.react_agent.custom_state.get("notifications", [])
        new_messages = self.react_agent.notification_system.message_queue.get_by_timestamp(
            timestamp=datetime.fromtimestamp(self.time_manager.time(), tz=UTC)
        )

        agent_messages = [message for message in new_messages if message.message_type == PASMessageType.AGENT_MESSAGE]
        env_notifications = [
            message for message in new_messages if message.message_type == PASMessageType.ENVIRONMENT_NOTIFICATION_USER
        ]
        env_stop_messages = [
            message for message in new_messages if message.message_type == PASMessageType.ENVIRONMENT_STOP
        ]

        # Reinsert the env notifications for user and agent, agent messages and any extra messages back into the notification system.
        # This is important because the preprocessing step and the next agent will use the same notification system.
        messages_to_put_back = [m for m in new_messages if m not in env_stop_messages]
        logger.debug(
            f"User agent get_notifications() -> message types to put back: {'; '.join([m.message_type.value for m in messages_to_put_back])}"
        )

        for message in messages_to_put_back:
            self.react_agent.notification_system.message_queue.put(message)

        return agent_messages, env_notifications, env_stop_messages

    def build_task_from_notifications(self, agent_messages: list[Message]) -> str:
        """Build User Agent task from agent messages.

        User messages comes from the User Agent in the form of accept/reject responses.
        Environment notifications are handled separately by preprocessing step.

        Args:
            agent_messages: List of agent messages.

        Returns:
            Task string for the User Agent.
        """
        if len(agent_messages) > 0:
            logger.debug(f"Agent Messages: {agent_messages}")
        task = "\n".join([message.message for message in agent_messages])
        return task

    def agent_loop(
        self,
        current_tools: list[AppTool],
        current_app: App | None = None,
        current_state: AppState | None = None,
        reset: bool = True,
    ) -> str | MMObservation | None:
        """Execute one user agent turn.

        This is completely synchronous function where the agent runs on notifications.

        Args:
            current_tools: Current tools to use for the turn.
            current_app: Current active app in the environment for the user.
            current_state: Current active state in the active app for the user.
            reset: Whether to reset the user agent.

        Returns:
            Result from the last agent turn execution.

        Raises:
            RuntimeError: If user agent is not initialized or notification system is not set.
        """
        result = ""

        if not self._initialized:
            raise RuntimeError("User agent must be initialized before running a turn.")

        if self.react_agent.notification_system is None:
            raise RuntimeError("Notification system not set")

        # inject current app and state into the custom state of the react agent.
        self.react_agent.custom_state["current_app"] = current_app
        self.react_agent.custom_state["current_state"] = current_state
        # Reset the internal iterations counter, otherwise after first turn, the agent will exit. And if we increase the number of max_iterations, then the agent will take multiple turns.
        # ! FIXME: Find a better solution for this iterations issue.
        self.react_agent.iterations = 0

        self.init_tools(current_tools)

        agent_messages, _, env_stop_messages = self.get_notifications()
        task = self.build_task_from_notifications(agent_messages)
        attachments: list[Attachment] = [attachment for message in agent_messages for attachment in message.attachments]
        if len(env_stop_messages) > 0:
            logger.warning(f"Environment stop message received - Stopping User Agent: {env_stop_messages}")
            return result

        # User will take action no matter what.
        result = self.react_agent.run(
            task=task, hint=None, reset=reset, attachments=attachments if attachments else None
        )
        running_state = self.react_agent.custom_state.get("running_state", None)
        if running_state == RunningState.FAILED:
            agent_logs = self.react_agent.get_agent_logs()
            error_message = f"Last User Agent log: {agent_logs[-1]}" if len(agent_logs) > 0 else "No User Agent logs"
            raise RuntimeError(f"User agent failed. {error_message}")

        return result
