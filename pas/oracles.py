"""Oracle matching helpers shared between session loop and task validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

    from are.simulation.types import CompletedEvent

    from pas.environment import StateAwareEnvironmentWrapper
    from pas.scenarios.types import OracleAction


def _normalise_value(value: object) -> object:
    if isinstance(value, dict) and "value" in value and len(value) == 1:
        return _normalise_value(value["value"])
    if isinstance(value, dict):
        return {key: _normalise_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalise_value(item) for item in value]
    if hasattr(value, "value") and not isinstance(value, str | bytes):
        enum_value = value.value
        if enum_value is not None:
            return enum_value
    return value


def _normalise_args(args: dict[str, object]) -> dict[str, object]:
    return {key: _normalise_value(val) for key, val in args.items() if key != "self"}


def event_matches(event: CompletedEvent, oracle: OracleAction) -> bool:
    """Return ``True`` when a completed event satisfies an oracle expectation."""
    if oracle.expected_event_type is not None and event.event_type is not oracle.expected_event_type:
        return False
    if event.app_name() != oracle.app:
        return False
    if event.function_name() != oracle.function:
        return False

    event_args = _normalise_args(event.action.args if event.action else {})
    expected = oracle.args or {}
    return all(_values_equal(event_args.get(key), value) for key, value in expected.items())


def _values_equal(found: object | None, expected: object) -> bool:
    if isinstance(expected, list):
        if not isinstance(found, list) or len(found) != len(expected):
            return False
        return all(_values_equal(f, e) for f, e in zip(found, expected, strict=False))
    if isinstance(expected, dict):
        if not isinstance(found, dict):
            return False
        return all(_values_equal(found.get(key), val) for key, val in expected.items())
    return found == expected


@dataclass(slots=True)
class OracleMatch:
    """Stores the mapping between an oracle expectation and the matched event."""

    oracle: OracleAction
    event: CompletedEvent


class OracleTracker:
    """Track oracle satisfaction by subscribing to completed events."""

    def __init__(self, env: StateAwareEnvironmentWrapper, oracle_actions: Sequence[OracleAction]) -> None:
        """Initialise tracker and subscribe to new and historical events."""
        self._env = env
        self._pending: list[OracleAction] = list(oracle_actions)
        self._matches: list[OracleMatch] = []
        self._env.subscribe_to_completed_events(self._on_event)
        existing_log = getattr(env, "event_log", None)
        if existing_log is not None:
            for event in existing_log.list_view():
                self._try_match(event)

    def _on_event(self, event: CompletedEvent) -> None:
        self._try_match(event)

    def _try_match(self, event: CompletedEvent) -> None:
        for index, oracle in enumerate(self._pending):
            if event_matches(event, oracle):
                self._matches.append(OracleMatch(oracle, event))
                del self._pending[index]
                break

    def is_satisfied(self) -> bool:
        """Return ``True`` when all oracle expectations have been met."""
        return not self._pending

    @property
    def matches(self) -> list[OracleMatch]:
        """Return matched oracle-event pairs encountered so far."""
        return list(self._matches)

    @property
    def pending(self) -> list[OracleAction]:
        """Return oracle expectations that are still outstanding."""
        return list(self._pending)

    @property
    def match_count(self) -> int:
        """Return the number of satisfied oracles."""
        return len(self._matches)


__all__ = ["OracleMatch", "OracleTracker", "event_matches"]
