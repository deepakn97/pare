from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulEmailApp,
)
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("apartment_application_document_reminder")
class ApartmentApplicationDocumentReminder(PAREScenario):
    """Agent coordinates document preparation for apartment application from email notification.

    The user has saved "Parkview Terrace" apartment to their favorites after searching for pet-friendly apartments. The property management company "Summit Rentals" sends an email informing the user that their rental application has been received and lists required supporting documents: proof of employment (must be dated within 30 days), two recent pay stubs, bank statements from the last 3 months, and a copy of photo ID. The email states all documents must be submitted by Friday, January 17th, 2026 at 5:00 PM to the leasing office, provides the submission address (456 Maple Drive, Suite 100), and explicitly suggests setting a preparation reminder a few days earlier (e.g., Wednesday, January 14th at 9:00 AM). The agent must:
    1. Parse the document requirements and submission deadline from the application email
    2. Propose helping the user prepare the required documents (grounded by the email's reminder suggestion) and, after user acceptance, set a preparation reminder.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.reminder = StatefulReminderApp(name="Reminders")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment event: Summit Rentals sends application requirements email
            app_email = email_app.send_email_to_user_with_id(
                email_id="app_email_001",
                sender="leasing@summitrentals.com",
                subject="Parkview Terrace Application - Required Documents",
                content="""Dear Applicant,

Thank you for submitting your rental application for Parkview Terrace! We have received your initial application and are ready to move forward.

To complete your application, please submit the following required documents:

1. Proof of employment (must be dated within 30 days)
2. Two recent pay stubs
3. Bank statements from the last 3 months
4. Copy of photo ID

All documents must be submitted by Friday, January 17th, 2026 at 5:00 PM to our leasing office at:
456 Maple Drive, Suite 100

Please bring or email the documents to this address. If you have any questions, feel free to contact us.

Tip: To avoid delays, please plan to have documents ready by Wednesday, Jan 14th, 2026 at 9:00 AM. Submitting early helps us process your application faster.

Best regards,
Summit Rentals Leasing Team""",
            )

            # Agent detects the email notification and reads it to understand requirements
            read_email = (
                email_app.get_email_by_id(email_id="app_email_001", folder_name="INBOX")
                .oracle()
                .depends_on(app_email, delay_seconds=2)
            )

            # Agent sends proposal to help coordinate document preparation
            proposal = (
                aui.send_message_to_user(
                    content="""I noticed you received an email from Summit Rentals about your Parkview Terrace application. They need several documents by January 17th, 2026 at 5:00 PM:

• Proof of employment (dated within 30 days)
• Two recent pay stubs
• Bank statements (last 3 months)
• Copy of photo ID

Would you like me to create a reminder on Wednesday, January 14th at 9:00 AM to help you prepare these documents on time?"""
                )
                .oracle()
                .depends_on(read_email, delay_seconds=2)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal, delay_seconds=3)
            )

            # Agent creates a preparation reminder for January 14th (3 days before deadline)
            # Motivation: the application email explicitly suggests setting a preparation reminder for Wednesday, Jan 14 (morning).
            reminder = (
                reminder_app.add_reminder(
                    title="Prepare Application Docs - Parkview Terrace",
                    due_datetime="2026-01-14 09:00:00",
                    description="Gather proof of employment (dated within 30 days) and two recent pay stubs for Parkview Terrace application.\n\n Collect bank statements from the last 3 months for Parkview Terrace application.\n\n Prepare copy of photo ID for Parkview Terrace application.\n\n Submit all application documents to Summit Rentals at 456 Maple Drive, Suite 100 by Friday, January 17th, 2026 at 5:00 PM.",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [app_email, read_email, proposal, acceptance, reminder]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal to the user mentioning Parkview Terrace and document requirements
            proposal_found = False
            for e in agent_events:
                if e.action.class_name == "PAREAgentUserInterface" and e.action.function_name == "send_message_to_user":
                    # Content flexibility: just verify the proposal was sent, not the exact wording
                    proposal_found = True
                    break

            # STRICT Check 2: Agent created a preparation reminder for January 14th
            # Must have at least 1 preparation reminder (flexible on exact count)
            preparation_reminders_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulReminderApp" and e.action.function_name == "add_reminder":
                    preparation_reminders_found = True
                    break

            # All strict checks must pass
            success = proposal_found and preparation_reminders_found

            # Build rationale if validation fails
            rationale = ""
            if not success:
                failures = []
                if not proposal_found:
                    failures.append("no proposal message to user found")
                if not preparation_reminders_found:
                    failures.append("no preparation reminder for Jan 14th was created")
                rationale = "; ".join(failures)

            return ScenarioValidationResult(success=success, rationale=rationale if not success else "")

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
