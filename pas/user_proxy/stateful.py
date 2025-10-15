"""Stateful user proxy that executes navigational user tools."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Condition
from typing import TYPE_CHECKING

from are.simulation.agents.user_proxy import UserProxy
from are.simulation.types import CompletedEvent, EventType

if TYPE_CHECKING:
    import logging

    from are.simulation.notification_system import BaseNotificationSystem
    from are.simulation.tool_utils import AppTool

    from pas.environment import StateAwareEnvironmentWrapper
else:
    BaseNotificationSystem = object  # type: ignore[assignment]
    AppTool = object  # type: ignore[assignment]
    StateAwareEnvironmentWrapper = object  # type: ignore[assignment]


@dataclass(slots=True)
class ToolInvocation:
    """Represents a concrete tool call executed by the proxy."""

    name: str
    args: dict[str, object]
    result: object | None
    event: CompletedEvent | None = None


class UserActionFailed(RuntimeError):
    """Raised when a user-tool action cannot be completed."""


class TurnLimitReached(RuntimeError):
    """Raised when the maximum number of user turns is exceeded."""


PlannerReturn = Sequence[tuple[str, str, dict[str, object]]]
PlannerCallable = Callable[[str, "StatefulUserProxy"], PlannerReturn]


class StatefulUserProxy(UserProxy):
    """User proxy that keeps track of navigation state via PAS apps."""

    def __init__(
        self,
        env: StateAwareEnvironmentWrapper,
        notification_system: BaseNotificationSystem,
        *,
        max_user_turns: int = 40,
        logger: logging.Logger,
        planner: PlannerCallable | None = None,
        event_timeout: float = 2.0,
    ) -> None:
        """Create a proxy bound to the provided environment and planner."""
        self._env = env
        self._notification_system = notification_system
        self._max_user_turns = max_user_turns
        self._logger = logger
        self._planner = planner
        self._event_timeout = float(event_timeout)

        self._transcript: list[dict[str, str]] = []
        self._recent_events: deque[CompletedEvent] = deque(maxlen=128)
        self._turns_taken = 0
        self._event_condition = Condition()
        self._last_tool_invocations: list[ToolInvocation] = []

        self._env.subscribe_to_completed_events(self._on_event)

    def init_conversation(self) -> str:
        """Reset transcripts and state before starting a new user turn sequence."""
        self._transcript.clear()
        self._recent_events.clear()
        self._last_tool_invocations.clear()
        self._turns_taken = 0
        return ""

    def reply(self, message: str) -> str:
        """Process a message from the agent and return the proxy's response."""
        return self._drive_turn(message, source="agent")

    def react_to_event(self, message: str) -> str:
        """Process a system notification and return the proxy's response."""
        return self._drive_turn(message, source="event")

    @property
    def transcript(self) -> tuple[dict[str, str], ...]:
        """Return the full conversation transcript."""
        return tuple(self._transcript)

    @property
    def last_tool_invocations(self) -> tuple[ToolInvocation, ...]:
        """Return tool invocations executed during the latest turn."""
        return tuple(self._last_tool_invocations)

    def consume_notifications(self) -> list[str]:
        """Drain new notifications for the user proxy."""
        queue = self._notification_system.message_queue
        current_timestamp = datetime.fromtimestamp(self._notification_system.get_current_time(), tz=UTC)

        notifications = queue.get_by_timestamp(current_timestamp)
        messages: list[str] = []
        for notification in notifications:
            text = notification.message
            if not text:
                continue
            if text.startswith("StatefulMessagingApp: New message received"):
                continue
            first_line = text.splitlines()[0] if text.splitlines() else text
            self._logger.info("Notification received (system notification): %s", first_line)
            messages.append(text)
        return messages

    def _plan_actions(self, message: str) -> PlannerReturn:
        if self._planner is None:
            raise UserActionFailed("No planner configured for StatefulUserProxy")
        plan = list(self._planner(message, self))
        if not plan:
            raise UserActionFailed("Unsupported request")
        return plan

    def _drive_turn(self, message: str, *, source: str) -> str:
        if self._turns_taken >= self._max_user_turns:
            raise TurnLimitReached("Maximum number of user turns reached")

        if source not in {"agent", "event"}:
            source = "agent"

        log_prefix = "Agent message received"
        transcript_role = "agent"
        if source == "event":
            log_prefix = "Event notification received"
            transcript_role = "system"

        self._transcript.append({"role": transcript_role, "content": message})
        self._logger.info("%s: %s", log_prefix, message)

        plan = self._plan_actions(message)
        self._logger.info("Planned %d tool invocation(s): %s", len(plan), plan)

        invocations: list[ToolInvocation] = []
        for app_name, method_name, args in plan:
            invocation = self._execute_tool(app_name, method_name, args)
            invocations.append(invocation)

        reply = self._format_reply(invocations)
        self._transcript.append({"role": "user", "content": reply})
        self._turns_taken += 1
        self._last_tool_invocations = invocations
        self._logger.info("User reply: %s", reply)
        return reply

    def _execute_tool(self, app_name: str, method_name: str, args: dict[str, object]) -> ToolInvocation:
        app = self._env.get_app(app_name)
        available = app.get_user_tools()

        tool = self._find_tool(available, method_name, app_name)
        self._logger.info("Executing tool %s.%s with args=%s", app_name, method_name, args)

        start_len = len(self._recent_events)
        bound_target = getattr(tool, "function", None)
        owner = getattr(bound_target, "__self__", None) if bound_target is not None else None

        if bound_target is not None and owner is not None and owner is not getattr(tool, "class_instance", None):
            result = bound_target(**args)
        else:
            result = tool(**args)

        event = None
        if tool.write_operation is True:
            event = self._wait_for_event(start_len)

        invocation = ToolInvocation(name=f"{app_name}.{method_name}", args=dict(args), result=result, event=event)
        self._logger.info("Tool result: %s", invocation)
        return invocation

    def _wait_for_event(self, start_len: int) -> CompletedEvent:
        deadline = time.monotonic() + self._event_timeout
        with self._event_condition:
            while True:
                if len(self._recent_events) > start_len:
                    return self._recent_events[-1]
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise UserActionFailed(f"Tool did not complete within {self._event_timeout:.1f}s")
                self._event_condition.wait(timeout=remaining)

    def _find_tool(self, tools: Sequence[AppTool], method_name: str, app_name: str) -> AppTool:
        for tool in tools:
            if tool.function is not None and tool.function.__name__ == method_name:
                return tool
        raise UserActionFailed(f"Tool '{method_name}' not available in current state of '{app_name}'")

    def _format_reply(self, invocations: Sequence[ToolInvocation]) -> str:
        if not invocations:
            return "No actions were required."
        if len(invocations) == 1 and invocations[0].name == "AgentUserInterface.send_message_to_agent":
            content = invocations[0].args.get("content") if invocations[0].args else None
            if isinstance(content, str) and content:
                return content
        parts = []
        for invocation in invocations:
            fragment = invocation.name
            if invocation.result not in (None, ""):
                fragment = f"{fragment} -> {invocation.result}"
            parts.append(fragment)
        return "Completed: " + ", ".join(parts) + "."

    def _on_event(self, event: CompletedEvent) -> None:
        if event.event_type is not EventType.USER:
            return
        with self._event_condition:
            self._recent_events.append(event)
            self._event_condition.notify_all()
        self._logger.info("User completed event: %s", event)


__all__ = ["PlannerCallable", "StatefulUserProxy", "ToolInvocation", "TurnLimitReached", "UserActionFailed"]
