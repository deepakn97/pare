"""Stateful user agent built on Meta ARE infrastructure with PAS runtime glue."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Condition
from typing import TYPE_CHECKING, Any, Protocol, cast

from are.simulation.agents.default_agent.base_agent import BaseAgent, BaseAgentLog
from are.simulation.agents.default_agent.termination_methods.are_simulation import (
    termination_step_are_simulation_final_answer,
)
from are.simulation.agents.default_agent.tools.json_action_executor import JsonActionExecutor, ParsedAction
from are.simulation.agents.llm.llm_engine import LLMEngine
from are.simulation.agents.user_proxy import UserProxy

from pas.llm_adapter import LLMClientProtocol, PasLLMEngine

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.notification_system import BaseNotificationSystem
    from are.simulation.tools import Tool
    from are.simulation.types import CompletedEvent


@dataclass(slots=True)
class ToolInvocation:
    """Tool invocation metadata captured during a single turn."""

    app: str
    method: str
    args: dict[str, Any]
    result: Any | None = None
    event: CompletedEvent | None = None


class UserAgentProtocol(Protocol):
    """Public contract for user-agent implementations consumed by higher layers."""

    def init_conversation(self) -> str:
        """Initialize or reset the conversation state."""

    def reply(self, message: str) -> str:
        """Process a user message and return the agent's response."""

    def react_to_event(self, message: str) -> str:
        """React to a system event and return the agent's response."""

    def consume_notifications(self) -> list[str]:
        """Consume pending notifications from the notification system."""

    @property
    def transcript(self) -> list[dict[str, str]]:
        """Get the conversation transcript."""

    @property
    def last_tool_invocations(self) -> tuple[ToolInvocation, ...]:
        """Get tool invocations from the last turn."""


class _CallableLLMWrapper(LLMClientProtocol):
    """Wrap a bare callable to satisfy LLMClientProtocol for PasLLMEngine."""

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    def complete(self, prompt: str) -> str:
        result = self.func(prompt)
        return str(result) if result is not None else ""

    def complete_with_metadata(self, prompt: str, *, temperature: float | None = None) -> tuple[str, dict[str, object]]:
        return self.complete(prompt), {}


class TurnLimitReached(RuntimeError):
    """Raised when the proxy exhausted the configured turn budget."""


class PasJsonActionExecutor(JsonActionExecutor):
    """JsonActionExecutor that records PAS tool metadata and waits for CompletedEvents."""

    def __init__(
        self, *, tools: dict[str, Tool] | None = None, wait_timeout: float = 2.0, use_custom_logger: bool = True
    ) -> None:
        super().__init__(tools=tools or {}, use_custom_logger=use_custom_logger)
        self.runtime: StatefulUserAgentRuntime | None = None
        self.agent: StatefulUserAgent | None = None
        self.wait_timeout = wait_timeout

    def set_runtime(self, runtime: StatefulUserAgentRuntime | None) -> None:
        self.runtime = runtime

    def set_agent(self, agent: StatefulUserAgent | None) -> None:
        self.agent = agent

    @staticmethod
    def _split_tool_name(tool_name: str) -> tuple[str, str]:
        if "__" in tool_name:
            app, method = tool_name.split("__", 1)
            return app, method
        return tool_name, ""

    def execute_tool_call(
        self,
        parsed_action: ParsedAction,
        append_agent_log: Callable[[BaseAgentLog], None],
        make_timestamp: Callable[[], float],
    ) -> Any:  # noqa: ANN401
        runtime = self.runtime
        previous_count = runtime.event_count if runtime is not None else 0
        observation = super().execute_tool_call(parsed_action, append_agent_log, make_timestamp)

        tool_name = parsed_action.tool_name or ""
        arguments = parsed_action.arguments if isinstance(parsed_action.arguments, dict) else {}
        app_name, method_name = self._split_tool_name(tool_name)

        tool = self.tools.get(tool_name)
        event: CompletedEvent | None = None
        # Skip event waiting for final_answer tool (termination signal)
        # Always wait for all other tool calls to ensure state transitions complete
        if runtime is not None and tool is not None and tool_name != "final_answer":
            try:
                event = runtime.wait_for_completed_event(previous_count, timeout=self.wait_timeout)
            except TimeoutError as error:
                runtime.logger.warning("Timed out waiting for completion after tool %s: %s", tool_name, error)

        invocation = ToolInvocation(
            app=app_name, method=method_name or tool_name, args=dict(arguments), result=observation, event=event
        )
        if self.agent is not None:
            self.agent.record_tool_invocation(invocation)
        return observation


