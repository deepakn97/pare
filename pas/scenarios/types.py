"""Shared scenario data structures such as Oracle expectations."""

from __future__ import annotations

import typing as t
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - hints only
    from are.simulation.types import EventType

if TYPE_CHECKING:  # pragma: no cover - hints only
    from pas.apps.proactive_agent_ui import ProactiveAgentUserInterface
    from pas.environment import StateAwareEnvironmentWrapper
    from pas.proactive import ProactiveAgentProtocol
    from pas.user_proxy import StatefulUserProxy


@dataclass(slots=True)
class OracleAction:
    """Describes an expected tool invocation for scenario validation."""

    app: str
    function: str
    args: dict[str, Any] = field(default_factory=dict)
    description: str | None = None
    source_event_id: str | None = None
    expected_event_type: EventType | None = None


@dataclass(slots=True)
class ScenarioSetup:
    """Bundle of runtime components together with oracle expectations."""

    env: StateAwareEnvironmentWrapper
    proxy: StatefulUserProxy
    agent: ProactiveAgentProtocol
    agent_ui: ProactiveAgentUserInterface
    oracle_actions: list[OracleAction] = field(default_factory=list)

    def __iter__(self) -> t.Iterator[Any]:  # pragma: no cover - convenient tuple-unpack
        yield self.env
        yield self.proxy
        yield self.agent
        yield self.agent_ui


__all__ = ["OracleAction", "ScenarioSetup"]
