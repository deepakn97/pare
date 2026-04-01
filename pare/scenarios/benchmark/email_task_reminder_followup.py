"""Scenario for creating reminders from email task list."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
)
from pare.apps.email import StatefulEmailApp
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("email_task_reminder_followup")
class EmailTaskReminderFollowup(PAREScenario):
    """Agent proposes creating reminders from emails with tasks from different colleagues.

    Story:
    1. User receives three emails from different colleagues with tasks:
       - Sarah Chen (Finance): Submit expense report by Friday (Nov 22)
       - Mike Johnson (Design): Review design mockups by next Tuesday (Nov 26)
       - Lisa Park (HR): Prepare team workshop proposal by end of this week (Nov 22)
    2. Agent reads the incoming emails, extracts the tasks and deadlines
    3. Agent proposes creating three reminders for these tasks
    4. User accepts the proposal
    5. Agent creates the three reminders with appropriate due datetimes

    This scenario exercises information extraction from multiple emails and user-gated
    reminder creation (email -> reminders).
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize reminder app
        self.reminder = StatefulReminderApp(name="Reminders")

        # Populate baseline data: existing older emails in INBOX (history context)
        self.email.create_and_add_email_with_time(
            sender="sarah.chen@company.com",
            subject="Welcome to the team!",
            content="Hi! Welcome aboard. Looking forward to working with you on upcoming projects.",
            email_time="2025-11-10 14:00:00",
            folder_name="INBOX",
        )

        # Populate baseline data: previous sent email showing the user has worked with manager before
        self.email.create_and_add_email_with_time(
            sender=self.email.user_email,
            recipients=["sarah.chen@company.com"],
            subject="Re: Welcome to the team!",
            content="Thanks Sarah! Excited to be here and contribute to the team.",
            email_time="2025-11-11 10:30:00",
            folder_name="SENT",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # ENV: Email from Sarah Chen (Finance) about expense report
            email_sarah = email_app.send_email_to_user_with_id(
                email_id="task_email_001",
                sender="sarah.chen@company.com",
                subject="Expense Report Reminder",
                content=(
                    "Hi,\n\n"
                    "Just a reminder that your expense report is due by Friday (Nov 22). "
                    "Please make sure to submit it before the deadline.\n\n"
                    "Thanks,\nSarah Chen\nFinance Department"
                ),
            ).delayed(5)

            # ENV: Email from Mike Johnson (Design) about design mockups
            email_mike = email_app.send_email_to_user_with_id(
                email_id="task_email_002",
                sender="mike.johnson@company.com",
                subject="Design Mockups Review Needed",
                content=(
                    "Hey,\n\n"
                    "I've finished the design mockups for the new feature. "
                    "Could you review them by next Tuesday (Nov 26)? "
                    "Let me know if you have any feedback.\n\n"
                    "Cheers,\nMike Johnson\nDesign Team"
                ),
            ).delayed(10)

            # ENV: Email from Lisa Park (HR) about workshop proposal
            email_lisa = email_app.send_email_to_user_with_id(
                email_id="task_email_003",
                sender="lisa.park@company.com",
                subject="Team Workshop Proposal",
                content=(
                    "Hi,\n\n"
                    "We're planning a team workshop for next month and need your input. "
                    "Could you prepare a workshop proposal by the end of this week (Nov 22)? "
                    "We need to finalize the agenda soon.\n\n"
                    "Best,\nLisa Park\nHR Department"
                ),
            ).delayed(15)

            # Oracle: Agent reads emails to extract action items
            read_emails_event = (
                email_app.list_emails(folder_name="INBOX").oracle().depends_on(email_lisa, delay_seconds=2)
            )

            # Oracle: Agent proposes creating reminders
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I noticed you have three tasks from colleagues with upcoming deadlines:\n"
                        "1. Submit expense report - Sarah Chen (due Nov 22)\n"
                        "2. Review design mockups - Mike Johnson (due Nov 26)\n"
                        "3. Prepare workshop proposal - Lisa Park (due Nov 22)\n\n"
                        "Would you like me to create reminders for these tasks?"
                    )
                )
                .oracle()
                .depends_on(read_emails_event, delay_seconds=2)
            )

            # User accepts the proposal (enables write actions like add_reminder)
            accept_event = (
                aui.accept_proposal(content="Yes, please add those three reminders.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle: Agent creates first reminder for expense report
            reminder_1_event = (
                reminder_app.add_reminder(
                    title="Submit expense report",
                    due_datetime="2025-11-22 17:00:00",
                    description="From Sarah Chen (Finance): submit expense report by Friday (Nov 22).",
                )
                .oracle()
                .depends_on(accept_event, delay_seconds=2)
            )

            # Oracle: Agent creates second reminder for design mockups review
            reminder_2_event = (
                reminder_app.add_reminder(
                    title="Review design mockups",
                    due_datetime="2025-11-26 17:00:00",
                    description="From Mike Johnson (Design): review design mockups by Tuesday (Nov 26).",
                )
                .oracle()
                .depends_on(reminder_1_event, delay_seconds=1)
            )

            # Oracle: Agent creates third reminder for workshop proposal
            reminder_3_event = (
                reminder_app.add_reminder(
                    title="Prepare workshop proposal",
                    due_datetime="2025-11-22 17:00:00",
                    description="From Lisa Park (HR): prepare team workshop proposal by end of this week.",
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

        self.events = [
            email_sarah,
            email_mike,
            email_lisa,
            read_emails_event,
            proposal_event,
            accept_event,
            reminder_1_event,
            reminder_2_event,
            reminder_3_event,
            completion_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent created reminders from email task list."""
        try:
            log_entries = env.event_log.list_view()
            agent_entries = [e for e in log_entries if e.event_type == EventType.AGENT]

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
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_entries
            )

            # Combine all checks
            all_checks_passed = reminders_created and initial_proposal_found

            if not all_checks_passed:
                # Build rationale for failure
                missing_checks = []
                if not reminders_created:
                    missing_checks.append(f"agent created {reminder_create_count} reminders instead of 3")
                if not initial_proposal_found:
                    missing_checks.append("agent did not send initial proposal about task tracking")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
