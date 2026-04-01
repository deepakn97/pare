from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from are.simulation.tool_utils import AppTool, AppToolAdapter, OperationType

from .prompts.execute_prompt import DEFAULT_PROACTIVE_EXECUTE_PROMPT_WITH_HINTS
from .prompts.notification_system import get_observe_notification_system_prompt
from .prompts.observe_prompt import DEFAULT_PROACTIVE_OBSERVE_PROMPT_WITH_HINTS
from .utils import DEFAULT_PROACTIVE_STEP_2_MESSAGE, DEFAULT_PROACTIVE_STEP_2_ROLE, ProactiveAgentMode

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.agents.base_agent import BaseAgent
    from are.simulation.llm_engine import LLMEngine
    from are.simulation.notification_system import BaseNotificationSystem
    from are.simulation.scenarios.scenario import Scenario
    from are.simulation.time_manager import TimeManager
    from are.simulation.tool_utils import Tool
    from are.simulation.types import BaseAgentLog, SimulatedGenerationTimeConfig

    from pas.apps import PASAgentUserInterface

logger = logging.getLogger(__name__)


class SingleAgentProactive:
    """Single agent proactive wrapper with unified history and llm engines for observe and execute modes.

    Unlike ProactiveAgent (separate observe/execute BaseAgents), this wraps ONE BaseAgent and dynamically switches tools based on mode.
    """

    def __init__(
        self,
        log_callback: Callable[[BaseAgentLog], None],
        pause_env: Callable[[], None] | None,
        resume_env: Callable[[float], None] | None,
        llm_engine: LLMEngine,
        base_agent: BaseAgent,
        time_manager: TimeManager,
        tools: list[Tool] | None = None,
        observe_max_iterations: int = 10,
        execute_max_iterations: int = 20,
        max_turns: int | None = None,
        simulated_generation_time_config: SimulatedGenerationTimeConfig | None = None,
        reset_history_on_mode_change: bool = False,
    ) -> None:
        """Initializes the SingleAgentProactive wrapper."""
        if tools is None:
            tools = []

        self.log_callback = log_callback
        self.pause_env = pause_env
        self.resume_env = resume_env
        self.llm_engine = llm_engine
        self.time_manager = time_manager
        self.tools = tools
        self.observe_max_iterations = observe_max_iterations
        self.execute_max_iterations = execute_max_iterations
        self.mode = ProactiveAgentMode.OBSERVE
        self.max_turns = max_turns
        self.simulated_generation_time_config = simulated_generation_time_config

        # BaseAgent arguments
        self.base_agent = base_agent
        self.base_agent.name = "proactive_base_agent"
        self.base_agent.llm_engine = self.llm_engine
        self.base_agent.time_manager = self.time_manager
        self.base_agent.log_callback = self.log_callback
        self.base_agent.simulated_generation_time_config = self.simulated_generation_time_config
        self.base_agent.role_dict = DEFAULT_PROACTIVE_STEP_2_ROLE
        self.base_agent.message_dict = DEFAULT_PROACTIVE_STEP_2_MESSAGE
        self.observe_system_prompt: str | None = None
        self.execute_system_prompt: str | None = None
        # NOTE: We are not setting the max_iterations here because it will be set dynamically based on the mode.

        self._initialized = False

    @property
    def agent_framework(self) -> str:
        """Name of the agent."""
        return "PASSingleAgentProactive"

    @property
    def model(self) -> str:
        """Name of the model."""
        return self.llm_engine.model_name

    def init_tools(self, scenario: Scenario) -> None:
        """Initialize the tools.

        - observe mode: wait + send_message + all read-only tools
        - execute mode: all tools except wait.

        Args:
            scenario: Scenario to initialize the tools for.
        """
        app_tools = self._remove_aui_irrelevant_tools(scenario.get_tools())
        logger.info(f"Found {len(app_tools)} tools: {[tool.name for tool in app_tools]}")
        are_simulation_tools = [AppToolAdapter(tool) for tool in app_tools]
        self.tools += are_simulation_tools

        # Core observe tools (always included in observe mode)
        core_observe_tool_names = ["PASAgentUserInterface__wait", "PASAgentUserInterface__send_message_to_user"]
        observe_tools: list[Tool] = []
        execute_tools: list[Tool] = []
        for tool in self.tools:
            if (
                tool.name in core_observe_tool_names
                or getattr(tool.function, "__operation_type__", OperationType.READ) == OperationType.READ
            ):
                observe_tools.append(tool)
            if tool.name != "PASAgentUserInterface__wait":
                execute_tools.append(tool)

        self.observe_tools = {tool.name: tool for tool in observe_tools}
        self.execute_tools = {tool.name: tool for tool in execute_tools}

    def init_notification_system(self, notification_system: BaseNotificationSystem) -> None:
        """Initialize the notification system.

        Args:
            notification_system: Notification system to initialize.
        """
        if notification_system is not None:
            logger.info(f"Setting notification system for Proactive Agent to provided one {notification_system}")
            self.base_agent.notification_system = notification_system

    # Private methods
    def _remove_aui_irrelevant_tools(self, app_tools: list[AppTool]) -> list[AppTool]:
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

    def _init_system_prompt(self, scenario: Scenario) -> str:
        """Initialize and return the observe system prompt.

        Args:
            scenario: Scenario to initialize the observe system prompt for.

        Returns:
            The initialized observe system prompt.
        """
        prompt = (
            DEFAULT_PROACTIVE_OBSERVE_PROMPT_WITH_HINTS
            if self.mode == ProactiveAgentMode.OBSERVE
            else DEFAULT_PROACTIVE_EXECUTE_PROMPT_WITH_HINTS
        )

        notification_system_prompt = get_observe_notification_system_prompt(
            self.base_agent.notification_system, scenario.apps
        )
        prompt = prompt.replace("<<notification_system_description>>", notification_system_prompt)

        date_str = datetime.fromtimestamp(scenario.start_time or 0, tz=UTC).strftime("%Y-%m-%d %H")
        prompt = prompt.replace("<<curent_time_description>>", f"Today's date in 'YYYY-MM-DD HH' format is {date_str}")
        prompt = prompt.replace("<<agent_reminder_description>>", "")

        return prompt

    def _switch_to_observe_mode(self) -> None:
        """Switch the agent to observe mode.

        Updates the base agent's tools to observe-only tools and sets the max iterations for observe mode.
        """
        self.base_agent.tools = self.observe_tools
        self.base_agent.init_tools()
        self.base_agent.init_system_prompts["system_prompt"] = self.observe_system_prompt
        self.base_agent.system_prompts = self.base_agent.update_system_prompt_tools(
            self.base_agent.init_system_prompts, self.observe_tools
        )
        self.base_agent.max_iterations = self.observe_max_iterations

        self.mode = ProactiveAgentMode.OBSERVE
        logger.debug(f"Switched to OBSERVE mode with {len(self.observe_tools)} tools")

    def _switch_to_execute_mode(self) -> None:
        """Switch the agent to execute mode.

        Updates the base agent's tools to all tools (except wait) and sets the max iterations for execute mode.
        """
        self.base_agent.tools = self.execute_tools
        self.base_agent.init_tools()
        self.base_agent.init_system_prompts["system_prompt"] = self.execute_system_prompt
        self.base_agent.system_prompts = self.base_agent.update_system_prompt_tools(
            self.base_agent.init_system_prompts, self.execute_tools
        )
        self.base_agent.max_iterations = self.execute_max_iterations
        self.mode = ProactiveAgentMode.EXECUTE
        logger.debug(f"Switched to EXECUTE mode with {len(self.execute_tools)} tools")
