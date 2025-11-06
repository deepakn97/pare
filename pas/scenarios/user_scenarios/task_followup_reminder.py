"""
Scenario: proactive_task_followup_reminder
Agent proactively checks calendar for tasks approaching deadlines
and sends reminder messages to responsible participants.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar import StatefulCalendarApp
from pas.apps.messaging import StatefulMessagingApp


# ---------- Logger ----------
logger = logging.getLogger(__name__)


# ---------- Parameters ----------
@dataclass
class FollowupParams:
    tag_keyword: str
    reminder_message: str


# ---------- Scenario ----------
@register_scenario("proactive_task_followup_reminder")
class ScenarioProactiveTaskFollowupReminder(Scenario):
    """Proactively detects near-deadline tasks and reminds assigned users."""

    def __init__(self) -> None:
        super().__init__()
        self._params = FollowupParams(
            tag_keyword="Task",
            reminder_message="Reminder: You have a pending task approaching its deadline. Please review and update your progress.",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize simulation apps."""
        aui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        messaging = StatefulMessagingApp()
        self.apps = [aui, system, calendar, messaging]
        logger.debug("proactive_task_followup_reminder: Apps initialized")

    def build_events_flow(self) -> None:
        """Define proactive task reminder workflow."""
        logger.debug("proactive_task_followup_reminder: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(StatefulCalendarApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Agent proactively checks upcoming tasks
            proactive_start = aui.send_message_to_user(
                content="I noticed you have some tasks due soon — shall I send reminders to the responsible team members?"
            ).depends_on(None, delay_seconds=1)

            # User approves proactive reminder action
            user_confirm = aui.send_message_to_agent(
                content="Yes, please send reminders for tasks due this week."
            ).depends_on(proactive_start, delay_seconds=1)

            # Retrieve current system time
            current_time = system.get_current_time().oracle().depends_on(user_confirm, delay_seconds=1)

            # Search calendar for tagged tasks
            task_events = calendar.get_calendar_events_by_tag(
                tag=p.tag_keyword
            ).oracle().depends_on(current_time, delay_seconds=1)

            # Agent summarizes found tasks
            summary_msg = aui.send_message_to_user(
                content=f"I found several calendar entries tagged with '{p.tag_keyword}'. Sending reminders now..."
            ).depends_on(task_events, delay_seconds=1)

            # Send reminder to relevant participants
            send_reminder = messaging.send_message(
                user_id="team_user",
                content=p.reminder_message,
            ).oracle().depends_on(summary_msg, delay_seconds=1)

            # Confirm completion
            finish = aui.send_message_to_user(
                content="All reminders were sent successfully. Would you like me to create a summary report?"
            ).depends_on(send_reminder, delay_seconds=1)

        self.events = [
            proactive_start,
            user_confirm,
            current_time,
            task_events,
            summary_msg,
            send_reminder,
            finish,
        ]
        logger.debug(f"proactive_task_followup_reminder: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate proactive trigger, task search, and reminder message."""
        logger.debug("proactive_task_followup_reminder: validate() called")

        try:
            events = env.event_log.list_view()
            p = self._params

            # Check proactive trigger
            proactive_triggered = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "tasks due soon" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Check task search in calendar
            task_search_executed = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_by_tag"
                and p.tag_keyword.lower() in str(e.action.args.get("tag", "")).lower()
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

            success = proactive_triggered and task_search_executed and reminder_sent

            logger.debug("[VALIDATION SUMMARY]")
            logger.debug(f"  - Proactive detection triggered: {'PASS' if proactive_triggered else 'FAIL'}")
            logger.debug(f"  - Calendar task search executed: {'PASS' if task_search_executed else 'FAIL'}")
            logger.debug(f"  - Reminder messages sent:        {'PASS' if reminder_sent else 'FAIL'}")
            logger.debug(f"  => Scenario result: {'PASS' if success else 'FAIL'}")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            logger.error(f"[ERROR] proactive_task_followup_reminder: Validation failed: {e}")
            return ScenarioValidationResult(success=False, exception=e)
