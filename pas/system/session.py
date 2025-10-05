"""Session orchestration helpers tying user proxy and proactive agent together."""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - hints only
    from logging import Logger

    from pas.environment import StateAwareEnvironmentWrapper
    from pas.proactive import InterventionResult, ProactiveAgentProtocol
    from pas.user_proxy import StatefulUserProxy
    from pas.user_proxy.decision_maker import DecisionMakerProtocol


@dataclass(slots=True)
class ProactiveCycleResult:
    """Structured summary of a single proactive session cycle."""

    notifications: list[tuple[str, str]]
    goal: str | None
    accepted: bool
    result: InterventionResult | None
    summary: str | None


class ProactiveSession:
    """Coordinates notifications, user proxy actions, and proactive execution."""

    def __init__(
        self,
        env: StateAwareEnvironmentWrapper,
        proxy: StatefulUserProxy,
        agent: ProactiveAgentProtocol,
        *,
        decision_maker: DecisionMakerProtocol,
        confirm_goal: typing.Callable[[str], bool],
        logger: Logger,
    ) -> None:
        """Bind environment, user proxy, and agent interfaces for a session."""
        self._env = env
        self._proxy = proxy
        self._agent = agent
        self._decision_maker = decision_maker
        self._confirm_goal = confirm_goal
        self._logger = logger

    def run_cycle(self) -> ProactiveCycleResult:
        """Process notifications, let the agent intervene if appropriate."""
        handled_notifications = self._handle_notifications()

        goal = self._agent.propose_goal()
        if goal is None:
            return ProactiveCycleResult(handled_notifications, None, False, None, None)

        user_decision = self._prompt_goal_confirmation(goal)
        if user_decision is None:
            accepted = self._confirm_goal(goal)
        else:
            accepted = user_decision
            if accepted and not self._confirm_goal(goal):
                accepted = False

        self._agent.record_decision(goal, accepted)
        if not accepted:
            self._logger.info("Goal declined: %s", goal)
            return ProactiveCycleResult(handled_notifications, goal, False, None, None)

        result = self._agent.execute(goal, self._env)
        summary = self._agent.pop_summary()
        self._agent.handoff(self._env)
        self._notify_user_completion(summary or result.notes)
        self._logger.info(
            "Goal executed: %s success=%s notes=%s summary=%s", goal, result.success, result.notes, summary
        )
        return ProactiveCycleResult(handled_notifications, goal, True, result, summary)

    def _handle_notifications(self) -> list[tuple[str, str]]:
        handled: list[tuple[str, str]] = []
        notifications = self._proxy.consume_notifications()
        for notification in notifications:
            reply = self._proxy.react_to_event(notification)
            handled.append((notification, reply))
            self._logger.info("Notification handled: %s -> %s", notification, reply)
        return handled

    def _prompt_goal_confirmation(self, goal: str) -> bool | None:
        prompt = (
            "Proactive assistant suggestion:\n"
            f"{goal}\n"
            "Reply with ACCEPT to let the proactive assistant handle it, or DECLINE to keep control yourself."
        )
        return self._prompt_user(prompt, accept_tokens={"accept"}, decline_tokens={"decline"})

    def _notify_user_completion(self, summary: str | None) -> None:
        if not summary:
            return
        prompt = f"Proactive assistant completed the request. Summary: {summary}\nReply RECEIVED to acknowledge."
        self._prompt_user(prompt, accept_tokens={"received"}, decline_tokens=set(), capture_decision=False)

    def _prompt_user(
        self,
        message: str,
        *,
        accept_tokens: typing.Iterable[str],
        decline_tokens: typing.Iterable[str],
        capture_decision: bool = True,
    ) -> bool | None:
        decision, raw = self._decision_maker.decide(
            message, accept_tokens=accept_tokens, decline_tokens=decline_tokens, capture_decision=capture_decision
        )

        self._logger.info("System prompt response: %s", raw)
        return decision


__all__ = ["ProactiveCycleResult", "ProactiveSession"]
