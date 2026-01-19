from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact, ContactsApp
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.apartment import StatefulApartmentApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("email_forward_apartment_inquiry")
class EmailForwardApartmentInquiry(PASScenario):
    """Agent forwards apartment inquiry email to leasing office extracted from apartment listing details.

    The user has saved an apartment "Riverside Towers Unit 402B" to their favorites. An email arrives from the user's
    partner asking if that Riverside apartment allows two cats and explicitly requesting that the agent forward the
    partner's email to the leasing office (so the original question/context is preserved). The agent must:
    1. Detect the inquiry email requesting pet policy information
    2. Extract the apartment name reference from the email content
    3. Search saved apartments to identify the specific listing
    4. Retrieve apartment details to find the leasing office contact email
    5. Compose a forward of the partner's question to the leasing office's email
    6. Present the draft forward for user approval
    7. Upon acceptance, send the email forward with appropriate context

    This scenario exercises unstructured query interpretation from incoming email, apartment reference resolution via saved list search, leasing office contact extraction from listing metadata, email forwarding with context preservation, and cross-app information routing (email → apartment → email).
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")
        self.email.user_email = "user@example.com"

        # Initialize apartment app with saved apartment
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Add Riverside Towers apartment with leasing office contact in amenities
        # Note: The Apartment dataclass doesn't have a dedicated property_manager_email field,
        # so we include the contact info as part of amenities list for discovery
        riverside_apt_id = self.apartment.add_new_apartment(
            name="Riverside Towers Unit 402B",
            location="Downtown Riverside",
            zip_code="92501",
            price=2400.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Contact leasing office for pet policy details",
            lease_term="1 year",
            amenities=["Parking", "Gym", "Pool", "leasing office:  (leasing@riversidetowers.com)"],
        )

        # Save the apartment to favorites
        self.apartment.save_apartment(riverside_apt_id)
        self.riverside_apt_id = riverside_apt_id

        # Initialize contacts app for leasing office reference
        self.contacts = ContactsApp(name="Contacts")

        # Add partner contact
        partner_contact = Contact(
            first_name="Alex", last_name="Johnson", email="alex.johnson@example.com", phone="+1-555-0123"
        )
        self.contacts.add_contact(partner_contact)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.apartment, self.contacts]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        # Store email ID for later reference
        partner_email_id = "email-partner-inquiry-001"

        with EventRegisterer.capture_mode():
            # Environment Event 1: Partner sends email asking about pet policy for Riverside apartment
            partner_email_event = email_app.send_email_to_user_with_id(
                email_id=partner_email_id,
                sender="alex.johnson@example.com",
                subject="Question about the apartment",
                content=(
                    "Hey! Can you find out if that Riverside apartment allows two cats? The listing wasn't clear about the pet policy and I want to make sure before we proceed.\n\n"
                    "Can you please forward this email to the leasing office for the Riverside Towers Unit 402B listing you saved, so they see my exact question and can reply?"
                ),
            ).delayed(10)

            # Oracle Event 1: Agent reads the partner's email to understand the inquiry
            # Motivation: The email notification triggered the agent to check inbox
            read_email_event = (
                email_app.get_email_by_id(email_id=partner_email_id, folder_name="INBOX")
                .oracle()
                .depends_on(partner_email_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent searches saved apartments to find the Riverside apartment mentioned in email
            # Motivation: Partner explicitly referenced the Riverside listing in the user's saved apartments.
            search_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(read_email_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent searches saved apartments for "Riverside" to identify the exact listing
            # Motivation: Narrow down to the specific saved listing referenced in the email.
            search_apts_event = (
                apartment_app.search_apartments(name="Riverside", saved_only=True)
                .oracle()
                .depends_on(search_saved_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent retrieves apartment details to extract the leasing office contact
            # Motivation: The listing details (amenities) contain "leasing office:  (email)".
            get_details_event = (
                apartment_app.get_apartment_details(apartment_id=self.riverside_apt_id)
                .oracle()
                .depends_on(search_apts_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent proposes forwarding the inquiry to leasing office
            # Motivation: Partner explicitly requested forwarding the email (not composing a new one), and apartment
            # details surfaced the leasing office contact info via tools.
            proposal_event = (
                aui.send_message_to_user(
                    content="I see Alex is asking about the pet policy for Riverside Towers Unit 402B. I checked the saved listing details and found the leasing office contact in the amenities:  (leasing@riversidetowers.com). Would you like me to forward Alex's question to the leasing office?"
                )
                .oracle()
                .depends_on([read_email_event, get_details_event], delay_seconds=2)
            )

            # Oracle Event 6: User accepts the proposal
            # Motivation: User approval to proceed with forwarding the email
            acceptance_event = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent forwards the email to leasing office
            # Motivation: User accepted the proposal, now execute the forwarding action using the email_id from the environment event
            forward_event = (
                email_app.forward_email(
                    email_id=partner_email_id, recipients=["leasing@riversidetowers.com"], folder_name="INBOX"
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            partner_email_event,
            read_email_event,
            search_saved_event,
            search_apts_event,
            get_details_event,
            proposal_event,
            acceptance_event,
            forward_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1 (STRICT): Agent proposed forwarding to the user
            proposal_found = False
            for e in agent_events:
                if e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user":
                    # The proposal exists; we do not check exact message content
                    proposal_found = True
                    break

            # Check 2 (STRICT): Agent forwarded the email to leasing office
            forward_found = False
            property_manager_email = "leasing@riversidetowers.com"
            for e in agent_events:
                if e.action.class_name == "StatefulEmailApp" and e.action.function_name == "forward_email":
                    args = e.action.args
                    # Verify the correct email_id and recipient
                    if args.get("email_id") == "email-partner-inquiry-001" and property_manager_email in args.get(
                        "recipients", []
                    ):
                        forward_found = True
                        break

            # Build rationale for failure
            missing_checks = []
            if not proposal_found:
                missing_checks.append("agent did not propose forwarding to user")
            if not forward_found:
                missing_checks.append("agent did not forward email to leasing office")

            success = proposal_found and forward_found

            if success:
                return ScenarioValidationResult(success=True)
            else:
                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
