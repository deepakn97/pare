from __future__ import annotations

import logging
from collections.abc import Callable  # noqa: TC003
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pas.scenarios.generator.prompt.scenario_generating_agent_prompts import (
    APPS_AND_DATA_USER_PROMPT,
    EVENTS_FLOW_USER_PROMPT,
    SCENARIO_DESCRIPTION_USER_PROMPT,
    VALIDATION_USER_PROMPT,
)

# Import the underlying `prompts` module directly so that updates from
# `configure_dynamic_context()` (which mutates module-level globals) are
# visible here.
from .claude_backend import ClaudeAgentRuntimeConfig, run_claude_conversation

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .scenario_uniqueness_agent import ScenarioUniquenessCheckAgent


class StepExecutionError(RuntimeError):
    """Raised when a step cannot complete within the allotted attempts."""


@dataclass
class StepResult:
    """Container for a single step's outcome and trace metadata."""

    name: str
    content: str
    iterations: int
    notes: dict[str, Any]
    conversation: list[dict[str, str]]


class BaseStepAgent:
    """Base helper that wraps LLM calls and retry/check logic for a pipeline step."""

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        max_iterations: int = 3,
        uniqueness_agent: ScenarioUniquenessCheckAgent | None = None,
        debug_prompts: bool = False,
        claude_runtime_config: ClaudeAgentRuntimeConfig | None = None,
    ) -> None:
        """Configure shared settings for a single multi-step generation phase."""
        self.name = name
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.uniqueness_agent = uniqueness_agent
        self.debug_prompts = debug_prompts
        self._claude_config = claude_runtime_config

    def _run_with_prompt(
        self,
        *,
        user_prompt: str,
        check_callback: Callable[[str, int], tuple[bool, str]] | None = None,
        debug_response_builder: Callable[[str], str] | None = None,
    ) -> StepResult:
        conversation = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if self.debug_prompts:
            return self._run_in_debug_mode(
                conversation=conversation,
                debug_response_builder=debug_response_builder,
            )
        for iteration in range(1, self.max_iterations + 1):
            response = self._invoke_llm(conversation, iteration)
            assistant_msg = {"role": "assistant", "content": response}
            notes: dict[str, Any] = {"iteration": iteration}

            if self.uniqueness_agent is not None:
                unique, verdict = self.uniqueness_agent.evaluate(response)
                notes["uniqueness_verdict"] = verdict
                if not unique:
                    logger.info(
                        "%s uniqueness rejection (iteration %s): %s\nCandidate description:\n%s",
                        self.name,
                        iteration,
                        verdict,
                        response,
                    )
                    conversation.extend([
                        assistant_msg,
                        {
                            "role": "user",
                            "content": f"Uniqueness review failed: {verdict}",
                        },
                    ])
                    continue

            check_passed = True
            feedback = ""
            if check_callback is not None:
                check_passed, feedback = check_callback(response, iteration)
                if feedback:
                    notes["check_feedback"] = feedback

            if not check_passed:
                logger.warning(
                    "%s check_callback failed at iteration %s. Feedback:\n%s",
                    self.name,
                    iteration,
                    feedback,
                )
                conversation.extend([
                    assistant_msg,
                    {
                        "role": "user",
                        "content": feedback or "Check failed; please revise.",
                    },
                ])
                continue

            full_conversation = [*conversation, assistant_msg]
            logger.info(
                "%s succeeded at iteration %s",
                self.name,
                iteration,
            )
            return StepResult(
                name=self.name,
                content=response,
                iterations=iteration,
                notes=notes,
                conversation=full_conversation,
            )
        raise StepExecutionError(f"{self.name} failed after {self.max_iterations} attempts.")

    def _invoke_llm(self, conversation: list[dict[str, str]], iteration: int) -> str:
        if self._claude_config is None:
            raise StepExecutionError(f"{self.name} is misconfigured: missing Claude runtime config.")
        return run_claude_conversation(
            conversation,
            system_prompt=self.system_prompt,
            config=self._claude_config,
            step_tag=self.name,
            iteration=iteration,
        )

    def _run_in_debug_mode(
        self,
        *,
        conversation: list[dict[str, str]],
        debug_response_builder: Callable[[str], str] | None = None,
    ) -> StepResult:
        self._emit_debug_prompts(conversation)
        user_prompt = conversation[-1]["content"]
        builder = debug_response_builder or self._default_debug_response
        response = builder(user_prompt)
        notes: dict[str, Any] = {"debug_mode": True}
        if self.uniqueness_agent is not None:
            _unique, verdict = self.uniqueness_agent.evaluate(response)
            notes["uniqueness_verdict"] = verdict
        assistant_msg = {"role": "assistant", "content": response}
        full_conversation = [*conversation, assistant_msg]
        return StepResult(
            name=self.name,
            content=response,
            iterations=0,
            notes=notes,
            conversation=full_conversation,
        )

    def _default_debug_response(self, _: str) -> str:
        return f"[DEBUG MOCK OUTPUT for {self.name}]"

    def _emit_debug_prompts(self, conversation: list[dict[str, str]]) -> None:
        header = f"\n=== DEBUG PROMPTS :: {self.name} ==="
        logger.info(header)
        for message in conversation:
            role = message.get("role", "unknown").upper()
            logger.info("[%s]\n%s", role, message.get("content", ""))


