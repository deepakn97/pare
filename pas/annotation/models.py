"""Data models for the annotation module."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

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
    tutorial: bool = False


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
    tutorial: bool = False
    correct_decision: TernaryDecision | None = None
    explanation: str | None = None

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
            tutorial=self.tutorial,
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
        gather_context_rationale: str | None = None,
    ) -> Annotation:
        """Create a new annotation record.

        Args:
            sample_id: The sample being annotated.
            annotator_id: The annotator's anonymous ID.
            human_decision: The human's accept/reject/gather_context decision.
            gather_context_rationale: Free-text rationale when decision is gather_context.

        Returns:
            A new Annotation instance.
        """
        return cls(
            annotation_id=str(uuid4()),
            sample_id=sample_id,
            annotator_id=annotator_id,
            human_decision=human_decision,
            gather_context_rationale=gather_context_rationale,
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
