"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("prep_reminder_after_calendar_reschedule")
class PrepReminderAfterCalendarReschedule(PASScenario):
    """Agent automatically adjusts preparation reminder timing when a calendar event is rescheduled.

    The user has a calendar event "Board Presentation" scheduled for November 25th at 10:00 AM with a reminder titled "Finalize board presentation deck" due November 24th at 6:00 PM (the evening before). A calendar notification arrives indicating that the organizer has rescheduled the Board Presentation to November 27th at 2:00 PM (two days later, different time). The agent must: 1. Detect the calendar reschedule notification, 2. Use search_events to identify the rescheduled event details, 3. List all reminders to find preparation-related reminders, 4. Match the preparation reminder to the rescheduled event by analyzing titles, 5. Calculate appropriate new reminder time (evening before the new date), 6. Edit the existing reminder's due_datetime to November 26th at 6:00 PM, 7. Confirm the adjustment to the user.

    This scenario exercises calendar-to-reminder dependency tracking, temporal reasoning across date changes, reminder search and modification workflows (list → identify → edit), and proactive deadline adjustment when upstream events shift. Unlike conversion or conflict scenarios, this tests the agent's ability to maintain preparation workflows when calendar events move.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.reminder = StatefulReminderApp(name="Reminders")

        # Populate baseline data: Calendar event "Board Presentation" scheduled for Nov 25, 2025 at 10:00 AM
        # The event will be rescheduled by an environment event in Step 3, not seeded here as already rescheduled.
        # We seed the ORIGINAL event state here (before reschedule).
        board_presentation_event = CalendarEvent(
            event_id="board_pres_001",
            title="Board Presentation",
            start_datetime=datetime(2025, 11, 25, 10, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 25, 11, 0, 0, tzinfo=UTC).timestamp(),
            description="Quarterly board presentation",
            location="Conference Room A",
            attendees=["User", "Board Members"],
        )
        self.calendar.set_calendar_event(board_presentation_event)

        # Populate baseline data: Reminder "Finalize board presentation deck" due Nov 24, 2025 at 6:00 PM
        # This is the preparation reminder that will need to be adjusted when the event is rescheduled.
        self.reminder.add_reminder(
            title="Finalize board presentation deck",
            due_datetime="2025-11-24 18:00:00",
            description="Complete and review the presentation slides before the board meeting",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.reminder]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Organizer deletes the old calendar event (first part of reschedule)
            # This creates a notification that the Board Presentation at the original time has been deleted
            delete_old_event = calendar_app.delete_calendar_event_by_attendee(
                event_id="board_pres_001", who_delete="Board Members"
            ).delayed(15)

            # Environment Event 2: Organizer adds the rescheduled calendar event (second part of reschedule)
            # This creates a notification about the new Board Presentation time: Nov 27 at 2:00 PM
            add_new_event = calendar_app.add_calendar_event_by_attendee(
                who_add="Board Members",
                title="Board Presentation",
                start_datetime="2025-11-27 14:00:00",  # Nov 27, 2:00 PM (rescheduled)
                end_datetime="2025-11-27 15:00:00",  # Nov 27, 3:00 PM
                description=(
                    "Quarterly board presentation (rescheduled from Nov 25).\n\n"
                    "Please update any prep reminders/tasks you set for the original date so they still happen before "
                    "the new meeting time (for example, if you have a reminder that contains Board Presentation info, "
                    "shift it to the same evening time slot before the new date)."
                ),
                location="Conference Room A",
                attendees=["User", "Board Members"],
            ).delayed(2)

            # Agent detects the calendar reschedule notifications and searches for the rescheduled event
            # Motivation: The agent received two calendar notifications (delete + add) mentioning "Board Presentation"
            search_rescheduled_event = (
                calendar_app.search_events(query="Board Presentation")
                .oracle()
                .depends_on(add_new_event, delay_seconds=3)
            )

            # Agent lists all reminders to find preparation-related reminders
            # Motivation: The rescheduled-event notification explicitly asks the user to update prep reminders/tasks
            # to match the new date/time, so the agent checks existing reminders to find the relevant prep reminder.
            list_reminders_event = (
                reminder_app.get_all_reminders().oracle().depends_on(search_rescheduled_event, delay_seconds=2)
            )

            # Agent proposes adjusting the preparation reminder to align with the new event date
            # Motivation: The rescheduled-event notification asks to update prep reminders/tasks for the new date/time,
            # and the agent observed an existing prep reminder ("Finalize board presentation deck") that was tied to the
            # original schedule, so it proposes shifting it to the evening before the new date.
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed the Board Presentation has been rescheduled from November 25th to November 27th at 2:00 PM. Your preparation reminder 'Finalize board presentation deck' is currently set for November 24th at 6:00 PM. Would you like me to adjust it to November 26th at 6:00 PM (the evening before the new date)?"
                )
                .oracle()
                .depends_on(list_reminders_event, delay_seconds=2)
            )

            # User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please update the reminder to November 26th at 6:00 PM.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Agent deletes the old reminder (first part of update pattern)
            # Motivation: User accepted the proposal; need to remove outdated reminder before adding updated one
            # This write action depends on user acceptance
            delete_reminder_event = (
                reminder_app.delete_reminder(
                    reminder_id=next(iter(reminder_app.reminders.keys()))  # The first (and only) reminder ID
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Agent adds the updated reminder with new due date (second part of update pattern)
            # Motivation: User accepted the proposal to adjust the reminder timing
            # This write action depends on the delete completing
            add_reminder_event = (
                reminder_app.add_reminder(
                    title="Finalize board presentation deck",
                    due_datetime="2025-11-26 18:00:00",  # Nov 26, 6:00 PM (evening before new date)
                    description="Complete and review the presentation slides before the board meeting",
                )
                .oracle()
                .depends_on(delete_reminder_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            delete_old_event,
            add_new_event,
            search_rescheduled_event,
            list_reminders_event,
            proposal_event,
            acceptance_event,
            delete_reminder_event,
            add_reminder_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning the calendar reschedule and reminder adjustment
            # The proposal must reference both the Board Presentation reschedule and the reminder adjustment
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent searched calendar for the rescheduled event
            # The agent must use search_events to locate the Board Presentation
            calendar_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "search_events"
                for e in log_entries
            )

            # STRICT Check 3: Agent listed reminders to find preparation reminder
            # The agent must use get_all_reminders to check existing reminders
            list_reminders_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "get_all_reminders"
                for e in log_entries
            )

            # STRICT Check 4: Agent deleted the old reminder
            # The agent must use delete_reminder to remove the outdated preparation reminder
            delete_reminder_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "delete_reminder"
                and e.action.args.get("reminder_id") is not None
                for e in log_entries
            )

            # STRICT Check 5: Agent added updated reminder with correct new due date
            # The agent must use add_reminder with the adjusted due_datetime (Nov 26 at 6:00 PM)
            # Flexible on title/description wording, but strict on the date (Nov 26, 18:00)
            add_reminder_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "add_reminder"
                and "2025-11-26" in e.action.args.get("due_datetime", "")
                for e in log_entries
            )

            # All strict checks must pass for success
            success = (
                proposal_found
                and calendar_search_found
                and list_reminders_found
                and delete_reminder_found
                and add_reminder_found
            )

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal mentioning Board Presentation reschedule and reminder")
                if not calendar_search_found:
                    missing_checks.append("calendar search for rescheduled event")
                if not list_reminders_found:
                    missing_checks.append("listing reminders to find preparation reminder")
                if not delete_reminder_found:
                    missing_checks.append("deleting old reminder")
                if not add_reminder_found:
                    missing_checks.append("adding updated reminder with new due date (Nov 26 at 6:00 PM)")

                rationale = f"Missing critical agent actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
