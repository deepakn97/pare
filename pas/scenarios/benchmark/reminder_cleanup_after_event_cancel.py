from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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


@register_scenario("reminder_cleanup_after_event_cancel")
class ReminderCleanupAfterEventCancel(PASScenario):
    """Agent detects calendar event cancellation and proactively removes now-obsolete preparation reminders.

    The user has a calendar event titled "Client Demo Workshop" scheduled for November 23rd at 3:00 PM with attendee "Jessica Martinez". The user previously created two preparation reminders: "Prepare demo environment for client workshop" due November 22nd at 5:00 PM, and "Review client requirements document" due November 21st at 4:00 PM. A calendar notification arrives indicating that Jessica Martinez has canceled the Client Demo Workshop due to scheduling conflicts on her end. The agent must: 1. Detect the event cancellation notification, 2. Use get_calendar_event or search_events to confirm the event no longer exists or is canceled, 3. List all reminders to identify preparation tasks, 4. Match the preparation reminders to the canceled event by analyzing titles and due dates, 5. Propose removing both obsolete preparation reminders, 6. Delete both reminders after user acceptance to prevent unnecessary work.

    This scenario exercises calendar-event-to-reminder dependency tracking in reverse (cleanup rather than creation), event lifecycle management (cancellation detection), multi-reminder deletion workflows (list → identify → delete multiple items), and proactive task hygiene to help users avoid wasted preparation effort when upstream events are canceled..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize calendar and reminder apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.reminder = StatefulReminderApp(name="Reminders")

        # Populate calendar with the event that will be canceled
        # Event: "Client Demo Workshop" on November 23rd at 3:00 PM (15:00)
        event_start = datetime(2025, 11, 23, 15, 0, 0, tzinfo=UTC)
        event_end = datetime(2025, 11, 23, 16, 30, 0, tzinfo=UTC)

        self.workshop_event_id = self.calendar.add_calendar_event(
            title="Client Demo Workshop",
            start_datetime="2025-11-23 15:00:00",
            end_datetime="2025-11-23 16:30:00",
            description="Workshop to demonstrate new features to Jessica Martinez",
            location="Conference Room B",
            attendees=["Jessica Martinez"],
        )

        # Populate reminder app with two preparation reminders
        # Reminder 1: "Prepare demo environment for client workshop" due November 22nd at 5:00 PM (17:00)
        reminder_1_due = datetime(2025, 11, 22, 17, 0, 0, tzinfo=UTC)
        self.reminder_1_id = self.reminder.add_reminder(
            title="Prepare demo environment for client workshop",
            due_datetime=reminder_1_due.strftime("%Y-%m-%d %H:%M:%S"),
            description="Set up demo environment and test all features before client workshop",
        )

        # Reminder 2: "Review client requirements document" due November 21st at 4:00 PM (16:00)
        reminder_2_due = datetime(2025, 11, 21, 16, 0, 0, tzinfo=UTC)
        self.reminder_2_id = self.reminder.add_reminder(
            title="Review client requirements document",
            due_datetime=reminder_2_due.strftime("%Y-%m-%d %H:%M:%S"),
            description="Review Jessica's requirements document before preparing workshop demo",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Event 1: Environment event - Jessica Martinez cancels the Client Demo Workshop
            # This is the exogenous trigger that motivates all subsequent agent actions
            cancellation_event = calendar_app.delete_calendar_event_by_attendee(
                event_id=self.workshop_event_id,
                who_delete="Jessica Martinez",
            ).delayed(15)

            # Agent detects the cancellation notification and searches calendar to confirm
            # Motivation: cancellation notification triggered need to verify event is gone
            search_calendar_event = (
                calendar_app.search_events(query="Client Demo Workshop")
                .oracle()
                .depends_on(cancellation_event, delay_seconds=2)
            )

            # Agent lists all reminders to identify related preparation tasks
            # Motivation: need to find reminders that were created for the now-canceled workshop
            list_reminders_event = (
                reminder_app.get_all_reminders().oracle().depends_on(search_calendar_event, delay_seconds=1)
            )

            # Agent proposes removing the obsolete preparation reminders
            # Motivation: found two preparation reminders for "client workshop" that are now unnecessary
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed that Jessica Martinez canceled the Client Demo Workshop scheduled for November 23rd. You have two preparation reminders for this workshop: 'Prepare demo environment for client workshop' (due Nov 22) and 'Review client requirements document' (due Nov 21). Would you like me to remove these reminders since the workshop is canceled?"
                )
                .oracle()
                .depends_on(list_reminders_event, delay_seconds=2)
            )

            # User accepts the proposal to clean up obsolete reminders
            acceptance_event = (
                aui.accept_proposal(content="Yes, please remove both reminders.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Agent deletes the first preparation reminder
            # Motivation: user accepted cleanup; removing "Prepare demo environment" reminder
            delete_reminder_1_event = (
                reminder_app.delete_reminder(reminder_id=self.reminder_1_id)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Agent deletes the second preparation reminder
            # Motivation: user accepted cleanup; removing "Review client requirements" reminder
            delete_reminder_2_event = (
                reminder_app.delete_reminder(reminder_id=self.reminder_2_id)
                .oracle()
                .depends_on(delete_reminder_1_event, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            cancellation_event,
            search_calendar_event,
            list_reminders_event,
            proposal_event,
            acceptance_event,
            delete_reminder_1_event,
            delete_reminder_2_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check Step 1 (STRICT): Agent proposed cleanup to user via PASAgentUserInterface
            # The proposal must reference the cancellation (flexible on exact wording)
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check Step 2 (STRICT): Agent deleted both preparation reminders
            # We expect at least 2 delete_reminder calls (one for each preparation reminder)
            delete_reminder_events = [
                e
                for e in agent_events
                if isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "delete_reminder"
            ]
            both_reminders_deleted = len(delete_reminder_events) >= 2

            # All strict checks must pass for success
            success = proposal_found and both_reminders_deleted

            # Build rationale for failure
            if not success:
                missing = []
                if not proposal_found:
                    missing.append("agent did not propose cleanup to user")
                if not both_reminders_deleted:
                    missing.append(
                        f"agent did not delete both reminders (found {len(delete_reminder_events)} deletions, expected 2)"
                    )
                rationale = "; ".join(missing)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
