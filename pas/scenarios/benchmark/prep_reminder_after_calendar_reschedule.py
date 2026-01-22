from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("prep_reminder_after_calendar_reschedule")
class PrepReminderAfterCalendarReschedule(PASScenario):
    """Agent automatically adjusts preparation reminder timing when a calendar event is rescheduled.

    The user has a calendar event "Board Presentation" scheduled for November 25th at 10:00 AM with a reminder titled "Finalize board presentation deck" due November 24th at 6:00 PM (the evening before). An email arrives indicating that the organizer has rescheduled the Board Presentation to November 27th at 2:00 PM (two days later, different time). The agent must: 1. Detect the reschedule notification, 2. Use search_events to identify the rescheduled event details, 3. List all reminders to find preparation-related reminders, 4. Match the preparation reminder to the rescheduled event by analyzing titles, 5. Calculate appropriate new reminder time (evening before the new date), 6. Edit the existing reminder's due_datetime to November 26th at 6:00 PM, 7. Confirm the adjustment to the user.

    This scenario exercises calendar-to-reminder dependency tracking, temporal reasoning across date changes, reminder search and modification workflows (list → identify → edit), and proactive deadline adjustment when upstream events shift. Unlike conversion or conflict scenarios, this tests the agent's ability to maintain preparation workflows when calendar events move.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.reminder = StatefulReminderApp(name="Reminders")
        self.email = StatefulEmailApp(name="Emails")

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
        self.board_presentation_event_id = board_presentation_event.event_id
        self.calendar.set_calendar_event(board_presentation_event)

        # Populate baseline data: Reminder "Finalize board presentation deck" due Nov 24, 2025 at 6:00 PM
        # This is the preparation reminder that will need to be adjusted when the event is rescheduled.
        self.prep_reminder_id = self.reminder.add_reminder(
            title="Finalize board presentation deck for tomorrow's meeting",
            due_datetime="2025-11-24 18:00:00",
            description="Complete and review the presentation slides before the board meeting tomorrow",
        )

        # Seed prior email context about the ORIGINAL date + prep expectations.
        # This makes the later reschedule email more realistic, and it explains why the user set a reminder one day before.
        self.original_prep_email_id = "board_pres_prep_original_001"
        self.user_ack_email_id = "sent_board_pres_prep_ack_001"

        prior_board_email = Email(
            email_id=self.original_prep_email_id,
            sender="board.members@company.example",
            recipients=[self.email.user_email],
            subject="Board Presentation (Nov 25, 10:00 AM) — prep expectations",
            content=(
                "Hi,\n\n"
                "Reminder that the Board Presentation is scheduled for Nov 25 at 10:00 AM.\n"
                "Please have your deck finalized and reviewed ahead of time.\n\n"
                "Thanks,\n"
                "Board Members"
            ),
            timestamp=datetime(2025, 11, 10, 16, 0, 0, tzinfo=UTC).timestamp(),
            is_read=True,
        )
        user_reply = Email(
            email_id=self.user_ack_email_id,
            sender=self.email.user_email,
            recipients=["board.members@company.example"],
            subject="Re: Board Presentation (Nov 25, 10:00 AM) — prep expectations",
            content=(
                "Thanks — confirmed.\n\n"
                "I'll set a prep reminder for the evening before (Nov 24 @ 6:00 PM) to finalize the deck.\n\n"
                "— John"
            ),
            timestamp=datetime(2025, 11, 10, 16, 12, 0, tzinfo=UTC).timestamp(),
            is_read=True,
            parent_id=self.original_prep_email_id,
        )
        self.email.folders[EmailFolderName.INBOX].add_email(prior_board_email)
        self.email.folders[EmailFolderName.SENT].add_email(user_reply)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.reminder, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Organizer deletes the old calendar event (first part of reschedule)
            # This creates a notification that the Board Presentation at the original time has been deleted
            delete_old_event = calendar_app.delete_calendar_event_by_attendee(
                event_id=self.board_presentation_event_id, who_delete="Board Members"
            ).delayed(15)

            # Environment Event 2: Calendar is updated with the rescheduled event (so search_events can discover it).
            add_new_event = calendar_app.add_calendar_event_by_attendee(
                who_add="Board Members",
                title="Board Presentation",
                start_datetime="2025-11-27 14:00:00",  # Nov 27, 2:00 PM (rescheduled)
                end_datetime="2025-11-27 15:00:00",  # Nov 27, 3:00 PM
                description="Quarterly board presentation (rescheduled from Nov 25).",
                location="Conference Room A",
                attendees=["Board Members"],
            ).delayed(30)

            # Environment Event 3: Organizer sends an email about the reschedule (more realistic cue than a group calendar message)
            reschedule_email_id = "board_pres_reschedule_001"
            reschedule_email_event = email_app.send_email_to_user_with_id(
                email_id=reschedule_email_id,
                sender="board.members@company.example",
                subject="Board Presentation rescheduled to Nov 27 (2:00 PM)",
                content=(
                    "Hi,\n\n"
                    "The Board Presentation has been rescheduled from Nov 25 (10:00 AM) to Nov 27 at 2:00 PM.\n\n"
                    "Please update any prep reminders you set for the original date so they still happen one day before the new meeting time.\n"
                    "Thanks,\n"
                    "Board Members"
                ),
            ).delayed(40)

            # Oracle Event 0: Agent reviews prior email thread context (INBOX + SENT) about the original date + reminder plan.
            list_inbox_event = (
                email_app.list_emails(folder_name="INBOX", offset=0, limit=10)
                .oracle()
                .depends_on(reschedule_email_event, delay_seconds=1)
            )
            list_sent_event = (
                email_app.list_emails(folder_name="SENT", offset=0, limit=10)
                .oracle()
                .depends_on(list_inbox_event, delay_seconds=1)
            )
            read_prior_board_email_event = (
                email_app.get_email_by_id(email_id=self.original_prep_email_id, folder_name="INBOX")
                .oracle()
                .depends_on(list_sent_event, delay_seconds=1)
            )
            read_user_ack_email_event = (
                email_app.get_email_by_id(email_id=self.user_ack_email_id, folder_name="SENT")
                .oracle()
                .depends_on(read_prior_board_email_event, delay_seconds=1)
            )

            # Agent detects the calendar reschedule notifications and searches for the rescheduled event
            # Motivation: The user received a reschedule email and the calendar was updated; the agent searches to confirm new timing.
            search_rescheduled_event = (
                calendar_app.search_events(query="Board Presentation")
                .oracle()
                .depends_on([add_new_event, read_user_ack_email_event], delay_seconds=2)
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
                aui.accept_proposal(content="Yes, please update it.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Agent updates the existing reminder in-place (preferred update pattern)
            # Motivation: user accepted the proposal; shift the prep reminder to the evening before the new date.
            update_reminder_event = (
                reminder_app.update_reminder(
                    reminder_id=self.prep_reminder_id,
                    title="Finalize board presentation deck for tomorrow's meeting",
                    description="Complete and review the presentation slides before the board meeting",
                    due_datetime="2025-11-26 18:00:00",  # Nov 26, 6:00 PM (evening before new date)
                    repetition_unit=None,
                    repetition_value=None,
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

        self.events = [
            delete_old_event,
            reschedule_email_event,
            add_new_event,
            list_inbox_event,
            list_sent_event,
            read_prior_board_email_event,
            read_user_ack_email_event,
            search_rescheduled_event,
            list_reminders_event,
            proposal_event,
            acceptance_event,
            update_reminder_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
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

            # STRICT Check 2: Agent deleted the old reminder
            # The agent must use delete_reminder to remove the outdated preparation reminder
            delete_reminder_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "delete_reminder"
                and e.action.args.get("reminder_id") is not None
                for e in log_entries
            )

            # STRICT Check 3: Agent added updated reminder with correct new due date
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

            # STRICT Check 4: Agent updated the existing reminder with the new due date (preferred single-call pattern)
            update_reminder_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "update_reminder"
                and e.action.args.get("reminder_id") is not None
                and "2025-11-26" in e.action.args.get("due_datetime", "")
                for e in log_entries
            )

            # All strict checks must pass for success
            reminder_updated = update_reminder_found or (delete_reminder_found and add_reminder_found)
            success = proposal_found and reminder_updated

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal mentioning Board Presentation reschedule and reminder")
                if not reminder_updated:
                    missing_checks.append(
                        "updating reminder timing (either update_reminder or delete+add) to Nov 26 at 6:00 PM"
                    )

                rationale = f"Missing critical agent actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
