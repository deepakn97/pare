"""LLM-backed plan executor that converts goals into app tool calls."""

from __future__ import annotations

import json
import re
import typing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from logging import Logger

    from pas.environment import StateAwareEnvironmentWrapper
else:
    Logger = object  # type: ignore[assignment]
    StateAwareEnvironmentWrapper = object  # type: ignore[assignment]
from pas.proactive.agent import InterventionResult, LLMClientProtocol


@dataclass(frozen=True)
class ToolParameter:
    """Description of a tool argument exposed to the LLM orchestrator."""

    name: str
    description: str
    type_hint: str = "string"
    required: bool = True


@dataclass(frozen=True)
class ToolSpec:
    """Metadata and executor for a tool available to the orchestrator."""

    name: str
    description: str
    parameters: typing.Sequence[ToolParameter]
    executor: typing.Callable[[StateAwareEnvironmentWrapper, dict[str, Any]], InterventionResult]


class LLMPlanExecutor:
    """Simple LLM-based planner that selects a tool and executes it."""

    def __init__(
        self, llm: LLMClientProtocol, tools: typing.Sequence[ToolSpec], *, system_prompt: str, logger: Logger
    ) -> None:
        """Initialise the executor with available tool specifications."""
        if not tools:
            raise ValueError("LLMPlanExecutor requires at least one tool specification")
        self._llm = llm
        self._tool_map = {tool.name: tool for tool in tools}
        self._system_prompt = system_prompt.strip()
        self._logger = logger

    def __call__(self, task: str, env: StateAwareEnvironmentWrapper) -> InterventionResult:
        """Run the LLM planner for ``task`` and execute the suggested tool."""
        prompt = self._build_prompt(task)
        self._logger.debug("Planner prompt for task '%s':\n%s", task, prompt)
        response = self._llm.complete(prompt)
        self._logger.debug("Planner raw response: %s", response)
        plan = self._parse_response(response)

        if plan is None:
            self._logger.debug("Planner produced no actionable plan: %s", plan)
            return InterventionResult(False, "LLM did not provide an actionable plan.")
        if "tool" not in plan:
            self._logger.debug("Planner omitted tool selection: %s", plan)
            return InterventionResult(False, "LLM did not provide an actionable plan.")
        tool_name = plan["tool"]
        if tool_name == "none":
            self._logger.debug("Planner explicitly declined to act")
            return InterventionResult(False, "LLM did not provide an actionable plan.")
        if tool_name not in self._tool_map:
            self._logger.warning("Planner suggested unknown tool '%s'", tool_name)
            return InterventionResult(False, f"Unknown tool '{tool_name}' suggested by LLM.")
        spec = self._tool_map[tool_name]
        if "args" not in plan:
            self._logger.warning("Planner omitted args for %s", tool_name)
            return InterventionResult(False, f"Missing required arguments for {tool_name}: none provided")
        raw_args = plan["args"]
        if not isinstance(raw_args, dict):
            self._logger.warning("Planner args for %s are not a JSON object: %s", tool_name, raw_args)
            return InterventionResult(False, f"Invalid arguments for {tool_name}")
        args = raw_args
        missing = [p.name for p in spec.parameters if p.required and p.name not in args]
        if missing:
            self._logger.warning("Planner missing required args for %s: %s", tool_name, missing)
            return InterventionResult(False, f"Missing required arguments for {tool_name}: {', '.join(missing)}")

        self._logger.debug("Executing tool %s with args=%s", tool_name, args)
        return spec.executor(env, args)

    # ------------------------------------------------------------------
    def _build_prompt(self, task: str) -> str:
        lines = [self._system_prompt.strip(), "Available tools (choose exactly one):"]
        for tool in self._tool_map.values():
            lines.append(f"- {tool.name}: {tool.description}")
            for param in tool.parameters:
                required_label = "required" if param.required else "optional"
                lines.append(f"    * {param.name} ({param.type_hint}, {required_label}) - {param.description}")
        lines.extend([
            "Respond with pure JSON, no commentary. Format exactly as:",
            '{"tool": "<tool_name>", "args": {"param": value}}',
            'If nothing is appropriate, return {"tool": "none"}.',
            "Tool arguments must match the specification above.",
            f"Task: {task}",
        ])
        return "\n".join(lines)

    def _parse_response(self, response: str) -> dict[str, Any] | None:
        response = response.strip()
        if not response:
            return None

        if response.lower() in {"none", "null"}:
            return {"tool": "none"}

        json_str = self._extract_json(response)
        if not json_str:
            return None

        parsed = json.loads(json_str)

        if not isinstance(parsed, dict):
            return None
        return parsed

    @staticmethod
    def _extract_json(text: str) -> str | None:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)
        return None


__all__ = ["LLMPlanExecutor", "ToolParameter", "ToolSpec"]
