from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from are.simulation.agents.llm.llm_engine import LLMEngine

from pare.scenarios.generator.prompt.summary_generator_prompts import (
    DEFAULT_SUMMARY_GENERATOR_SYSTEM_PROMPT,
    SUMMARY_TASK_TEMPLATE,
)

logger = logging.getLogger(__name__)


class SummaryGeneratingAgent:
    """Agent for generating summaries of scenario code."""

    def __init__(self, llm_engine: LLMEngine) -> None:
        """Initialize the summary generating agent.

        Args:
            llm_engine: The LLM engine to use for summary generation
        """
        self.llm_engine = llm_engine
        self.system_prompt = DEFAULT_SUMMARY_GENERATOR_SYSTEM_PROMPT

    def generate_summary(self, scenario_code: str) -> str | None:
        """Generate a summary for the given scenario code.

        Args:
            scenario_code: The scenario Python code as a string

        Returns:
            The generated summary or None if generation failed
        """
        # Create the task message
        task_message = SUMMARY_TASK_TEMPLATE.format(scenario_code=scenario_code)

        # Create messages for the LLM
        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": task_message}]

        logger.info("Generating summary for scenario code...")

        try:
            # Call the LLM
            llm_output_tuple = self.llm_engine(
                messages, stop_sequences=[], additional_trace_tags=["scenario_summary_generation"], schema=None
            )
            if isinstance(llm_output_tuple, tuple) and len(llm_output_tuple) == 2:
                llm_output, _ = llm_output_tuple
            else:
                llm_output = llm_output_tuple

            if isinstance(llm_output, str):
                # Clean up the output - remove any code blocks or extra formatting
                summary = llm_output.strip()
                # Remove markdown code blocks if present
                summary = re.sub(r"```[a-z]*\n?", "", summary)
                summary = re.sub(r"```", "", summary)
                summary = summary.strip()

                # Remove common prefixes that LLMs might add
                prefixes_to_remove = ["Summary:", "The scenario", "This scenario", "Scenario summary:", "Summary"]
                for prefix in prefixes_to_remove:
                    if summary.lower().startswith(prefix.lower()):
                        summary = summary[len(prefix) :].strip()
                        # Remove leading colon if present
                        if summary.startswith(":"):
                            summary = summary[1:].strip()
                        break

                logger.info(f"Generated summary: {summary[:100]}...")
                return summary
            else:
                logger.warning("LLM output is not a string")
                return None

        except Exception:
            logger.exception("Error generating summary")
            return None

    def generate_summary_from_file(self, file_path: Path | str) -> tuple[str | None, str | None]:
        """Generate a summary for a scenario file and extract its scenario ID.

        Args:
            file_path: Path to the scenario Python file

        Returns:
            Tuple of (scenario_id, summary). Returns (None, None) if extraction/generation fails.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"Scenario file not found: {file_path}")
            return None, None

        # Read the scenario code
        try:
            scenario_code = file_path.read_text(encoding="utf-8")
        except Exception:
            logger.exception(f"Failed to read scenario file {file_path}")
            return None, None

        # Extract scenario ID from the code
        scenario_id = self._extract_scenario_id(scenario_code)
        if not scenario_id:
            logger.warning(f"Could not extract scenario ID from {file_path}")
            # Try to extract from filename as fallback
            scenario_id = file_path.stem

        # Generate summary
        summary = self.generate_summary(scenario_code)

        return scenario_id, summary

    def _extract_scenario_id(self, code: str) -> str | None:
        """Extract the scenario ID from scenario code.

        Args:
            code: The scenario Python code as a string

        Returns:
            The scenario ID or None if not found
        """
        # Look for @register_scenario decorator
        match = re.search(r'@register_scenario\(["\']([^"\']+)["\']\)', code)
        if match:
            return match.group(1).strip()
        return None
