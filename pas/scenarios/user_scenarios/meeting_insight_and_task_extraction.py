"""
Scenario: meeting_insight_and_task_extraction
Agent automatically summarizes meeting discussion, extracts action items,
and offers to schedule follow-up or create tasks.

Flow:
1. System detects meeting transcript or notes.
2. Agent summarizes key insights.
3. Agent extracts action items.
4. User confirms creation of tasks/follow-up meeting.
5. Oracle writes follow-up event to calendar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar import StatefulCalendarApp


@dataclass
class MeetingInsightParams:
    """Parameters for meeting insight extraction."""
    meeting_title: str
    transcript_snippet: str
    followup_title: str
    followup_start: str
    followup_end: str


@register_scenario("meeting_insight_and_task_extraction")
class ScenarioMeetingInsightAndTaskExtraction(Scenario):
    """Extract insights & tasks from meeting notes, propose follow-up actions."""

    def __init__(self) -> None:
        super().__init__()
        self._params = self._get_default_params()

    def _get_default_params(self) -> MeetingInsightParams:
        return MeetingInsightParams(
            meeting_title="Product Roadmap Review",
            transcript_snippet=(
                "Alice: We need to finalize the Q4 launch timeline.\n"
                "Bob: I'll update the marketing brief by Wednesday.\n"
                "Carol: Let's meet next Monday to review progress."
            ),
            followup_title="Roadmap Progress Check-In",
            followup_start="2025-11-03T10:00:00Z",
            followup_end="2025-11-03T10:30:00Z",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        print("[DEBUG] meeting_insight_and_task_extraction: init_and_populate_apps called")
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        self.apps = [agui, system, calendar]
        print("[DEBUG] meeting_insight_and_task_extraction: apps initialized")

    def build_events_flow(self) -> None:
        print("[DEBUG] meeting_insight_and_task_extraction: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # System detects meeting transcript
            detected = aui.send_message_to_agent(
                content=f"[System] Meeting '{p.meeting_title}' just ended. Transcript snippet:\n{p.transcript_snippet}"
            ).depends_on(None, delay_seconds=1)

            # Agent summarizes key insights
            summary_text = (
                f"Meeting Summary for '{p.meeting_title}':\n"
                f"- Discussed Q4 launch timeline.\n"
                f"- Marketing brief to be updated by Wednesday (Bob).\n"
                f"- Agreed to review progress next Monday.\n"
            )
            summary_msg = aui.send_message_to_user(content=summary_text).depends_on(detected, delay_seconds=1)

            # Agent extracts action items
            tasks_text = (
                "Extracted Action Items:\n"
                "1. Bob → Update marketing brief by Wednesday\n"
                "2. Alice → Finalize Q4 launch plan\n"
                "3. Carol → Prepare progress deck for Monday meeting\n\n"
                "Would you like me to schedule the follow-up meeting?"
            )
            task_msg = aui.send_message_to_user(content=tasks_text).depends_on(summary_msg, delay_seconds=1)

            # Simulate user confirmation
            user_confirm = aui.send_message_to_agent(
                content="Yes, please schedule the follow-up meeting."
            ).depends_on(task_msg, delay_seconds=1)

            # Oracle creates follow-up calendar event
            followup_event = calendar.add_calendar_event(
                title=p.followup_title,
                start_datetime=p.followup_start,
                end_datetime=p.followup_end,
                description="Auto-created from meeting insight extraction",
                location="TBD",
                attendees=["alice@example.com", "bob@example.com", "carol@example.com"],
                tag=None,
            ).oracle().depends_on(user_confirm, delay_seconds=1)

            # Agent confirms success
            confirm_msg = aui.send_message_to_user(
                content=f"Follow-up meeting '{p.followup_title}' scheduled for {p.followup_start}."
            ).depends_on(followup_event, delay_seconds=1)

        self.events = [detected, summary_msg, task_msg, user_confirm, followup_event, confirm_msg]
        print(f"[DEBUG] meeting_insight_and_task_extraction: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        print("[DEBUG] meeting_insight_and_task_extraction: validate() called")
        try:
            events = env.event_log.list_view()
            p = self._params

            created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "StatefulCalendarApp"
                and event.action.function_name == "add_calendar_event"
                and event.action.args.get("title") == p.followup_title
                for event in events
            )

            print(f"[INFO] meeting_insight_and_task_extraction: Validation success={created}")
            return ScenarioValidationResult(success=created)

        except Exception as e:
            print(f"[ERROR] meeting_insight_and_task_extraction: Validation failed: {e}")
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
