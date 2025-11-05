"""
Scenario: proactive_post_meeting_summary_generator
Agent proactively detects recently ended meetings, summarizes them,
and sends the summary to participants automatically.
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
from pas.apps.messaging import StatefulMessagingApp


# ---------- Parameters ----------
@dataclass
class PostMeetingParams:
    summary_template: str


# ---------- Scenario ----------
@register_scenario("proactive_post_meeting_summary_generator")
class ScenarioProactivePostMeetingSummaryGenerator(Scenario):
    """Agent proactively summarizes completed meetings and notifies participants."""

    def __init__(self) -> None:
        super().__init__()
        self._params = PostMeetingParams(
            summary_template=(
                "Summary of '{title}':\n"
                "- Discussed project progress updates\n"
                "- Assigned next steps to team members\n"
                "- Scheduled next sync for next week"
            )
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all required apps."""
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        messaging = StatefulMessagingApp()
        self.apps = [agui, system, calendar, messaging]
        print("[DEBUG] proactive_post_meeting_summary_generator: Apps initialized")

    def build_events_flow(self) -> None:
        """Define proactive post-meeting summary workflow."""
        print("[DEBUG] proactive_post_meeting_summary_generator: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(StatefulCalendarApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Agent proactively detects recently ended meetings
            proactive_start = aui.send_message_to_user(
                content="I noticed your meeting just ended — let me summarize the discussion and share it with the team."
            ).depends_on(None, delay_seconds=1)

            # Get current time
            current_time = system.get_current_time().oracle().depends_on(proactive_start, delay_seconds=1)

            # Retrieve today's meetings
            read_meetings = calendar.read_today_calendar_events().oracle().depends_on(current_time, delay_seconds=1)

            # Agent informs user it's generating summary
            preparing_summary = aui.send_message_to_user(
                content="Generating post-meeting summary now..."
            ).depends_on(read_meetings, delay_seconds=1)

            # Create and send summary message to participants
            summary_text = p.summary_template.format(title="Product Sprint Sync")
            send_summary = messaging.send_message(
                user_id="team_channel",
                content=summary_text,
            ).oracle().depends_on(preparing_summary, delay_seconds=1)

            # Confirm to user that summaries were delivered
            finish = aui.send_message_to_user(
                content="I've sent the meeting summary to all participants."
            ).depends_on(send_summary, delay_seconds=1)

        self.events = [
            proactive_start,
            current_time,
            read_meetings,
            preparing_summary,
            send_summary,
            finish,
        ]
        print(f"[DEBUG] proactive_post_meeting_summary_generator: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that proactive initiation and summary dispatch occurred."""
        print("[DEBUG] proactive_post_meeting_summary_generator: validate() called")

        try:
            events = env.event_log.list_view()

            # Check proactive initiation message
            proactive_detected = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "meeting just ended" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Check message summary sent to participants
            summary_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and "summary" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = proactive_detected and summary_sent

            print("\n[VALIDATION SUMMARY]")
            print(f"  - Proactive initiation detected: {'PASS' if proactive_detected else 'FAIL'}")
            print(f"  - Summary message sent:          {'PASS' if summary_sent else 'FAIL'}")
            print(f"  => Scenario result: {'PASS' if success else 'FAIL'}\n")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            print(f"[ERROR] proactive_post_meeting_summary_generator: Validation failed: {e}")
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
