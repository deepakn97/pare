"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
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


@register_scenario("enrich_contacts_from_signatures")
class EnrichContactsFromSignatures(PASScenario):
    """Agent enriches incomplete contact records by extracting professional details from email signatures.

    The user has existing contacts for colleagues Sarah Kim and Robert Martinez with only basic information (name and email). Two separate work-related emails arrive from these contacts. Each email includes a detailed signature (job title, direct phone number, office address) and explicitly asks the recipient to update their address book/contact card with the updated info. The agent must: 1. Parse incoming emails and extract structured information from professional signatures. 2. Cross-reference sender emails against existing contacts to identify enrichment opportunities. 3. Recognize that job title, work phone, and address fields are currently empty in the contact records. 4. Propose updating both contacts with the newly discovered professional information. 5. After user acceptance, edit both contact records to include the extracted details.

    This scenario exercises implicit information extraction from formatted text (email signatures), bidirectional cross-app data comparison (checking what's missing in contacts based on email content), batch contact enrichment from multiple independent emails, and structured data parsing from semi-standardized signature formats..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize contacts app
        self.contacts = StatefulContactsApp(name="Contacts")

        # Create baseline contacts with minimal information (name and email only)
        # These contacts are missing job, phone, and address information
        sarah_contact = Contact(
            first_name="Sarah",
            last_name="Kim",
            contact_id="contact-sarah-kim",
            email="sarah.kim@techcorp.com",
            job=None,
            phone=None,
            address=None,
        )

        robert_contact = Contact(
            first_name="Robert",
            last_name="Martinez",
            contact_id="contact-robert-martinez",
            email="robert.martinez@innovate.io",
            job=None,
            phone=None,
            address=None,
        )

        # Add contacts to the contacts app
        self.contacts.add_contact(sarah_contact)
        self.contacts.add_contact(robert_contact)

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Email from Sarah Kim with detailed signature
            email1_event = email_app.send_email_to_user_with_id(
                email_id="email-sarah-project-update",
                sender="sarah.kim@techcorp.com",
                subject="Q4 Project Status Update",
                content="""Hi,

Just wanted to share the latest project status. We're on track for the Q4 deadline and making good progress on all deliverables.

P.S. I updated my work contact details recently - please update your address book/contact card with my direct line and office address below.

Best regards,
Sarah Kim
Senior Product Manager
TechCorp Solutions
Direct: +1-555-234-5678
Office: 350 Mission Street, San Francisco, CA 94105""",
            ).delayed(15)

            # Environment Event 2: Email from Robert Martinez with detailed signature
            email2_event = email_app.send_email_to_user_with_id(
                email_id="email-robert-budget-review",
                sender="robert.martinez@innovate.io",
                subject="Budget Review Meeting Notes",
                content="""Hello,

Please find attached the notes from yesterday's budget review meeting. Let me know if you have any questions.

P.S. My office details changed - please update my contact card/address book with the information in my signature.

Regards,
Robert Martinez
Chief Technology Officer
Innovate Technologies
Mobile: +1-555-876-5432
Address: 1200 Park Avenue, New York, NY 10128""",
            ).delayed(8)

            # Oracle Event 1: Agent searches contacts to identify enrichment opportunities
            # Evidence: Sarah's email explicitly asks to "update your address book/contact card" with her updated details.
            search_sarah_event = (
                contacts_app.search_contacts(query="Sarah Kim").oracle().depends_on(email1_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent searches for Robert's contact
            # Evidence: Robert's email explicitly asks to "update my contact card/address book" with his updated details.
            search_robert_event = (
                contacts_app.search_contacts(query="Robert Martinez").oracle().depends_on(email2_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent gets Sarah's contact details to check what's missing
            get_sarah_event = (
                contacts_app.get_contacts(offset=0).oracle().depends_on(search_sarah_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent proposes enriching both contacts with extracted information
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I noticed emails from Sarah Kim and Robert Martinez included detailed signatures (job titles, "
                        "phone numbers, and addresses), and both emails explicitly asked to update your address book/"
                        "contact cards with their updated details. Would you like me to update their contact records "
                        "with the information from their signatures?"
                    )
                )
                .oracle()
                .depends_on(get_sarah_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please update both contacts with the information from their signatures."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent updates Sarah Kim's contact with extracted details
            update_sarah_event = (
                contacts_app.edit_contact(
                    contact_id="contact-sarah-kim",
                    updates={
                        "job": "Senior Product Manager",
                        "phone": "+1-555-234-5678",
                        "address": "350 Mission Street, San Francisco, CA 94105",
                    },
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent updates Robert Martinez's contact with extracted details
            update_robert_event = (
                contacts_app.edit_contact(
                    contact_id="contact-robert-martinez",
                    updates={
                        "job": "Chief Technology Officer",
                        "phone": "+1-555-876-5432",
                        "address": "1200 Park Avenue, New York, NY 10128",
                    },
                )
                .oracle()
                .depends_on(update_sarah_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            email1_event,
            email2_event,
            search_sarah_event,
            search_robert_event,
            get_sarah_event,
            proposal_event,
            acceptance_event,
            update_sarah_event,
            update_robert_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal to enrich contacts with signature information (STRICT on logic, FLEXIBLE on wording)
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    name in e.action.args.get("content", "")
                    for name in ["Sarah Kim", "Robert Martinez", "Sarah", "Robert"]
                )
                for e in log_entries
            )

            # Check 2: Agent searched for Sarah Kim's contact (STRICT)
            search_sarah_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                and any(name in e.action.args.get("query", "") for name in ["Sarah", "Kim", "Sarah Kim"])
                for e in log_entries
            )

            # Check 3: Agent searched for Robert Martinez's contact (STRICT)
            search_robert_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                and any(name in e.action.args.get("query", "") for name in ["Robert", "Martinez", "Robert Martinez"])
                for e in log_entries
            )

            # Check 4: Agent updated Sarah Kim's contact with extracted information (STRICT on structure, FLEXIBLE on exact values)
            update_sarah_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "edit_contact"
                and e.action.args.get("contact_id") == "contact-sarah-kim"
                for e in log_entries
            )

            # Check 5: Agent updated Robert Martinez's contact with extracted information (STRICT on structure, FLEXIBLE on exact values)
            update_robert_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "edit_contact"
                and e.action.args.get("contact_id") == "contact-robert-martinez"
                for e in log_entries
            )

            # Determine success and build rationale for failures
            success = (
                proposal_found
                and search_sarah_found
                and search_robert_found
                and update_sarah_found
                and update_robert_found
            )

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("no proposal message to user offering contact enrichment")
                if not search_sarah_found:
                    missing_checks.append("no search for Sarah Kim's contact")
                if not search_robert_found:
                    missing_checks.append("no search for Robert Martinez's contact")
                if not update_sarah_found:
                    missing_checks.append("no edit_contact call for Sarah Kim with job/phone/address updates")
                if not update_robert_found:
                    missing_checks.append("no edit_contact call for Robert Martinez with job/phone/address updates")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
