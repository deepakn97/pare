"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.email import StatefulEmailApp
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("email_task_reminder_followup")
class EmailTaskReminderFollowup(PASScenario):
    """Agent proposes creating reminders from an email task list, and creates them after user approval.

    The user receives an email from their project manager listing three tasks with deadlines: submit an expense report
    by Friday (Nov 22), review design mockups by next Tuesday (Nov 26), and schedule a team workshop next month. The
    agent must:
    1. Read the incoming email and extract the three tasks and deadlines
    2. Propose creating three reminders for these tasks
    3. After user acceptance, create the three reminders with appropriate due datetimes
    4. Confirm to the user that the reminders were created

    This scenario exercises information extraction from email and user-gated reminder creation (email -> reminders).
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app with user email
        self.email = StatefulEmailApp(name="Emails", user_email="user@company.com")

        # Initialize reminder app
        self.reminder = StatefulReminderApp(name="Reminders")

        # Populate baseline data: existing older emails in INBOX (history context)
        older_email_1 = Email(
            email_id="older_email_001",
            sender="sarah.chen@company.com",
            recipients=["user@company.com"],
            subject="Welcome to the team!",
            content="Hi! Welcome aboard. Looking forward to working with you on upcoming projects.",
            timestamp=datetime(2025, 11, 10, 14, 0, 0, tzinfo=UTC).timestamp(),
            is_read=True,
        )
        self.email.add_email(older_email_1, EmailFolderName.INBOX)

        # Populate baseline data: previous sent email showing the user has worked with manager before
        sent_email = Email(
            email_id="sent_email_001",
            sender="user@company.com",
            recipients=["sarah.chen@company.com"],
            subject="Re: Welcome to the team!",
            content="Thanks Sarah! Excited to be here and contribute to the team.",
            timestamp=datetime(2025, 11, 11, 10, 30, 0, tzinfo=UTC).timestamp(),
            is_read=True,
            parent_id="older_email_001",
        )
        self.email.add_email(sent_email, EmailFolderName.SENT)

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.reminder]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment event: Incoming email from project manager with task list
            task_email_event = email_app.send_email_to_user_with_id(
                email_id="task_email_001",
                sender="sarah.chen@company.com",
                subject="Action Items for This Week",
                content="Hi! Here are three tasks that need your attention:\n\n1. Submit your expense report by Friday (Nov 22)\n2. Review the design mockups by next Tuesday (Nov 26)\n3. Schedule the team workshop for sometime next month\n\nLet me know if you have any questions!\n\nBest,\nSarah",
            ).delayed(5)

            # Agent reads the incoming email to extract action items (motivated by the new email notification)
            read_email_event = (
                email_app.get_email_by_id(email_id="task_email_001", folder_name="INBOX")
                .oracle()
                .depends_on(task_email_event, delay_seconds=2)
            )

            # Agent proposes creating reminders (read-only before user acceptance)
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw Sarah's email with three action items and deadlines. Would you like me to create three reminders for:\n1. Submit expense report (due Nov 22)\n2. Review design mockups (due Nov 26)\n3. Schedule team workshop (due Nov 30)?"
                )
                .oracle()
                .depends_on([task_email_event, read_email_event], delay_seconds=2)
            )

            # User accepts the proposal (enables write actions like add_reminder)
            accept_event = (
                aui.accept_proposal(content="Yes, please add those three reminders.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Agent creates first reminder for expense report (write action gated by user acceptance)
            reminder_1_event = (
                reminder_app.add_reminder(
                    title="Submit expense report",
                    due_datetime="2025-11-22 17:00:00",
                    description="From Sarah's email: submit expense report by Friday (Nov 22).",
                )
                .oracle()
                .depends_on(accept_event, delay_seconds=2)
            )

            # Agent creates second reminder for design mockups review (write action gated by user acceptance)
            reminder_2_event = (
                reminder_app.add_reminder(
                    title="Review design mockups",
                    due_datetime="2025-11-26 17:00:00",
                    description="From Sarah's email: review design mockups by Tuesday (Nov 26).",
                )
                .oracle()
                .depends_on(reminder_1_event, delay_seconds=1)
            )

            # Agent creates third reminder for workshop scheduling (write action gated by user acceptance)
            reminder_3_event = (
                reminder_app.add_reminder(
                    title="Schedule team workshop",
                    due_datetime="2025-11-30 17:00:00",
                    description="From Sarah's email: schedule the team workshop next month.",
                )
                .oracle()
                .depends_on(reminder_2_event, delay_seconds=1)
            )

            # Agent confirms completion to the user
            completion_event = (
                aui.send_message_to_user(content="Done — I added the three reminders for Sarah's action items.")
                .oracle()
                .depends_on(reminder_3_event, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            task_email_event,
            read_email_event,
            proposal_event,
            accept_event,
            reminder_1_event,
            reminder_2_event,
            reminder_3_event,
            completion_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_entries = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT: Check that agent read the incoming email from Sarah
            read_email_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["get_email_by_id", "list_emails"]
                for e in agent_entries
            )

            # STRICT: Check that agent created reminders for the tasks
            # Count how many reminders were created (expect 3 reminders)
            reminder_create_count = sum(
                1
                for e in agent_entries
                if isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "add_reminder"
            )
            reminders_created = reminder_create_count == 3

            # STRICT: Check that agent sent an initial proposal to the user about task tracking
            initial_proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_entries
            )

            # Combine all checks
            all_checks_passed = read_email_found and reminders_created and initial_proposal_found

            if not all_checks_passed:
                # Build rationale for failure
                missing_checks = []
                if not read_email_found:
                    missing_checks.append("agent did not read the incoming task email")
                if not reminders_created:
                    missing_checks.append(f"agent created {reminder_create_count} reminders instead of 3")
                if not initial_proposal_found:
                    missing_checks.append("agent did not send initial proposal about task tracking")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
