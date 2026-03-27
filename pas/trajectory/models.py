"""Data models for trajectory analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class DecisionPoint:
    """A proposal-decision pair extracted from a trace.

    Represents a single decision point where the user agent responds
    to a proactive agent's proposal. The decision can be accept, reject,
    or gather_context (user called another tool before accepting/rejecting).
    """

    sample_id: str
    scenario_id: str
    run_number: int
    proactive_model_id: str
    user_model_id: str
    trace_file: Path
    user_agent_decision: str  # "accept", "reject", "gather_context"
    llm_input: list[dict[str, Any]]  # Raw message array with timestamp annotations
    agent_proposal: str
    final_decision: bool  # True=accept, False=reject (always set)
    meta_task_description: str
    gather_context_delta: list[dict[str, Any]] | None = None

    @staticmethod
    def generate_sample_id(scenario_id: str, run_number: int, proposal_index: int) -> str:
        """Generate a unique sample ID.

        Args:
            scenario_id: The scenario identifier.
            run_number: The run number.
            proposal_index: Zero-based index of the proposal in the trace.

        Returns:
            Unique sample ID string.
        """
        return f"{scenario_id}_run_{run_number}_p{proposal_index}"

    def to_sample_dict(self) -> dict[str, str | int | bool | None]:
        """Serialize to dict for parquet storage.

        Returns:
            Dictionary with all fields, llm_input and gather_context_delta as JSON strings.
        """
        return {
            "sample_id": self.sample_id,
            "scenario_id": self.scenario_id,
            "run_number": self.run_number,
            "proactive_model_id": self.proactive_model_id,
            "user_model_id": self.user_model_id,
            "trace_file": str(self.trace_file),
            "user_agent_decision": self.user_agent_decision,
            "llm_input": json.dumps(self.llm_input),
            "agent_proposal": self.agent_proposal,
            "final_decision": self.final_decision,
            "meta_task_description": self.meta_task_description,
            "gather_context_delta": json.dumps(self.gather_context_delta) if self.gather_context_delta else None,
        }
