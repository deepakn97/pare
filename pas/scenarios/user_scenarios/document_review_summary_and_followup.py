"""
Scenario: proactive_document_review_summary_and_followup
Agent reviews recent document comments, summarizes key points,
and proactively proposes a follow-up meeting to resolve open issues.

Flow:
1. Agent detects new document feedback.
2. Agent summarizes review highlights.
3. Agent proposes a follow-up meeting.
4. User confirms scheduling.
5. Oracle creates a calendar event.
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
class DocumentReviewParams:
    document_title: str
    review_summary: str
    followup_title: str
    followup_start: str
    followup_end: str


# ---------- Scenario ----------
@register_scenario("proactive_document_review_summary_and_followup")
class ScenarioDocumentReviewSummaryAndFollowup(Scenario):
    """Agent summarizes document review and proactively schedules a follow-up meeting."""

    def __init__(self) -> None:
        super().__init__()
        self._params = self._get_default_params()

    def _get_default_params(self) -> DocumentReviewParams:
        return DocumentReviewParams(
            document_title="Q4 Product Design Proposal",
            review_summary=(
                "• The color palette needs to align with new brand guidelines.\n"
                "• The onboarding flow could be simplified for clarity.\n"
                "• Suggested adding a section on accessibility compliance.\n"
                "• Minor typos found in section 3.2."
            ),
            followup_title="Design Proposal Review Sync",
            followup_start="2025-11-04T09:00:00Z",
            followup_end="2025-11-04T09:30:00Z",
        )

    # ---------- App Initialization ----------
    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps used in this scenario."""
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        self.apps = [agui, system, calendar]

    # ---------- Event Flow ----------
    def build_events_flow(self) -> None:
        """Define proactive event flow for document review and meeting scheduling."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Agent detects and proactively summarizes feedback
            detect_feedback = aui.send_message_to_user(
                content=f"I noticed new comments on '{p.document_title}'. Here's a quick summary of key points:\n{p.review_summary}"
            ).depends_on(None, delay_seconds=1)

            # Agent proposes a follow-up meeting
            propose_meeting = aui.send_message_to_user(
                content=(
                    "Several issues need alignment. Would you like me to schedule a 30-minute follow-up meeting "
                    "to finalize decisions?"
                )
            ).depends_on(detect_feedback, delay_seconds=1)

            # User confirms scheduling
            confirm_user = aui.send_message_to_agent(
                content="Yes, please schedule the follow-up meeting for tomorrow morning."
            ).depends_on(propose_meeting, delay_seconds=1)

            # Oracle adds the calendar event
            add_event = (
                calendar.add_calendar_event(
                    title=p.followup_title,
                    start_datetime=p.followup_start,
                    end_datetime=p.followup_end,
                    description="Follow-up discussion for design proposal feedback.",
                    location="Virtual Meeting Room",
                    attendees=["design-team@example.com"],
                    tag=None,
                )
                .oracle()
                .depends_on(confirm_user, delay_seconds=1)
            )

            # Agent confirms success
            confirm_msg = aui.send_message_to_user(
                content=f"Follow-up meeting '{p.followup_title}' scheduled for {p.followup_start}."
            ).depends_on(add_event, delay_seconds=1)

        self.events = [
            detect_feedback,
            propose_meeting,
            confirm_user,
            add_event,
            confirm_msg,
        ]

    # ---------- Validation ----------
    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent summarized feedback and created a meeting."""
        print("[DEBUG] proactive_document_review_summary_and_followup: validate() called")

        try:
            events = env.event_log.list_view()
            p = self._params

            # Check if agent proactively mentioned the document and review summary
            proactive_summary = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and p.document_title.lower() in e.action.args.get("content", "").lower()
                for e in events
            )

            # Check if follow-up meeting was created
            followup_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("title") == p.followup_title
                for e in events
            )

            success = proactive_summary and followup_created

            print("\n[VALIDATION SUMMARY]")
            print(f"  - Proactive review summary detected: {'PASS' if proactive_summary else 'FAIL'}")
            print(f"  - Follow-up meeting created:         {'PASS' if followup_created else 'FAIL'}")
            print(f"  => Scenario result: {'PASS' if success else 'FAIL'}\n")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
