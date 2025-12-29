"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.apartment_listing import Apartment
from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulApartmentApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("apartment_lease_expiry_renewal_prep")
class ApartmentLeaseExpiryRenewalPrep(PASScenario):
    """Agent prepares lease renewal response after receiving landlord notification about expiring lease term.

    The user has their current apartment "Downtown Lofts Unit 5C" saved in their favorites. An email arrives from the
    property manager stating the lease expires in 60 days (March 15th, 2025) and offering renewal at $2600/month (up
    from $2400), with a decision deadline of January 25th. The email also notes they may be able to offer a price match
    if the tenant can share comparable listings. The agent must:
    1. Detect and read the lease renewal email with renewal terms and deadline
    2. Propose to the user to (a) confirm the current saved-apartment rent and (b) search for comparable Downtown options
       to use as leverage for a counter-offer / price-match request
    3. After user acceptance, list saved apartments and search the apartment catalog for comparable alternatives at or
       below $2600/month
    4. Draft a reply email requesting a lower renewal rate (e.g., $2500/month) and referencing the comparable listings /
       price-match option

    This scenario exercises lease lifecycle management, comparative rent analysis across saved vs. catalog listings, deadline-driven response preparation, negotiation email composition with data-backed context, and contingency planning through proactive apartment searches triggered by housing-status changes communicated via email..
    """

    start_time = datetime(2025, 1, 14, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Populate apartment catalog with current residence (Downtown Lofts Unit 5C) that user has saved
        # This is the user's current apartment at $2400/month
        current_apt_id = "current_downtown_lofts_5c"
        current_apartment = Apartment(
            apartment_id=current_apt_id,
            name="Downtown Lofts Unit 5C",
            location="Downtown",
            zip_code="90012",
            price=2400.0,
            bedrooms=2,
            bathrooms=2,
            property_type="Apartment",
            square_footage=950,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "Parking", "In-unit laundry"],
            saved=True,
        )
        self.apartment.apartments[current_apt_id] = current_apartment
        self.apartment.saved_apartments.append(current_apt_id)

        # Add comparable alternatives to the catalog (these will be discoverable via search in Step 3)
        alt_1_id = "riverside_towers_8b"
        alt_1 = Apartment(
            apartment_id=alt_1_id,
            name="Riverside Towers 8B",
            location="Downtown",
            zip_code="90013",
            price=2550.0,
            bedrooms=2,
            bathrooms=2,
            property_type="Apartment",
            square_footage=920,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Parking", "Pool"],
            saved=False,
        )
        self.apartment.apartments[alt_1_id] = alt_1

        alt_2_id = "urban_place_3d"
        alt_2 = Apartment(
            apartment_id=alt_2_id,
            name="Urban Place 3D",
            location="Downtown",
            zip_code="90014",
            price=2450.0,
            bedrooms=2,
            bathrooms=2,
            property_type="Condo",
            square_footage=980,
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "In-unit laundry"],
            saved=False,
        )
        self.apartment.apartments[alt_2_id] = alt_2

        alt_3_id = "city_view_12a"
        alt_3 = Apartment(
            apartment_id=alt_3_id,
            name="City View Apartments 12A",
            location="Downtown",
            zip_code="90015",
            price=2595.0,
            bedrooms=2,
            bathrooms=2,
            property_type="Apartment",
            square_footage=1000,
            furnished_status="Semi-furnished",
            floor_level="Penthouse",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Gym", "Parking", "Pool", "Rooftop deck"],
            saved=False,
        )
        self.apartment.apartments[alt_3_id] = alt_3

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Add property manager contact (for Step 3 email reply)
        property_manager = Contact(
            first_name="Sarah",
            last_name="Johnson",
            email="sjohnson@downtownlofts.com",
            phone="555-0123",
            job="Property Manager",
        )
        # Note: ContactsApp is not in selected apps, so we don't seed contacts directly.
        # The email itself will provide the sender address for reply purposes.

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # Environment event 1: Lease renewal email from property manager arrives
            # This is the exogenous trigger: landlord notifying user about lease expiration + renewal terms
            lease_email_id = "lease_renewal_email_2025"
            lease_email_event = email_app.send_email_to_user_with_id(
                email_id=lease_email_id,
                sender="sjohnson@downtownlofts.com",
                subject="Lease Renewal Notice - Downtown Lofts Unit 5C",
                content=(
                    "Dear Tenant,\n\n"
                    "Your lease for Downtown Lofts Unit 5C expires in 60 days on March 15th, 2025. "
                    "We are pleased to offer you the opportunity to renew your lease for another year.\n\n"
                    "Renewal Terms:\n"
                    "- Monthly rent: $2600 (current rent: $2400)\n"
                    "- Lease term: 1 year\n"
                    "- Response deadline: January 25th, 2025\n\n"
                    "Please let me know your decision by January 25th so we can proceed accordingly. "
                    "If you've found comparable apartments at a lower monthly rate, feel free to share them—we may be able to offer a price match.\n\n"
                    "If you have any questions or would like to discuss the terms, feel free to reach out.\n\n"
                    "Best regards,\n"
                    "Sarah Johnson\n"
                    "Property Manager\n"
                    "Downtown Lofts"
                ),
            ).delayed(5)

            # Oracle event 1: Agent reads the lease renewal email to understand the situation
            # Evidence: lease_email_event delivered the renewal notification with specific terms
            read_email_event = (
                email_app.get_email_by_id(email_id=lease_email_id, folder_name="INBOX")
                .oracle()
                .depends_on(lease_email_event, delay_seconds=3)
            )

            # Oracle event 2: Agent proposes help with lease renewal decision and drafting response
            # Evidence: lease_email_event content explicitly mentions renewal deadline, price increase, and price-match option
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I noticed you received a lease renewal notice from Downtown Lofts for Unit 5C. "
                        "The rent is increasing from $2400 to $2600/month (8.3% increase), with a decision deadline of January 25th.\n\n"
                        "They also mentioned they may be able to price-match if you can share comparable listings at a lower rate. "
                        "If you'd like, I can (1) pull your saved apartment info to confirm the current rent and (2) search for comparable Downtown options "
                        "to use as leverage, then draft a reply requesting a lower renewal rate.\n\n"
                        "Should I do that and draft a response?"
                    )
                )
                .oracle()
                .depends_on([lease_email_event, read_email_event], delay_seconds=3)
            )

            # Oracle event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes—please look up comparable options and draft a response asking if they can do $2500/month."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle event 4: Agent lists saved apartments to identify the current residence (AFTER user approval)
            # Evidence: email mentions "Downtown Lofts Unit 5C" which should match a saved apartment
            list_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle event 5: Agent searches for comparable alternatives in the same location (AFTER user approval)
            # Evidence: email specifies renewal at $2600 and invites price matching based on comparable listings
            search_alternatives_event = (
                apartment_app.search_apartments(
                    location="Downtown",
                    number_of_bedrooms=2,
                    number_of_bathrooms=2,
                    max_price=2600,
                )
                .oracle()
                .depends_on(list_saved_event, delay_seconds=2)
            )

            # Oracle event 6: Agent composes reply email requesting counter-offer
            # Evidence: user accepted proposal and specified $2500 target in acceptance_event
            reply_event = (
                email_app.reply_to_email(
                    email_id=lease_email_id,
                    folder_name="INBOX",
                    content=(
                        "Dear Sarah,\n\n"
                        "Thank you for the lease renewal notice. I appreciate the opportunity to continue living at Downtown Lofts Unit 5C.\n\n"
                        "I've reviewed the proposed $2600/month rate and would like to discuss the possibility of renewing at $2500/month instead. "
                        "I've been a reliable tenant and would be happy to commit to another year if we can reach an agreement on this rate.\n\n"
                        "You mentioned the possibility of a price match based on comparable listings. I found several similar 2BR/2BA options in Downtown "
                        "at or below $2600/month, so I wanted to ask if you could match closer to $2500/month for my renewal.\n\n"
                        "Would you be open to this counter-offer? I'm happy to discuss further if needed.\n\n"
                        "Thank you for your consideration.\n\n"
                        "Best regards"
                    ),
                )
                .oracle()
                .depends_on(search_alternatives_event, delay_seconds=3)
            )

            # Oracle event 7: Agent sends summary message to user confirming action taken
            # Evidence: reply_event completed the draft/send, so agent can now report completion
            summary_event = (
                aui.send_message_to_user(
                    content=(
                        "I've sent a reply to Sarah Johnson requesting a lease renewal at $2500/month instead of $2600. "
                        "The email highlights your reliable tenancy and willingness to commit to another year.\n\n"
                        "I'll keep monitoring your inbox for her response. "
                        "If she declines, we can explore those alternative apartments I found."
                    )
                )
                .oracle()
                .depends_on(reply_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            lease_email_event,
            read_email_event,
            list_saved_event,
            search_alternatives_event,
            proposal_event,
            acceptance_event,
            reply_event,
            summary_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal to user about lease renewal
            # Must mention lease/renewal and present alternatives or offer to help
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent read the lease renewal email
            # This proves the agent detected the triggering environment event
            email_read_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                and e.action.args.get("email_id") == "lease_renewal_email_2025"
                for e in log_entries
            )

            # STRICT Check 3: Agent searched for alternative apartments
            # Must search catalog for comparable alternatives in Downtown
            alternatives_searched = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "search_apartments"
                and e.action.args.get("location") == "Downtown"
                and e.action.args.get("max_price") is not None
                for e in log_entries
            )

            # STRICT Check 4: Agent sent reply email with counter-offer
            # Must reply to the lease renewal email (not just any email)
            reply_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "lease_renewal_email_2025"
                for e in log_entries
            )

            # All strict checks must pass for success
            success = proposal_found and email_read_found and alternatives_searched and reply_sent

            if not success:
                # Build rationale for failure
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not send proposal to user about lease renewal")
                if not email_read_found:
                    failed_checks.append("agent did not read the lease renewal email")
                if not alternatives_searched:
                    failed_checks.append("agent did not search for alternative apartments")
                if not reply_sent:
                    failed_checks.append("agent did not send reply email with counter-offer")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