class StatefulUserAgent(BaseAgent):
    """User agent built on Meta ARE's BaseAgent with PAS-specific state handling."""

    def __init__(
        self,
        llm_engine: LLMClientProtocol | LLMEngine | Callable[..., Any],
        tools: dict[str, Tool] | None = None,
        system_prompts: dict[str, str] | None = None,
        *,
        max_iterations: int = 10,
        max_turns: int = 40,
        wait_timeout: float = 2.0,
        **kwargs: Any,
    ) -> None:
        """Initialize the stateful user agent.

        Args:
            llm_engine: LLM engine or client for generating responses.
            tools: Dictionary of available tools indexed by name.
            system_prompts: System prompts for the agent.
            max_iterations: Maximum iterations per turn.
            max_turns: Maximum number of conversation turns.
            wait_timeout: Timeout for waiting on completed events.
            **kwargs: Additional arguments passed to BaseAgent.
        """
        self.logger = logging.getLogger(__name__)
        prepared_prompts = dict(system_prompts or {"system_prompt": self._default_system_prompt()})
        llm_engine = self._wrap_llm_engine(llm_engine)

        # Note: final_answer tool is injected in scenarios/base.py, not here
        all_tools = dict(tools or {})

        self.executor = PasJsonActionExecutor(tools=all_tools, wait_timeout=wait_timeout)
        super().__init__(
            llm_engine=llm_engine,
            system_prompts=prepared_prompts,
            tools=all_tools,
            action_executor=self.executor,
            max_iterations=max_iterations,
            **kwargs,
        )
        self.name = "stateful_user_agent"
        self.base_system_prompt = prepared_prompts.get("system_prompt", "")
        self.max_turns = max(1, int(max_turns))
        self.turns_taken = 0
        self.transcript_history: list[dict[str, str]] = []
        self.tool_history_list: list[ToolInvocation] = []
        self.current_turn_invocations: list[ToolInvocation] = []
        self.last_tool_invocations_tuple: tuple[ToolInvocation, ...] = ()
        self.runtime: StatefulUserAgentRuntime | None = None
        self.executor.set_agent(self)

        # Use native Meta ARE termination step for final_answer
        self.termination_step = termination_step_are_simulation_final_answer()

    # --------------------------------------------------------------------- #
    # Runtime wiring
    # --------------------------------------------------------------------- #
    def attach_runtime(self, runtime: StatefulUserAgentRuntime | None) -> None:
        """Attach the runtime responsible for event routing and notifications."""
        self.runtime = runtime
        self.executor.set_runtime(runtime)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    @property
    def transcript(self) -> list[dict[str, str]]:
        """Get a copy of the conversation transcript."""
        return list(self.transcript_history)

    @property
    def tool_history(self) -> list[ToolInvocation]:
        """Get a copy of the complete tool invocation history."""
        return list(self.tool_history_list)

    @property
    def last_tool_invocations(self) -> tuple[ToolInvocation, ...]:
        """Get tool invocations from the last turn."""
        return self.last_tool_invocations_tuple

    def init_conversation(self) -> str:
        """Initialize or reset the conversation state."""
        """Initialize or reset the conversation state."""
        self.turns_taken = 0
        self.transcript_history.clear()
        self.tool_history_list.clear()
        self.last_tool_invocations_tuple = ()
        return ""

    def consume_notifications(self) -> list[str]:
        """Consume pending notifications from the notification system."""
        """Consume pending notifications from the notification system."""
        if self.notification_system is None:
            return []
        queue = self.notification_system.message_queue
        current_timestamp = datetime.fromtimestamp(self.notification_system.get_current_time(), tz=UTC)
        notifications = queue.get_by_timestamp(current_timestamp)
        payloads: list[str] = []
        for notification in notifications:
            text = notification.message
            if not text:
                continue
            payloads.append(text)
        return payloads

    def react_to_event(self, message: str) -> str:
        """React to a system event and return the agent's response."""
        """React to a system event and return the agent's response."""
        return self._handle_turn(message, source="system")

    def reply(self, message: str) -> str:
        """Process a user message and return the agent's response."""
        """Process a user message and return the agent's response."""
        return self._handle_turn(message, source="agent")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _handle_turn(self, message: str, source: str) -> str:
        cleaned_message = message.strip()
        role = "agent" if source == "agent" else "system"
        if cleaned_message:
            self.transcript_history.append({"role": role, "content": cleaned_message})

        self._begin_turn()
        try:
            result = self.run(task=cleaned_message)
        finally:
            self._finalise_turn()

        reply_text = str(result) if result is not None else "No response"
        self.transcript_history.append({"role": "user", "content": reply_text})
        self.turns_taken += 1
        return reply_text

    def _begin_turn(self) -> None:
        self.current_turn_invocations = []

    def _finalise_turn(self) -> None:
        self.last_tool_invocations_tuple = tuple(self.current_turn_invocations)
        self.tool_history_list.extend(self.current_turn_invocations)

    def record_tool_invocation(self, invocation: ToolInvocation) -> None:
        """Record a tool invocation for the current turn."""
        self.current_turn_invocations.append(invocation)

    def update_tools_for_app(self, app_name: str, new_tools: list[Tool]) -> None:
        """Update tools for a specific app and refresh system prompt.

        This is called by Environment when a StatefulApp transitions state.

        Args:
            app_name: Name of the app that updated
            new_tools: New list of tools for this app
        """
        # Update the tool dictionary
        for tool in new_tools:
            self.tools[tool.name] = tool

        # Update the action executor
        if hasattr(self, "action_executor"):
            self.action_executor.update_tools(self.tools)

        # Refresh system prompt with updated tool descriptions
        self._refresh_system_prompt_tools()

        self.logger.debug("Updated tools for app %s: %d tools total", app_name, len(self.tools))

    def _refresh_system_prompt_tools(self) -> None:
        """Update system prompt with current tool descriptions."""
        from are.simulation.tool_box import DEFAULT_TOOL_DESCRIPTION_TEMPLATE, Toolbox

        toolbox = Toolbox(list(self.tools.values()))
        tool_descriptions = toolbox.show_tool_descriptions(DEFAULT_TOOL_DESCRIPTION_TEMPLATE)

        # Replace tool descriptions in system prompt
        current_prompt = self.init_system_prompts.get("system_prompt", "")
        if "<<tool_descriptions>>" in current_prompt:
            updated_prompt = current_prompt.replace("<<tool_descriptions>>", tool_descriptions)
            self.init_system_prompts["system_prompt"] = updated_prompt

    def update_system_context(self, *, active_app: str | None, message: str | None, source: str) -> None:
        """Update system prompt with lightweight contextual hints for the next turn."""
        context_parts: list[str] = []
        if active_app:
            context_parts.append(f"app={active_app}")
        if source == "system" and message:
            preview = message.strip().replace("\n", " ")
            context_parts.append(f"notification={preview[:160]}")
        elif source == "agent" and message:
            snippet = message.strip().replace("\n", " ")
            context_parts.append(f"agent_message={snippet[:160]}")

        if context_parts:
            context_text = "Current context: " + ", ".join(context_parts) + "."
            updated_prompt = f"{self.base_system_prompt}\n\n{context_text}"
        else:
            updated_prompt = self.base_system_prompt

        self.init_system_prompts["system_prompt"] = updated_prompt

    def _wrap_llm_engine(self, candidate: LLMClientProtocol | LLMEngine | Callable[..., Any]) -> LLMEngine:
        if isinstance(candidate, LLMEngine):
            return candidate
        if hasattr(candidate, "complete"):
            return PasLLMEngine(cast("LLMClientProtocol", candidate), logger=self.logger)
        return PasLLMEngine(_CallableLLMWrapper(candidate), logger=self.logger)

    @staticmethod
    def _default_system_prompt() -> str:
        return """You are an AI user agent that interacts with other agents on behalf of a human user.

Your role is to:
1. Receive messages from other agents
2. Determine appropriate actions based on available tools
3. Execute actions and respond to agents

Key principles:
- Always think step by step and explain your reasoning
- Be concise and clear in your communications
- Only use the tools provided to you

Available tools: <<tool_descriptions>>

Current time: <<curent_time_description>>
Notification system: <<notification_system_description>>

IMPORTANT: You MUST follow this exact format for every response:

Thought: [Your reasoning about what to do next]
Action:
{"action": "tool_name", "action_input": {"param1": "value1", "param2": "value2"}}<end_action>

After each action, you will receive an observation. Continue the cycle:
Thought: [Analysis of the observation]
Action:
{"action": "next_tool", "action_input": {...}}<end_action>

When you've completed the task, use the final_answer tool:
Thought: [Brief summary of what was accomplished]
Action:
{"action": "final_answer", "action_input": {"answer": "Summary of task completion"}}<end_action>

Remember, you are representing a human user, so act accordingly."""


