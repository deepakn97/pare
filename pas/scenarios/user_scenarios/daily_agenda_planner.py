"""
Scenario: proactive_daily_agenda_planner
Agent proactively reviews today's calendar events and tasks,
summarizes the agenda, and offers to schedule focus time or reminders.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar import StatefulCalendarApp


# ---------- Logger ----------
logger = logging.getLogger(__name__)


# ---------- Parameters ----------
@dataclass
class AgendaParams:
    """Parameters for proactive daily agenda planner."""

    date: str
    focus_time_start: str
    focus_time_end: str


# ---------- Scenario ----------
@register_scenario("proactive_daily_agenda_planner")
class ScenarioDailyAgendaPlanner(Scenario):
    """Agent summarizes today's schedule and offers to create focus time."""

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
        """Initialize apps."""
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        self.apps = [agui, system, calendar]
        logger.debug("proactive_daily_agenda_planner: Apps initialized")

    def build_events_flow(self) -> None:
        """Build proactive flow for daily agenda planning."""
        logger.debug("proactive_daily_agenda_planner: Building event flow")

        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Agent proactively starts the day
            morning_trigger = aui.send_message_to_user(
                content=f"Good morning! Let me check your agenda for {p.date}."
            ).depends_on(None, delay_seconds=1)

            # Agent retrieves today's calendar events (oracle)
            start_dt = f"{p.date}T00:00:00Z"
            end_dt = f"{p.date}T23:59:59Z"
            fetch_events = (
                calendar.get_calendar_events_from_to(
                    start_datetime=start_dt, end_datetime=end_dt
                )
                .oracle()
                .depends_on(morning_trigger, delay_seconds=2)
            )

            # Agent summarizes schedule and tasks
            summary_message = aui.send_message_to_user(
                content=(
                    f"Here’s your plan for {p.date}:\n"
                    f"- Meetings: Standup at 9AM, Project Sync at 11AM, Client Call at 2PM.\n"
                    f"- Tasks: Prepare report slides, Review budget proposal.\n\n"
                    f"Would you like me to block focus time from 3–5 PM?"
                )
            ).depends_on(fetch_events, delay_seconds=2)

            # User confirms scheduling
            user_reply = aui.send_message_to_agent(
                content="Yes, please schedule focus time from 3–5 PM."
            ).depends_on(summary_message, delay_seconds=2)

            # Agent creates focus time event (oracle)
            create_focus_time = (
                calendar.add_calendar_event(
                    title="Focus Time",
                    start_datetime=p.focus_time_start,
                    end_datetime=p.focus_time_end,
                    description="Reserved for deep work",
                    location="",
                    attendees=None,
                    tag=None,
                )
                .oracle()
                .depends_on(user_reply, delay_seconds=2)
            )

            # Agent confirms success
            confirm_msg = aui.send_message_to_user(
                content="I've scheduled Focus Time from 3–5 PM. Have a productive day!"
            ).depends_on(create_focus_time, delay_seconds=2)

        self.events = [
            morning_trigger,
            fetch_events,
            summary_message,
            user_reply,
            create_focus_time,
            confirm_msg,
        ]
        logger.debug(f"proactive_daily_agenda_planner: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate proactive summary and focus-time creation."""
        logger.debug("proactive_daily_agenda_planner: validate() called")

        try:
            events = env.event_log.list_view()

            # Detect proactive morning message
            proactive_summary = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    kw in e.action.args.get("content", "").lower()
                    for kw in ["good morning", "agenda", "plan for", "focus time"]
                )
                for e in events
                if e.event_type in (EventType.ENV, EventType.AGENT)
            )

            # Detect focus time creation
            focus_event_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("title") == "Focus Time"
                for e in events
            )

            success = proactive_summary and focus_event_created

            logger.debug("[VALIDATION SUMMARY]")
            logger.debug(f"  - Proactive morning summary detected: {'PASS' if proactive_summary else 'FAIL'}")
            logger.debug(f"  - Focus Time event created:           {'PASS' if focus_event_created else 'FAIL'}")
            logger.debug(f"  => Scenario result: {'PASS' if success else 'FAIL'}")

            return ScenarioValidationResult(success=success)

        except Exception as exc:
            logger.error(f"[ERROR] daily_agenda_planner: Validation failed: {exc}")
            return ScenarioValidationResult(success=False, exception=exc)
