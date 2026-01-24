from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.apartment import StatefulApartmentApp
from pas.apps.cab import StatefulCabApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("apartment_comparison_transport_cost_factor")
class ApartmentComparisonTransportCostFactor(PASScenario):
    """Agent incorporates daily commute costs into apartment affordability comparison when user reviews saved options.

    The user has three apartments saved to favorites: "Downtown Lofts" at 101 Main Street ($2,200/month), "Suburban Gardens" at 555 Green Lane ($1,600/month), and "Midtown Plaza" at 888 Center Avenue ($1,900/month). The user receives a notification from the apartment app reminding them that their current lease expires in 30 days and prompting a decision. The user's ride history shows consistent weekday morning rides from their current address (123 Oak Street) to their workplace (777 Corporate Blvd) at 8:00 AM, costing approximately $18-22 per trip. The agent must: 1) detect the lease expiration reminder notification, 2) retrieve all saved apartment details, 3) analyze ride history to identify the recurring commute pattern and average cost, 4) get ride quotations from each saved apartment location to the workplace (777 Corporate Blvd) at 8:00 AM, 5) calculate total monthly housing cost (rent + 20 commute rides/month) for each option, 6) present a comparison showing that Midtown Plaza ($1,900 + $200 commute = $2,100 total) is more affordable than Downtown Lofts ($2,200 + $150 = $2,350) despite Suburban Gardens having lowest rent ($1,600 + $500 = $2,100), and 7) recommend Midtown Plaza or Suburban Gardens based on total cost-of-living analysis.

    This scenario exercises lease timeline tracking via apartment notifications, ride history pattern recognition for commute identification, batch quotation requests across multiple origin points to a fixed destination, total-cost-of-ownership calculations that combine rent and transportation, multi-option comparison tables with derived metrics, and decision support that challenges rent-only thinking by incorporating transportation economics.

    ---.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Add three apartments to the catalog and save them to favorites
        # Downtown Lofts - closest to work, highest rent
        downtown_id = self.apartment.add_new_apartment(
            name="Downtown Lofts",
            location="101 Main Street",
            zip_code="90001",
            price=2200.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=750,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Gym", "Parking", "Pool"],
        )
        self.apartment.save_apartment(downtown_id)

        # Suburban Gardens - furthest from work, lowest rent
        suburban_id = self.apartment.add_new_apartment(
            name="Suburban Gardens",
            location="555 Green Lane",
            zip_code="90002",
            price=1600.0,
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=950,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Parking", "Garden"],
        )
        self.apartment.save_apartment(suburban_id)

        # Midtown Plaza - moderate distance, moderate rent
        midtown_id = self.apartment.add_new_apartment(
            name="Midtown Plaza",
            location="888 Center Avenue",
            zip_code="90003",
            price=1900.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=800,
            property_type="Apartment",
            furnished_status="Semi-furnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "Parking"],
        )
        self.apartment.save_apartment(midtown_id)
        self.midtown_id = midtown_id

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Seed ride history with consistent weekday morning commutes from current address to workplace
        # User's current address: 123 Oak Street
        # Workplace: 777 Corporate Blvd
        # Pattern: weekday mornings around 8:00 AM, costing $18-22

        # Calculate timestamps for past weekday rides (going back 2 weeks, Mon-Fri)
        # start_time is 2025-11-18 09:00:00 UTC (Tuesday)
        base_ts = self.start_time

        # Add rides from the past 10 weekdays (2 weeks)
        # Going backwards: Mon Nov 17, Fri Nov 14, Thu Nov 13, Wed Nov 12, Tue Nov 11,
        #                  Mon Nov 10, Fri Nov 7, Thu Nov 6, Wed Nov 5, Tue Nov 4
        past_ride_days = [
            -1,  # Mon Nov 17 (1 day ago)
            -4,  # Fri Nov 14 (4 days ago)
            -5,  # Thu Nov 13
            -6,  # Wed Nov 12
            -7,  # Tue Nov 11
            -8,  # Mon Nov 10
            -11,  # Fri Nov 7
            -12,  # Thu Nov 6
            -13,  # Wed Nov 5
            -14,  # Tue Nov 4
        ]

        prices = [18.5, 19.2, 21.0, 20.5, 18.0, 19.8, 22.0, 20.0, 18.5, 19.5]

        for day_offset, price in zip(past_ride_days, prices, strict=False):
            ride_timestamp = base_ts + (day_offset * 86400) - 3600  # 8:00 AM each day
            self.cab.add_new_ride(
                service_type="Default",
                start_location="123 Oak Street",
                end_location="777 Corporate Blvd",
                price=price,
                duration=20.0 * 60,  # 20 minutes in seconds
                time_stamp=ride_timestamp,
                distance_km=12.0,
            )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment event: New competitive apartment listing appears in the market
            # This prompts the agent to review and compare all saved apartments with commute costs
            new_listing_event = apartment_app.add_new_apartment(
                name="Riverside View",
                location="200 River Road",
                zip_code="90004",
                price=2100.0,
                number_of_bedrooms=1,
                number_of_bathrooms=1,
                square_footage=850,
                property_type="Apartment",
                furnished_status="Unfurnished",
                floor_level="Upper floors",
                pet_policy="No pets",
                lease_term="1 year",
                amenities=["Pool", "Gym"],
            ).delayed(5)

            # Agent detects the new listing notification and retrieves all saved apartments to compare
            list_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(new_listing_event, delay_seconds=2)
            )

            # Agent informs the user about the new listing + saved apartments, and asks whether to run a commute-cost comparison.
            # (No commute/workplace specifics yet; user has not requested the deeper analysis.)
            notify_event = (
                aui.send_message_to_user(
                    content="I saw a new apartment listing (Riverside View, $2,100/month). You currently have 3 apartments saved. Do you want me to compare your saved options (and this new one) using your recommended way?"
                )
                .oracle()
                .depends_on(list_saved_event, delay_seconds=2)
            )

            # User accepts the proposal to compare apartments with commute costs
            user_request_compare_event = (
                aui.accept_proposal(content="Yes, please compare them using commute costs.")
                .oracle()
                .depends_on(notify_event, delay_seconds=2)
            )

            # Agent analyzes ride history to identify the commute pattern (user's consistent workplace commute)
            get_ride_history_event = (
                cab_app.get_ride_history(offset=0, limit=10)
                .oracle()
                .depends_on(user_request_compare_event, delay_seconds=2)
            )

            # Agent gets quotations from each saved apartment location to the workplace (identified from ride history as 777 Corporate Blvd)
            # Downtown Lofts (101 Main Street) to workplace
            quote_downtown_event = (
                cab_app.get_quotation(
                    start_location="101 Main Street",
                    end_location="777 Corporate Blvd",
                    service_type="Default",
                    ride_time=None,
                )
                .oracle()
                .depends_on(get_ride_history_event, delay_seconds=2)
            )

            # Suburban Gardens (555 Green Lane) to workplace
            quote_suburban_event = (
                cab_app.get_quotation(
                    start_location="555 Green Lane",
                    end_location="777 Corporate Blvd",
                    service_type="Default",
                    ride_time=None,
                )
                .oracle()
                .depends_on(quote_downtown_event, delay_seconds=2)
            )

            # Midtown Plaza (888 Center Avenue) to workplace
            quote_midtown_event = (
                cab_app.get_quotation(
                    start_location="888 Center Avenue",
                    end_location="777 Corporate Blvd",
                    service_type="Default",
                    ride_time=None,
                )
                .oracle()
                .depends_on(quote_suburban_event, delay_seconds=2)
            )

            # Agent sends comprehensive cost comparison proposal after running the requested cab analyses.
            comparison_event = (
                aui.send_message_to_user(
                    content="I saw the new apartment listing (Riverside View, $2,100/month) and compared it with your saved options, factoring in commute costs to 777 Corporate Blvd:\n\n"
                    "- Downtown Lofts: $2,200 rent + ~$150 commute (20 rides/month) = $2,350 total\n"
                    "- Midtown Plaza: $1,900 rent + ~$200 commute = $2,100 total\n"
                    "- Suburban Gardens: $1,600 rent + ~$500 commute = $2,100 total\n"
                    "- Riverside View: $2,100 rent + ~$250 commute = $2,350 total\n\n"
                    "Midtown Plaza and Suburban Gardens tie for best value. Midtown has better amenities and location. Would you like me to save the Midtown Plaza apartment as well?"
                )
                .oracle()
                .depends_on(quote_midtown_event, delay_seconds=3)
            )

            # User accepts the analysis and selects Midtown Plaza
            accept_event = (
                aui.accept_proposal(content="Great analysis! Let's save the Midtown Plaza apartment as well.")
                .oracle()
                .depends_on(comparison_event, delay_seconds=2)
            )

            save_midtown_event = (
                apartment_app.save_apartment(apartment_id=self.midtown_id)
                .oracle()
                .depends_on(accept_event, delay_seconds=1)
            )

        self.events = [
            new_listing_event,
            list_saved_event,
            notify_event,
            user_request_compare_event,
            get_ride_history_event,
            quote_downtown_event,
            quote_suburban_event,
            quote_midtown_event,
            comparison_event,
            accept_event,
            save_midtown_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1 (STRICT): Agent sent proposal to user with cost comparison
            # Content flexibility: require "commute" or "total" mentioned, not exact wording
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and (
                    "commute" in e.action.args.get("content", "").lower()
                    or "total" in e.action.args.get("content", "").lower()
                )
                for e in log_entries
            )

            # Check 2 (STRICT): Agent saved the selected apartment after user acceptance
            save_apartment_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "save_apartment"
                and e.action.args.get("apartment_id") == self.midtown_id
                for e in log_entries
            )

            # Compute success: all strict checks must pass
            strict_checks = proposal_found and save_apartment_found

            success = strict_checks

            # Build rationale for failures
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal to user with cost comparison not found")
                if not save_apartment_found:
                    missing_checks.append("agent did not save Midtown Plaza apartment")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
