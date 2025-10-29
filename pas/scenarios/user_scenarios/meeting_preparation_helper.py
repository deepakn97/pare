"""
Scenario: meeting_preparation_helper
Agent proactively checks the calendar for meetings starting soon
and sends participants a reminder message with meeting details.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, EventRegisterer

from pas.apps.calendar import StatefulCalendarApp
from pas.apps.messaging import StatefulMessagingApp


@dataclass
class MeetingPrepParams:
    reminder_window_minutes: int
    reminder_message_template: str


@register_scenario("meeting_preparation_helper")
class ScenarioMeetingPreparationHelper(Scenario):
    """Detect meetings starting soon and notify participants with agenda details."""

    def __init__(self) -> None:
        super().__init__()
        self._params = MeetingPrepParams(
            reminder_window_minutes=10,
            reminder_message_template="Reminder: Your meeting '{title}' starts in {minutes} minutes.",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        print("[DEBUG] meeting_preparation_helper: init_and_populate_apps called")
        self.apps = [
            AgentUserInterface(),
            SystemApp(),
            StatefulCalendarApp(),
            StatefulMessagingApp(),
        ]
        print("[DEBUG] meeting_preparation_helper: apps initialized")

    def build_events_flow(self) -> None:
        print("[DEBUG] meeting_preparation_helper: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(StatefulCalendarApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Step 1: Trigger check
            start_check = aui.send_message_to_agent(
                content="[System] Check for meetings starting soon."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Get current time
            current_time = system.get_current_time().oracle().depends_on(start_check, delay_seconds=1)

            # Step 3: Get today's meetings
            todays_meetings = calendar.read_today_calendar_events().oracle().depends_on(current_time, delay_seconds=1)

            # Step 4: Notify user of upcoming meeting
            found_meeting = aui.send_message_to_user(
                content="Found meetings scheduled today. Checking which ones start soon..."
            ).depends_on(todays_meetings, delay_seconds=1)

            # Step 5: Send reminder (simulated)
            reminder_text = p.reminder_message_template.format(title="Weekly Sync", minutes=p.reminder_window_minutes)
            send_reminder = messaging.send_message(
                user_id="user_001",  # mock participant
                content=reminder_text,
            ).oracle().depends_on(found_meeting, delay_seconds=1)

            # Step 6: Final confirmation to user
            finish = aui.send_message_to_user(
                content="Meeting reminders sent successfully."
            ).depends_on(send_reminder, delay_seconds=1)

        self.events = [
            start_check,
            current_time,
            todays_meetings,
            found_meeting,
            send_reminder,
            finish,
        ]
        print(f"[DEBUG] meeting_preparation_helper: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Confirm that a reminder message was sent."""
        print("[DEBUG] meeting_preparation_helper: validate() called")
        try:
            events = env.event_log.list_view()

            def stringify(e) -> str:
                parts = []
                if hasattr(e, "action"):
                    parts.extend([
                        getattr(e.action, "function_name", ""),
                        getattr(e.action, "app_name", ""),
                    ])
                return " ".join(parts).lower()

            sent_msg = any("send_message" in stringify(e) for e in events)
            print(f"[INFO] meeting_preparation_helper: Validation success={sent_msg}")
            return ScenarioValidationResult(success=sent_msg)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
