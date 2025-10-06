"""Task abstractions built around scenarios and oracle expectations."""

from __future__ import annotations

import typing as t
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # pragma: no cover - hints only
    from are.simulation.types import CompletedEvent

    from pas.proactive import LLMClientProtocol
    from pas.scenarios.types import OracleAction, ScenarioSetup
    from pas.system import ProactiveCycleResult


@dataclass(slots=True)
class TaskContext:
    """Parameters required to construct a scenario run for a task."""

    llm: LLMClientProtocol
    user_llm: LLMClientProtocol
    max_user_turns: int
    log_mode: Literal["overwrite", "append"]
    primary_app: str


@dataclass(slots=True)
class TaskDefinition:
    """Reusable task specification wrapping a scenario builder and metadata."""

    task_id: str
    description: str
    scenario_builder: t.Callable[[TaskContext], ScenarioSetup]
    goal_hint: str | None = None


@dataclass(slots=True)
class OracleCheckResult:
    """Outcome of matching a completed event against an oracle expectation."""

    oracle: OracleAction
    satisfied: bool
    matched_event: CompletedEvent | None = None


@dataclass(slots=True)
class TaskRunResult:
    """Summary of executing a single task."""

    task: TaskDefinition
    setup: ScenarioSetup
    cycle: ProactiveCycleResult
    oracle_checks: list[OracleCheckResult]

    @property
    def success(self) -> bool:
        """Task succeeds when the cycle is accepted and all oracle checks pass."""
        return self.cycle.accepted and all(check.satisfied for check in self.oracle_checks)


__all__ = ["OracleCheckResult", "TaskContext", "TaskDefinition", "TaskRunResult"]
