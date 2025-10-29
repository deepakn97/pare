from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp, RentAFlat
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("compare_apartment_rentals")
class CompareApartmentRentals(Scenario):
    """A scenario where the agent proactively proposes comparing housing listings across two apps.

    The agent helps the user compare available apartments between ApartmentListingApp and RentAFlat,
    identifies best matches within budget and preferences, and proposes to save one favorite listing
    after user approval.

    This scenario demonstrates:
    1. Cross-checking results from two apartment rental platforms
    2. Proactive proposal and user confirmation pattern
    3. Use of all available apps: AgentUserInterface, SystemApp, ApartmentListingApp, RentAFlat
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate the applications used in this scenario."""
        aui = AgentUserInterface()
        system = SystemApp(name="system_integration")
        listing_app = ApartmentListingApp()
        rentaflat = RentAFlat()

        # All apps must be initialized
        self.apps = [aui, system, listing_app, rentaflat]

    def build_events_flow(self) -> None:
        """Build the proactive comparison and confirmation flow between two housing apps."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        apt_listing = self.get_typed_app(ApartmentListingApp)
        rentaflat = self.get_typed_app(RentAFlat)

        with EventRegisterer.capture_mode():
            # Step 1: user asks about apartment options in a specific area
            user_message = aui.send_message_to_agent(
                content="I'm looking for a 2-bedroom apartment in downtown within $2500 monthly budget."
            ).depends_on(None, delay_seconds=1)

            # Step 2: agent checks current time to inform about market freshness
            current_time = system.get_current_time().depends_on(user_message, delay_seconds=1)

            # Step 3: agent searches listings using both apps
            listing_search = apt_listing.search_apartments(
                location="Downtown", number_of_bedrooms=2, max_price=2500
            ).depends_on(current_time, delay_seconds=1)

            rentaflat_search = rentaflat.search_apartments(
                location="Downtown", number_of_bedrooms=2, max_price=2500
            ).depends_on(listing_search, delay_seconds=1)

            # Step 4: proactive proposal — agent proposes summarizing and saving favorite
            proposal = aui.send_message_to_user(
                content=(
                    "I found several 2-bedroom options in Downtown under $2500 from both sources. "
                    "Would you like me to compare and save the top-rated one to your favorites?"
                )
            ).depends_on(rentaflat_search, delay_seconds=1)

            # Step 5: user approves the proposal
            user_approval = aui.send_message_to_agent(
                content="Yes, please compare and save the best apartment in my favorites."
            ).depends_on(proposal, delay_seconds=1)

            # Step 6: agent chooses a listing and saves it in ApartmentListingApp favorites (oracle action)
            save_in_listing = (
                apt_listing.save_apartment(apartment_id="apt_downtown_best_01")
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Step 7: also saves same or related item in RentAFlat to demonstrate cross-app state update
            save_in_rentaflat = (
                rentaflat.save_apartment(apartment_id="rf_downtown_best_01")
                .oracle()
                .depends_on(save_in_listing, delay_seconds=1)
            )

            # Step 8: wait event to simulate idle time until completion
            wait_system = system.wait_for_notification(timeout=5).depends_on(save_in_rentaflat, delay_seconds=1)

        self.events = [
            user_message,
            current_time,
            listing_search,
            rentaflat_search,
            proposal,
            user_approval,
            save_in_listing,
            save_in_rentaflat,
            wait_system,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the proactive pattern and cross-platform saving actions occurred."""
        try:
            events = env.event_log.list_view()

            # Check proactive message presence
            proposal_sent = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and event.action.function_name == "send_message_to_user"
                and "compare" in event.action.args.get("content", "").lower()
                for event in events
            )

            # Check that ApartmentListingApp save_apartment was triggered
            saved_listing = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "ApartmentListingApp"
                and event.action.function_name == "save_apartment"
                and event.action.args.get("apartment_id") == "apt_downtown_best_01"
                for event in events
            )

            # Check that RentAFlat save_apartment was triggered
            saved_rentaflat = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "RentAFlat"
                and event.action.function_name == "save_apartment"
                and event.action.args.get("apartment_id") == "rf_downtown_best_01"
                for event in events
            )

            # The agent should have fetched current time before suggesting
            time_checked = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "SystemApp"
                and event.action.function_name == "get_current_time"
                for event in events
            )

            return ScenarioValidationResult(
                success=(proposal_sent and saved_listing and saved_rentaflat and time_checked)
            )

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
