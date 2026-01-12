"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.reminder import Reminder
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("email_reminder_batch_cancellation")
class EmailReminderBatchCancellation(PASScenario):
    """Agent cancels multiple reminders based on project cancellation notification received via email.

    The user has three active reminders related to the "Aurora Marketing Campaign" project: "Review Aurora campaign draft" (due Dec 1st), "Submit Aurora budget proposal" (due Dec 3rd), and "Aurora campaign kickoff meeting prep" (due Dec 5th). The user receives an email from their project lead, Sarah Martinez, informing them that the Aurora Marketing Campaign has been canceled due to budget reallocation, and all related tasks and deadlines are no longer applicable. The agent must:
    1. Parse the email notification and identify the project name ("Aurora Marketing Campaign")
    2. Search all reminders to find those related to the canceled project
    3. Propose deleting the three Aurora-related reminders to clean up the user's task list
    4. After user acceptance, delete each of the three matching reminders using their reminder IDs
    5. Reply to Sarah's email confirming that all Aurora campaign reminders have been removed

    This scenario exercises email-triggered reminder cleanup, cross-app information matching (email content → reminder search), batch reminder deletion operations, and confirmation communication back to the email sender..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize reminder app
        self.reminder = StatefulReminderApp(name="Reminders")

        # Seed three Aurora-related reminders
        # Reminder 1: Review Aurora campaign draft (due Dec 1st, 2025)
        reminder1 = Reminder(
            reminder_id="aurora_reminder_1",
            title="Review Aurora campaign draft",
            description="Review the marketing draft for Aurora Marketing Campaign before team review",
            due_datetime=datetime(2025, 12, 1, 14, 0, 0, tzinfo=UTC),
        )
        self.reminder.reminders["aurora_reminder_1"] = reminder1

        # Reminder 2: Submit Aurora budget proposal (due Dec 3rd, 2025)
        reminder2 = Reminder(
            reminder_id="aurora_reminder_2",
            title="Submit Aurora budget proposal",
            description="Submit budget proposal for Aurora Marketing Campaign to finance team",
            due_datetime=datetime(2025, 12, 3, 16, 0, 0, tzinfo=UTC),
        )
        self.reminder.reminders["aurora_reminder_2"] = reminder2

        # Reminder 3: Aurora campaign kickoff meeting prep (due Dec 5th, 2025)
        reminder3 = Reminder(
            reminder_id="aurora_reminder_3",
            title="Aurora campaign kickoff meeting prep",
            description="Prepare presentation slides and materials for Aurora Marketing Campaign kickoff meeting",
            due_datetime=datetime(2025, 12, 5, 10, 0, 0, tzinfo=UTC),
        )
        self.reminder.reminders["aurora_reminder_3"] = reminder3

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Seed contact for Sarah Martinez (project lead)
        sarah_contact = Contact(
            first_name="Sarah",
            last_name="Martinez",
            email="sarah.martinez@company.com",
            job="Marketing Director",
        )

        # Note: The cancellation email will be delivered as an environment event in Step 3
        # (not seeded here) so the agent can observe its arrival as a trigger

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.reminder, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment event: Sarah sends project cancellation email
            cancellation_email = email_app.send_email_to_user_with_id(
                email_id="aurora_cancellation_email",
                sender="sarah.martinez@company.com",
                subject="Aurora Marketing Campaign - Project Canceled",
                content="Hi,\n\nI wanted to let you know that the Aurora Marketing Campaign has been canceled due to budget reallocation. All related tasks and deadlines are no longer applicable. Please disregard any reminders or action items associated with this project.\n\nThanks,\nSarah Martinez\nMarketing Director",
            ).delayed(5)

            # Agent reads the cancellation email to understand the trigger
            read_email = (
                email_app.get_email_by_id(email_id="aurora_cancellation_email", folder_name="INBOX")
                .oracle()
                .depends_on(cancellation_email, delay_seconds=2)
            )

            # Agent retrieves all reminders to search for Aurora-related ones
            get_reminders = reminder_app.get_all_reminders().oracle().depends_on(read_email, delay_seconds=1)

            # Agent proposes deletion of Aurora reminders to the user
            proposal = (
                aui.send_message_to_user(
                    content="I saw the email from Sarah Martinez about the Aurora Marketing Campaign cancellation. You have three reminders related to this project: 'Review Aurora campaign draft' (Dec 1st), 'Submit Aurora budget proposal' (Dec 3rd), and 'Aurora campaign kickoff meeting prep' (Dec 5th). Would you like me to delete these reminders since the project is canceled?"
                )
                .oracle()
                .depends_on([cancellation_email, get_reminders], delay_seconds=2)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please delete all Aurora reminders.")
                .oracle()
                .depends_on(proposal, delay_seconds=3)
            )

            # Agent deletes the three Aurora reminders (after user acceptance)
            delete_reminder1 = (
                reminder_app.delete_reminder(reminder_id="aurora_reminder_1")
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

            delete_reminder2 = (
                reminder_app.delete_reminder(reminder_id="aurora_reminder_2")
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

            delete_reminder3 = (
                reminder_app.delete_reminder(reminder_id="aurora_reminder_3")
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            cancellation_email,
            read_email,
            get_reminders,
            proposal,
            acceptance,
            delete_reminder1,
            delete_reminder2,
            delete_reminder3,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to AGENT events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT: Check Step 1 - Agent read the cancellation email
            read_email_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                and e.action.args.get("email_id") == "aurora_cancellation_email"
                for e in agent_events
            )

            # STRICT: Check Step 2 - Agent retrieved all reminders to identify Aurora-related ones
            get_reminders_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "get_all_reminders"
                for e in agent_events
            )

            # FLEXIBLE: Check Step 3 - Agent proposed to delete Aurora reminders (flexible on exact wording)
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT: Check Step 4 - Agent deleted all three Aurora reminders (after acceptance)
            # Count deletion calls for the three specific reminder IDs
            deleted_reminder_ids = set()
            for e in agent_events:
                if (
                    isinstance(e.action, Action)
                    and e.action.class_name == "StatefulReminderApp"
                    and e.action.function_name == "delete_reminder"
                ):
                    reminder_id = e.action.args.get("reminder_id")
                    if reminder_id in ["aurora_reminder_1", "aurora_reminder_2", "aurora_reminder_3"]:
                        deleted_reminder_ids.add(reminder_id)

            all_reminders_deleted = len(deleted_reminder_ids) == 3

            # All strict checks must pass
            success = read_email_found and get_reminders_found and proposal_found and all_reminders_deleted

            if not success:
                # Build rationale for failure
                missing = []
                if not read_email_found:
                    missing.append("agent did not read cancellation email")
                if not get_reminders_found:
                    missing.append("agent did not retrieve all reminders")
                if not proposal_found:
                    missing.append("agent did not send proposal to user")
                if not all_reminders_deleted:
                    missing.append(f"agent deleted {len(deleted_reminder_ids)}/3 Aurora reminders")

                rationale = "; ".join(missing)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
