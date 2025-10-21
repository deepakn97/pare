"""Proactive agent protocol and lightweight implementations."""

from __future__ import annotations

import typing
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from are.simulation.types import CompletedEvent, EventType

from pas.llm_adapter import LLMClientProtocol

if TYPE_CHECKING:
    from logging import Logger

    from pas.environment import StateAwareEnvironmentWrapper
else:
    Logger = object  # type: ignore[assignment]
    StateAwareEnvironmentWrapper = object  # type: ignore[assignment]


@dataclass(slots=True)
class InterventionResult:
    """Represents the outcome of a proactive intervention."""

    success: bool
    notes: str
    metadata: dict[str, object] | None = None


class ProactiveInterventionError(RuntimeError):
    """Raised when an autonomous intervention fails."""


class ProactiveAgentProtocol(Protocol):
    """Contract that all proactive agents must follow."""

    def observe(self, event: CompletedEvent) -> None:
        """Receive an event emitted by the environment."""

    def propose_goal(self) -> str | None:
        """Return a human readable goal hypothesis, or ``None`` if undecided."""

    def record_decision(self, task_guess: str, accepted: bool) -> None:
        """Record whether the user accepted the proposed goal."""

    def execute(self, task_guess: str, env: StateAwareEnvironmentWrapper) -> InterventionResult:
        """Execute an intervention for the confirmed task."""

    def handoff(self, env: StateAwareEnvironmentWrapper) -> None:
        """Restore environment state before giving control back to the user."""

    def pop_summary(self) -> str | None:
        """Return the most recent intervention summary, consuming it."""


class LLMBasedProactiveAgent(ProactiveAgentProtocol):
    """A lightweight LLM-backed proactive agent implementation.

    The agent keeps a bounded history of completed events, builds a prompt for an
    LLM, and defers execution to a user-provided callable. This keeps the class
    flexible enough for tests while matching the documented public contract.
    """

    def __init__(
        self,
        llm: LLMClientProtocol,
        *,
        system_prompt: str,
        max_context_events: int,
        plan_executor: typing.Callable[[str, StateAwareEnvironmentWrapper], InterventionResult],
        summary_builder: typing.Callable[[InterventionResult], str],
        logger: Logger,
    ) -> None:
        """Initialise the agent with shared dependencies."""
        self._llm = llm
        self._system_prompt = system_prompt.strip()
        self._events: deque[CompletedEvent] = deque(maxlen=max_context_events)
        self._plan_executor = plan_executor
        self._summary_builder = summary_builder
        self._pending_summary: str | None = None
        self._last_task: str | None = None
        self._logger = logger

    def observe(self, event: CompletedEvent) -> None:
        """Store a completed event for later prompting."""
        if len(self._events) == self._events.maxlen:
            self._events.popleft()
        self._events.append(event)
        self._logger.info("Observed event: %s.%s (%s)", event.app_name(), event.function_name(), event.event_type)

    def propose_goal(self) -> str | None:
        """Generate a proactive goal proposal via the LLM."""
        if not self._events:
            self._logger.info("No events available to propose a goal")
            return None

        prompt = self._build_goal_prompt(self._events)
        self._logger.debug("LLM prompt:\n%s", prompt)
        response = self._llm.complete(prompt)
        goal = self._parse_goal(response)
        self._logger.info("LLM prompt built with %d events", len(self._events))
        self._logger.info("LLM response: %s", response)

        if goal is None:
            self._logger.info("LLM returned no actionable goal")
            return None

        self._last_task = goal
        self._logger.info("Proposed goal: %s", goal)
        return goal

    def record_decision(self, task_guess: str, accepted: bool) -> None:
        """Note whether the user accepted the proposed goal."""
        if not accepted:
            self._pending_summary = "User declined proactive assistance."
            self._last_task = None
        else:
            self._last_task = task_guess
        self._logger.info("Decision recorded for '%s': accepted=%s", task_guess, accepted)

    def execute(self, task_guess: str, env: StateAwareEnvironmentWrapper) -> InterventionResult:
        """Run the orchestrated plan for the accepted goal."""
        self._logger.info("Executing plan for task: %s", task_guess)
        result = self._plan_executor(task_guess, env)
        summary = self._summary_builder(result)
        self._pending_summary = summary
        self._logger.info("Execution result: success=%s, notes=%s", result.success, result.notes)
        return result

    def handoff(self, env: StateAwareEnvironmentWrapper) -> None:
        """Clear transient state after executing the plan."""
        self._last_task = None
        self._logger.info("Handoff completed")

    def pop_summary(self) -> str | None:
        """Return the cached execution summary, if any."""
        summary = self._pending_summary
        self._pending_summary = None
        if summary:
            self._logger.info("Summary delivered: %s", summary)
        return summary

    def _build_goal_prompt(self, events: typing.Iterable[CompletedEvent]) -> str:
        """Construct the goal-prompt string sent to the LLM."""
        lines: list[str] = []
        if self._system_prompt:
            lines.append(self._system_prompt)
        lines.append("Recent events:")
        for event in events:
            direction = "USER" if event.event_type is EventType.USER else event.event_type.value
            return_value = event.metadata.return_value if event.metadata else None
            lines.append(
                f"- [{direction}] {event.app_name()}.{event.function_name()} "
                f"args={event.action.args} return={return_value}"
            )
        if self._last_task:
            lines.append(f"Previous hypothesis: {self._last_task}")
        lines.append(
            "Respond with the next user goal suggestion or 'none'. "
            "If you are not confident, answer 'none'—guessing wrong will frustrate the user."
        )
        return "\n".join(lines)

    @staticmethod
    def _parse_goal(response: str) -> str | None:
        """Normalise LLM output into a usable goal string."""
        cleaned = response.strip()
        if not cleaned or cleaned.lower() == "none":
            return None
        return cleaned


__all__ = [
    "InterventionResult",
    "LLMBasedProactiveAgent",
    "LLMClientProtocol",
    "ProactiveAgentProtocol",
    "ProactiveInterventionError",
]
