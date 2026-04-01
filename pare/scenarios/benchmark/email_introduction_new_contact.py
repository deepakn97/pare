"""Agent creates new contact from professional email introduction thread.

The user receives a professional introduction email from their colleague Sarah Kim
connecting them with a new partner, Robert Chen, who works at a client company.
Sarah CCs Robert on the introduction email. The user replies to acknowledge the
introduction, and then Robert replies to the thread with his contact details in
his email signature.

The agent must:
1. Detect Robert's reply in the email thread
2. Parse the email to identify Robert Chen and extract his contact information
3. Verify Robert is not already in the user's contacts
4. Propose creating a new contact record for Robert Chen
5. After user approval, create the contact

This scenario exercises email thread monitoring, contact extraction from email
signatures, duplicate detection before contact creation, and proactive contact
management from professional introductions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulContactsApp,
    StatefulEmailApp,
)
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("email_introduction_new_contact")
class EmailIntroductionNewContact(PAREScenario):
    """Agent creates new contact from professional email introduction thread."""

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    # Store email IDs for use in build_events_flow
    sarah_intro_email_id = "sarah-intro-email"
    user_reply_email_id = "user-reply-email"

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts app
        self.contacts = StatefulContactsApp(name="Contacts")

        # Populate contacts with existing contacts (no Robert Chen yet)
        sarah_kim = Contact(
            first_name="Sarah",
            last_name="Kim",
            email="sarah.kim@usercompany.com",
            phone="+1-555-0123",
            job="Senior Product Manager",
        )

        alice_johnson = Contact(
            first_name="Alice",
            last_name="Johnson",
            email="alice.johnson@usercompany.com",
            phone="+1-555-0124",
            job="Engineering Lead",
        )

        self.contacts.add_contact(sarah_kim)
        self.contacts.add_contact(alice_johnson)

        # Initialize Email app
        self.email = StatefulEmailApp(name="Emails")

        # 1. Sarah's introduction email (INBOX), CC'ing Robert
        intro_email = Email(
            email_id=self.sarah_intro_email_id,
            sender="sarah.kim@usercompany.com",
            recipients=[self.email.user_email],
            cc=["robert.chen@acmecorp.com"],
            subject="Introduction: Meet Robert Chen from Acme Corp",
            content="""Hi there,

I'd like to introduce you to Robert Chen from Acme Corp. Robert is the Product Manager leading their Q1 collaboration initiatives. I think you two should connect about our partnership project.

Robert, meet our Design Lead who's been driving the user experience strategy for our platform. You both should chat about aligning on the Q1 roadmap.

Best,
Sarah""",
            timestamp=self.start_time - 600,  # 10 min before
            is_read=True,
        )
        self.email.add_email(intro_email, folder_name=EmailFolderName.INBOX)

        # 2. User's reply to Sarah (SENT folder, with Robert as recipient for threading)
        user_reply = Email(
            email_id=self.user_reply_email_id,
            sender=self.email.user_email,
            recipients=["sarah.kim@usercompany.com", "robert.chen@acmecorp.com"],
            subject="Re: Introduction: Meet Robert Chen from Acme Corp",
            content="Thanks for the introduction Sarah! Robert, looking forward to connecting.",
            timestamp=self.start_time - 300,  # 5 min before
            parent_id=self.sarah_intro_email_id,
        )
        self.email.add_email(user_reply, folder_name=EmailFolderName.SENT)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Robert replies to the thread with his contact details
            robert_reply_event = email_app.reply_to_email_from_user(
                sender="robert.chen@acmecorp.com",
                email_id=self.user_reply_email_id,
                content="""Thanks Sarah for connecting us!

Great to meet you! I'm excited about the Q1 collaboration project. Let's definitely schedule time to discuss aligning our roadmaps.

Best,
Robert Chen
Product Manager | Acme Corp
+1-555-0199
San Francisco, CA""",
            )

            # Oracle Event 2: Agent searches contacts to verify Robert is not already present
            search_event = (
                contacts_app.search_contacts(query="Robert Chen")
                .oracle()
                .depends_on(robert_reply_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent reads Robert's email to extract contact details
            list_emails_event = (
                email_app.list_emails(folder_name="INBOX").oracle().depends_on(search_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent proposes creating new contact
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Robert Chen replied to the introduction thread from Sarah. Robert isn't in your contacts yet. Would you like me to add him (with his email robert.chen@acmecorp.com and phone +1-555-0199) and send a reply acknowledging the connection?"
                )
                .oracle()
                .depends_on(list_emails_event, delay_seconds=2)
            )

            # Environment Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please add Robert and reply.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent creates new contact for Robert Chen
            create_contact_event = (
                contacts_app.add_new_contact(
                    first_name="Robert",
                    last_name="Chen",
                    email="robert.chen@acmecorp.com",
                    phone="+1-555-0199",
                    job="Product Manager",
                    city_living="San Francisco",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent confirms completion to user
            confirmation_event = (
                aui.send_message_to_user(content="I've added Robert Chen to your contacts.")
                .oracle()
                .depends_on(create_contact_event, delay_seconds=1)
            )

        self.events = [
            robert_reply_event,
            search_event,
            list_emails_event,
            proposal_event,
            acceptance_event,
            create_contact_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent proposed adding Robert Chen
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent searched contacts to verify Robert doesn't exist
            search_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                for e in log_entries
            )

            # Check 3: Agent created new contact for Robert Chen
            create_contact_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "add_new_contact"
                and e.action.args.get("first_name") == "Robert"
                and e.action.args.get("last_name") == "Chen"
                and e.action.args.get("email") == "robert.chen@acmecorp.com"
                and e.action.args.get("phone") == "+1-555-0199"
                for e in log_entries
            )

            success = proposal_found and search_found and create_contact_found

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("agent proposal")
                if not search_found:
                    missing.append("contact search")
                if not create_contact_found:
                    missing.append("contact creation")
                rationale = f"Missing critical checks: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
