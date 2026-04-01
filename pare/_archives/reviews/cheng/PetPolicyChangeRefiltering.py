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


@register_scenario("pet_policy_change_refiltering")
class PetPolicyChangeRefiltering(PASScenario):
    """Agent removes incompatible apartment and finds alternatives after detecting pet policy change while user is en route to acquire a pet.

    The user has saved "Parkside Apartments" (2BR, $1,800/month, pet-friendly) to their favorites and has an active cab ride to "Sunny Paws Animal Shelter" scheduled for pickup at 3:00 PM. A notification arrives from the apartment app indicating that Parkside Apartments has updated its pet policy from "pets allowed" to "no pets allowed" due to new building regulations. The agent must:
    1. Detect the pet policy change notification for the saved apartment
    2. Check current ride status and recognize the pet-related destination
    3. Infer urgency: user is actively acquiring a pet and needs pet-friendly housing
    4. Remove Parkside Apartments from saved list
    5. Search for alternative pet-friendly apartments with similar criteria (2BR, price range, same location)
    6. Present filtered alternatives to the user
    7. Optionally save promising alternatives to the favorites list

    This scenario exercises policy-change detection, cross-app context inference (cab destination implying housing requirement urgency), saved-item curation, multi-filter apartment search, and proactive re-planning based on changing constraints..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Populate apartment catalog with several listings
        # Parkside Apartments - the one that will have policy changed (initially pet-friendly)
        parkside_id = self.apartment.add_new_apartment(
            name="Parkside Apartments",
            location="Downtown",
            zip_code="90210",
            price=1800.0,
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=950,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Parking", "Gym", "Pool"],
        )
        # Save Parkside Apartments to favorites
        self.apartment.save_apartment(parkside_id)

        # Add other apartments to the catalog (will serve as alternatives)
        riverside_lofts_id = self.apartment.add_new_apartment(
            name="Riverside Lofts",
            location="Downtown",
            zip_code="90210",
            price=1900.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1000,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Parking", "Gym"],
        )
        self.riverside_lofts_id = riverside_lofts_id

        self.apartment.add_new_apartment(
            name="Greenview Apartments",
            location="Downtown",
            zip_code="90210",
            price=1750.0,
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=900,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Parking"],
        )

        self.apartment.add_new_apartment(
            name="City Heights",
            location="Downtown",
            zip_code="90210",
            price=2100.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Apartment",
            furnished_status="Semi-furnished",
            floor_level="Penthouse",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Parking", "Gym", "Pool", "Balcony"],
        )

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Book a ride to Sunny Paws Animal Shelter scheduled for 3:00 PM (15:00)
        ride_time_str = "2025-11-18 15:00:00"
        self.cab.order_ride(
            start_location="123 Main Street",
            end_location="Sunny Paws Animal Shelter",
            service_type="Default",
            ride_time=ride_time_str,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        # Get parkside_id BEFORE entering capture_mode
        saved_apts = apartment_app.list_saved_apartments()
        parkside_id = None
        for apt_id, apt in saved_apts.items():
            if apt.name == "Parkside Apartments":
                parkside_id = apt_id
                break

        with EventRegisterer.capture_mode():
            # Environment event 1: Cab status update - ride is delayed, showing the pet shelter destination
            env1 = cab_app.update_ride_status(
                status="DELAYED",
                message="Traffic delay on Route 101. ETA pushed back by 15 minutes. Pickup to Sunny Paws Animal Shelter.",
            )

            # Environment event 2: Delete the old Parkside Apartments listing (simulating policy change)
            env2 = apartment_app.delete_apartment(apartment_id=parkside_id).delayed(5)

            # Environment event 3: Re-add Parkside Apartments with "No pets" policy
            env3 = apartment_app.add_new_apartment(
                name="Parkside Apartments",
                location="Downtown",
                zip_code="90210",
                price=1800.0,
                number_of_bedrooms=2,
                number_of_bathrooms=1,
                square_footage=950,
                property_type="Apartment",
                furnished_status="Unfurnished",
                floor_level="Upper floors",
                pet_policy="No pets",
                lease_term="1 year",
                amenities=["Parking", "Gym", "Pool"],
            ).delayed(10)

            # Agent inference and observation: Agent sees cab delay notification with pet shelter destination
            # and apartment policy change notifications, infers user needs pet-friendly housing urgently

            # Oracle event 1: Agent checks current ride status to understand context
            oracle1 = cab_app.get_current_ride_status().oracle().depends_on([env1], delay_seconds=3)

            # Oracle event 2: Agent lists saved apartments to see what's affected
            oracle2 = apartment_app.list_saved_apartments().oracle().depends_on([env2], delay_seconds=2)

            # Oracle event 3: Agent searches for pet-friendly alternatives
            oracle3 = (
                apartment_app.search_apartments(
                    location="Downtown", number_of_bedrooms=2, max_price=2000.0, pet_policy="Pets allowed"
                )
                .oracle()
                .depends_on([oracle2], delay_seconds=3)
            )

            # Oracle event 4: Agent sends proposal to user about the situation
            proposal = (
                aui.send_message_to_user(
                    content="I noticed that Parkside Apartments in your saved list has changed its pet policy to 'No pets'. "
                    "Since you have a cab booked to Sunny Paws Animal Shelter, it seems you're planning to get a pet. "
                    "I found two pet-friendly alternatives in Downtown: Riverside Lofts (2BR, $1,900/month) and "
                    "Greenview Apartments (2BR, $1,750/month, cats only). Would you like me to remove Parkside "
                    "from your saved list and save these alternatives instead?"
                )
                .oracle()
                .depends_on([oracle3], delay_seconds=5)
            )

            # User event: User accepts the proposal
            user1 = (
                aui.accept_proposal(content="Yes, please remove Parkside and save Riverside Lofts to my favorites.")
                .oracle()
                .depends_on([proposal], delay_seconds=3)
            )

            # Oracle event 5: Agent removes the incompatible apartment from saved list
            # Note: We need to find the new Parkside ID after it was re-added
            oracle4 = apartment_app.list_all_apartments().oracle().depends_on([user1], delay_seconds=2)

            # Oracle event 6: Agent removes Parkside from saved (if still there from old listing)
            # This will fail gracefully if already removed, so we'll search and conditionally remove
            oracle5 = apartment_app.list_saved_apartments().oracle().depends_on([oracle4], delay_seconds=1)

            # Oracle event 7: Agent searches for Riverside Lofts to get its ID
            oracle6 = (
                apartment_app.search_apartments(name="Riverside Lofts").oracle().depends_on([oracle5], delay_seconds=2)
            )

            # Oracle event 8: Agent saves Riverside Lofts
            # Save is the actual commit action; we use the seeded id (which is also discoverable via the preceding search/list calls).
            oracle7 = (
                apartment_app.save_apartment(apartment_id=self.riverside_lofts_id)
                .oracle()
                .depends_on([oracle6], delay_seconds=1)
            )

        # Register ALL events
        self.events = [env1, env2, env3, oracle1, oracle2, oracle3, proposal, user1, oracle4, oracle5, oracle6, oracle7]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT type events (oracle events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent checked the current ride status
            # This demonstrates awareness of the cab context (pet shelter destination)
            ride_status_checked = False
            for e in agent_events:
                if e.action.class_name == "StatefulCabApp" and e.action.function_name == "get_current_ride_status":
                    ride_status_checked = True
                    break

            # STRICT Check 2: Agent listed saved apartments
            # This shows the agent identified which apartments are affected by policy changes
            saved_apts_checked = False
            for e in agent_events:
                if e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "list_saved_apartments":
                    saved_apts_checked = True
                    break

            # STRICT Check 3: Agent searched for pet-friendly alternatives
            # This is the core proactive action - finding replacements
            search_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "search_apartments":
                    # Check if the search included pet_policy filter
                    args = e.action.args
                    if args.get("pet_policy"):
                        search_found = True
                        break

            # STRICT Check 4: Agent sent proposal message to user
            # Must inform user about the situation and offer alternatives
            proposal_sent = False
            for e in agent_events:
                if e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user":
                    # We don't check exact content, just that a message was sent
                    # The message should be the initial proposal (not a follow-up confirmation)
                    proposal_sent = True
                    break

            # STRICT Check 5: Agent saved Riverside Lofts to favorites (commit action requested by user)
            saved_riverside = any(
                e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "save_apartment"
                and e.action.args.get("apartment_id") == self.riverside_lofts_id
                for e in agent_events
            )

            # Determine overall success
            success = ride_status_checked and saved_apts_checked and search_found and proposal_sent and saved_riverside

            # Build failure rationale if any strict checks failed
            if not success:
                missing_checks = []
                if not ride_status_checked:
                    missing_checks.append("agent did not check current ride status")
                if not saved_apts_checked:
                    missing_checks.append("agent did not list saved apartments")
                if not search_found:
                    missing_checks.append("agent did not search for pet-friendly alternatives")
                if not proposal_sent:
                    missing_checks.append("agent did not send proposal message to user")
                if not saved_riverside:
                    missing_checks.append("agent did not save Riverside Lofts to favorites")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
