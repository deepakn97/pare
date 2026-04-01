from __future__ import annotations

import logging
from typing import Any

from pare.scenarios.generator.prompt.scenario_generating_agent_prompts import (
    SCENARIO_UNIQUENESS_SYSTEM_PROMPT,
    SCENARIO_UNIQUENESS_USER_PROMPT,
)

from .claude_backend import ClaudeAgentRuntimeConfig, run_claude_conversation

logger = logging.getLogger(__name__)


class ScenarioUniquenessCheckAgent:
    """Lightweight reviewer that enforces the Step 0 uniqueness requirement."""

    def __init__(
        self,
        historical_descriptions: list[dict[str, Any]] | None = None,
        *,
        scenario_metadata_path: str | None = None,
        debug_prompts: bool = False,
        claude_runtime_config: ClaudeAgentRuntimeConfig | None = None,
    ) -> None:
        """Configure the LLM engine and historical description buffer."""
        self.historical_descriptions: list[dict[str, Any]] = historical_descriptions or []
        self.scenario_metadata_path = scenario_metadata_path or "pare/scenarios/scenario_metadata.json"
        self.debug_prompts = debug_prompts
        self._claude_config = claude_runtime_config

    def evaluate(self, scenario_description: str) -> tuple[bool, str]:
        """Return (is_unique, verdict_text)."""
        user_prompt = SCENARIO_UNIQUENESS_USER_PROMPT.format(
            scenario_description=scenario_description.strip(),
            scenario_metadata_path=self.scenario_metadata_path,
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
        text = verdict.strip()
        # Primary rule: look at the FIRST non-empty line so any later
        # "Comparison/Key overlap" analysis can't override a clear verdict.
        first_line = ""
        for line in text.splitlines():
            if line.strip():
                first_line = line.strip().lstrip("* ").strip()
                break
        if not first_line:
            return False, text

        upper = first_line.upper()
        if upper.startswith("PARES"):
            return True, text
        if upper.startswith("RETRY"):
            return False, text

        # Fallback: if the model didn't follow the "first line is PARES/RETRY"
        # contract, scan subsequent non-empty lines for a line that *starts*
        # with PARES or RETRY. This still ignores any mention of those tokens
        # inside later prose or bullet points.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            normalized = line.upper().lstrip("* ").strip()
            if normalized.startswith("PARES"):
                return True, text
            if normalized.startswith("RETRY"):
                return False, text

        return False, text

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
        if self._claude_config is None:
            raise TypeError("Scenario uniqueness check is misconfigured: missing Claude runtime config.")
        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return run_claude_conversation(
            conversation,
            system_prompt=system_prompt,
            config=self._claude_config,
            step_tag=trace_tag,
            iteration=1,
        )

    def _emit_debug_prompts(self, *, system_prompt: str, user_prompt: str) -> None:
        logger.info("\n=== DEBUG PROMPTS :: Scenario Uniqueness Check ===")
        logger.info("[SYSTEM PROMPT]\n%s", system_prompt)
        logger.info("[USER PROMPT]\n%s", user_prompt)
