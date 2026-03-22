"""Data models for the annotation module."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel


@dataclass
class ActionWithObservation:
    """A single user action with its formatted observation."""

    action: str  # e.g., "Messages__open_conversation(conversation_id='fc78...')"
    observation: str  # Formatted, human-readable observation
    raw_observation: Any = None  # Original observation data (for debugging)
    timestamp: float | None = None  # Unix timestamp of the action


@dataclass
class Turn:
    """A single turn of user interaction."""

    turn_number: int
    notifications: list[str] = field(default_factory=list)
    actions: list[ActionWithObservation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "turn_number": self.turn_number,
            "notifications": self.notifications,
            "actions": [
                {"action": a.action, "observation": a.observation, "timestamp": a.timestamp} for a in self.actions
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Turn:
        """Create from dictionary."""
        return cls(
            turn_number=data["turn_number"],
            notifications=data.get("notifications", []),
            actions=[
                ActionWithObservation(
                    action=a["action"],
                    observation=a["observation"],
                    timestamp=a.get("timestamp"),
                )
                for a in data.get("actions", [])
            ],
        )


@dataclass
class DecisionPoint:
    """A single decision point extracted from a trace.

    Represents a moment when the user agent made an accept/reject decision
    on a proactive agent's proposal.
    """

    sample_id: str  # {scenario_id}_run_{run_number}_{content_hash}
    scenario_id: str
    run_number: int
    proactive_model_id: str
    user_model_id: str
    trace_file: Path
    meta_task_description: str  # From scenario metadata (may be empty)
    turns: list[Turn]  # All turns before this decision
    agent_proposal: str  # The proposal text
    user_agent_decision: bool  # True=accept, False=reject
    decision_timestamp: float  # Timestamp of the decision event

    @staticmethod
    def generate_sample_id(scenario_id: str, run_number: int, proposal: str, decision_timestamp: float) -> str:
        """Generate a unique sample ID.

        Args:
            scenario_id: The scenario identifier.
            run_number: The run number.
            proposal: The agent's proposal text.
            decision_timestamp: Timestamp of the decision.

        Returns:
            A unique sample ID string.
        """
        content = f"{scenario_id}_{run_number}_{proposal}_{decision_timestamp}"
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"{scenario_id}_run_{run_number}_{content_hash}"

    def to_sample_dict(self) -> dict[str, Any]:
        """Convert to dictionary for parquet storage."""
        return {
            "sample_id": self.sample_id,
            "scenario_id": self.scenario_id,
            "run_number": self.run_number,
            "proactive_model_id": self.proactive_model_id,
            "user_model_id": self.user_model_id,
            "trace_file": str(self.trace_file),
            "user_agent_decision": self.user_agent_decision,
            "agent_proposal": self.agent_proposal,
            "meta_task_description": self.meta_task_description,
            "decision_timestamp": self.decision_timestamp,
            "context_json": json.dumps({
                "turns": [t.to_dict() for t in self.turns],
            }),
        }


class Sample(BaseModel):
    """A sample for annotation (loaded from parquet)."""

    sample_id: str
    scenario_id: str
    run_number: int
    proactive_model_id: str
    user_model_id: str
    trace_file: str
    user_agent_decision: bool
    agent_proposal: str
    meta_task_description: str
    decision_timestamp: float
    context_json: str

    def get_turns(self) -> list[Turn]:
        """Parse and return the turns from context_json."""
        context = json.loads(self.context_json)
        return [Turn.from_dict(t) for t in context.get("turns", [])]

    def to_api_response(self, progress_completed: int, progress_total: int) -> dict[str, Any]:
        """Convert to API response format."""
        turns = self.get_turns()
        return {
            "sample_id": self.sample_id,
            "scenario_context": self.meta_task_description if self.meta_task_description else None,
            "turns": [t.to_dict() for t in turns],
            "agent_proposal": self.agent_proposal,
            "progress": {
                "completed": progress_completed,
                "total": progress_total,
            },
        }


class Annotation(BaseModel):
    """A single annotation record."""

    annotation_id: str
    sample_id: str
    annotator_id: str
    human_decision: bool
    timestamp: str

    @classmethod
    def create(cls, sample_id: str, annotator_id: str, human_decision: bool) -> Annotation:
        """Create a new annotation record.

        Args:
            sample_id: The sample being annotated.
            annotator_id: The annotator's anonymous ID.
            human_decision: The human's accept/reject decision.

        Returns:
            A new Annotation instance.
        """
        return cls(
            annotation_id=str(uuid4()),
            sample_id=sample_id,
            annotator_id=annotator_id,
            human_decision=human_decision,
            timestamp=datetime.now().isoformat(),
        )

    def to_csv_row(self) -> str:
        """Convert to CSV row string."""
        return f"{self.annotation_id},{self.sample_id},{self.annotator_id},{self.human_decision},{self.timestamp}\n"

    @classmethod
    def csv_header(cls) -> str:
        """Get CSV header row."""
        return "annotation_id,sample_id,annotator_id,human_decision,timestamp\n"
