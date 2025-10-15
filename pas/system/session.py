"""Session orchestration helpers tying user proxy and proactive agent together."""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pas.oracles import OracleTracker

if TYPE_CHECKING:  # pragma: no cover - hints only
    from logging import Logger

    from pas.apps.proactive_agent_ui import ProactiveAgentUserInterface
    from pas.environment import StateAwareEnvironmentWrapper
    from pas.proactive import InterventionResult, ProactiveAgentProtocol
    from pas.scenarios.types import OracleAction
    from pas.user_proxy import StatefulUserProxy


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
        agent_ui: ProactiveAgentUserInterface,
        *,
        confirm_goal: typing.Callable[[str], bool],
        logger: Logger,
        oracle_actions: list[OracleAction] | None = None,
    ) -> None:
        """Bind environment, user proxy, and agent interfaces for a session."""
        self._env = env
        self._proxy = proxy
        self._agent = agent
        self._agent_ui = agent_ui
        self._confirm_goal = confirm_goal
        self._logger = logger
        self._oracle_tracker = OracleTracker(env, oracle_actions or [])
        self._has_oracles = bool(oracle_actions)

        # Connect AgentUserInterface to proxy
        self._agent_ui.user_proxy = proxy

    def run_cycle(self) -> ProactiveCycleResult:
        """Drain notifications, allow the agent to act, and repeat until idle."""
        handled_notifications: list[tuple[str, str]] = []
        last_goal: str | None = None
        last_result: InterventionResult | None = None
        last_summary: str | None = None
        accepted = False
        attempted_goals: set[str] = set()
        pending_notifications = self._proxy.consume_notifications()

        for _ in range(MAX_PROACTIVE_ITERATIONS):
            if self._has_oracles and self._oracle_tracker.is_satisfied():
                accepted = True
                break

            goal = self._agent.propose_goal()
            if goal is None:
                handled_notifications.extend(self._handle_notifications(pending_notifications))
                break

            if goal in attempted_goals:
                raise RuntimeError(f"Repeated proactive goal within a single cycle: {goal}")
            attempted_goals.add(goal)
            last_goal = goal

            decision, newly_handled = self._prompt_goal_confirmation(goal, pending_notifications)
            handled_notifications.extend(newly_handled)
            pending_notifications.extend(self._proxy.consume_notifications())
            if decision is None:
                raise RuntimeError(f"User decision was not captured for goal: {goal}")
            confirmed = decision and self._confirm_goal(goal)

            self._agent.record_decision(goal, confirmed)
            if not confirmed:
                self._logger.info("Goal declined: %s", goal)
                break

            result, summary, completion_decision = self._execute_confirmed_goal(goal, handled_notifications)

            requires_ack = bool(summary or getattr(result, "notes", None))
            if requires_ack and completion_decision is None:
                raise RuntimeError("User failed to acknowledge proactive completion summary")

            last_result = result
            last_summary = summary

            accepted, should_break = self._update_acceptance(completion_decision, accepted)
            if should_break:
                break
        else:
            raise RuntimeError("Proactive session exceeded iteration budget without satisfying oracles")

        handled_notifications.extend(self._handle_notifications(pending_notifications))

        cycle = ProactiveCycleResult(handled_notifications, last_goal, accepted, last_result, last_summary)
        self._validate_cycle_outcome(cycle)
        return cycle

    def _execute_confirmed_goal(
        self, goal: str, handled_notifications: list[tuple[str, str]]
    ) -> tuple[InterventionResult, str | None, bool | None]:
        """Execute a confirmed goal and notify the user about the outcome."""
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
        return result, summary, completion_decision

    def _update_acceptance(self, completion_decision: bool | None, current: bool) -> tuple[bool, bool]:
        """Update acceptance flag based on user completion feedback."""
        if completion_decision is None:
            return current, False
        if not completion_decision:
            return False, True
        if not self._has_oracles:
            return True, True
        return True, False

    def _validate_cycle_outcome(self, cycle: ProactiveCycleResult) -> None:
        """Enforce oracle satisfaction and proactive contract guarantees."""
        if self._has_oracles and not self._oracle_tracker.is_satisfied():
            raise RuntimeError("Proactive session completed without satisfying oracle requirements.")
        if cycle.goal is None:
            raise RuntimeError("Proactive session ended without proposing a proactive goal.")
        if not cycle.accepted:
            raise RuntimeError("Proactive session ended without an accepted proactive plan.")
        if cycle.result is None:
            raise RuntimeError("Proactive session ended without executing the accepted plan.")
        if not cycle.result.success:
            raise RuntimeError(f"Proactive intervention reported failure: {cycle.result.notes}")

    def _handle_notifications(self, prefetched: list[str] | None = None) -> list[tuple[str, str]]:
        handled: list[tuple[str, str]] = []
        if prefetched is not None:
            notifications = list(prefetched)
            prefetched.clear()
        else:
            notifications = self._proxy.consume_notifications()
        for notification in notifications:
            reply = self._proxy.react_to_event(notification)
            handled.append((notification, reply))
            self._logger.info("Notification handled: %s -> %s", notification, reply)
        return handled

    def _prompt_goal_confirmation(
        self, goal: str, pending_notifications: list[str]
    ) -> tuple[bool | None, list[tuple[str, str]]]:
        """Send proposal to user through AgentUI and wait for response."""
        # Send proposal as a notification
        self._agent_ui.send_proposal_to_user(goal)
        self._logger.info("Sent proposal to user: %s", goal)

        # Ensure any pending notifications (existing or new) are processed by the user proxy
        pending_notifications.extend(self._proxy.consume_notifications())
        handled = self._handle_notifications(pending_notifications)

        # Check if user accepted or declined
        if self._agent_ui.pending_proposal is None and self._agent_ui.proposal_history:
            # Proposal was handled (accepted or declined)
            # Check the last action in proposal_history
            last_proposal, was_accepted = self._agent_ui.proposal_history[-1]
            if last_proposal.goal == goal:
                return was_accepted, handled

        # No decision yet - user might have ignored it or done something else
        return None, handled

    def _notify_user_completion(self, summary: str | None) -> bool | None:
        """Notify user of completion - for now just log it."""
        if not summary:
            return None
        self._logger.info("Proactive action completed: %s", summary)
        # User doesn't need to explicitly acknowledge completion
        return True


__all__ = ["ProactiveCycleResult", "ProactiveSession"]
