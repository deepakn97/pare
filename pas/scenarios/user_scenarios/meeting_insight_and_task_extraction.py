"""
Scenario: proactive_meeting_insight_and_task_extraction
Agent proactively summarizes a meeting discussion, extracts action items,
and proposes follow-up scheduling.

Flow:
1. Agent detects a completed meeting and transcript.
2. Agent summarizes key insights and extracts tasks.
3. Agent asks if user wants a follow-up scheduled.
4. User confirms scheduling.
5. Oracle creates the follow-up event.
6. Agent confirms success.
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


# ---------- Parameters ----------
@dataclass
class MeetingInsightParams:
    meeting_title: str
    transcript_snippet: str
    followup_title: str
    followup_start: str
    followup_end: str


# ---------- Scenario ----------
@register_scenario("proactive_meeting_insight_and_task_extraction")
class ScenarioMeetingInsightAndTaskExtraction(Scenario):
    """Agent summarizes meeting insights, extracts tasks, and schedules follow-up."""

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
            followup_start="2025-11-05T10:00:00Z",
            followup_end="2025-11-05T10:30:00Z",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all apps used in this scenario."""
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        self.apps = [agui, system, calendar]

    def build_events_flow(self) -> None:
        """Build proactive flow: summary → task extraction → confirmation → follow-up scheduling."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Agent proactively initiates the summary after meeting ends
            proactive_intro = aui.send_message_to_user(
                content=(
                    f"I noticed the meeting '{p.meeting_title}' has just ended. "
                    f"Here's what was discussed:\n{p.transcript_snippet}"
                )
            ).depends_on(None, delay_seconds=1)

            # Agent summarizes key insights
            summary_text = (
                f"**Summary of '{p.meeting_title}':**\n"
                f"- Discussed Q4 launch timeline.\n"
                f"- Bob will update the marketing brief by Wednesday.\n"
                f"- Carol proposed a progress review next Monday.\n"
            )
            summary_msg = aui.send_message_to_user(content=summary_text).depends_on(proactive_intro, delay_seconds=1)

            # Agent extracts and lists action items
            tasks_text = (
                "Here are the extracted action items:\n"
                "1. Alice → Finalize Q4 launch plan.\n"
                "2. Bob → Update marketing brief by Wednesday.\n"
                "3. Carol → Prepare progress deck for next meeting.\n\n"
                "Would you like me to schedule a follow-up session?"
            )
            task_msg = aui.send_message_to_user(content=tasks_text).depends_on(summary_msg, delay_seconds=1)

            # User confirms scheduling
            user_confirm = aui.send_message_to_agent(
                content="Yes, please schedule the follow-up meeting."
            ).depends_on(task_msg, delay_seconds=1)

            # Oracle creates the calendar follow-up event
            followup_event = (
                calendar.add_calendar_event(
                    title=p.followup_title,
                    start_datetime=p.followup_start,
                    end_datetime=p.followup_end,
                    description="Follow-up session generated from meeting insights.",
                    location="TBD",
                    attendees=["alice@example.com", "bob@example.com", "carol@example.com"],
                    tag=None,
                )
                .oracle()
                .depends_on(user_confirm, delay_seconds=1)
            )

            # Agent confirms success
            confirm_msg = aui.send_message_to_user(
                content=f"Follow-up meeting '{p.followup_title}' has been scheduled for {p.followup_start}."
            ).depends_on(followup_event, delay_seconds=1)

        self.events = [proactive_intro, summary_msg, task_msg, user_confirm, followup_event, confirm_msg]
        print(f"[DEBUG] proactive_meeting_insight_and_task_extraction: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate proactive summary and successful follow-up scheduling."""
        print("[DEBUG] proactive_meeting_insight_and_task_extraction: validate() called")

        try:
            events = env.event_log.list_view()
            p = self._params

            # Agent proactively initiates meeting summary
            proactive_detected = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "meeting" in e.action.args.get("content", "").lower()
                and "ended" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Follow-up calendar event created
            event_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("title") == p.followup_title
                for e in events
            )

            success = proactive_detected and event_created

            print("\n[VALIDATION SUMMARY]")
            print(f"  - Proactive initiation detected: {'PASS' if proactive_detected else 'FAIL'}")
            print(f"  - Follow-up meeting created:     {'PASS' if event_created else 'FAIL'}")
            print(f"  => Scenario result: {'PASS' if success else 'FAIL'}\n")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            print(f"[ERROR] proactive_meeting_insight_and_task_extraction: Validation failed: {e}")
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
