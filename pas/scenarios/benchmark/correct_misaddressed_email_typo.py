from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("correct_misaddressed_email_typo")
class CorrectMisaddressedEmailTypo(PASScenario):
    """Agent detects and corrects an email addressing error by cross-referencing the contacts app. The user receives an urgent email reply from a colleague saying "I think you meant to send this to Jennifer Thompson, not Jennifer Thomson - I don't recognize this project." The original email in the thread shows the user sent a project-sensitive document to jennifer.thomson@company.com (typo). The agent must: 1. Parse the reply to identify the addressing error and intended recipient name. 2. Search contacts for "Jennifer Thompson" to retrieve the correct email address. 3. Verify that jennifer.thomson@company.com is not in contacts (confirming it's likely a typo). 4. Compose a new email to the correct Jennifer Thompson with the original message. 5. Reply to the colleague confirming the correction was made.

    This scenario exercises error detection from natural language feedback, contacts as a validation and lookup tool rather than a modification target, cross-app reasoning where email problems are solved using contact data, typo/similarity matching to distinguish intended vs misaddressed recipients, and corrective email composition that preserves original content.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize contacts app
        self.contacts = StatefulContactsApp(name="Contacts")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Populate contacts with baseline data
        # Current user
        user_contact = Contact(
            first_name="Alex",
            last_name="Chen",
            email="alex.chen@company.com",
            is_user=True,
        )
        self.contacts.add_contact(user_contact)

        # Jennifer Thompson - the correct intended recipient
        jennifer_thompson = Contact(
            first_name="Jennifer",
            last_name="Thompson",
            email="jennifer.thompson@company.com",
            job="Project Manager",
        )
        self.contacts.add_contact(jennifer_thompson)

        # Mark Davis - the colleague who will notice the mistake
        mark_davis = Contact(
            first_name="Mark",
            last_name="Davis",
            email="mark.davis@company.com",
            job="Team Lead",
        )
        self.contacts.add_contact(mark_davis)

        # Populate email app with baseline data
        # The original email sent by the user (with the typo) - exists in SENT folder
        original_email = Email(
            email_id="original_email_001",
            sender="alex.chen@company.com",
            recipients=["jennifer.thomson@company.com"],  # Typo: thomson instead of thompson
            cc=["mark.davis@company.com"],
            subject="Q4 Budget Proposal - Review Needed",
            content="Hi Jennifer,\n\nPlease review the attached Q4 budget proposal for the marketing campaign. I need your approval by end of week.\n\nBest regards,\nAlex",
            timestamp=self.start_time - 3600,  # Sent 1 hour before scenario start
            is_read=True,
        )
        self.email.add_email(original_email, EmailFolderName.SENT)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Mark Davis (colleague) replies to the original email pointing out the addressing error
            MARK_REPLY_ID = "mark_reply_001"
            reply_email_event = email_app.send_email_to_user_with_id(
                email_id=MARK_REPLY_ID,
                sender="mark.davis@company.com",
                subject="Re: Q4 Budget Proposal - Review Needed",
                content="Hi Alex,\n\nI think you meant to send this to Jennifer Thompson, not Jennifer Thomson - I don't recognize this project. You might want to double-check the email address.\n\nBest,\nMark",
            ).delayed(30)

            # Oracle Event 1: Agent reads the reply email to understand the error
            read_reply_event = (
                email_app.list_emails(folder_name="INBOX", offset=0, limit=5)
                .oracle()
                .depends_on(reply_email_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent reads the sent email to find the original message with typo
            read_sent_event = (
                email_app.list_emails(folder_name="SENT", offset=0, limit=5)
                .oracle()
                .depends_on(read_reply_event, delay_seconds=3)
            )

            # Oracle Event 3: Agent searches contacts to find correct Jennifer Thompson
            search_jennifer_event = (
                contacts_app.search_contacts(query="Jennifer Thompson")
                .oracle()
                .depends_on(read_sent_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent proposes to correct the addressing error
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Mark Davis pointed out an email addressing error. You sent the Q4 Budget Proposal to 'jennifer.thomson@company.com' (typo), but Jennifer Thompson's correct email is 'jennifer.thompson@company.com'. Would you like me to forward the email to the correct address and notify Mark?"
                )
                .oracle()
                .depends_on(search_jennifer_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please correct the mistake and send it to the right person.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent retrieves the original email from SENT folder to forward it
            get_original_event = (
                email_app.get_email_by_id(email_id="original_email_001", folder_name="SENT")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent sends corrected email to Jennifer Thompson with original content
            send_corrected_event = (
                email_app.send_email(
                    recipients=["jennifer.thompson@company.com"],
                    subject="Q4 Budget Proposal - Review Needed",
                    content="Hi Jennifer,\n\nPlease review the attached Q4 budget proposal for the marketing campaign. I need your approval by end of week.\n\n(Resending to correct email address - apologies for any confusion)\n\nBest regards,\nAlex",
                    cc=["mark.davis@company.com"],
                )
                .oracle()
                .depends_on(get_original_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent replies to Mark confirming the correction
            reply_to_mark_event = (
                email_app.reply_to_email(
                    email_id=MARK_REPLY_ID,
                    folder_name="INBOX",
                    content="Thanks for catching that, Mark! I've corrected the email and sent it to Jennifer Thompson at the right address.",
                )
                .oracle()
                .depends_on(send_corrected_event, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            reply_email_event,
            read_reply_event,
            read_sent_event,
            search_jennifer_event,
            proposal_event,
            acceptance_event,
            get_original_event,
            send_corrected_event,
            reply_to_mark_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check: Agent sent corrected email to Jennifer Thompson
            send_corrected_email_found = any(
                e.event_type in (EventType.AGENT, EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "jennifer.thompson@company.com" in str(e.action.args.get("recipients", []))
                for e in log_entries
            )

            # Check: Agent replied to Mark Davis
            reply_to_mark_found = any(
                e.event_type in (EventType.AGENT, EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "mark_reply_001"
                for e in log_entries
            )

            success = send_corrected_email_found and reply_to_mark_found

            if not success:
                missing_checks = []
                if not send_corrected_email_found:
                    missing_checks.append("corrected email to jennifer.thompson@company.com")
                if not reply_to_mark_found:
                    missing_checks.append("reply to Mark Davis (email_id=mark_reply_001)")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
