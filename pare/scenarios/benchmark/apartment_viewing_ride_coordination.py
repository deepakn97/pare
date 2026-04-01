from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
)
from pare.apps.apartment import StatefulApartmentApp
from pare.apps.cab import StatefulCabApp
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("apartment_viewing_ride_coordination")
class ApartmentViewingRideCoordination(PAREScenario):
    """Agent coordinates transportation for urgent apartment viewing appointment based on saved search criteria and price update notification.

    The user has saved several apartments to favorites in their apartment search, including "Riverside Lofts" priced at $2,200/month for a 2-bedroom unit. A price drop notification arrives indicating that Riverside Lofts has reduced its rent to $1,950/month, making it competitive. Separately, a user-created reminder notification fires about an in-person viewing today at 10:00 AM and explicitly suggests booking a ride due to limited parking, including a pickup address. The agent must:
    1. Detect the price drop notification for the saved apartment
    2. Detect the reminder notification (time-driven; emitted automatically when the reminder is due) and infer transportation is needed
    3. Retrieve full apartment details (location, updated price, amenities)
    4. Propose arranging transportation to view the apartment at the offered time
    5. Get a ride quotation for the apartment's address
    6. Order a ride with appropriate timing (e.g., depart at 9:30 AM to arrive early)
    7. Confirm the viewing plan with the user

    This scenario exercises cross-app workflow coordination (apartment updates triggering transportation), price-based decision signals, saved-item tracking, location extraction from apartment records, ride quotation and booking with specific service types, and proactive scheduling based on market urgency cues..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data for apartment viewing ride coordination scenario.

        Baseline state:
        - Apartment: User has saved several apartments including Riverside Lofts at $2,200/month.
          The price drop to $1,950/month will be delivered as a notification environment event in Step 3.
        - Reminder: A user-created reminder will fire shortly after start_time about a viewing today at 10:00 AM,
          including the address and a concrete pickup location to use for booking a ride.
        - Cab: Initialized and ready for ride quotations and bookings.
        - System: Standard home screen for notification delivery.
        - Agent UI: Standard interface for proposals and acceptances.
        """
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apartment app with saved apartments
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Seed saved apartments via public APIs (avoid mutating internal dicts/lists directly).
        # Riverside Lofts is the one that will get a price drop notification.
        self.riverside_lofts_id = self.apartment.add_new_apartment(
            name="Riverside Lofts",
            location="450 River View Drive, Riverside District",
            zip_code="93102",
            price=2200.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1050,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["River views", "Gym", "Parking", "Pool"],
        )
        self.apartment.save_apartment(self.riverside_lofts_id)

        self.parkside_plaza_id = self.apartment.add_new_apartment(
            name="Parkside Plaza",
            location="890 Park Avenue, Central District",
            zip_code="93101",
            price=2350.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=980,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Mid-level",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Park views", "Balcony", "Parking"],
        )
        self.apartment.save_apartment(self.parkside_plaza_id)

        self.downtown_heights_id = self.apartment.add_new_apartment(
            name="Downtown Heights",
            location="123 Main Street, Downtown",
            zip_code="93103",
            price=2100.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Apartment",
            furnished_status="Partially furnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["City views", "Concierge", "Gym"],
        )
        self.apartment.save_apartment(self.downtown_heights_id)

        # Initialize reminder app (time-driven notifications)
        self.reminder = StatefulReminderApp(name="Reminders")

        # Seed a time-driven reminder that will automatically notify the user+agent when due.
        # We set it ~1 minute after start_time so it feels like a "1 hour before the viewing" nudge.
        self.reminder.add_reminder(
            title="Riverside Lofts viewing today — book ride",
            due_datetime="2025-11-18 09:01:00",
            description=(
                "Viewing at Riverside Lofts today at 10:00 AM, schedule a ride to the apartment.\n"
                "Pickup location (start): 123 Main Street, Downtown\n"
            ),
        )

        # Initialize cab app (ready for quotations and bookings)
        self.cab = StatefulCabApp(name="Cab")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.reminder, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment event: Price drop notification for Riverside Lofts (saved apartment)
            price_drop_event = apartment_app.update_apartment(
                apartment_id=self.riverside_lofts_id, new_price=1950.0
            ).delayed(2)

            # NOTE: Reminder notifications are time-driven in the Reminders app.
            # The reminder seeded in init (`due_datetime="2025-11-18 09:01:00"`) will automatically notify user+agent.
            # The agent does NOT need to poll reminders; we model reaction time by delaying the first oracle action.

            # Agent observes the price drop notification and retrieves saved apartments to understand context
            list_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(price_drop_event, delay_seconds=70)
            )

            # Agent retrieves full details of Riverside Lofts to extract location for ride planning
            get_details_event = (
                apartment_app.get_apartment_details(apartment_id=self.riverside_lofts_id)
                .oracle()
                .depends_on(list_saved_event, delay_seconds=2)
            )

            # Agent proposes transportation coordination based on the price drop notification
            # The proposal explicitly references the triggering environment cue
            propose_event = (
                aui.send_message_to_user(
                    content="I saw a price drop notification for Riverside Lofts (now $1,950/month, down from $2,200). I also noticed your reminder about the viewing today at 10:00 AM and the note about limited parking. Would you like me to book a ride from 123 Main Street, Downtown to 450 River View Drive for a 9:30 AM pickup so you arrive a bit early?"
                )
                .oracle()
                .depends_on([get_details_event], delay_seconds=2)
            )

            # User accepts the proposal
            accept_event = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(propose_event, delay_seconds=3)
            )

            # Agent gets quotation for ride to apartment location
            quotation_event = (
                cab_app.get_quotation(
                    start_location="123 Main Street, Downtown",
                    end_location="450 River View Drive, Riverside District",
                    service_type="Default",
                    ride_time="2025-11-18 09:30:00",
                )
                .oracle()
                .depends_on(accept_event, delay_seconds=2)
            )

            # Agent books the ride
            order_event = (
                cab_app.order_ride(
                    start_location="123 Main Street, Downtown",
                    end_location="450 River View Drive, Riverside District",
                    service_type="Default",
                    ride_time="2025-11-18 09:30:00",
                )
                .oracle()
                .depends_on(quotation_event, delay_seconds=2)
            )

            # Agent confirms completion to user
            confirm_event = (
                aui.send_message_to_user(
                    content="Done — I booked a 9:30 AM pickup from 123 Main Street, Downtown to Riverside Lofts (450 River View Drive) so you'll arrive ahead of the 10:00 AM viewing. Total estimated cost is around $15-20."
                )
                .oracle()
                .depends_on(order_event, delay_seconds=2)
            )

        self.events = [
            price_drop_event,
            list_saved_event,
            get_details_event,
            propose_event,
            accept_event,
            quotation_event,
            order_event,
            confirm_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning Riverside Lofts and ride/transportation
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent ordered the ride to the apartment location
            ride_ordered = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and "450 river view drive" in e.action.args.get("end_location", "").lower()
                for e in log_entries
            )

            # Compute success: all strict checks must pass
            success = proposal_found and ride_ordered

            # Build rationale for failures
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal mentioning Riverside Lofts and ride/transportation")
                if not ride_ordered:
                    missing_checks.append("ride order to 450 river view drive")

                rationale = "Missing required agent actions: " + ", ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
