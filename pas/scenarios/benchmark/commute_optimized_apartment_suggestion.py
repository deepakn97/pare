"""Scenario: Agent identifies apartments near frequent commute destination and proposes saving them."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.apartment import StatefulApartmentApp
from pas.apps.cab import StatefulCabApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("commute_optimized_apartment_suggestion")
class CommuteOptimizedApartmentSuggestion(PASScenario):
    """Agent identifies apartments near frequent commute destination and proposes saving them.

    The user has a ride history showing regular weekday commutes between home at "456 Elm Street" and
    their office at "129 Commerce Street", plus some weekend leisure trips. Two apartments exist on
    Commerce Street: "City Center Lofts" at 123 Commerce Street and "Skyview Apartments" at 124
    Commerce Street. A price drop notification arrives for Skyview Apartments (from $2,300 to $2,050).
    The agent must:
    1. Detect the price drop notification for Skyview Apartments
    2. Analyze ride history to identify frequent destinations (129 Commerce Street appears daily)
    3. Recognize that Skyview (124 Commerce Street) is on the same street as the office
    4. Search apartments and discover City Center Lofts at 123 Commerce Street is also on Commerce Street
    5. Propose saving BOTH Commerce Street apartments since they're near the user's workplace
    6. Save both apartments to favorites after user acceptance

    This scenario exercises ride history analysis, pattern recognition for frequent destinations,
    street-based proximity reasoning, apartment discovery, and proactive recommendations based on
    commute optimization.
    """

    start_time = datetime(2025, 11, 17, 9, 0, 0, tzinfo=UTC).timestamp()  # Monday morning
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You are looking for an apartment with a shorter commute to work.
Only accept proposals that suggest saving BOTH Commerce Street apartments (City Center Lofts and Skyview Apartments).
Reject proposals that only mention one apartment or don't include saving both to favorites."""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.apartment = StatefulApartmentApp(name="Apartment")
        self.cab = StatefulCabApp(name="Cab")

        # Populate apartment app with existing listings
        # City Center Lofts at 123 Commerce Street (near office at 129 Commerce Street)
        self.city_center_apt_id = self.apartment.add_new_apartment(
            name="City Center Lofts",
            location="123 Commerce Street",
            zip_code="12345",
            price=2100.0,
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=950,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "Parking", "In-unit laundry"],
        )

        # Skyview Apartments at 124 Commerce Street (also near office)
        self.skyview_apt_id = self.apartment.add_new_apartment(
            name="Skyview Apartments",
            location="124 Commerce Street",
            zip_code="12345",
            price=2300.0,  # Original price before discount
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=980,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "Parking"],
        )

        # Other apartments not on Commerce Street (for context)
        self.apartment.add_new_apartment(
            name="Riverside Towers",
            location="789 River Road",
            zip_code="12346",
            price=1850.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=750,
            property_type="Apartment",
            furnished_status="Furnished",
            floor_level="Ground floor",
            pet_policy="No pets",
            lease_term="6 months",
            amenities=["Pool", "Gym"],
        )

        self.apartment.add_new_apartment(
            name="Parkside Gardens",
            location="321 Park Avenue",
            zip_code="12347",
            price=2400.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Condo",
            furnished_status="Unfurnished",
            floor_level="Penthouse",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Parking", "Rooftop deck", "Concierge"],
        )

        # Populate cab app with one week of ride history
        # User's home: 456 Elm Street
        # User's office: 129 Commerce Street
        # Weekday commutes (Mon-Fri) + weekend leisure trips

        base_timestamp = self.start_time  # Monday morning
        day_seconds = 24 * 60 * 60
        commute_distance = 8.5  # Same distance for all office commutes

        # Previous week's rides (going backwards from Monday)
        # Sunday (1 day ago) - Museum trip
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="City Art Museum",
            price=12.50,
            duration=15.0,
            time_stamp=base_timestamp - 1 * day_seconds + 36000,  # Sunday 10am
            distance_km=5.2,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="City Art Museum",
            end_location="456 Elm Street",
            price=13.00,
            duration=16.0,
            time_stamp=base_timestamp - 1 * day_seconds + 50400,  # Sunday 2pm
            distance_km=5.2,
        )

        # Saturday (2 days ago) - Pub trip
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="The Blue Note Pub",
            price=15.00,
            duration=18.0,
            time_stamp=base_timestamp - 2 * day_seconds + 68400,  # Saturday 7pm
            distance_km=6.8,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="The Blue Note Pub",
            end_location="456 Elm Street",
            price=16.50,
            duration=20.0,
            time_stamp=base_timestamp - 2 * day_seconds + 79200,  # Saturday 10pm
            distance_km=6.8,
        )

        # Friday (3 days ago) - Office commute
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="129 Commerce Street",
            price=19.00,
            duration=20.0,
            time_stamp=base_timestamp - 3 * day_seconds + 28800,  # Friday 8am
            distance_km=commute_distance,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="129 Commerce Street",
            end_location="456 Elm Street",
            price=21.00,
            duration=25.0,
            time_stamp=base_timestamp - 3 * day_seconds + 64800,  # Friday 6pm
            distance_km=commute_distance,
        )

        # Thursday (4 days ago) - Office commute
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="129 Commerce Street",
            price=18.50,
            duration=19.0,
            time_stamp=base_timestamp - 4 * day_seconds + 28800,  # Thursday 8am
            distance_km=commute_distance,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="129 Commerce Street",
            end_location="456 Elm Street",
            price=20.50,
            duration=24.0,
            time_stamp=base_timestamp - 4 * day_seconds + 64800,  # Thursday 6pm
            distance_km=commute_distance,
        )

        # Wednesday (5 days ago) - Office commute
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="129 Commerce Street",
            price=19.50,
            duration=21.0,
            time_stamp=base_timestamp - 5 * day_seconds + 28800,  # Wednesday 8am
            distance_km=commute_distance,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="129 Commerce Street",
            end_location="456 Elm Street",
            price=20.00,
            duration=23.0,
            time_stamp=base_timestamp - 5 * day_seconds + 64800,  # Wednesday 6pm
            distance_km=commute_distance,
        )

        # Tuesday (6 days ago) - Office commute
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="129 Commerce Street",
            price=18.00,
            duration=18.0,
            time_stamp=base_timestamp - 6 * day_seconds + 28800,  # Tuesday 8am
            distance_km=commute_distance,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="129 Commerce Street",
            end_location="456 Elm Street",
            price=22.00,
            duration=26.0,
            time_stamp=base_timestamp - 6 * day_seconds + 64800,  # Tuesday 6pm
            distance_km=commute_distance,
        )

        # Monday (7 days ago) - Office commute
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="129 Commerce Street",
            price=19.00,
            duration=20.0,
            time_stamp=base_timestamp - 7 * day_seconds + 28800,  # Monday 8am
            distance_km=commute_distance,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="129 Commerce Street",
            end_location="456 Elm Street",
            price=20.50,
            duration=24.0,
            time_stamp=base_timestamp - 7 * day_seconds + 64800,  # Monday 6pm
            distance_km=commute_distance,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event: Skyview apartment price drop notification
            # Price reduced from $2,300 to $2,050/month
            price_drop_notification = apartment_app.update_apartment(
                apartment_id=self.skyview_apt_id,
                new_price=2050.0,
            ).delayed(5)

            # Oracle: Agent retrieves ride history to analyze commute patterns
            get_ride_history_event = (
                cab_app.get_ride_history(offset=0, limit=20)
                .oracle()
                .depends_on(price_drop_notification, delay_seconds=3)
            )

            # Oracle: Agent searches for apartments on Commerce Street
            search_apartments_event = (
                apartment_app.search_apartments(location="Commerce Street")
                .oracle()
                .depends_on(get_ride_history_event, delay_seconds=2)
            )

            # Oracle: Agent proposes saving BOTH Commerce Street apartments
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Skyview Apartments at 124 Commerce Street dropped in price from $2,300 to $2,050/month. Looking at your ride history, you commute daily to 129 Commerce Street for work. I found two apartments on the same street as your office: City Center Lofts at 123 Commerce Street ($2,100/month) and Skyview Apartments at 124 Commerce Street ($2,050/month). Would you like me to save both of these to your favorites since they're right near your workplace?"
                )
                .oracle()
                .depends_on(search_apartments_event, delay_seconds=3)
            )

            # Oracle: User accepts the proposal
            user_acceptance_event = (
                aui.accept_proposal(content="Yes, please save both apartments to my favorites.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle: Agent saves City Center Lofts to favorites
            save_city_center_event = (
                apartment_app.save_apartment(apartment_id=self.city_center_apt_id)
                .oracle()
                .depends_on(user_acceptance_event, delay_seconds=2)
            )

            # Oracle: Agent saves Skyview Apartments to favorites
            save_skyview_event = (
                apartment_app.save_apartment(apartment_id=self.skyview_apt_id)
                .oracle()
                .depends_on(save_city_center_event, delay_seconds=1)
            )

        self.events = [
            price_drop_notification,
            get_ride_history_event,
            search_apartments_event,
            proposal_event,
            user_acceptance_event,
            save_city_center_event,
            save_skyview_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent achieved the essential outcomes for this scenario.

        Essential outcomes (what we check):
        - Agent sent proposal to user about saving Commerce Street apartments
        - Agent saved City Center Lofts to favorites
        - Agent saved Skyview Apartments to favorites

        Not checked (intermediate steps the agent might do differently):
        - How agent analyzed ride history (get_ride_history, etc.)
        - How agent searched apartments (search_apartments, list_all_apartments, etc.)
        """
        try:
            log_entries = env.event_log.list_view()

            # CHECK 1: Agent sent proposal to user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # CHECK 2: Agent saved City Center Lofts (self.city_center_apt_id)
            saved_apartments = []
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and e.action.class_name == "StatefulApartmentApp"
                    and e.action.function_name == "save_apartment"
                ):
                    args = e.action.args if e.action.args else e.action.resolved_args
                    saved_apartments.append(args.get("apartment_id"))

            correct_apartments_saved = (
                self.city_center_apt_id in saved_apartments
                and self.skyview_apt_id in saved_apartments
                and len(saved_apartments) == 2
            )

            success = proposal_found and correct_apartments_saved

            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not send proposal to user")
                if not correct_apartments_saved:
                    failed_checks.append("agent did not save both apartments correctly")
                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
