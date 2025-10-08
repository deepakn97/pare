"""Helpers for constructing proactive plan executors."""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING

from pas.proactive.react_adapter import react_intervention

if TYPE_CHECKING:
    import logging

    from pas.environment import StateAwareEnvironmentWrapper
    from pas.proactive import InterventionResult, LLMClientProtocol
else:
    StateAwareEnvironmentWrapper = object  # type: ignore[assignment]


def build_plan_executor(
    llm_client: LLMClientProtocol, *, logger: logging.Logger
) -> typing.Callable[[str, StateAwareEnvironmentWrapper], InterventionResult]:
    """Create a callable that runs a Meta ARE-style ReAct loop over PAS tools."""

    def _execute(task: str, env: StateAwareEnvironmentWrapper) -> InterventionResult:
        return react_intervention(goal=task, env=env, llm=llm_client, logger=logger)

    return _execute


__all__ = ["build_plan_executor"]
