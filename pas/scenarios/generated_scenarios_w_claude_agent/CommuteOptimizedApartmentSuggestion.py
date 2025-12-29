"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
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
    """Agent identifies apartment listing near frequent ride destinations and proposes viewing with commute cost analysis.

    The user has an extensive ride history showing regular trips between "Downtown Office Plaza" and home at "456 Elm Street" (15+ rides over the past month, averaging $18-22 per ride). A new apartment listing notification arrives advertising "City Center Lofts" (2BR, $2,100/month) located at "123 Commerce Street" — only 0.3 miles from Downtown Office Plaza. The agent must: 1) detect the new apartment listing notification, 2) retrieve full apartment details including exact address, 3) analyze ride history to identify frequent destinations and typical ride costs, 4) recognize geographic proximity between the apartment location (123 Commerce Street) and the frequent ride destination (Downtown Office Plaza), 5) infer potential commute cost savings (walking distance vs. $18-22 daily rides), 6) calculate monthly savings ($360-440/month saved on rides), 7) get a ride quotation for viewing the apartment from the current home location, 8) propose viewing the apartment with a data-driven pitch emphasizing the commute optimization opportunity, and 9) offer to book the viewing ride upon user acceptance.

    This scenario exercises ride history retrieval and analysis, geographic proximity reasoning across apps, cost-benefit calculation for location-based decisions, new listing detection, multi-record aggregation (ride history patterns), apartment search/detail retrieval, ride quotation for viewing logistics, and proactive financial optimization recommendations based on discovered behavioral patterns rather than explicit user requests..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.apartment = StatefulApartmentApp(name="Apartment")
        self.cab = StatefulCabApp(name="Cab")

        # Populate apartment app with existing listings
        # Add the key listing that will be featured in the notification
        # Location: "123 Commerce Street" (near Downtown Office Plaza)
        self.apartment.add_new_apartment(
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

        # Add a few other apartment listings for context
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

        # Populate cab app with extensive ride history
        # 15+ rides over the past month between "Downtown Office Plaza" and "456 Elm Street"
        # Prices averaging $18-22, distances around 10-12 km
        # Timestamps span the past 30 days from start_time, going backwards
        # start_time = 2025-11-18 09:00:00 UTC (timestamp: 1763488800.0 approximately)

        # For each ride: we need service_type, start_location, end_location, price, duration, time_stamp, distance_km
        # Rides span past 30 days, approximately every 2 days (morning and evening commutes)

        base_timestamp = self.start_time
        day_seconds = 24 * 60 * 60

        # Morning commutes: 456 Elm Street -> Downtown Office Plaza
        # Ride 1 (1 day ago, morning)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="Downtown Office Plaza",
            price=19.50,
            duration=18.0,  # minutes
            time_stamp=base_timestamp - 1 * day_seconds - 3600,
            distance_km=11.2,
        )

        # Evening commute: Downtown Office Plaza -> 456 Elm Street
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Office Plaza",
            end_location="456 Elm Street",
            price=20.25,
            duration=22.0,
            time_stamp=base_timestamp - 1 * day_seconds + 32400,
            distance_km=11.2,
        )

        # Ride 3 (3 days ago, morning)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="Downtown Office Plaza",
            price=18.75,
            duration=17.0,
            time_stamp=base_timestamp - 3 * day_seconds - 3600,
            distance_km=10.8,
        )

        # Ride 4 (3 days ago, evening)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Office Plaza",
            end_location="456 Elm Street",
            price=21.50,
            duration=25.0,
            time_stamp=base_timestamp - 3 * day_seconds + 36000,
            distance_km=10.8,
        )

        # Ride 5 (5 days ago, morning)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="Downtown Office Plaza",
            price=19.00,
            duration=19.0,
            time_stamp=base_timestamp - 5 * day_seconds - 3600,
            distance_km=11.0,
        )

        # Ride 6 (5 days ago, evening)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Office Plaza",
            end_location="456 Elm Street",
            price=20.00,
            duration=20.0,
            time_stamp=base_timestamp - 5 * day_seconds + 32400,
            distance_km=11.0,
        )

        # Ride 7 (8 days ago, morning)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="Downtown Office Plaza",
            price=18.25,
            duration=16.0,
            time_stamp=base_timestamp - 8 * day_seconds - 3600,
            distance_km=10.5,
        )

        # Ride 8 (8 days ago, evening)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Office Plaza",
            end_location="456 Elm Street",
            price=22.00,
            duration=24.0,
            time_stamp=base_timestamp - 8 * day_seconds + 36000,
            distance_km=10.5,
        )

        # Ride 9 (10 days ago, morning)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="Downtown Office Plaza",
            price=19.75,
            duration=19.0,
            time_stamp=base_timestamp - 10 * day_seconds - 3600,
            distance_km=11.3,
        )

        # Ride 10 (10 days ago, evening)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Office Plaza",
            end_location="456 Elm Street",
            price=20.50,
            duration=21.0,
            time_stamp=base_timestamp - 10 * day_seconds + 32400,
            distance_km=11.3,
        )

        # Ride 11 (13 days ago, morning)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="Downtown Office Plaza",
            price=18.50,
            duration=17.0,
            time_stamp=base_timestamp - 13 * day_seconds - 3600,
            distance_km=10.7,
        )

        # Ride 12 (13 days ago, evening)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Office Plaza",
            end_location="456 Elm Street",
            price=21.25,
            duration=23.0,
            time_stamp=base_timestamp - 13 * day_seconds + 36000,
            distance_km=10.7,
        )

        # Ride 13 (17 days ago, morning)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="Downtown Office Plaza",
            price=19.25,
            duration=18.0,
            time_stamp=base_timestamp - 17 * day_seconds - 3600,
            distance_km=11.1,
        )

        # Ride 14 (17 days ago, evening)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Office Plaza",
            end_location="456 Elm Street",
            price=20.75,
            duration=22.0,
            time_stamp=base_timestamp - 17 * day_seconds + 32400,
            distance_km=11.1,
        )

        # Ride 15 (21 days ago, morning)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="Downtown Office Plaza",
            price=18.00,
            duration=16.0,
            time_stamp=base_timestamp - 21 * day_seconds - 3600,
            distance_km=10.4,
        )

        # Ride 16 (21 days ago, evening)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Office Plaza",
            end_location="456 Elm Street",
            price=21.75,
            duration=24.0,
            time_stamp=base_timestamp - 21 * day_seconds + 36000,
            distance_km=10.4,
        )

        # Ride 17 (25 days ago, morning)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Elm Street",
            end_location="Downtown Office Plaza",
            price=19.50,
            duration=19.0,
            time_stamp=base_timestamp - 25 * day_seconds - 3600,
            distance_km=11.2,
        )

        # Ride 18 (28 days ago, evening)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Office Plaza",
            end_location="456 Elm Street",
            price=20.25,
            duration=21.0,
            time_stamp=base_timestamp - 28 * day_seconds + 32400,
            distance_km=11.2,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: New apartment listing notification arrives
            # This is the trigger - a new listing that matches user's saved search criteria
            new_listing_notification = apartment_app.add_new_apartment(
                name="Skyline Residences",
                location="125 Commerce Street",
                zip_code="12345",
                price=2200.0,
                number_of_bedrooms=2,
                number_of_bathrooms=1,
                square_footage=980,
                property_type="Apartment",
                furnished_status="Unfurnished",
                floor_level="Upper floors",
                pet_policy="No pets",
                lease_term="1 year",
                amenities=["Gym", "Parking"],
            ).delayed(5)

            # Oracle Event 1: Agent retrieves ride history to analyze commute patterns
            # Motivated by: the new apartment notification triggers analysis of location relevance
            get_ride_history_event = (
                cab_app.get_ride_history(offset=0, limit=20)
                .oracle()
                .depends_on(new_listing_notification, delay_seconds=3)
            )

            # Oracle Event 2: Agent searches for the key apartment listing (City Center Lofts at 123 Commerce Street)
            # Motivated by: the notification mentions Commerce Street; agent searches for nearby apartments
            search_apartments_event = (
                apartment_app.search_apartments(location="Commerce Street")
                .oracle()
                .depends_on(get_ride_history_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent gets quotation for viewing ride from current home to the apartment
            # Motivated by: agent identified City Center Lofts at 123 Commerce Street and needs to propose a viewing
            get_viewing_quotation_event = (
                cab_app.get_quotation(
                    start_location="456 Elm Street",
                    end_location="123 Commerce Street",
                    service_type="Default",
                )
                .oracle()
                .depends_on(search_apartments_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends proposal with commute optimization analysis
            # Motivated by: new listing notification at 125 Commerce Street, ride history shows frequent trips to Downtown Office Plaza,
            # and search revealed City Center Lofts at nearby 123 Commerce Street
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed a new apartment listing notification for Skyline Residences at 125 Commerce Street. While reviewing this, I found another excellent option nearby: City Center Lofts at 123 Commerce Street ($2,100/month, 2BR). Based on your ride history, you take frequent trips between your current home (456 Elm Street) and Downtown Office Plaza, averaging $18-22 per ride. The City Center Lofts apartment is only 0.3 miles from your frequent destination, which could save you approximately $360-440/month in commute costs. Would you like me to book a viewing ride to 123 Commerce Street to see this apartment?"
                )
                .oracle()
                .depends_on(get_viewing_quotation_event, delay_seconds=3)
            )

            # Oracle Event 5: User accepts the proposal
            user_acceptance_event = (
                aui.accept_proposal(
                    content="Yes, that sounds great! Please book the viewing ride and save that apartment to my favorites."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle Event 6: Agent gets apartment details for the City Center Lofts listing
            # Motivated by: user accepted; agent needs the apartment_id to save it
            get_apartment_details_event = (
                apartment_app.list_all_apartments().oracle().depends_on(user_acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent books the viewing ride
            # Motivated by: user explicitly requested ride booking in their acceptance message
            book_viewing_ride_event = (
                cab_app.order_ride(
                    start_location="456 Elm Street",
                    end_location="123 Commerce Street",
                    service_type="Default",
                )
                .oracle()
                .depends_on(get_apartment_details_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent sends completion message
            # Motivated by: all requested actions completed; summarize for user
            completion_message_event = (
                aui.send_message_to_user(
                    content="Done! I've booked a ride to 123 Commerce Street for your apartment viewing, and I've saved City Center Lofts to your favorites. The ride is confirmed and ready."
                )
                .oracle()
                .depends_on(book_viewing_ride_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            new_listing_notification,
            get_ride_history_event,
            search_apartments_event,
            get_viewing_quotation_event,
            proposal_event,
            user_acceptance_event,
            get_apartment_details_event,
            book_viewing_ride_event,
            completion_message_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent retrieved ride history to analyze commute patterns
            ride_history_retrieved = False
            for e in agent_events:
                if e.action.class_name == "StatefulCabApp" and e.action.function_name == "get_ride_history":
                    ride_history_retrieved = True
                    break

            # STRICT Check 2: Agent searched for apartments (equivalence: search_apartments OR list_all_apartments)
            apartment_search_performed = False
            for e in agent_events:
                if e.action.class_name == "StatefulApartmentApp" and e.action.function_name in [
                    "search_apartments",
                    "list_all_apartments",
                ]:
                    apartment_search_performed = True
                    break

            # STRICT Check 3: Agent obtained a ride quotation for viewing
            viewing_quotation_obtained = False
            for e in agent_events:
                if e.action.class_name == "StatefulCabApp" and e.action.function_name == "get_quotation":
                    # Verify it's for the correct destination (flexible on exact address format)
                    args = e.action.args if e.action.args else e.action.resolved_args
                    end_location = args.get("end_location", "")
                    if "commerce street" in end_location.lower() or "123" in end_location:
                        viewing_quotation_obtained = True
                        break

            # STRICT Check 4: Agent sent proposal to user mentioning commute optimization
            # (Flexible: any message to user that occurred after history/search/quotation checks is acceptable)
            proposal_sent = False
            for e in agent_events:
                if e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user":
                    proposal_sent = True
                    break

            # STRICT Check 5: Agent booked the viewing ride after user acceptance
            viewing_ride_booked = False
            for e in agent_events:
                if e.action.class_name == "StatefulCabApp" and e.action.function_name == "order_ride":
                    # Verify it's for the correct destination (flexible on exact address format)
                    args = e.action.args if e.action.args else e.action.resolved_args
                    end_location = args.get("end_location", "")
                    if "Commerce Street" in end_location or "123" in end_location:
                        viewing_ride_booked = True
                        break

            # Build validation result
            success = (
                ride_history_retrieved
                and apartment_search_performed
                and viewing_quotation_obtained
                and proposal_sent
                and viewing_ride_booked
            )

            if not success:
                # Build rationale string for debugging
                failures = []
                if not ride_history_retrieved:
                    failures.append("ride history not retrieved")
                if not apartment_search_performed:
                    failures.append("apartment search not performed")
                if not viewing_quotation_obtained:
                    failures.append("viewing quotation not obtained for Commerce Street location")
                if not proposal_sent:
                    failures.append("proposal message not sent to user")
                if not viewing_ride_booked:
                    failures.append("viewing ride not booked to Commerce Street location")

                rationale = f"Missing critical agent actions: {', '.join(failures)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
