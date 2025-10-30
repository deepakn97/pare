"""Proactive agent wrapper that manages observe and execute agents.

Wraps two Meta-ARE BaseAgent instances: observer and executer.
Based on meta-are/are/simulation/agents/default_agent/are_simulation_main.py
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from are.simulation.agents.agent_log import ToolCallLog
from are.simulation.notification_system import Message, MessageType
from are.simulation.tool_utils import AppTool, AppToolAdapter

from .prompts.notification_system import get_execute_notification_system_prompt, get_observe_notification_system_prompt

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.agents.base_agent import BaseAgent
    from are.simulation.llm_engine import LLMEngine
    from are.simulation.notification_system import BaseNotificationSystem
    from are.simulation.scenarios.scenario import Scenario
    from are.simulation.time_manager import TimeManager
    from are.simulation.tool_utils import Tool
    from are.simulation.types import Attachment, BaseAgentLog, MMObservation, SimulatedGenerationTimeConfig

    from pas.apps import PASAgentUserInterface

logger = logging.getLogger(__name__)


class ProactiveAgentMode(Enum):
    """Runtime state of the Proactive Agent."""

    OBSERVE = "observe"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTE = "execute"  # Execute the confirmed goal


class ProactiveAgent:
    """Proactive agent wrapper that manages observe and execute agents.

    Observer agent is responsible for continuous monitoring of the environment and proposing goals to the user.
    Executer agent is responsible for executing the confirmed goal.
    """

    def __init__(
        self,
        log_callback: Callable[[BaseAgentLog], None],
        pause_env: Callable[[], None] | None,
        resume_env: Callable[[float], None] | None,
        # ! FIXME: Observer agent doesn't need to be a base agent. A simple LLMEnginer call is enough. Infact observe agent should be a different protocol which users can extend to implement a rule based or statistical ML model based observer.
        observe_llm_engine: LLMEngine,
        observe_agent: BaseAgent,
        execute_llm_engine: LLMEngine,
        execute_agent: BaseAgent,
        time_manager: TimeManager,
        tools: list[Tool] | None = None,
        observe_max_iterations: int = 1,
        execute_max_iterations: int = 20,
        max_turns: int | None = None,
        simulated_generation_time_config: SimulatedGenerationTimeConfig | None = None,
    ) -> None:
        """Initializes the ProactiveAgent wrapper.

        Args:
            log_callback: Callback to log agent logs.
            pause_env: Callback to pause the environment.
            resume_env: Callback to resume the environment.
            observe_llm_engine: LLM engine to use for the observer agent.
            observe_agent: Observer agent to wrap.
            execute_llm_engine: LLM engine to use for the execute agent.
            execute_agent: Execute agent to wrap.
            time_manager: Time manager to use for the agent.
            tools: Tools to use for the agent.
            observe_max_iterations: Maximum number of iterations to run per turn for the observer agent.
            execute_max_iterations: Maximum number of iterations to run per turn for the execute agent.
            max_turns: Maximum number of turns to run.
            simulated_generation_time_config: Simulated generation time config to use for the agent.
        """
        # Wrapper Agent model arguments
        if tools is None:
            tools = []

        self.time_manager = time_manager
        self.max_turns = max_turns
        self.tools = tools
        self.observe_max_iterations = observe_max_iterations
        self.execute_max_iterations = execute_max_iterations
        self.mode = ProactiveAgentMode.OBSERVE
        self.pending_goal: str | None = None

        # Observer Agent arguments
        self.observe_llm_engine = observe_llm_engine
        self.observe_agent = observe_agent
        self.observe_agent.name = "observe_base_agent"
        self.observe_agent.max_iterations = observe_max_iterations
        self.observe_agent.llm_engine = self.observe_llm_engine
        self.observe_agent.time_manager = self.time_manager
        self.observe_agent.log_callback = log_callback

        # Execute Agent arguments
        self.execute_llm_engine = execute_llm_engine
        self.execute_agent = execute_agent
        self.execute_agent.name = "execute_base_agent"
        self.execute_agent.max_iterations = execute_max_iterations
        self.execute_agent.llm_engine = self.execute_llm_engine
        self.execute_agent.time_manager = self.time_manager
        self.execute_agent.log_callback = log_callback

        # Environment methods to handle simulation time.
        self.simulated_generation_time_config = simulated_generation_time_config
        self.pause_env = pause_env
        self.resume_env = resume_env
        self.observe_agent.simulated_generation_time_config = self.simulated_generation_time_config
        self.execute_agent.simulated_generation_time_config = self.simulated_generation_time_config

        # Tracks if both agents are initialized.
        self._initialized = False

    @property
    def agent_framework(self) -> str:
        """Name of the agent."""
        return "PASProactiveAgent"

    @property
    def observe_model(self) -> str:
        """Name of the observe model."""
        return self.observe_llm_engine.model_name

    @property
    def execute_model(self) -> str:
        """Name of the execute model."""
        return self.execute_llm_engine.model_name

    def init_tools(self, scenario: Scenario) -> None:
        """Initialize the tools.

        Args:
            scenario: Scenario to initialize the tools for.
        """
        app_tools = self.remove_aui_irrelevant_tools(scenario.get_tools())
        logger.info(f"Found {len(app_tools)} tools: {[tool.name for tool in app_tools]}")
        are_simulation_tools = [AppToolAdapter(tool) for tool in app_tools]
        self.tools += are_simulation_tools

        observe_tools = [tool for tool in self.tools if "send_message_to_user" in tool.name.lower()]
        if len(observe_tools) == 0:
            raise ValueError("No observe tools found. The observe agent must have the send_message_to_user tool.")
        self.observe_agent.tools = {tool.name: tool for tool in observe_tools}
        self.execute_agent.tools = {tool.name: tool for tool in self.tools}

    def init_observe_system_prompt(self, scenario: Scenario) -> None:
        """Initialize the observe system prompt.

        Args:
            scenario: Scenario to initialize the observe system prompt for.
        """
        # ! NOTE: We don't need to check the additional system prompt here because that is meant for the user agent.
        notification_system_prompt = get_observe_notification_system_prompt(
            self.observe_agent.notification_system, scenario.apps
        )
        self.observe_agent.init_system_prompts["system_prompt"] = self.observe_agent.init_system_prompts[
            "system_prompt"
        ].replace("<<notification_system_description>>", notification_system_prompt)

        date_str = datetime.fromtimestamp(scenario.start_time or 0, tz=UTC).strftime("%Y-%m-%d %H")
        self.observe_agent.init_system_prompts["system_prompt"] = self.observe_agent.init_system_prompts[
            "system_prompt"
        ].replace("<<curent_time_description>>", f"Today's date in 'YYYY-MM-DD HH' format is {date_str}")

        self.observe_agent.init_system_prompts["system_prompt"] = self.observe_agent.init_system_prompts[
            "system_prompt"
        ].replace("<<agent_reminder_description>>", "")

        logger.debug(f"Initialized observe system prompt: {self.observe_agent.init_system_prompts['system_prompt']}")

    def init_execute_system_prompt(self, scenario: Scenario) -> None:
        """Initialize the execute system prompt.

        Args:
            scenario: Scenario to initialize the execute system prompt for.
        """
        notification_system_prompt = get_execute_notification_system_prompt(
            self.execute_agent.notification_system, scenario.apps
        )
        self.execute_agent.init_system_prompts["system_prompt"] = self.execute_agent.init_system_prompts[
            "system_prompt"
        ].replace("<<notification_system_description>>", notification_system_prompt)

        date_str = datetime.fromtimestamp(scenario.start_time or 0, tz=UTC).strftime("%Y-%m-%d %H")
        self.execute_agent.init_system_prompts["system_prompt"] = self.execute_agent.init_system_prompts[
            "system_prompt"
        ].replace("<<curent_time_description>>", f"Today's date in 'YYYY-MM-DD HH' format is {date_str}")

        self.execute_agent.init_system_prompts["system_prompt"] = self.execute_agent.init_system_prompts[
            "system_prompt"
        ].replace("<<agent_reminder_description>>", "")

        logger.debug(f"Initialized execute system prompt: {self.execute_agent.init_system_prompts['system_prompt']}")

    def init_notification_system(self, notification_system: BaseNotificationSystem) -> None:
        """Initialize the notification system.

        Args:
            notification_system: Notification system to initialize.
        """
        if notification_system is not None:
            logger.info(f"Setting notification system for Proactive Agent to provided one {notification_system}")
            self.observe_agent.notification_system = notification_system
            self.execute_agent.notification_system = notification_system

    def prepare_proactive_agent_run(
        self,
        scenario: Scenario,
        notification_system: BaseNotificationSystem | None = None,
        observe_agent_logs: list[BaseAgentLog] | None = None,
        execute_agent_logs: list[BaseAgentLog] | None = None,
    ) -> None:
        """Prepare the proactive agent run.

        Args:
            scenario: Scenario to run the turn for.
            notification_system: Notification system to use for the agent.
            observe_agent_logs: Initial agent logs to use for the observe agent.
            execute_agent_logs: Initial agent logs to use for the execute agent.
        """
        self.init_tools(scenario)
        self.init_notification_system(notification_system)
        self.init_observe_system_prompt(scenario)
        self.init_execute_system_prompt(scenario)
        # ! NOTE: We don't need to replay at all for our agents.
        if observe_agent_logs is not None and len(observe_agent_logs) > 0:
            self.observe_agent.replay(observe_agent_logs)
        if execute_agent_logs is not None and len(execute_agent_logs) > 0:
            self.execute_agent.replay(execute_agent_logs)

        if self.simulated_generation_time_config is not None and (self.pause_env is None or self.resume_env is None):
            raise RuntimeError(
                "Pause and resume environment functions must be provided if simulated generation time config is set"
            )
        self.observe_agent.pause_env = self.pause_env
        self.observe_agent.resume_env = self.resume_env
        self.execute_agent.pause_env = self.pause_env
        self.execute_agent.resume_env = self.resume_env
        self._initialized = True

    def remove_aui_irrelevant_tools(self, app_tools: list[AppTool]) -> list[AppTool]:
        """Remove irrelevant tools from the app tools.

        Args:
            app_tools: List of app tools.

        Returns:
            List of app tools.
        """
        aui_tool = next(tool for tool in app_tools if "ProactiveAgentUserInterface" in tool.name)

        if aui_tool is not None:
            aui: PASAgentUserInterface = aui_tool.class_instance
            # We set this to True here because all the messages from the user are going to be received by the Agent as notifications
            # And thus handled as new tasks, instead of the Agent blocking when sending a message to the user waiting for a response.
            logger.warning("Setting wait_for_user_response to False in AgentUserInterface")
            aui.wait_for_user_response = False

            # Here we remove these tools, because all user messages will be injected to Agent
            # And thus he won't need to use these tools to get the messages.
            # FIXME: The name of the tools might be wrong here. Check in future.
            tools_to_remove = {
                "ProactiveAgentUserInterface__get_last_message_from_user",
                "ProactiveAgentUserInterface__get_last_message_from_agent",
                "ProactiveAgentUserInterface__get_last_unread_messages",
                "ProactiveAgentUserInterface__get_all_messages",
            }
            logger.warning(f"Removing tools {tools_to_remove} from app_tools")
            app_tools = [tool for tool in app_tools if tool.name not in tools_to_remove]
        return app_tools

    def get_notifications(
        self, notification_system: BaseNotificationSystem
    ) -> tuple[list[Message], list[Message], list[Message]]:
        """Get new notifications from the notification system.

        From the Proactive Agent perspective:
        - user_messages: messages sent by the user to the agent.
        - environment_notifications: Environment events like incoming email, messages etc.
        - env_stop_messages: Environment stop signals

        Args:
            notification_system: Notification system to get notifications from.

        Returns:
            Tuple of (list of new user messages, list of new environment notifications, list of environment stop messages).

        Raises:
                RuntimeError: If notification system is not set.
        """
        if notification_system is None:
            raise RuntimeError("Notification system not set")

        new_messages = notification_system.message_queue.get_by_timestamp(
            datetime.fromtimestamp(self.time_manager.time(), tz=UTC)
        )

        # Filter for USER_MESSAGE (User messages to Proactive Agent)
        # Note: We check against the string value to support both MessageType and PASMessageType
        new_user_messages = [message for message in new_messages if message.message_type == MessageType.USER_MESSAGE]

        new_env_notifications = [
            message for message in new_messages if message.message_type == MessageType.ENVIRONMENT_NOTIFICATION
        ]

        for message in new_env_notifications:
            notification_system.message_queue.put(message)

        env_stop_messages = [
            message for message in new_messages if message.message_type == MessageType.ENVIRONMENT_STOP
        ]

        return new_user_messages, new_env_notifications, env_stop_messages

    def build_task_from_notifications(self, user_messages: list[Message]) -> str:
        """Build User Agent task from agent messages.

        User messages comes from the User Agent in the form of accept/reject responses.
        Environment notifications are handled separately by preprocessing step.

        Args:
            user_messages: List of user messages.

        Returns:
            Task string for the User Agent.
        """
        if len(user_messages) > 0:
            logger.info(f"User Messages: {user_messages}")
        task = "\n".join([message.message for message in user_messages])
        return task

    def check_for_proposal(self) -> tuple[bool, str | None]:
        """Check if the Proactive Agent sent a proposal to the user.

        Inspect observe_agent_logs for send_message_to_user calls.

        Returns:
            Returns (True, proposal content) if a proposal was sent, (False, None) otherwise.
        """
        logs = self.observe_agent.get_agent_logs()

        for log in reversed(logs):
            if isinstance(log, ToolCallLog) and "send_message_to_user" in log.tool_name.lower():
                if isinstance(log.tool_arguments, dict):
                    content = log.tool_arguments.get("content", "")
                else:
                    content = str(log.tool_arguments)
                logger.info(f"Proactive Agent sent a proposal: {content}")
                return True, content
        return False, None

    def agent_loop(
        self,
        initial_task: str | None = None,
    ) -> str | MMObservation | None:
        """Execute one proactive agent turn either in observe or execute mode.

        Args:
            initial_task: Initial task to run the agent with.

        Returns:
            Result from the last agent turn execution.

        Raises:
            RuntimeError: If notification system is not set for either observe or execute agent.
        """
        if self.observe_agent.notification_system is None or self.execute_agent.notification_system is None:
            raise RuntimeError("Notification system not set for either observe or execute agent")

        if initial_task is not None:
            self.observe_agent.notification_system.message_queue.put(
                Message(
                    message_type=MessageType.USER_MESSAGE,
                    message=initial_task,
                    timestamp=datetime.fromtimestamp(self.time_manager.time(), tz=UTC),
                )
            )

        new_user_messages, new_env_notifications, env_stop_messages = self.get_notifications(
            self.observe_agent.notification_system
        )

        if len(env_stop_messages) > 0:
            logger.warning(f"Environment stop message received - Stopping Agent: {env_stop_messages}")
            return None

        task = ""
        if len(new_user_messages) > 0 or len(new_env_notifications) > 0:
            if self.mode == ProactiveAgentMode.OBSERVE:
                result = self._run_observe_mode(new_user_messages, new_env_notifications)
                return result
            elif self.mode == ProactiveAgentMode.AWAITING_CONFIRMATION:
                accepted, _ = self._check_confirmation(new_user_messages)
                if accepted:
                    self.mode = ProactiveAgentMode.EXECUTE
                    return self._run_execute_mode(new_user_messages, new_env_notifications)
            elif self.mode == ProactiveAgentMode.EXECUTE:
                return self._run_execute_mode(new_user_messages, new_env_notifications)
            else:
                raise RuntimeError(f"Unknown mode: {self.mode}")
        return None

    def _check_confirmation(self, user_messages: list[Message]) -> tuple[bool, str | None]:
        """Check if user accepted or rejected the proposal.

        Args:
            user_messages: List of user messages.

        Returns:
            Tuple of (True, response) if user accepted the proposal, (False, None) if user rejected the proposal, (False, None) if response is unclear.
        """
        if not user_messages:
            logger.debug("No user response yet, still awaiting confirmation")
            return False, None

        response = user_messages[-1].message
        if "[ACCEPT]" in response:
            logger.info("User ACCEPTED the proposal")
            return True, response
        elif "[REJECT]" in response:
            logger.info("User REJECTED the proposal")
            self.mode = ProactiveAgentMode.OBSERVE
            return False, None
        else:
            logger.warning(f"Unclear response: {response}, still awaiting confirmation")
            return False, None

    def _run_observe_mode(
        self,
        user_messages: list[Message],
        env_notifications: list[Message],
    ) -> str | MMObservation | None:
        """Run the observe agent and check for proposals.

        Args:
            user_messages: List of user messages.
            env_notifications: List of environment notifications.

        Returns:
            Result from the last agent turn execution.
        """
        logger.info("Running in OBSERVE mode")
        # ! TODO: We should add a generic observation task string if user messages is empty. If user sent message, then pass that as a task. Use build_task_from_notifications function for this.
        task = self.build_task_from_notifications(user_messages)
        attachments: list[Attachment] = [attachment for message in user_messages for attachment in message.attachments]
        result = self.observe_agent.run(task=task, hint=None, attachments=attachments)

        proposal_made, proposal_content = self.check_for_proposal()
        if proposal_made:
            logger.info(f"Proactive Agent sent a proposal: {proposal_content}")
            self.mode = ProactiveAgentMode.AWAITING_CONFIRMATION
            self.pending_goal = proposal_content

        return result

    def _run_execute_mode(
        self,
        user_messages: list[Message],
        env_notifications: list[Message],
    ) -> str | MMObservation | None:
        """Run the execute agent and check for completion.

        Args:
            user_messages: List of user messages.
            env_notifications: List of environment notifications.

        Returns:
            Result from the last agent turn execution.

        Raises:
            RuntimeError: If notification system is not set for either observe or execute agent.
        """
        if self.execute_agent.notification_system is None:
            raise RuntimeError("Notification system not set for execute agent")

        if not self.pending_goal:
            raise RuntimeError("Execute mode called without pending_goal")

        task = f"Proposed Goal: {self.pending_goal}"
        task += f"\nUser reply: {self.build_task_from_notifications(user_messages)}"
        attachments: list[Attachment] = [attachment for message in user_messages for attachment in message.attachments]
        result = self.execute_agent.run(task=task, hint=None, attachments=attachments)

        self.mode = ProactiveAgentMode.OBSERVE
        self.pending_goal = None

        return result
