"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.email_client import Email
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


@register_scenario("email_introduction_new_contact")
class EmailIntroductionNewContact(PASScenario):
    """Agent creates new contact from professional email introduction.

    The user receives a professional introduction email from their colleague Sarah Kim connecting them with a new partner, Robert Chen, who works at a client company. The email follows the classic introduction format: "Hi [User], I'd like to introduce you to Robert Chen from Acme Corp. Robert, meet [User] who leads our design team. You two should connect about the Q1 collaboration project." Robert's email signature includes his full contact details: phone number, job title (Product Manager), and company email. The agent must: 1. Parse the introduction email to identify the new contact being introduced (Robert Chen). 2. Extract structured contact information from Robert's email signature and the introduction text. 3. Verify Robert is not already in the user's contacts. 4. Create a new contact record for Robert Chen with extracted details. 5. Reply-all to acknowledge the introduction and facilitate the connection.

    This scenario exercises email introduction pattern recognition, new contact creation from unstructured text and signature data, duplicate detection before contact creation, multi-party email thread etiquette (reply-all), and social connection facilitation through proactive contact management..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
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

        # Add contacts to the app
        self.contacts.add_contact(sarah_kim)
        self.contacts.add_contact(alice_johnson)

        # Initialize Email app
        self.email = StatefulEmailApp(name="Emails")

        # Populate email app with prior correspondence from Sarah
        prior_email = Email(
            sender="sarah.kim@usercompany.com",
            recipients=[self.email.user_email],
            subject="Quick sync on Q1 partnerships",
            content="Hey, wanted to touch base about our Q1 partnership plans. I think I found a great contact at Acme Corp who could help with our collaboration project. Will introduce you both tomorrow!",
            timestamp=self.start_time - 86400,  # 1 day before start_time
            is_read=True,
        )
        self.email.add_email(prior_email)

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Introduction email arrives from Sarah Kim
            # The email introduces Robert Chen with his contact details in signature
            intro_email_id = "intro-email-robert-chen"
            intro_email_event = email_app.send_email_to_user_with_id(
                email_id=intro_email_id,
                sender="sarah.kim@usercompany.com",
                subject="Introduction: Meet Robert Chen from Acme Corp",
                content="""Hi there,

I'd like to introduce you to Robert Chen from Acme Corp. Robert is the Product Manager leading their Q1 collaboration initiatives and I think you two should connect about our partnership project.

Robert, meet our Design Lead who's been driving the user experience strategy for our platform. You both should chat about aligning on the Q1 roadmap.

Looking forward to seeing this collaboration take shape!

Best,
Sarah

---
Robert Chen
Product Manager | Acme Corp
robert.chen@acmecorp.com
+1-555-0199
San Francisco, CA""",
            )

            # Oracle Event 2: Agent searches contacts to verify Robert is not already present
            search_event = (
                contacts_app.search_contacts(query="Robert Chen")
                .oracle()
                .depends_on(intro_email_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent opens the introduction email to parse details
            open_email_event = (
                email_app.get_email_by_id(email_id=intro_email_id, folder_name="INBOX")
                .oracle()
                .depends_on(search_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent proposes creating new contact and replying
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Sarah introduced you to Robert Chen from Acme Corp regarding the Q1 collaboration. Robert isn't in your contacts yet. Would you like me to add him (with his email robert.chen@acmecorp.com and phone +1-555-0199) and send a reply acknowledging the introduction?"
                )
                .oracle()
                .depends_on(open_email_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please add Robert and reply to the introduction.")
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

            # Oracle Event 7: Agent replies to the introduction email (reply-all behavior)
            reply_event = (
                email_app.reply_to_email(
                    email_id=intro_email_id,
                    folder_name="INBOX",
                    content="Thanks Sarah for the introduction! Hi Robert, great to connect. I'm excited to discuss the Q1 collaboration project. Let's schedule time to align on our roadmaps.",
                )
                .oracle()
                .depends_on(create_contact_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent confirms completion to user
            confirmation_event = (
                aui.send_message_to_agent(
                    content="I've added Robert Chen to your contacts and replied to the introduction email."
                )
                .oracle()
                .depends_on(reply_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            intro_email_event,
            search_event,
            open_email_event,
            proposal_event,
            acceptance_event,
            create_contact_event,
            reply_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent proposed adding Robert Chen and replying to introduction (FLEXIBLE on wording)
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent searched contacts to verify Robert doesn't exist (STRICT on app/function)
            search_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                for e in log_entries
            )

            # Check 3: Agent read the introduction email to extract details (STRICT on email_id and app)
            read_email_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                and e.action.args.get("email_id") == "intro-email-robert-chen"
                for e in log_entries
            )

            # Check 4: Agent created new contact for Robert Chen (STRICT on structural data)
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

            # Check 5: Agent replied to the introduction email (STRICT on function/app, FLEXIBLE on content)
            reply_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "intro-email-robert-chen"
                for e in log_entries
            )

            # Strict checks: search, read email, create contact, and reply must all be present
            strict_checks = (
                search_found and read_email_found and create_contact_found and reply_found and proposal_found
            )

            success = strict_checks

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("agent proposal")
                if not search_found:
                    missing.append("contact search")
                if not read_email_found:
                    missing.append("email read")
                if not create_contact_found:
                    missing.append("contact creation")
                if not reply_found:
                    missing.append("email reply")
                rationale = f"Missing critical checks: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
