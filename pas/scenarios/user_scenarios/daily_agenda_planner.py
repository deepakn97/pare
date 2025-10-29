"""
Scenario: daily_agenda_planner
Agent proactively reviews today’s calendar events and tasks,
summarizes the day’s agenda, and offers to schedule focus time or reminders.

Key features:
- Aggregates today’s meetings from the calendar.
- Retrieves pending tasks (simulated).
- Generates a proactive morning summary message.
- Offers follow-up action suggestions (e.g., schedule focus time).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar import StatefulCalendarApp


@dataclass
class AgendaParams:
    """Parameters for the daily agenda planner scenario."""
    date: str
    focus_time_start: str
    focus_time_end: str


@register_scenario("daily_agenda_planner")
class ScenarioDailyAgendaPlanner(Scenario):
    """Agent summarizes today’s schedule and offers to create focus time."""

    def __init__(self) -> None:
        super().__init__()
        self._params = self._get_default_params()

    def _get_default_params(self) -> AgendaParams:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return AgendaParams(
            date=today,
            focus_time_start=f"{today}T15:00:00Z",
            focus_time_end=f"{today}T17:00:00Z",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        print("[DEBUG] daily_agenda_planner: init_and_populate_apps called")
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        self.apps = [agui, system, calendar]
        print("[DEBUG] daily_agenda_planner: apps initialized")

    def build_events_flow(self) -> None:
        print("[DEBUG] daily_agenda_planner: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        p = self._params

        # Simulated example calendar events for the day
        todays_events = [
            {"title": "Team Standup", "time": "09:00 AM"},
            {"title": "Project Sync", "time": "11:00 AM"},
            {"title": "Client Call", "time": "14:00 PM"},
        ]
        pending_tasks = ["Prepare report slides", "Review budget proposal"]

        with EventRegisterer.capture_mode():
            # System detects it's morning
            detected = aui.send_message_to_agent(
                content=f"[System] It's morning of {p.date}. Reviewing today's schedule..."
            ).depends_on(None, delay_seconds=1)

            # Agent composes a summary of today's agenda
            events_summary = "\n".join([f"- {e['title']} at {e['time']}" for e in todays_events])
            tasks_summary = "\n".join([f"- {t}" for t in pending_tasks])
            summary_text = (
                f"Here’s your agenda for {p.date}:\n"
                f"Meetings:\n{events_summary}\n\n"
                f"Pending tasks:\n{tasks_summary}\n\n"
                f"Would you like me to block focus time from 3–5 PM?"
            )

            summary_msg = aui.send_message_to_user(content=summary_text).depends_on(detected, delay_seconds=1)

            # Simulate user confirming focus time scheduling
            user_reply = aui.send_message_to_agent(
                content="Yes, please schedule focus time from 3–5 PM."
            ).depends_on(summary_msg, delay_seconds=1)

            # Oracle creates focus time event
            focus_event = calendar.add_calendar_event(
                title="Focus Time",
                start_datetime=p.focus_time_start,
                end_datetime=p.focus_time_end,
                description="Reserved for deep work",
                location="",
                attendees=None,
                tag=None,
            ).oracle().depends_on(user_reply, delay_seconds=1)

            # Agent confirms success
            confirm_msg = aui.send_message_to_user(
                content="Focus time scheduled from 3–5 PM. Have a productive day!"
            ).depends_on(focus_event, delay_seconds=1)

        self.events = [detected, summary_msg, user_reply, focus_event, confirm_msg]
        print(f"[DEBUG] daily_agenda_planner: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        print("[DEBUG] daily_agenda_planner: validate() called")
        try:
            events = env.event_log.list_view()
            p = self._params

            focus_event_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "StatefulCalendarApp"
                and event.action.function_name == "add_calendar_event"
                and event.action.args.get("title") == "Focus Time"
                for event in events
            )

            print(f"[INFO] daily_agenda_planner: Validation success={focus_event_created}")
            return ScenarioValidationResult(success=focus_event_created)

        except Exception as e:
            print(f"[ERROR] daily_agenda_planner: Validation failed: {e}")
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
