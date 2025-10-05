"""Helpers for constructing proactive plan executors."""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING

from pas.proactive import InterventionResult, LLMClientProtocol, LLMPlanExecutor, ToolSpec

if TYPE_CHECKING:
    import logging

    from pas.environment import StateAwareEnvironmentWrapper
else:
    StateAwareEnvironmentWrapper = object  # type: ignore[assignment]


def build_plan_executor(
    llm_client: LLMClientProtocol, tool_specs: typing.Sequence[ToolSpec], *, system_prompt: str, logger: logging.Logger
) -> typing.Callable[[str, StateAwareEnvironmentWrapper], InterventionResult]:
    """Create a callable that delegates execution to the LLM orchestrator."""
    orchestrator = LLMPlanExecutor(llm_client, list(tool_specs), system_prompt=system_prompt, logger=logger)

    def _execute(task: str, env: StateAwareEnvironmentWrapper) -> InterventionResult:
        return orchestrator(task, env)

    return _execute


__all__ = ["build_plan_executor"]
