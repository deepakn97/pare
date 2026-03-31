"""Data models for the annotation module."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

from pydantic import BaseModel

from pas.trajectory.models import TernaryDecision  # noqa: TC001 - Pydantic needs runtime access


class MessageType(StrEnum):
    """Classification of messages for UI rendering."""

    USER_ACTION = "user_action"
    TOOL_OBSERVATION = "tool_observation"
    PROPOSAL = "proposal"
    ENVIRONMENT_NOTIFICATION = "environment_notification"


class UIMessage(BaseModel):
    """A single renderable message for the annotation UI."""

    msg_type: MessageType
    content: str
    timestamp: float | None = None


class SampleResponse(BaseModel):
    """API response payload for a single annotation sample."""

    sample_id: str
    scenario_context: str | None
    messages: list[UIMessage]
    progress_completed: int
    progress_total: int


@dataclass
class ActionWithObservation:
    """A single user action with its formatted observation.

    .. deprecated::
        Part of old binary pipeline. Will be removed after UI update.
    """

    action: str  # e.g., "Messages__open_conversation(conversation_id='fc78...')"
    observation: str  # Formatted, human-readable observation
    raw_observation: Any = None  # Original observation data (for debugging)
    timestamp: float | None = None  # Unix timestamp of the action


@dataclass
class Turn:
    """A single turn of user interaction.

    .. deprecated::
        Part of old binary pipeline. Will be removed after UI update.
    """

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

    .. deprecated::
        Superseded by ``pas.trajectory.models.DecisionPoint`` which supports
        ternary decisions. Will be removed after UI update.

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
    user_agent_decision: TernaryDecision
    agent_proposal: str
    meta_task_description: str
    llm_input: str
    final_decision: bool
    gather_context_delta: str | None = None

    def get_turns(self) -> list[Turn]:
        """Parse and return the turns from context_json.

        Note: This method is kept for backward compatibility but is not used
        by the new ternary decision pipeline.
        """
        raise NotImplementedError("get_turns() is not supported in the ternary decision pipeline")

    # Message types to strip from UI rendering
    _STRIPPED_MSG_TYPES: frozenset[str] = frozenset({
        "system_prompt",
        "available_tools",
        "current_app_state",
        "unknown",
    })

    @staticmethod
    def _extract_observation_content(content: str) -> str:
        r"""Strip Meta-ARE boilerplate from tool observation content.

        Extracts the text between ``***`` delimiters from format:
        ``[OUTPUT OF STEP N] Observation:\\n***\\n<content>\\n***``

        Args:
            content: Raw tool-response content string.

        Returns:
            Cleaned observation text, or original content if pattern doesn't match.
        """
        match = re.search(r"\*\*\*\n(.*?)\n\*\*\*", content, re.DOTALL)
        return match.group(1).strip() if match else content

    @staticmethod
    def _extract_notification_content(content: str) -> str:
        r"""Strip wrapper from environment notification content.

        Extracts text between ``***`` delimiters from format:
        ``Environment notifications updates:\\n***\\n<content>\\n***``

        Args:
            content: Raw environment notification content string.

        Returns:
            Cleaned notification text.
        """
        match = re.search(r"\*\*\*\n(.*?)\n\*\*\*", content, re.DOTALL)
        return match.group(1).strip() if match else content

    @staticmethod
    def _extract_tool_name(user_action_content: str) -> str:
        """Extract tool name from a user_action message content.

        Parses the ``Action: AppName__tool_name`` line from ReAct format.

        Args:
            user_action_content: The assistant role message content.

        Returns:
            Tool name string, or empty string if not found.
        """
        match = re.search(r"Action:\s*(\S+)", user_action_content)
        return match.group(1) if match else ""

    def to_api_response(self, progress_completed: int, progress_total: int) -> SampleResponse:
        """Convert to structured API response for the annotation UI.

        Parses llm_input JSON, filters out non-renderable message types,
        formats observations and notifications for human readability,
        and returns a typed SampleResponse.

        Args:
            progress_completed: Number of completed annotations.
            progress_total: Total number of annotations.

        Returns:
            SampleResponse with filtered, typed, formatted messages.
        """
        from pas.annotation.observation_formatter import ObservationFormatter, format_notification

        raw_messages: list[dict[str, object]] = json.loads(self.llm_input)

        messages: list[UIMessage] = []
        last_tool_name = ""
        for msg in raw_messages:
            msg_type_str = str(msg.get("msg_type", "unknown"))
            if msg_type_str in self._STRIPPED_MSG_TYPES:
                continue

            content = str(msg.get("content", ""))

            # Track tool name from user_action for formatting the next tool_observation
            if msg_type_str == "user_action":
                last_tool_name = self._extract_tool_name(content)

            # Format tool observations using ObservationFormatter
            if msg_type_str == "tool_observation":
                raw_obs = self._extract_observation_content(content)
                content = ObservationFormatter.format(last_tool_name, raw_obs)

            # Format notifications to strip hex IDs
            if msg_type_str == "environment_notification":
                raw_notif = self._extract_notification_content(content)
                content = format_notification(raw_notif)

            timestamp_val = msg.get("timestamp")
            timestamp = float(timestamp_val) if isinstance(timestamp_val, (int, float)) else None

            messages.append(
                UIMessage(
                    msg_type=MessageType(msg_type_str),
                    content=content,
                    timestamp=timestamp,
                )
            )

        return SampleResponse(
            sample_id=self.sample_id,
            scenario_context=self.meta_task_description if self.meta_task_description else None,
            messages=messages,
            progress_completed=progress_completed,
            progress_total=progress_total,
        )


class Annotation(BaseModel):
    """A single annotation record."""

    annotation_id: str
    sample_id: str
    annotator_id: str
    human_decision: TernaryDecision
    gather_context_rationale: str | None = None
    timestamp: str

    @classmethod
    def create(
        cls,
        sample_id: str,
        annotator_id: str,
        human_decision: TernaryDecision,
    ) -> Annotation:
        """Create a new annotation record.

        Args:
            sample_id: The sample being annotated.
            annotator_id: The annotator's anonymous ID.
            human_decision: The human's accept/reject/gather_context decision.

        Returns:
            A new Annotation instance.
        """
        return cls(
            annotation_id=str(uuid4()),
            sample_id=sample_id,
            annotator_id=annotator_id,
            human_decision=human_decision,
            gather_context_rationale=None,
            timestamp=datetime.now().isoformat(),
        )

    def to_csv_row(self) -> str:
        """Convert to CSV row string."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            self.annotation_id,
            self.sample_id,
            self.annotator_id,
            self.human_decision,
            self.gather_context_rationale or "",
            self.timestamp,
        ])
        return output.getvalue()

    @classmethod
    def csv_header(cls) -> str:
        """Get CSV header row."""
        return "annotation_id,sample_id,annotator_id,human_decision,gather_context_rationale,timestamp\n"
