"""
Scenario: document_review_summary_and_followup
Agent reviews recent document comments, summarizes key points,
and proposes a follow-up meeting to resolve open issues.

Flow:
1. System detects new document feedback.
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


@dataclass
class DocumentReviewParams:
    document_title: str
    review_summary: str
    followup_title: str
    followup_start: str
    followup_end: str


@register_scenario("document_review_summary_and_followup")
class ScenarioDocumentReviewSummaryAndFollowup(Scenario):
    """Summarize document review and schedule a follow-up meeting."""

    def __init__(self) -> None:
        super().__init__()
        self._params = self._get_default_params()

    def _get_default_params(self) -> DocumentReviewParams:
        return DocumentReviewParams(
            document_title="Q4 Product Design Proposal",
            review_summary=(
                "• The color palette needs to align with new brand guidelines.\n"
                "• The user onboarding flow lacks clarity.\n"
                "• Suggested adding a section on accessibility compliance.\n"
                "• Minor typos found in section 3.2."
            ),
            followup_title="Design Proposal Review Sync",
            followup_start="2025-11-04T09:00:00Z",
            followup_end="2025-11-04T09:30:00Z",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps used in this scenario."""
        print("[DEBUG] document_review_summary_and_followup: init_and_populate_apps called")
        self.apps = [AgentUserInterface(), SystemApp(), StatefulCalendarApp()]
        print("[DEBUG] document_review_summary_and_followup: apps initialized")

    def build_events_flow(self) -> None:
        """Define event flow."""
        print("[DEBUG] document_review_summary_and_followup: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # System detects document feedback
            detected = aui.send_message_to_agent(
                content=f"[System] New feedback received for document: '{p.document_title}'."
            ).depends_on(None, delay_seconds=1)

            # Agent summarizes key comments
            summary_msg = aui.send_message_to_user(
                content=f"Document '{p.document_title}' Review Summary:\n{p.review_summary}"
            ).depends_on(detected, delay_seconds=1)

            # Agent proposes a follow-up meeting
            proposal = aui.send_message_to_user(
                content=(
                    "Several points need alignment. Would you like to schedule a 30-minute follow-up meeting "
                    "to resolve open design items?"
                )
            ).depends_on(summary_msg, delay_seconds=1)

            # Simulate user confirmation
            confirm_user = aui.send_message_to_agent(
                content="Yes, please schedule it for next Tuesday morning."
            ).depends_on(proposal, delay_seconds=1)

            # Oracle adds calendar event
            add_event = calendar.add_calendar_event(
                title=p.followup_title,
                start_datetime=p.followup_start,
                end_datetime=p.followup_end,
                description="Follow-up discussion for design proposal feedback.",
                location="Virtual Meeting Room",
                attendees=["design-team@example.com"],
                tag=None,
            ).oracle().depends_on(confirm_user, delay_seconds=1)

            # Agent confirms success
            confirm_msg = aui.send_message_to_user(
                content=f"Follow-up meeting '{p.followup_title}' scheduled for {p.followup_start}."
            ).depends_on(add_event, delay_seconds=1)

        self.events = [detected, summary_msg, proposal, confirm_user, add_event, confirm_msg]
        print(f"[DEBUG] document_review_summary_and_followup: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        print("[DEBUG] document_review_summary_and_followup: validate() called")
        try:
            events = env.event_log.list_view()
            p = self._params

            created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("title") == p.followup_title
                for e in events
            )

            print(f"[INFO] document_review_summary_and_followup: Validation success={created}")
            return ScenarioValidationResult(success=created)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
