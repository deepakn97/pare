from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulApartmentApp,
    StatefulEmailApp,
)
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("apartment_lease_expiry_renewal_prep")
class ApartmentLeaseExpiryRenewalPrep(PAREScenario):
    """Agent prepares lease renewal response after receiving landlord notification about expiring lease term.

    The user has their current apartment "Downtown Lofts Unit 5C" saved in their favorites. An email arrives from the
    property manager stating the lease expires in 60 days (March 15th, 2025) and offering renewal at $2600/month (up
    from $2400), with a decision deadline of January 25th. The email also notes they may be able to offer a price match
    if the tenant can share comparable listings. The agent must:
    1. Detect and read the lease renewal email with renewal terms and deadline
    2. Propose to the user to search for comparable Downtown options to use as leverage for a counter-offer / price-match
       request
    3. After user acceptance, search the apartment catalog for comparable alternatives at or below $2600/month
    4. Send a reply email requesting a lower renewal rate (e.g., $2500/month) and referencing the specific comparable
       listings (names + prices) as requested in the landlord email

    This scenario exercises lease lifecycle management, deadline-driven response preparation, data-backed negotiation
    email composition, and user-gated apartment searches triggered by a renewal notification.
    """

    start_time = datetime(2025, 1, 14, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Seed apartment catalog via public APIs (avoid mutating internal dicts/lists directly).
        # Current residence (user has saved it).
        self.current_apt_id = self.apartment.add_new_apartment(
            name="Downtown Lofts Unit 5C",
            location="Downtown",
            zip_code="90012",
            price=2400.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=950,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "Parking", "In-unit laundry"],
        )
        self.apartment.save_apartment(self.current_apt_id)

        # Add comparable alternatives to the catalog (these will be discoverable via search in Step 3)
        self.alt_1_id = self.apartment.add_new_apartment(
            name="Riverside Towers 8B",
            location="Downtown",
            zip_code="90013",
            price=2450.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=920,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Parking", "Pool"],
        )

        self.alt_2_id = self.apartment.add_new_apartment(
            name="Urban Place 3D",
            location="Downtown",
            zip_code="90014",
            price=2450.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=980,
            property_type="Condo",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "In-unit laundry"],
        )

        self.alt_3_id = self.apartment.add_new_apartment(
            name="City View Apartments 12A",
            location="Downtown",
            zip_code="90015",
            price=2495.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1000,
            property_type="Apartment",
            furnished_status="Semi-furnished",
            floor_level="Penthouse",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Gym", "Parking", "Pool", "Rooftop deck"],
        )

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
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize apps
        aui = self.get_typed_app(PAREAgentUserInterface)
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
                    "If you'd like us to consider a price match, please reply with at least two comparable Downtown 2BR/2BA listings (building/unit name and monthly rent) at a lower monthly rate—we may be able to offer a match.\n\n"
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
                        "If you'd like, I can search for comparable Downtown options to use as leverage, then send a reply email requesting a lower renewal rate.\n\n"
                        "Should I do that and send a reply email?"
                    )
                )
                .oracle()
                .depends_on([lease_email_event, read_email_event], delay_seconds=3)
            )

            # Oracle event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please do that.").oracle().depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle event 4: Agent searches for comparable alternatives in the same location (AFTER user approval)
            # Evidence: email specifies renewal at $2600 and invites price matching based on comparable listings
            search_alternatives_event = (
                apartment_app.search_apartments(
                    location="Downtown",
                    number_of_bedrooms=2,
                    number_of_bathrooms=2,
                    max_price=2600,
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle event 5: Agent composes reply email requesting counter-offer
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
                        "You mentioned the possibility of a price match based on comparable listings (names + prices). Here are three similar 2BR/2BA options in Downtown "
                        "at or below $2600/month that I found:\n"
                        "- Urban Place 3D: $2450/month\n"
                        "- Riverside Towers 8B: $2450/month\n"
                        "- City View Apartments 12A: $2495/month\n\n"
                        "Given these comparable rates, I wanted to ask if you could match closer to $2500/month for my renewal.\n\n"
                        "Would you be open to this counter-offer? I'm happy to discuss further if needed.\n\n"
                        "Thank you for your consideration.\n\n"
                        "Best regards"
                    ),
                )
                .oracle()
                .depends_on(search_alternatives_event, delay_seconds=3)
            )

            # Oracle event 6: Agent sends summary message to user confirming action taken
            # Evidence: reply_event completed the draft/send, so agent can now report completion
            summary_event = (
                aui.send_message_to_user(
                    content=(
                        "I've sent a reply to Sarah Johnson requesting a lease renewal at $2500/month instead of $2600. "
                        "The email highlights your reliable tenancy and includes comparable Downtown 2BR/2BA listings (Urban Place 3D $2450, Riverside Towers 8B $2450, City View Apartments 12A $2495).\n\n"
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
            search_alternatives_event,
            proposal_event,
            acceptance_event,
            reply_event,
            summary_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal to user about lease renewal
            # Must mention lease/renewal and present alternatives or offer to help
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent sent reply email with counter-offer
            # Must reply to the lease renewal email (not just any email)
            reply_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "lease_renewal_email_2025"
                for e in log_entries
            )

            # STRICT Check 3: Reply email includes specific comparable listing names (to prove search results were used)
            reply_mentions_comps = False
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.class_name == "StatefulEmailApp"
                    and e.action.function_name == "reply_to_email"
                    and e.action.args.get("email_id") == "lease_renewal_email_2025"
                ):
                    content = (e.action.args.get("content") or "").lower()
                    comps = [
                        "urban place 3d",
                        "riverside towers 8b",
                        "city view apartments 12a",
                    ]
                    if sum(1 for c in comps if c in content) >= 2:
                        reply_mentions_comps = True
                    break

            # All strict checks must pass for success
            success = proposal_found and reply_sent and reply_mentions_comps

            if not success:
                # Build rationale for failure
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not send proposal to user about lease renewal")
                if not reply_sent:
                    failed_checks.append("agent did not send reply email with counter-offer")
                if not reply_mentions_comps:
                    failed_checks.append(
                        "reply email did not reference at least two specific comparable listings by name"
                    )

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
