"""
Scenario: proactive_meeting_preparation_helper
Agent proactively checks upcoming meetings and reminds participants.
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
class MeetingPrepParams:
    reminder_window_minutes: int
    reminder_message_template: str


# ---------- Scenario ----------
@register_scenario("proactive_meeting_preparation_helper")
class ScenarioMeetingPreparationHelper(Scenario):
    """Agent proactively detects meetings starting soon and notifies participants."""

    def __init__(self) -> None:
        super().__init__()
        self._params = MeetingPrepParams(
            reminder_window_minutes=10,
            reminder_message_template="⏰ Reminder: Your meeting '{title}' starts in {minutes} minutes.",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps."""
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        messaging = StatefulMessagingApp()
        self.apps = [agui, system, calendar, messaging]
        print("[DEBUG] proactive_meeting_preparation_helper: Apps initialized")

    def build_events_flow(self) -> None:
        """Define proactive meeting reminder workflow."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(StatefulCalendarApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Agent proactively initiates morning meeting check
            proactive_start = aui.send_message_to_user(
                content="Good morning! Let me check if you have any meetings starting soon."
            ).depends_on(None, delay_seconds=1)

            # Agent queries current time
            get_time = system.get_current_time().oracle().depends_on(proactive_start, delay_seconds=1)

            # Agent reads today's calendar events
            read_calendar = calendar.read_today_calendar_events().oracle().depends_on(get_time, delay_seconds=1)

            # Agent informs user of found meetings
            found_meeting = aui.send_message_to_user(
                content="I found several meetings on your calendar. Checking which ones are starting soon..."
            ).depends_on(read_calendar, delay_seconds=1)

            # Agent sends reminder message (simulated)
            reminder_text = p.reminder_message_template.format(title="Weekly Sync", minutes=p.reminder_window_minutes)
            send_reminder = messaging.send_message(
                user_id="user_team_channel",
                content=reminder_text,
            ).oracle().depends_on(found_meeting, delay_seconds=1)

            # Agent confirms reminders were sent
            confirm_msg = aui.send_message_to_user(
                content="I've sent reminders to all participants for upcoming meetings."
            ).depends_on(send_reminder, delay_seconds=1)

        self.events = [
            proactive_start,
            get_time,
            read_calendar,
            found_meeting,
            send_reminder,
            confirm_msg,
        ]
        print(f"[DEBUG] proactive_meeting_preparation_helper: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that proactive initiation and reminder sending occurred."""
        print("[DEBUG] proactive_meeting_preparation_helper: validate() called")
        try:
            events = env.event_log.list_view()

            # Check proactive start message
            proactive_detected = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "meeting" in e.action.args.get("content", "").lower()
                and "check" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Check reminder sent
            reminder_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and "reminder" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = proactive_detected and reminder_sent

            print("\n[VALIDATION SUMMARY]")
            print(f"  - Proactive initiation detected: {'PASS' if proactive_detected else 'FAIL'}")
            print(f"  - Reminder message sent:         {'PASS' if reminder_sent else 'FAIL'}")
            print(f"  => Scenario result: {'PASS' if success else 'FAIL'}\n")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