class StatefulUserAgentRuntime(UserProxy):
    """Coordinates environment events, notifications, and tool completions."""

    def __init__(
        self,
        *,
        agent: StatefulUserAgent,
        notification_system: BaseNotificationSystem,
        logger: logging.Logger,
        max_user_turns: int = 40,
        event_timeout: float = 2.0,
    ) -> None:
        """Initialize the user agent runtime.

        Args:
            agent: The underlying StatefulUserAgent.
            notification_system: Notification system for the agent.
            logger: Logger for the runtime.
            max_user_turns: Maximum number of conversation turns.
            event_timeout: Timeout for waiting on completed events.
        """
        self.agent = agent
        self.notification_system = notification_system
        self.logger = logger
        self.max_user_turns = max(1, int(max_user_turns))
        self.event_timeout = event_timeout
        self.event_condition = Condition()
        self.recent_events: deque[CompletedEvent] = deque(maxlen=256)
        self.agent.notification_system = notification_system
        self.agent.attach_runtime(self)

    # ------------------------------------------------------------------ #
    # Public facade
    # ------------------------------------------------------------------ #
    def init_conversation(self) -> str:
        """Initialize or reset the conversation state."""
        with self.event_condition:
            self.recent_events.clear()
        return self.agent.init_conversation()

    def reply(self, message: str) -> str:
        """Process a user message and return the agent's response."""
        self._enforce_turn_budget()
        self._prepare_prompt(message, source="agent")
        return self.agent.reply(message)

    def react_to_event(self, message: str) -> str:
        """React to a system event and return the agent's response."""
        self._enforce_turn_budget()
        self._prepare_prompt(message, source="system")
        return self.agent.react_to_event(message)

    def consume_notifications(self) -> list[str]:
        """Consume pending notifications from the notification system."""
        return self.agent.consume_notifications()

    @property
    def last_tool_invocations(self) -> tuple[ToolInvocation, ...]:
        """Get tool invocations from the last turn."""
        return self.agent.last_tool_invocations

    @property
    def transcript(self) -> list[dict[str, str]]:
        """Get the conversation transcript."""
        return self.agent.transcript

    @property
    def event_count(self) -> int:
        """Get the number of recent events."""
        with self.event_condition:
            return len(self.recent_events)

    def wait_for_completed_event(self, previous_count: int, timeout: float | None = None) -> CompletedEvent:
        """Block until a new CompletedEvent arrives after the given counter."""
        deadline = time.monotonic() + (timeout if timeout is not None else self.event_timeout)
        with self.event_condition:
            while len(self.recent_events) <= previous_count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"No completed event received within {self.event_timeout:.1f}s")
                self.event_condition.wait(timeout=remaining)
            return self.recent_events[-1]

    def reset(self) -> None:
        """Reset the event queue."""
        with self.event_condition:
            self.recent_events.clear()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _enforce_turn_budget(self) -> None:
        if self.agent.turns_taken >= self.max_user_turns:
            raise TurnLimitReached("Maximum user turns exhausted")

    def _on_event(self, event: CompletedEvent) -> None:
        """Record completed events for synchronization.

        Tool refreshing is now handled by Environment.
        """
        with self.event_condition:
            self.recent_events.append(event)
            self.event_condition.notify_all()
        self.logger.debug(
            "Completed event observed: app=%s function=%s type=%s",
            event.app_name(),
            event.function_name(),
            event.event_type,
        )

    def _prepare_prompt(self, message: str, source: str) -> None:
        active_app = self._infer_active_app()
        self.agent.update_system_context(active_app=active_app, message=message or None, source=source)

    def _infer_active_app(self) -> str | None:
        invocations = self.agent.last_tool_invocations
        for invocation in reversed(invocations):
            if invocation.app == "system":
                if invocation.method == "open_app":
                    target = invocation.args.get("app_name") if invocation.args else None
                    if isinstance(target, str):
                        return target
                if invocation.method == "go_home":
                    return None
                continue
            if invocation.app:
                return invocation.app
        return None


__all__ = ["StatefulUserAgent", "StatefulUserAgentRuntime", "ToolInvocation", "TurnLimitReached", "UserAgentProtocol"]
