"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.apartment_listing import Apartment
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.apartment import StatefulApartmentApp
from pas.apps.cab import StatefulCabApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("apartment_viewing_ride_coordination")
class ApartmentViewingRideCoordination(PASScenario):
    """Agent coordinates transportation for urgent apartment viewing appointment based on saved search criteria and price update notification.

    The user has saved several apartments to favorites in their apartment search, including "Riverside Lofts" priced at $2,200/month for a 2-bedroom unit. A price drop notification arrives indicating that Riverside Lofts has reduced its rent to $1,950/month, making it competitive. Separately, an email from the Riverside Lofts leasing office notes that pricing has recently changed (no numbers in the email) and that viewing slots are filling up, offering an open slot tomorrow at 10:00 AM. The agent must:
    1. Detect the price drop notification for the saved apartment
    2. Read the leasing office email and extract the proposed viewing time (tomorrow at 10:00 AM)
    3. Retrieve full apartment details (location, updated price, amenities)
    4. Propose arranging transportation to view the apartment at the offered time
    5. Get a ride quotation for the apartment's address
    6. Order a ride with appropriate timing (e.g., tomorrow morning)
    7. Confirm the viewing plan with the user

    This scenario exercises cross-app workflow coordination (apartment updates triggering transportation), price-based decision signals, saved-item tracking, location extraction from apartment records, ride quotation and booking with specific service types, and proactive scheduling based on market urgency cues..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for apartment viewing ride coordination scenario.

        Baseline state:
        - Apartment: User has saved several apartments including Riverside Lofts at $2,200/month.
          The price drop to $1,950/month will be delivered as a notification environment event in Step 3.
        - Email: The Riverside Lofts leasing office will send an email noting a recent price change (no numbers)
          and offering a viewing slot tomorrow at 10:00 AM.
        - Cab: Initialized and ready for ride quotations and bookings.
        - System: Standard home screen for notification delivery.
        - Agent UI: Standard interface for proposals and acceptances.
        """
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apartment app with saved apartments
        self.apartment = StatefulApartmentApp(name="Apartment")

        # User has saved several apartments to favorites
        # Riverside Lofts is the one that will get a price drop notification
        riverside_lofts = Apartment(
            apartment_id="apt_riverside_001",
            name="Riverside Lofts",
            location="450 River View Drive, Riverside District",
            zip_code="93102",
            price=2200.0,  # Original price before the drop
            bedrooms=2,
            bathrooms=2,
            property_type="Apartment",
            square_footage=1050,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["River views", "Gym", "Parking", "Pool"],
            saved=True,
        )

        # A few other saved apartments for context (user is actively searching)
        parkside_plaza = Apartment(
            apartment_id="apt_park_002",
            name="Parkside Plaza",
            location="890 Park Avenue, Central District",
            zip_code="93101",
            price=2350.0,
            bedrooms=2,
            bathrooms=1.5,
            property_type="Apartment",
            square_footage=980,
            furnished_status="Unfurnished",
            floor_level="Mid-level",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Park views", "Balcony", "Parking"],
            saved=True,
        )

        downtown_heights = Apartment(
            apartment_id="apt_downtown_003",
            name="Downtown Heights",
            location="123 Main Street, Downtown",
            zip_code="93103",
            price=2100.0,
            bedrooms=2,
            bathrooms=2,
            property_type="Apartment",
            square_footage=1100,
            furnished_status="Partially furnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["City views", "Concierge", "Gym"],
            saved=True,
        )

        # Add apartments to the app's internal storage
        self.apartment.apartments["apt_riverside_001"] = riverside_lofts
        self.apartment.saved_apartments.append("apt_riverside_001")
        self.apartment.apartments["apt_park_002"] = parkside_plaza
        self.apartment.saved_apartments.append("apt_park_002")
        self.apartment.apartments["apt_downtown_003"] = downtown_heights
        self.apartment.saved_apartments.append("apt_downtown_003")

        # Initialize email app (used only for an environment cue; no reply needed)
        self.email = StatefulEmailApp(name="Emails")

        # Initialize cab app (ready for quotations and bookings)
        self.cab = StatefulCabApp(name="Cab")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.email, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment event: Price drop notification for Riverside Lofts (saved apartment)
            # This is the concrete exogenous trigger that motivates all subsequent agent actions
            price_drop_event = apartment_app.update_apartment(
                apartment_id="apt_riverside_001", new_price=1950.0
            ).delayed(2)

            # Environment event: Leasing office email offering a viewing slot (does not include numeric price)
            # This provides an explicit reason to schedule a visit tomorrow at 10:00 AM.
            leasing_email_id = "riverside_viewing_slot_001"
            leasing_email_event = email_app.send_email_to_user_with_id(
                email_id=leasing_email_id,
                sender="leasing@riversidelofts.example",
                subject="Riverside Lofts: Viewing slots available tomorrow",
                content=(
                    "Hi,\n\n"
                    "We noticed you saved Riverside Lofts. Our pricing has recently changed, and interest has picked up.\n"
                    "If you'd like to tour soon, we have an open viewing slot tomorrow at 10:00 AM.\n\n"
                    "Thanks,\n"
                    "Riverside Lofts Leasing Office"
                ),
            ).delayed(5)

            # Oracle: Agent reads the leasing email to ground the proposed viewing time
            read_leasing_email_event = (
                email_app.get_email_by_id(email_id=leasing_email_id, folder_name="INBOX")
                .oracle()
                .depends_on(leasing_email_event, delay_seconds=2)
            )

            # Agent observes the price drop notification and retrieves saved apartments to understand context
            list_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(price_drop_event, delay_seconds=2)
            )

            # Agent retrieves full details of Riverside Lofts to extract location for ride planning
            get_details_event = (
                apartment_app.get_apartment_details(apartment_id="apt_riverside_001")
                .oracle()
                .depends_on(list_saved_event, delay_seconds=2)
            )

            # Agent proposes transportation coordination based on the price drop notification
            # The proposal explicitly references the triggering environment cue
            propose_event = (
                aui.send_message_to_user(
                    content="I saw a price drop notification for Riverside Lofts (now $1,950/month, down from $2,200). I also received an email from the leasing office offering a viewing slot tomorrow at 10:00 AM. Would you like me to arrange a ride to take you to the viewing?"
                )
                .oracle()
                .depends_on([get_details_event, read_leasing_email_event], delay_seconds=2)
            )

            # User accepts the proposal
            accept_event = (
                aui.accept_proposal(content="Yes, please arrange a ride for tomorrow at 10 AM.")
                .oracle()
                .depends_on(propose_event, delay_seconds=3)
            )

            # Agent gets quotation for ride to apartment location
            quotation_event = (
                cab_app.get_quotation(
                    start_location="Current Location",
                    end_location="450 River View Drive, Riverside District",
                    service_type="Default",
                    ride_time="2025-11-19 10:00:00",
                )
                .oracle()
                .depends_on(accept_event, delay_seconds=2)
            )

            # Agent books the ride
            order_event = (
                cab_app.order_ride(
                    start_location="Current Location",
                    end_location="450 River View Drive, Riverside District",
                    service_type="Default",
                    ride_time="2025-11-19 10:00:00",
                )
                .oracle()
                .depends_on(quotation_event, delay_seconds=2)
            )

            # Agent confirms completion to user
            confirm_event = (
                aui.send_message_to_user(
                    content="I've booked a ride for tomorrow at 10 AM to Riverside Lofts. The ride will pick you up from your current location and take you to 450 River View Drive. Total estimated cost is around $15-20."
                )
                .oracle()
                .depends_on(order_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            leasing_email_event,
            price_drop_event,
            read_leasing_email_event,
            list_saved_event,
            get_details_event,
            propose_event,
            accept_event,
            quotation_event,
            order_event,
            confirm_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning Riverside Lofts and ride/transportation
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent observed saved apartments (list or specific retrieval)
            # Accept either list_saved_apartments OR get_apartment_details as valid observation methods
            apartments_observed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name in ["list_saved_apartments", "get_apartment_details"]
                for e in log_entries
            )

            # STRICT Check 3: Agent retrieved apartment details to get location
            apartment_details_retrieved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "get_apartment_details"
                and e.action.args.get("apartment_id") == "apt_riverside_001"
                for e in log_entries
            )

            # STRICT Check 4: Agent ordered the ride to the apartment location
            ride_ordered = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and "450 river view drive" in e.action.args.get("end_location", "").lower()
                for e in log_entries
            )

            # Compute success: all strict checks must pass
            success = proposal_found and apartments_observed and apartment_details_retrieved and ride_ordered

            # Build rationale for failures
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal mentioning Riverside Lofts and ride/transportation")
                if not apartments_observed:
                    missing_checks.append("agent observation of saved apartments")
                if not apartment_details_retrieved:
                    missing_checks.append("agent retrieval of Riverside Lofts details (apt_riverside_001)")
                if not ride_ordered:
                    missing_checks.append("ride order to 450 river view drive")

                rationale = "Missing required agent actions: " + ", ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
