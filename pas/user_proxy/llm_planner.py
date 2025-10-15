"""LLM-backed planner that maps user messages to tool invocations."""

from __future__ import annotations

import json
import re
import typing
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging

    from pas.proactive.agent import LLMClientProtocol
    from pas.user_proxy.stateful import StatefulUserProxy
else:

    class LLMClientProtocol(typing.Protocol):  # pragma: no cover - runtime stub
        def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class UserToolParameter:
    """Metadata describing a single argument accepted by a user tool."""

    name: str
    description: str
    type_hint: str = "string"
    required: bool = True


@dataclass(frozen=True)
class UserToolSpec:
    """Metadata describing a user tool accessible to the simulated user."""

    name: str
    description: str
    app: str
    method: str
    parameters: Sequence[UserToolParameter]


PlannerReturn = list[tuple[str, str, dict[str, Any]]]


class LLMUserPlanner:
    """Convert free-form user intent into tool invocations via an LLM."""

    def __init__(
        self, llm: LLMClientProtocol, tools: Sequence[UserToolSpec], *, system_prompt: str, logger: logging.Logger
    ) -> None:
        """Initialise planner state with tool metadata and prompts."""
        if not tools:
            raise ValueError("LLMUserPlanner requires at least one tool specification")
        self._llm = llm
        self._ordered_tools = list(tools)
        self._tool_map = {tool.name: tool for tool in self._ordered_tools}
        self._alias_map = {self._alias_for_index(idx): tool for idx, tool in enumerate(self._ordered_tools)}
        self._name_to_alias = {tool.name: alias for alias, tool in self._alias_map.items()}
        self._system_prompt = system_prompt.strip()
        self._logger = logger

    def __call__(self, message: str, _proxy: StatefulUserProxy) -> PlannerReturn:
        """Convert a free-form message into tool invocations."""
        prompt = self._build_prompt(message)
        self._logger.info("User planner prompt:\n%s", prompt)
        response = self._llm.complete(prompt)
        self._logger.info("User planner raw response: %s", response)
        plan = self._parse_response(response)

        actions: PlannerReturn = []
        for item in plan:
            action = self._convert_plan_item(item)
            if action is not None:
                actions.append(action)

        if not actions:
            self._logger.info("Planner returned no actions for user message: %s", message)
        else:
            self._logger.info("Planner actions: %s", actions)
        return actions

    # ------------------------------------------------------------------
    def _build_prompt(self, message: str) -> str:
        instructions, context_attrs = self._split_system_prompt()
        lines: list[str] = []
        if instructions:
            lines.append(f"Instructions: {instructions}")
        if context_attrs:
            lines.append("Context:")
            lines.extend(self._format_context(context_attrs))
        lines.extend(self._format_observation(message))
        lines.append("Available actions:")
        lines.extend(self._render_tool_catalog())
        lines.append("Response format:")
        lines.append('  {"actions": [{"tool": "<option_id>", "args": {"param": value}}]}')
        return "\n".join(lines)

    def _convert_plan_item(self, item: dict[str, Any]) -> tuple[str, str, dict[str, Any]] | None:
        tool_name = item.get("tool")
        if not isinstance(tool_name, str):
            return None
        spec = self._alias_map.get(tool_name) or self._tool_map.get(tool_name)
        if spec is None:
            self._logger.info("Planner suggested unknown option '%s'", tool_name)
            return None

        raw_args = item.get("args")
        if not isinstance(raw_args, dict):
            self._logger.info("Planner produced non-object args for %s: %s", tool_name, raw_args)
            return None

        args: dict[str, Any] = {}
        for param in spec.parameters:
            if param.name in raw_args:
                args[param.name] = raw_args[param.name]
        missing = [p.name for p in spec.parameters if p.required and p.name not in args]
        if missing:
            self._logger.info("Planner omitted required args for %s: %s", tool_name, missing)
            return None

        return spec.app, spec.method, args

    def _split_system_prompt(self) -> tuple[str, dict[str, str]]:
        text = self._system_prompt.strip()
        if "Current context:" not in text:
            return text, {}
        prefix, context_part = text.split("Current context:", 1)
        instructions = prefix.strip()
        context_attrs: dict[str, str] = {}
        fragments = context_part.strip().rstrip(".").split(",")
        for fragment in fragments:
            fragment = fragment.strip()
            if "=" not in fragment:
                continue
            key, value = fragment.split("=", 1)
            context_attrs[key.strip()] = value.strip()
        return instructions, context_attrs

    def _format_context(self, context_attrs: dict[str, str]) -> list[str]:
        return [f"  - {key}: {value}" for key, value in context_attrs.items()]

    def _format_observation(self, message: str) -> list[str]:
        message_lines = message.splitlines() or [""]
        app_hint = self._extract_app_hint(message_lines[0] if message_lines else "")
        header = (
            f"Observation (system notification from app: {app_hint}):"
            if app_hint
            else "Observation (system notification):"
        )
        lines = [header]
        lines.extend(self._indent_message_lines(message_lines))
        return lines

    @staticmethod
    def _extract_app_hint(first_line: str) -> str | None:
        if not first_line.startswith("Notification (app:"):
            return None
        start = first_line.find("(app:") + len("(app:")
        end = first_line.find(")", start)
        if end == -1:
            return None
        return first_line[start:end].strip()

    @staticmethod
    def _indent_message_lines(message_lines: list[str]) -> list[str]:
        formatted: list[str] = []
        previous = ""
        for line in message_lines:
            indent = "  " if not previous.rstrip().endswith(":") else "    "
            formatted.append(f"{indent}{line.lstrip()}")
            previous = line
        return formatted

    def _render_tool_catalog(self) -> list[str]:
        lines: list[str] = []
        for idx, tool in enumerate(self._ordered_tools):
            alias = self._alias_for_index(idx)
            tool_label = f"{tool.app}.{tool.method}" if tool.app and tool.method else tool.name
            lines.append(f"  - {alias}: {tool_label}")
            description = self._clean_text(tool.description)
            if description:
                lines.append(f"      description: {description}")
            if tool.parameters:
                lines.append("      parameters:")
            for param in tool.parameters:
                lines.append(self._format_parameter(param))
        return lines

    @staticmethod
    def _clean_text(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.split())

    def _format_parameter(self, param: UserToolParameter) -> str:
        required = "required" if param.required else "optional"
        description = self._clean_text(param.description)
        return f"        - {param.name} ({param.type_hint}, {required}): {description}"

    def _parse_response(self, response: str) -> list[dict[str, Any]]:
        response = response.strip()
        if not response:
            return []
        json_str = self._extract_json(response)
        if not json_str:
            return []
        parsed = json.loads(json_str)
        if not isinstance(parsed, dict) or "actions" not in parsed:
            return []
        actions = parsed["actions"]
        if not isinstance(actions, list):
            return []
        filtered: list[dict[str, Any]] = []
        for action in actions:
            if isinstance(action, dict) and "tool" in action:
                filtered.append(action)
        return filtered

    @staticmethod
    def _extract_json(text: str) -> str | None:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)
        return None

    @staticmethod
    def _alias_for_index(index: int) -> str:
        return f"option_{index + 1}"


UserPlannerCallable = Callable[[str, "StatefulUserProxy"], PlannerReturn]

__all__ = ["LLMUserPlanner", "UserPlannerCallable", "UserToolParameter", "UserToolSpec"]
