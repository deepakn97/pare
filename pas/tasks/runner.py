"""Helpers to execute tasks and validate oracle expectations."""

from __future__ import annotations

import logging
import typing as t
from typing import TYPE_CHECKING

from pas.system import ProactiveSession
from pas.tasks.types import OracleCheckResult, TaskContext, TaskDefinition, TaskRunResult

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
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

    matches = []
    for oracle in oracle_actions:
        matched_event = _find_matching_event(completed_events, oracle)
        matches.append(
            OracleCheckResult(oracle=oracle, satisfied=matched_event is not None, matched_event=matched_event)
        )
    return matches


def _find_matching_event(events: t.Iterable[CompletedEvent], oracle: OracleAction) -> CompletedEvent | None:
    for event in events:
        if event.app_name() != oracle.app:
            continue
        if event.function_name() != oracle.function:
            continue
        event_args = _normalise_args(event.action.args if event.action else {})
        expected_args = oracle.args or {}
        if all(_args_equal(event_args.get(key), value) for key, value in expected_args.items()):
            return event
    return None


def _normalise_args(args: dict[str, object]) -> dict[str, object]:
    normalised: dict[str, object] = {}
    for key, value in args.items():
        if key == "self":
            continue
        normalised[key] = _normalise_value(value)
    return normalised


def _normalise_value(value: object) -> object:
    if isinstance(value, dict) and "value" in value and len(value) == 1:
        return _normalise_value(value["value"])
    if isinstance(value, dict):
        return {k: _normalise_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalise_value(v) for v in value]
    # Handle enums (EmailFolderName etc.)
    if hasattr(value, "value") and not isinstance(value, str | bytes):
        enum_value = value.value
        if enum_value is not None:
            return enum_value
    return value


def _args_equal(found: object | None, expected: object) -> bool:
    if isinstance(expected, list):
        return (
            isinstance(found, list)
            and len(found) == len(expected)
            and all(_args_equal(f, e) for f, e in zip(found, expected, strict=False))
        )
    if isinstance(expected, dict):
        return isinstance(found, dict) and all(_args_equal(found.get(k), v) for k, v in expected.items())
    return found == expected


__all__ = ["evaluate_oracles", "run_task"]
