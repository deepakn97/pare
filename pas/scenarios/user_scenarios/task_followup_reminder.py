"""
Scenario: task_followup_reminder
Agent checks calendar for upcoming tasks or follow-ups
and sends reminders to responsible participants via messaging.
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
class FollowupParams:
    tag_keyword: str
    reminder_message: str


@register_scenario("task_followup_reminder")
class ScenarioTaskFollowupReminder(Scenario):
    """Detect upcoming tasks in calendar and notify relevant participants."""

    def __init__(self) -> None:
        super().__init__()
        self._params = FollowupParams(
            tag_keyword="Task",
            reminder_message="Reminder: You have a pending task approaching its deadline.",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        print("[DEBUG] task_followup_reminder: init_and_populate_apps called")
        self.apps = [
            AgentUserInterface(),
            SystemApp(),
            StatefulCalendarApp(),
            StatefulMessagingApp(),
        ]
        print("[DEBUG] task_followup_reminder: apps initialized")

    def build_events_flow(self) -> None:
        print("[DEBUG] task_followup_reminder: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(StatefulCalendarApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Step 1: Trigger scenario
            start_check = aui.send_message_to_agent(
                content="[System] Proactive check for pending tasks this week."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Read current time
            now = system.get_current_time().oracle().depends_on(start_check, delay_seconds=1)

            # Step 3: Search calendar events by tag
            get_tasks = calendar.get_calendar_events_by_tag(
                tag=p.tag_keyword
            ).oracle().depends_on(now, delay_seconds=1)

            # Step 4: Notify user of found tasks
            summary = aui.send_message_to_user(
                content="🔍 Found calendar events tagged with 'Task'. Preparing reminders..."
            ).depends_on(get_tasks, delay_seconds=1)

            # Step 5: Send reminders to responsible participants
            send_reminder = messaging.send_message(
                user_id="user_001",  # mock recipient
                content=p.reminder_message,
            ).oracle().depends_on(summary, delay_seconds=1)

            # Step 6: Confirm completion
            finish = aui.send_message_to_user(
                content="All reminders sent successfully."
            ).depends_on(send_reminder, delay_seconds=1)

        self.events = [
            start_check,
            now,
            get_tasks,
            summary,
            send_reminder,
            finish,
        ]
        print(f"[DEBUG] task_followup_reminder: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Confirm that a reminder message was sent."""
        print("[DEBUG] task_followup_reminder: validate() called")
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
            print(f"[INFO] task_followup_reminder: Validation success={sent_msg}")
            return ScenarioValidationResult(success=sent_msg)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
