from __future__ import annotations

import logging
from collections.abc import Callable  # noqa: TC003
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pas.scenario_generator.prompt.multi_step_scenario_generating_agent_prompts import (
    APPS_AND_DATA_USER_PROMPT,
    EVENTS_FLOW_USER_PROMPT,
    SCENARIO_DESCRIPTION_USER_PROMPT,
    VALIDATION_USER_PROMPT,
)

# Import the underlying `prompts` module directly so that updates from
# `configure_dynamic_context()` (which mutates module-level globals) are
# visible here.
from pas.scenario_generator.prompt.multi_step_scenario_generating_agent_prompts import (
    prompts as prompt_context,
)

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
        debug_printer: Callable[[str], None] | None = None,
        claude_runtime_config: ClaudeAgentRuntimeConfig | None = None,
    ) -> None:
        """Configure shared settings for a single multi-step generation phase."""
        self.name = name
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.uniqueness_agent = uniqueness_agent
        self.debug_prompts = debug_prompts
        self._debug_printer = debug_printer
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
        printer = self._debug_printer or print
        header = f"\n=== DEBUG PROMPTS :: {self.name} ==="
        printer(header)
        for message in conversation:
            role = message.get("role", "unknown").upper()
            printer(f"[{role}]")
            printer(message.get("content", ""))


class ScenarioDescriptionAgent(BaseStepAgent):
    """Step 1 agent that drafts the high-level narrative description."""

    def __init__(
        self,
        *,
        max_iterations: int,
        uniqueness_agent: ScenarioUniquenessCheckAgent,
        debug_prompts: bool = False,
        debug_printer: Callable[[str], None] | None = None,
        claude_runtime_config: ClaudeAgentRuntimeConfig | None = None,
    ) -> None:
        """Initialize the narrative step agent."""
        super().__init__(
            name="Step 1: Scenario Description",
            # Pull the system prompt from the dynamic context module so that
            # updates from `configure_dynamic_context()` are reflected here.
            system_prompt=prompt_context.SCENARIO_DESCRIPTION_SYSTEM_PROMPT,
            max_iterations=max_iterations,
            uniqueness_agent=uniqueness_agent,
            debug_prompts=debug_prompts,
            debug_printer=debug_printer,
            claude_runtime_config=claude_runtime_config,
        )

    def run(
        self,
        *,
        historical_descriptions: str,
        check_callback: Callable[[str, int], tuple[bool, str]] | None = None,
    ) -> StepResult:
        """Generate a new scenario description, respecting uniqueness checks."""
        history_text = historical_descriptions.strip() or "(none recorded yet)"
        user_prompt = SCENARIO_DESCRIPTION_USER_PROMPT.format(historical_descriptions=history_text)

        def debug_builder(_: str) -> str:
            return "[DEBUG SCENARIO DESCRIPTION | novel request]"

        return self._run_with_prompt(
            user_prompt=user_prompt,
            check_callback=check_callback,
            debug_response_builder=debug_builder,
        )


class AppsAndDataSetupAgent(BaseStepAgent):
    """Step 2 agent that plans app initialization and seed data."""

    def __init__(
        self,
        *,
        max_iterations: int,
        debug_prompts: bool = False,
        debug_printer: Callable[[str], None] | None = None,
        claude_runtime_config: ClaudeAgentRuntimeConfig | None = None,
    ) -> None:
        """Initialize the apps-and-data step agent."""
        super().__init__(
            name="Step 2: Apps & Data Setup",
            system_prompt=prompt_context.APPS_AND_DATA_SYSTEM_PROMPT,
            max_iterations=max_iterations,
            debug_prompts=debug_prompts,
            debug_printer=debug_printer,
            claude_runtime_config=claude_runtime_config,
        )

    def run(
        self,
        *,
        scenario_description: str,
        scenario_file_path: str,
        scenario_file_contents: str,
        check_callback: Callable[[str, int], tuple[bool, str]] | None = None,
    ) -> StepResult:
        """Produce an `init_and_populate_apps()` plan for the target scenario file."""
        user_prompt = APPS_AND_DATA_USER_PROMPT.format(
            scenario_description=scenario_description,
            scenario_file_path=scenario_file_path,
            scenario_file_contents=scenario_file_contents,
        )

        def debug_builder(_: str) -> str:
            return (
                "[DEBUG APPS & DATA OUTPUT placeholder]\n"
                f"# scenario_file_path: {scenario_file_path}\n"
                "# (LLM call skipped)"
            )

        return self._run_with_prompt(
            user_prompt=user_prompt,
            check_callback=check_callback,
            debug_response_builder=debug_builder,
        )


class EventsFlowAgent(BaseStepAgent):
    """Step 3 agent that builds the temporal sequence of events."""

    def __init__(
        self,
        *,
        max_iterations: int,
        debug_prompts: bool = False,
        debug_printer: Callable[[str], None] | None = None,
        claude_runtime_config: ClaudeAgentRuntimeConfig | None = None,
    ) -> None:
        """Initialize the events-flow step agent."""
        super().__init__(
            name="Step 3: Events Flow",
            system_prompt=prompt_context.EVENTS_FLOW_SYSTEM_PROMPT,
            max_iterations=max_iterations,
            debug_prompts=debug_prompts,
            debug_printer=debug_printer,
            claude_runtime_config=claude_runtime_config,
        )

    def run(
        self,
        *,
        scenario_description: str,
        apps_and_data: str,
        scenario_file_contents: str,
        check_callback: Callable[[str, int], tuple[bool, str]] | None = None,
    ) -> StepResult:
        """Author the concrete `build_events_flow()` implementation."""
        user_prompt = EVENTS_FLOW_USER_PROMPT.format(
            scenario_description=scenario_description,
            apps_and_data=apps_and_data,
            scenario_file_contents=scenario_file_contents,
        )

        def debug_builder(_: str) -> str:
            return "[DEBUG EVENTS FLOW OUTPUT placeholder]\n# (LLM call skipped)"

        return self._run_with_prompt(
            user_prompt=user_prompt,
            check_callback=check_callback,
            debug_response_builder=debug_builder,
        )


class ValidationAgent(BaseStepAgent):
    """Step 4 agent that designs validation checks for the scenario."""

    def __init__(
        self,
        *,
        max_iterations: int,
        debug_prompts: bool = False,
        debug_printer: Callable[[str], None] | None = None,
        claude_runtime_config: ClaudeAgentRuntimeConfig | None = None,
    ) -> None:
        """Initialize the validation step agent."""
        super().__init__(
            name="Step 4: Validation Conditions",
            system_prompt=prompt_context.VALIDATION_SYSTEM_PROMPT,
            max_iterations=max_iterations,
            debug_prompts=debug_prompts,
            debug_printer=debug_printer,
            claude_runtime_config=claude_runtime_config,
        )

    def run(
        self,
        *,
        scenario_description: str,
        events_flow: str,
        scenario_file_contents: str,
        check_callback: Callable[[str, int], tuple[bool, str]] | None = None,
    ) -> StepResult:
        """Fill in the `validate()` function according to the agreed pattern."""
        user_prompt = VALIDATION_USER_PROMPT.format(
            scenario_description=scenario_description,
            events_flow=events_flow,
            scenario_file_contents=scenario_file_contents,
        )

        def debug_builder(_: str) -> str:
            return "[DEBUG VALIDATION OUTPUT placeholder]\n# (LLM call skipped)"

        return self._run_with_prompt(
            user_prompt=user_prompt,
            check_callback=check_callback,
            debug_response_builder=debug_builder,
        )