class StepEditAgent(BaseStepAgent):
    """Unified multi-step scenario agent parametrized by step kind."""

    def __init__(
        self,
        *,
        step_name: str,
        step_kind: str,
        system_prompt: str,
        max_iterations: int,
        debug_prompts: bool = False,
        claude_runtime_config: ClaudeAgentRuntimeConfig | None = None,
        uniqueness_agent: ScenarioUniquenessCheckAgent | None = None,
    ) -> None:
        """Initialize a generic scenario step agent."""
        self.step_kind = step_kind
        super().__init__(
            name=step_name,
            system_prompt=system_prompt,
            max_iterations=max_iterations,
            uniqueness_agent=uniqueness_agent,
            debug_prompts=debug_prompts,
            claude_runtime_config=claude_runtime_config,
        )

    def run(  # noqa: C901
        self,
        *,
        scenario_metadata_path: str | None = None,
        scenario_description: str | None = None,
        scenario_file_path: str | None = None,
        apps_and_data: str | None = None,
        events_flow: str | None = None,
        check_callback: Callable[[str, int], tuple[bool, str]] | None = None,
    ) -> StepResult:
        """Dispatch to the appropriate per-step prompt builder."""
        if self.step_kind == "description":
            metadata_path = (scenario_metadata_path or "").strip() or "pas/scenarios/scenario_metadata.json"
            user_prompt = SCENARIO_DESCRIPTION_USER_PROMPT.format(scenario_metadata_path=metadata_path)

            def debug_builder(_: str) -> str:
                return "[DEBUG SCENARIO DESCRIPTION | novel request]"

        elif self.step_kind == "apps_and_data":
            if scenario_description is None or scenario_file_path is None:
                raise StepExecutionError(
                    "Apps & Data step requires scenario_description and scenario_file_path.",
                )
            user_prompt = APPS_AND_DATA_USER_PROMPT.format(
                scenario_description=scenario_description,
                scenario_file_path=scenario_file_path,
            )

            def debug_builder(_: str) -> str:
                return (
                    "[DEBUG APPS & DATA OUTPUT placeholder]\n"
                    f"# scenario_file_path: {scenario_file_path}\n"
                    "# (LLM call skipped)"
                )

        elif self.step_kind == "events_flow":
            if scenario_description is None or apps_and_data is None or scenario_file_path is None:
                raise StepExecutionError(
                    "Events Flow step requires scenario_description, apps_and_data, and scenario_file_path.",
                )
            user_prompt = EVENTS_FLOW_USER_PROMPT.format(
                scenario_description=scenario_description,
                apps_and_data=apps_and_data,
                scenario_file_path=scenario_file_path,
            )

            def debug_builder(_: str) -> str:
                return "[DEBUG EVENTS FLOW OUTPUT placeholder]\n# (LLM call skipped)"

        elif self.step_kind == "validation":
            if scenario_description is None or events_flow is None or scenario_file_path is None:
                raise StepExecutionError(
                    "Validation step requires scenario_description, events_flow, and scenario_file_path.",
                )
            user_prompt = VALIDATION_USER_PROMPT.format(
                scenario_description=scenario_description,
                events_flow=events_flow,
                scenario_file_path=scenario_file_path,
            )

            def debug_builder(_: str) -> str:
                return "[DEBUG VALIDATION OUTPUT placeholder]\n# (LLM call skipped)"

        else:
            raise StepExecutionError(f"Unknown step kind: {self.step_kind!r}")

        return self._run_with_prompt(
            user_prompt=user_prompt,
            check_callback=check_callback,
            debug_response_builder=debug_builder,
        )
