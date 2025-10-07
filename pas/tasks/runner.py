"""Helpers to execute tasks and validate oracle expectations."""

from __future__ import annotations

import logging
import typing as t
from typing import TYPE_CHECKING

from pas.oracles import event_matches
from pas.system import ProactiveSession
from pas.tasks.types import OracleCheckResult, TaskContext, TaskDefinition, TaskRunResult

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from are.simulation.types import CompletedEvent

    from pas.environment import StateAwareEnvironmentWrapper
    from pas.scenarios.types import OracleAction


def run_task(definition: TaskDefinition, context: TaskContext) -> TaskRunResult:
    """Execute a task by building its scenario and running a single proactive cycle."""
    setup = definition.scenario_builder(context)
    env, proxy, agent, decision_maker = setup

    session = ProactiveSession(
        env,
        proxy,
        agent,
        decision_maker=decision_maker,
        confirm_goal=lambda goal: True,
        logger=logging.getLogger(f"pas.tasks.{definition.task_id}"),
        oracle_actions=setup.oracle_actions,
    )

    proxy.init_conversation()
    cycle = session.run_cycle()

    oracle_checks = evaluate_oracles(env, setup.oracle_actions)
    return TaskRunResult(task=definition, setup=setup, cycle=cycle, oracle_checks=oracle_checks)


def evaluate_oracles(
    env: StateAwareEnvironmentWrapper, oracle_actions: t.Sequence[OracleAction]
) -> list[OracleCheckResult]:
    """Simple matcher between completed events and oracle expectations."""
    if not oracle_actions:
        return []

    event_log = getattr(env, "event_log", None)
    if event_log is None:
        raise AttributeError("StateAwareEnvironmentWrapper missing event_log for oracle evaluation")
    completed_events = list(event_log.list_view())

    matches: list[OracleCheckResult] = []
    for oracle in oracle_actions:
        matched_event = _find_first_match(completed_events, oracle)
        matches.append(
            OracleCheckResult(oracle=oracle, satisfied=matched_event is not None, matched_event=matched_event)
        )
    return matches


def _find_first_match(events: t.Iterable[CompletedEvent], oracle: OracleAction) -> CompletedEvent | None:
    return next((event for event in events if event_matches(event, oracle)), None)


__all__ = ["evaluate_oracles", "run_task"]
