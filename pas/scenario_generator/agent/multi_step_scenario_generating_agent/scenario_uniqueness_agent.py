from __future__ import annotations

from collections.abc import Callable  # noqa: TC003
from typing import TYPE_CHECKING, Any

from pas.scenario_generator.prompt.multi_step_scenario_generating_agent_prompts.prompts import (
    SCENARIO_UNIQUENESS_SYSTEM_PROMPT,
    SCENARIO_UNIQUENESS_USER_PROMPT,
)

if TYPE_CHECKING:
    from are.simulation.agents.llm.llm_engine import LLMEngine


class ScenarioUniquenessCheckAgent:
    """Lightweight reviewer that enforces the Step 0 uniqueness requirement."""

    def __init__(
        self,
        llm_engine: LLMEngine,
        historical_descriptions: list[dict[str, Any]] | None = None,
        *,
        debug_prompts: bool = False,
        debug_printer: Callable[[str], None] | None = None,
    ) -> None:
        """Configure the LLM engine and historical description buffer."""
        self.llm_engine = llm_engine
        self.historical_descriptions: list[dict[str, Any]] = historical_descriptions or []
        self.debug_prompts = debug_prompts
        self._debug_printer = debug_printer

    def evaluate(self, scenario_description: str) -> tuple[bool, str]:
        """Return (is_unique, verdict_text)."""
        history_block = self.get_recent_history()
        user_prompt = SCENARIO_UNIQUENESS_USER_PROMPT.format(
            scenario_description=scenario_description.strip(),
            historical_descriptions=history_block,
        )
        if self.debug_prompts:
            self._emit_debug_prompts(
                system_prompt=SCENARIO_UNIQUENESS_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            verdict = "[DEBUG MODE] Scenario uniqueness check skipped."
            return True, verdict
        verdict = self._invoke_llm(
            system_prompt=SCENARIO_UNIQUENESS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            trace_tag="multi_step_step1_uniqueness",
        )
        normalized = verdict.strip().upper()
        is_unique = normalized.startswith("PASS")
        return is_unique, verdict.strip()

    def get_recent_history(self, limit: int = 8) -> str:
        """Return a human-friendly summary of previously accepted descriptions."""
        return self._format_historical_descriptions(limit=limit)

    def _format_historical_descriptions(self, limit: int = 8) -> str:
        if not self.historical_descriptions:
            return "(none recorded yet)"
        recent = self.historical_descriptions[-limit:]
        lines: list[str] = []
        for entry in reversed(recent):
            description = (entry.get("description") or "").strip().replace("\n", " ")
            if len(description) > 220:
                description = f"{description[:220].rstrip()}..."
            timestamp = entry.get("timestamp") or "unknown time"
            lines.append(f"- {description} (logged {timestamp})")
        return "\n".join(lines)

    def _invoke_llm(self, *, system_prompt: str, user_prompt: str, trace_tag: str) -> str:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        raw = self.llm_engine(
            messages,
            stop_sequences=[],
            additional_trace_tags=[trace_tag],
            schema=None,
        )
        if isinstance(raw, tuple) and len(raw) == 2:
            raw = raw[0]
        if not isinstance(raw, str):
            raise TypeError("Scenario uniqueness check did not return textual output.")
        return raw.strip()

    def _emit_debug_prompts(self, *, system_prompt: str, user_prompt: str) -> None:
        printer = self._debug_printer or print
        header = "\n=== DEBUG PROMPTS :: Scenario Uniqueness Check ==="
        printer(header)
        printer("[SYSTEM PROMPT]")
        printer(system_prompt)
        printer("[USER PROMPT]")
        printer(user_prompt)
