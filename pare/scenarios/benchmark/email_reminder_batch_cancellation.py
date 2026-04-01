"""Scenario for batch cancellation of reminders based on email notification."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulEmailApp,
)
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("email_reminder_batch_cancellation")
class EmailReminderBatchCancellation(PAREScenario):
    """Agent cancels multiple reminders based on project cancellation notification received via email.

    Story:
    1. User has three active reminders related to the "Aurora Marketing Campaign" project
    2. User also has reminders for other projects (Quarterly Report, Team Building)
    3. User receives an email from project lead Sarah Martinez saying Aurora campaign is canceled
    4. Agent reads the email and finds Aurora-related reminders
    5. Agent proposes deleting only the three Aurora reminders (not the other project reminders)
    6. User accepts
    7. Agent deletes the three Aurora reminders, leaving other project reminders intact

    This scenario exercises email-triggered reminder cleanup, cross-app information matching
    (email content to reminder search), selective batch reminder deletion, and ensures
    agent doesn't over-delete unrelated reminders.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize reminder app
        self.reminder = StatefulReminderApp(name="Reminders")

        # Add three Aurora-related reminders using the proper API
        self.reminder_id_1 = self.reminder.add_reminder(
            title="Review Aurora campaign draft",
            due_datetime="2025-12-01 14:00:00",
            description="Review the marketing draft for Aurora Marketing Campaign before team review",
        )

        self.reminder_id_2 = self.reminder.add_reminder(
            title="Submit Aurora budget proposal",
            due_datetime="2025-12-03 16:00:00",
            description="Submit budget proposal for Aurora Marketing Campaign to finance team",
        )

        self.reminder_id_3 = self.reminder.add_reminder(
            title="Aurora campaign kickoff meeting prep",
            due_datetime="2025-12-05 10:00:00",
            description="Prepare presentation slides and materials for Aurora Marketing Campaign kickoff meeting",
        )

        # Add non-Aurora reminders (these should NOT be deleted)
        self.other_reminder_id_1 = self.reminder.add_reminder(
            title="Quarterly report review",
            due_datetime="2025-12-10 15:00:00",
            description="Review Q4 quarterly report and prepare executive summary",
        )

        self.other_reminder_id_2 = self.reminder.add_reminder(
            title="Team building event planning",
            due_datetime="2025-12-15 11:00:00",
            description="Finalize venue and activities for December team building event",
        )

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.reminder, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - email triggers agent to propose deleting related reminders."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # ENV Event: Sarah sends project cancellation email
            cancellation_email = email_app.send_email_to_user_only(
                sender="sarah.martinez@company.com",
                subject="Aurora Marketing Campaign - Project Canceled",
                content=(
                    "Hi,\n\n"
                    "I wanted to let you know that the Aurora Marketing Campaign has been canceled "
                    "due to budget reallocation. All related tasks and deadlines are no longer applicable. "
                    "Please disregard any reminders or action items associated with this project.\n\n"
                    "Thanks,\n"
                    "Sarah Martinez\n"
                    "Marketing Director"
                ),
            ).delayed(5)

            # Oracle: Agent retrieves all reminders to search for Aurora-related ones
            get_reminders = reminder_app.get_all_reminders().oracle().depends_on(cancellation_email, delay_seconds=2)

            # Oracle: Agent proposes deletion of Aurora reminders to the user
            proposal = (
                aui.send_message_to_user(
                    content=(
                        "I saw the email from Sarah Martinez about the Aurora Marketing Campaign cancellation. "
                        "You have three reminders related to this project: 'Review Aurora campaign draft' (Dec 1st), "
                        "'Submit Aurora budget proposal' (Dec 3rd), and 'Aurora campaign kickoff meeting prep' (Dec 5th). "
                        "Would you like me to delete these reminders since the project is canceled?"
                    )
                )
                .oracle()
                .depends_on(get_reminders, delay_seconds=2)
            )

            # Oracle: User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please delete all Aurora reminders.")
                .oracle()
                .depends_on(proposal, delay_seconds=2)
            )

            # Oracle: Agent deletes the three Aurora reminders
            delete_reminder1 = (
                reminder_app.delete_reminder(reminder_id=self.reminder_id_1)
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

            delete_reminder2 = (
                reminder_app.delete_reminder(reminder_id=self.reminder_id_2)
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

            delete_reminder3 = (
                reminder_app.delete_reminder(reminder_id=self.reminder_id_3)
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

        self.events = [
            cancellation_email,
            get_reminders,
            proposal,
            acceptance,
            delete_reminder1,
            delete_reminder2,
            delete_reminder3,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent proposed and deleted Aurora reminders.

        Essential outcomes checked:
        1. Agent sent proposal to user about deleting reminders
        2. Agent deleted all three Aurora reminders
        """
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal to user
            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent deleted all three Aurora reminders
            deleted_reminder_ids = set()
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.class_name == "StatefulReminderApp"
                    and e.action.function_name == "delete_reminder"
                ):
                    reminder_id = e.action.args.get("reminder_id")
                    if reminder_id in [self.reminder_id_1, self.reminder_id_2, self.reminder_id_3]:
                        deleted_reminder_ids.add(reminder_id)

            all_reminders_deleted = len(deleted_reminder_ids) == 3

            success = proposal_sent and all_reminders_deleted

            if not success:
                missing = []
                if not proposal_sent:
                    missing.append("proposal to user about deleting Aurora reminders")
                if not all_reminders_deleted:
                    missing.append(f"deleted {len(deleted_reminder_ids)}/3 Aurora reminders")
                return ScenarioValidationResult(
                    success=False,
                    rationale=f"Missing required actions: {', '.join(missing)}",
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
