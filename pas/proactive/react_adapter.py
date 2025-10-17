"""Adapter utilities to bridge PAS tooling with Meta ARE ReAct agent."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from types import UnionType
from typing import TYPE_CHECKING, Any, Union, cast, get_origin

from are.simulation.agents.are_simulation_agent_config import ARESimulationReactBaseAgentConfig
from are.simulation.agents.default_agent.agent_factory import are_simulation_react_json_agent
from are.simulation.agents.default_agent.prompts.system_prompt import DEFAULT_ARE_SIMULATION_REACT_JSON_SYSTEM_PROMPT
from are.simulation.agents.default_agent.termination_methods.are_simulation import (
    termination_step_are_simulation_final_answer,
)
from are.simulation.agents.default_agent.tools.json_action_executor import JsonActionExecutor
from are.simulation.tool_box import Toolbox
from are.simulation.tools import Tool

from pas.llm_adapter import LLMClientProtocol
from pas.llm_adapter import PasLLMEngine as _PasLLMEngine
from pas.proactive import InterventionResult

if TYPE_CHECKING:
    from are.simulation.tool_utils import AppTool, AppToolArg

    from pas.environment import StateAwareEnvironmentWrapper


def _map_input_type(arg: AppToolArg) -> str:
    """Translate AppTool argument type to a Tool.validate_arguments-compatible primitive."""
    type_obj = getattr(arg, "type_obj", None)
    origin = get_origin(type_obj) if type_obj is not None else None

    if type_obj in {int, float}:
        return "number" if type_obj is float else "integer"
    if type_obj is bool:
        return "boolean"
    if type_obj is str:
        return "string"

    if origin in {list, tuple, set, dict, Union, UnionType}:
        return "any"

    normalised = str(arg.arg_type).lower()
    if normalised in {"int", "integer"}:
        return "integer"
    if normalised in {"float", "number"}:
        return "number"
    if normalised in {"bool", "boolean"}:
        return "boolean"
    if any(token in normalised for token in ("list[", "dict[", "|")):
        return "any"
    return "string"


def _format_input_description(arg: AppToolArg) -> str:
    base = arg.description or "Argument with no description provided."
    hint = str(arg.arg_type)
    normalised = hint.lower()

    if "list[" in normalised:
        example = '["item@example.com"]'
        return f"{base} Expected JSON array (e.g. {example})."
    if "dict[" in normalised:
        return f"{base} Expected JSON object matching {hint}."
    if "|" in hint:
        return f"{base} Expected type: {hint}."
    return base


class PasToolAdapter(Tool):
    """Wrap a PAS AppTool so Meta ARE's JsonActionExecutor can invoke it."""

    def __init__(self, app_tool: AppTool) -> None:
        """Initialise the adapter with the underlying PAS tool."""
        super().__init__()
        self._tool = app_tool
        self.name = app_tool.name
        self.description = app_tool.function_description or "No description provided."
        self.inputs = {
            arg.name: {"type": _map_input_type(arg), "description": _format_input_description(arg)}
            for arg in app_tool.args
        }
        self.output_type = "string"

    def validate_arguments(self, do_validate_forward: bool = True) -> None:
        """Reuse base validation while skipping the strict forward signature check."""
        super().validate_arguments(do_validate_forward=False)

    def forward(self, **kwargs: Any) -> str:
        """Invoke the wrapped tool and coerce results into a string."""
        missing: list[str] = []
        for arg in self._tool.args:
            if arg.name not in kwargs:
                if arg.has_default:
                    continue
                missing.append(arg.name)
        if missing:
            raise ValueError(f"Missing required arguments for {self._tool.name}: {', '.join(missing)}")
        result = self._tool(**kwargs)
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, default=str)
        except (TypeError, ValueError):
            return str(result)


# PasLLMEngine moved to pas.llm_adapter to avoid circular dependencies
PasLLMEngine = _PasLLMEngine


@dataclass
class ReactExecutionResult:
    """Bundle success metadata from a ReAct execution."""

    success: bool
    notes: str
    raw_logs: list[Any]


def build_toolbox(env: StateAwareEnvironmentWrapper) -> Toolbox:
    """Construct a Meta ARE toolbox from PAS environment tools.

    Note: final_answer is a control-flow tool added in scenarios, not from apps.
    """
    adapters = [PasToolAdapter(tool) for tool in env.get_tools()]
    return Toolbox(adapters)


def run_react_agent(
    *,
    goal: str,
    env: StateAwareEnvironmentWrapper,
    llm: LLMClientProtocol,
    logger: logging.Logger,
    max_iterations: int = 12,
) -> ReactExecutionResult:
    """Execute a ReAct loop using Meta ARE's BaseAgent over PAS tools."""
    toolbox = build_toolbox(env)
    llm_engine = PasLLMEngine(llm, logger)
    base_agent_config = ARESimulationReactBaseAgentConfig(
        system_prompt=DEFAULT_ARE_SIMULATION_REACT_JSON_SYSTEM_PROMPT, max_iterations=max_iterations
    )

    base_agent = are_simulation_react_json_agent(llm_engine, base_agent_config)
    if isinstance(base_agent.action_executor, JsonActionExecutor):
        base_agent.action_executor.update_tools(toolbox.tools)
    base_agent.tools = toolbox.tools
    base_agent.notification_system = getattr(env, "notification_system", None)
    base_agent.termination_step = termination_step_are_simulation_final_answer()

    result = base_agent.run(goal)

    success = isinstance(result, str) and result != ""
    notes = result if isinstance(result, str) else "Agent finished without final answer."
    return ReactExecutionResult(success=success, notes=notes, raw_logs=base_agent.get_agent_logs())


def react_intervention(
    *,
    goal: str,
    env: StateAwareEnvironmentWrapper,
    llm: LLMClientProtocol,
    logger: logging.Logger,
    max_iterations: int = 12,
) -> InterventionResult:
    """Convenience wrapper returning PAS InterventionResult from a ReAct run."""
    execution = run_react_agent(goal=goal, env=env, llm=llm, logger=logger, max_iterations=max_iterations)
    metadata: dict[str, object] = {"logs": cast("object", execution.raw_logs)}
    return InterventionResult(execution.success, execution.notes, metadata)
