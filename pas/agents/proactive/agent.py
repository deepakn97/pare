"""Proactive agent wrapper that manages observe and execute agents.

Wraps two Meta-ARE BaseAgent instances: observer and executer.
Based on meta-are/are/simulation/agents/default_agent/are_simulation_main.py
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from are.simulation.agents.agent_log import TaskLog, ToolCallLog
from are.simulation.agents.default_agent.base_agent import TerminationStep
from are.simulation.notification_system import Message
from are.simulation.tool_utils import AppTool, AppToolAdapter, OperationType

from pas.notification_system import PASMessageType

from .prompts.notification_system import get_execute_notification_system_prompt, get_observe_notification_system_prompt
from .utils import DEFAULT_PROACTIVE_STEP_2_MESSAGE, DEFAULT_PROACTIVE_STEP_2_ROLE, ProactiveAgentMode

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


def stop_condition(agent: BaseAgent) -> bool:
    """Stop the agent if a turn ending tool is called or max iterations is reached.

    Args:
        agent: The agent to stop.
    """
    logs = agent.get_agent_logs()
    turn_ending_tools = ["wait", "send_message_to_user"]
    if agent.iterations >= agent.max_iterations:
        logger.info(f"TERMINATING AGENT {agent.name} DUE TO MAX ITERATIONS {agent.max_iterations}")
        return True
    for log in reversed(logs):
        if isinstance(log, ToolCallLog) and any(name.lower() in log.tool_name.lower() for name in turn_ending_tools):
            logger.info(f"TERMINATING AGENT {agent.name} DUE TO TURN ENDING TOOL {log.tool_name}")
            return True
        if isinstance(log, TaskLog):
            break
    return False


termination_step = TerminationStep(condition=stop_condition)


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
        observe_max_iterations: int = 10,
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
        self.observe_agent.role_dict = DEFAULT_PROACTIVE_STEP_2_ROLE
        self.observe_agent.message_dict = DEFAULT_PROACTIVE_STEP_2_MESSAGE
        self.observe_agent.termination_step = termination_step

        # Execute Agent arguments
        self.execute_llm_engine = execute_llm_engine
        self.execute_agent = execute_agent
        self.execute_agent.name = "execute_base_agent"
        self.execute_agent.max_iterations = execute_max_iterations
        self.execute_agent.llm_engine = self.execute_llm_engine
        self.execute_agent.time_manager = self.time_manager
        self.execute_agent.log_callback = log_callback
        self.execute_agent.role_dict = DEFAULT_PROACTIVE_STEP_2_ROLE
        self.execute_agent.message_dict = DEFAULT_PROACTIVE_STEP_2_MESSAGE
        self.execute_agent.termination_step = termination_step

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

        observe_tool_names = ["PASAgentUserInterface__wait", "PASAgentUserInterface__send_message_to_user"]

        observe_tools: list[AppTool] = []
        execute_tools: list[AppTool] = []
        for tool in app_tools:
            if (
                tool.name in observe_tool_names
                or getattr(tool.function, "__operation_type__", OperationType.READ) == OperationType.READ
            ):
                observe_tools.append(tool)
            if tool.name != "PASAgentUserInterface__wait":
                execute_tools.append(tool)

        if len(observe_tools) == 0:
            raise ValueError("No observe tools found. The observe agent must have the send_message_to_user tool.")
        if len(execute_tools) == 0:
            raise ValueError(
                "No execute tools found. The execute agent must have at least the send_message_to_user tool."
            )
        self.observe_agent.tools = {tool.name: tool for tool in observe_tools}
        self.execute_agent.tools = {tool.name: tool for tool in execute_tools}

        logger.debug(f"Observe agent has {len(observe_tools)} tools: {[tool.name for tool in observe_tools]}")
        logger.debug(f"Execute agent has {len(execute_tools)} tools: {[tool.name for tool in execute_tools]}")

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
        aui_tool = next(tool for tool in app_tools if "PASAgentUserInterface" in tool.name)

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
                "PASAgentUserInterface__get_last_message_from_user",
                "PASAgentUserInterface__get_last_message_from_agent",
                "PASAgentUserInterface__get_last_unread_messages",
                "PASAgentUserInterface__get_all_messages",
            }
            logger.warning(f"Removing tools {tools_to_remove} from app_tools")
            app_tools = [tool for tool in app_tools if tool.name not in tools_to_remove]
        return app_tools

    def get_notifications(self) -> tuple[list[Message], list[Message], list[Message]]:
        """Get new notifications from the custom state, NOT from the notification system.

        Notification system get_by_timestamp() method is destructive and removes messages from the queue. This creates an assymetric view of system notifications for the two agents.

        From the Proactive Agent perspective:
        - user_messages: messages sent by the user to the agent.
        - environment_notifications: Environment events like incoming email, messages etc.
        - env_stop_messages: Environment stop signals

        Returns:
            Tuple of (list of new user messages, list of new environment notifications, list of environment stop messages).
        """
        # new_messages = self.observe_agent.custom_state.get("notifications", [])
        new_messages = self.observe_agent.notification_system.message_queue.get_by_timestamp(
            timestamp=datetime.fromtimestamp(self.time_manager.time(), tz=UTC)
        )

        # Filter for USER_MESSAGE (User messages to Proactive Agent)
        # Note: We check against the string value to support both MessageType and PASMessageType
        user_messages = [message for message in new_messages if message.message_type == PASMessageType.USER_MESSAGE]

        env_notifications = [
            message for message in new_messages if message.message_type == PASMessageType.ENVIRONMENT_NOTIFICATION_AGENT
        ]

        env_stop_messages = [
            message for message in new_messages if message.message_type == PASMessageType.ENVIRONMENT_STOP
        ]
        # Reinsert the env notifications for user and agent + any extra messages back into the notification system.
        # This is important because the preprocessing step and the next agent will use the same notification system.
        # Here we don't need to reinsert the user messages because they are consumed while building the task.
        messages_to_put_back = [m for m in new_messages if m not in user_messages + env_stop_messages]

        logger.info(
            f"Proactive agent get_notifications() -> message types to put back: {'; '.join([m.message_type.value for m in messages_to_put_back])}"
        )
        for message in messages_to_put_back:
            self.observe_agent.notification_system.message_queue.put(message)

        return user_messages, env_notifications, env_stop_messages

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

    def get_turn_ending_tool(self, agent: BaseAgent) -> dict[str, str | None]:
        """Get the turn ending tool from the agent logs.

        Args:
            agent: The agent to get the turn ending tool for.

        Returns:
            The turn ending tool name.
        """
        logs = agent.get_agent_logs()
        for log in reversed(logs):
            if isinstance(log, ToolCallLog):
                tool_name_lower = log.tool_name.lower()
                if "wait" in tool_name_lower:
                    return {"tool_name": "wait", "tool_arguments": None}
                elif "send_message_to_user" in tool_name_lower:
                    content = (
                        log.tool_arguments.get("content", "")
                        if isinstance(log.tool_arguments, dict)
                        else str(log.tool_arguments)
                    )
                    return {"tool_name": "send_message_to_user", "tool_arguments": content}
            if isinstance(log, TaskLog):
                break
        return {}

    def agent_loop(
        self,
        initial_task: str | None = None,
        reset: bool = True,
    ) -> str | MMObservation | None:
        """Execute one proactive agent turn either in observe or execute mode.

        Args:
            initial_task: Initial task to run the agent with.
            reset: Whether to reset the proactive agent.

        Returns:
            Result from the last agent turn execution.

        Raises:
            RuntimeError: If notification system is not set for either observe or execute agent.
        """
        if self.observe_agent.notification_system is None or self.execute_agent.notification_system is None:
            raise RuntimeError("Notification system not set for either observe or execute agent")

        # ? NOTE: Here also we need to put this notification in the custom state and not in the notification system.
        if initial_task is not None:
            self.observe_agent.custom_state.get("notifications", []).append(
                Message(
                    message_type=PASMessageType.USER_MESSAGE,
                    message=initial_task,
                    timestamp=datetime.fromtimestamp(self.time_manager.time(), tz=UTC),
                )
            )

        new_user_messages, new_env_notifications, env_stop_messages = self.get_notifications()
        logger.info(f"New user messages: {new_user_messages}")
        logger.info(f"New environment notifications: {new_env_notifications}")
        logger.info(f"Environment stop messages: {env_stop_messages}")

        if len(env_stop_messages) > 0:
            logger.warning(f"Environment stop message received - Stopping Agent: {env_stop_messages}")
            return None

        task = ""
        if len(new_user_messages) > 0 or len(new_env_notifications) > 0:
            if self.mode == ProactiveAgentMode.OBSERVE:
                result = self._run_observe_mode(new_user_messages, new_env_notifications, reset)
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
        else:
            logger.info("No new messages from user agent or environment. Sleeping for 2 seconds.")
            time.sleep(2)
        return None

    def _check_confirmation(self, user_messages: list[Message]) -> tuple[bool, str | None]:
        """Check if user accepted or rejected the proposal.

        Args:
            user_messages: List of user messages.

        Returns:
            Tuple of (True, response) if user accepted the proposal, (False, None) if user rejected the proposal, (False, None) if response is unclear.
        """
        if not user_messages:
            logger.info("No user response yet, still awaiting confirmation")
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
        reset: bool = True,
    ) -> str | MMObservation | None:
        """Run the observe agent and check for proposals.

        Args:
            user_messages: List of user messages.
            env_notifications: List of environment notifications.
            reset: Whether to reset the observe agent.

        Returns:
            Result from the last agent turn execution.
        """
        logger.info("Running in OBSERVE mode")
        # Reset the internal iterations counter, otherwise after first turn, the agent will exit. And if we increase the number of max_iterations, then the agent will take multiple turns.
        # ! FIXME: Find a better solution for this iterations issue.
        self.observe_agent.iterations = 0

        task = self.build_task_from_notifications(user_messages)
        attachments: list[Attachment] = [attachment for message in user_messages for attachment in message.attachments]
        result = self.observe_agent.run(
            task=task, hint=None, reset=reset, attachments=attachments if attachments else None
        )

        turn_end_reason = self.get_turn_ending_tool(self.observe_agent)
        if turn_end_reason.get("tool_name", "") == "send_message_to_user":
            logger.info(f"Proactive Agent sent a proposal: {turn_end_reason.get('tool_arguments', '')}")
            self.mode = ProactiveAgentMode.AWAITING_CONFIRMATION
            self.pending_goal = turn_end_reason.get("tool_arguments", "")
        elif turn_end_reason.get("tool_name", "") == "wait":
            logger.info("Proactive Agent waited for more information")

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
        self.execute_agent.initialize(attachments=attachments)
        result = self.execute_agent.run(task=task, hint=None, attachments=attachments)

        self.mode = ProactiveAgentMode.OBSERVE
        self.pending_goal = None

        return result
