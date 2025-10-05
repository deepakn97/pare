"""Adapter utilities to bridge PAS tooling with Meta ARE ReAct agent."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from are.simulation.agents.are_simulation_agent_config import ARESimulationReactBaseAgentConfig
from are.simulation.agents.default_agent.agent_factory import are_simulation_react_json_agent
from are.simulation.agents.default_agent.prompts.system_prompt import DEFAULT_ARE_SIMULATION_REACT_JSON_SYSTEM_PROMPT
from are.simulation.agents.default_agent.termination_methods.are_simulation import (
    termination_step_are_simulation_final_answer,
)
from are.simulation.agents.default_agent.tools.json_action_executor import JsonActionExecutor
from are.simulation.agents.llm.llm_engine import LLMEngine
from are.simulation.tool_box import Toolbox
from are.simulation.tool_utils import AppTool  # noqa: TC002
from are.simulation.tools import Tool

from pas.proactive import InterventionResult, LLMClientProtocol

if TYPE_CHECKING:
    from pas.environment import StateAwareEnvironmentWrapper


def _map_input_type(arg_type: str) -> str:
    """Translate AppTool argument type to Meta ARE Tool schema type."""
    normalised = str(arg_type).lower()
    if normalised in {"int", "integer"}:
        return "integer"
    if normalised in {"float", "number"}:
        return "number"
    if normalised in {"bool", "boolean"}:
        return "boolean"
    return "string"


class PasToolAdapter(Tool):
    """Wrap a PAS AppTool so Meta ARE's JsonActionExecutor can invoke it."""

    def __init__(self, app_tool: AppTool) -> None:
        """Initialise the adapter with the underlying PAS tool."""
        super().__init__()
        self._tool = app_tool
        self.name = app_tool.name
        self.description = app_tool.function_description or "No description provided."
        self.inputs = {
            arg.name: {
                "type": _map_input_type(arg.arg_type),
                "description": arg.description or "Argument with no description provided.",
            }
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


class FinalAnswerTool(Tool):
    """Meta ARE convention tool to terminate a ReAct loop with a final answer."""

    name: ClassVar[str] = "final_answer"
    description: ClassVar[str] = "Return the final response once the task is complete."
    inputs: ClassVar[dict[str, dict[str, str]]] = {
        "answer": {"type": "string", "description": "User-facing summary of the completed task."}
    }
    output_type: ClassVar[str] = "string"

    def forward(self, answer: str) -> str:
        """Return the final response unchanged."""
        return answer


class PasLLMEngine(LLMEngine):
    """Adapter turning a PAS LLM client into Meta ARE's LLMEngine protocol."""

    def __init__(self, llm: LLMClientProtocol, logger: logging.Logger | None = None) -> None:
        """Store the PAS LLM client for subsequent chat completions."""
        super().__init__(model_name="pas-llm-client")
        self._llm = llm
        self._logger = logger or logging.getLogger(__name__)

    @staticmethod
    def _format_messages(messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for message in messages:
            role = message.get("role", "assistant").upper()
            content = message.get("content", "")
            parts.append(f"{role}: {content}")
        return "\n\n".join(parts)

    def chat_completion(
        self, messages: list[dict[str, Any]], stop_sequences: list[str] | None = None, **kwargs: Any
    ) -> tuple[str, dict[str, Any] | None]:
        """Format messages for the PAS client and relay the response."""
        prompt = self._format_messages(messages)
        if stop_sequences:
            prompt = f"{prompt}\n\n[Stop tokens: {', '.join(stop_sequences)}]"
        response = self._llm.complete(prompt)
        self._logger.debug("Meta ARE bridge prompt:\n%s", prompt)
        self._logger.debug("Meta ARE bridge response: %s", response)
        return response, None

    def simple_call(self, prompt: str) -> str:
        """Proxy simple prompts directly to the PAS client."""
        return self._llm.complete(prompt)


@dataclass
class ReactExecutionResult:
    """Bundle success metadata from a ReAct execution."""

    success: bool
    notes: str
    raw_logs: list[Any]


def build_toolbox(env: StateAwareEnvironmentWrapper) -> Toolbox:
    """Construct a Meta ARE toolbox from PAS environment tools."""
    adapters = [PasToolAdapter(tool) for tool in env.get_tools()]
    adapters.append(FinalAnswerTool())
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
