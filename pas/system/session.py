"""Session orchestration helpers tying user proxy and proactive agent together."""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pas.oracles import OracleTracker

if TYPE_CHECKING:  # pragma: no cover - hints only
    from logging import Logger

    from pas.environment import StateAwareEnvironmentWrapper
    from pas.proactive import InterventionResult, ProactiveAgentProtocol
    from pas.scenarios.types import OracleAction
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


MAX_PROACTIVE_ITERATIONS = 32


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
        oracle_actions: list[OracleAction] | None = None,
    ) -> None:
        """Bind environment, user proxy, and agent interfaces for a session."""
        self._env = env
        self._proxy = proxy
        self._agent = agent
        self._decision_maker = decision_maker
        self._confirm_goal = confirm_goal
        self._logger = logger
        self._oracle_tracker = OracleTracker(env, oracle_actions or [])
        self._has_oracles = bool(oracle_actions)

    def run_cycle(self) -> ProactiveCycleResult:
        """Drain notifications, allow the agent to act, and repeat until idle."""
        handled_notifications = self._handle_notifications()

        last_goal: str | None = None
        last_result: InterventionResult | None = None
        last_summary: str | None = None
        accepted = False
        attempted_goals: set[str] = set()

        for _ in range(MAX_PROACTIVE_ITERATIONS):
            if self._has_oracles and self._oracle_tracker.is_satisfied():
                accepted = True
                break

            goal = self._agent.propose_goal()
            if goal is None:
                break

            if goal in attempted_goals:
                raise RuntimeError(f"Repeated proactive goal within a single cycle: {goal}")
            attempted_goals.add(goal)
            last_goal = goal

            decision = self._prompt_goal_confirmation(goal)
            confirmed = self._confirm_goal(goal) if decision is None else decision and self._confirm_goal(goal)

            self._agent.record_decision(goal, confirmed)
            if not confirmed:
                self._logger.info("Goal declined: %s", goal)
                break

            (result, summary, completion_decision, new_notifications, matches_before) = self._execute_confirmed_goal(
                goal, handled_notifications
            )

            last_result = result
            last_summary = summary

            accepted, should_break = self._update_acceptance(completion_decision, accepted)
            if should_break:
                break

            accepted, should_break = self._handle_oracle_state(matches_before, new_notifications, accepted)
            if should_break:
                break
        else:
            raise RuntimeError("Proactive session exceeded iteration budget without satisfying oracles")

        return ProactiveCycleResult(handled_notifications, last_goal, accepted, last_result, last_summary)

    def _execute_confirmed_goal(
        self, goal: str, handled_notifications: list[tuple[str, str]]
    ) -> tuple[InterventionResult, str | None, bool | None, list[tuple[str, str]], int]:
        """Execute a confirmed goal and notify the user about the outcome."""
        matches_before = self._oracle_tracker.match_count
        result = self._agent.execute(goal, self._env)
        summary = self._agent.pop_summary()
        self._agent.handoff(self._env)
        completion_text = summary or result.notes
        completion_decision = self._notify_user_completion(completion_text)
        self._logger.info(
            "Goal executed: %s success=%s notes=%s summary=%s", goal, result.success, result.notes, summary
        )

        new_notifications = self._handle_notifications()
        handled_notifications.extend(new_notifications)
        return result, summary, completion_decision, new_notifications, matches_before

    def _update_acceptance(self, completion_decision: bool | None, current: bool) -> tuple[bool, bool]:
        """Update acceptance flag based on user completion feedback."""
        if completion_decision is None:
            return current, False
        if not completion_decision:
            return False, True
        if not self._has_oracles:
            return True, True
        return True, False

    def _handle_oracle_state(
        self, matches_before: int, new_notifications: list[tuple[str, str]], current: bool
    ) -> tuple[bool, bool]:
        """Ensure oracle progress and decide whether the loop should exit."""
        if not self._has_oracles:
            return current, False
        if self._oracle_tracker.is_satisfied():
            return True, True
        progress = self._oracle_tracker.match_count > matches_before or bool(new_notifications)
        if not progress:
            raise RuntimeError("Proactive intervention ended without satisfying oracle requirements.")
        return current, False

    def _handle_notifications(self) -> list[tuple[str, str]]:
        handled: list[tuple[str, str]] = []
        notifications = self._proxy.consume_notifications()
        for notification in notifications:
            reply = self._proxy.react_to_event(notification)
            handled.append((notification, reply))
            self._logger.info("Notification handled: %s -> %s", notification, reply)
        return handled

    def _prompt_goal_confirmation(self, goal: str) -> bool | None:
        latest_system = self._latest_system_message()
        sections: list[str] = []
        if latest_system:
            sections.append("Latest notification:")
            sections.append(latest_system.strip())
        sections.append("Proposed proactive action:")
        sections.append(goal.strip())
        sections.append("Do you want the assistant to proceed?")
        prompt = "\n\n".join(sections)
        return self._prompt_user(prompt, accept_tokens={"accept"}, decline_tokens={"decline"})

    def _notify_user_completion(self, summary: str | None) -> bool | None:
        if not summary:
            return None
        latest_system = self._latest_system_message()
        sections: list[str] = []
        if latest_system:
            sections.append("Latest notification:")
            sections.append(latest_system.strip())
        sections.append("Proactive assistant completed the request. Summary:")
        sections.append(summary.strip())
        sections.append("Reply ACCEPT to acknowledge or DECLINE if something looks wrong.")
        prompt = "\n\n".join(sections)
        return self._prompt_user(prompt, accept_tokens={"accept"}, decline_tokens={"decline"}, capture_decision=True)

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

    def _latest_system_message(self) -> str | None:
        transcript = getattr(self._proxy, "transcript", ())
        for entry in reversed(transcript):
            if entry.get("role") == "system":
                return entry.get("content")
        return None


__all__ = ["ProactiveCycleResult", "ProactiveSession"]
