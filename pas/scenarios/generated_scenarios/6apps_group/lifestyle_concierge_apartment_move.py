from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.cab import CabApp
from are.simulation.apps.city import CityApp
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("lifestyle_concierge_apartment_move")
class LifestyleConciergeApartmentMove(Scenario):
    """A comprehensive lifestyle planning scenario involving all apps.

    The agent helps the user to find a new apartment in a safe area, check its crime rate,
    buy home essentials, and arrange transportation to visit the shortlisted apartments.

    Includes proactive interaction: the agent proposes booking a cab, user approves, and then the ride is booked.
    """

    start_time: float | None = 0
    duration: float | None = 24

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all applications with initial conditions."""
        aui = AgentUserInterface()
        system = SystemApp(name="system-core")
        city = CityApp()
        listings = ApartmentListingApp()
        shopping = ShoppingApp()
        cab = CabApp()

        # Register all apps for later use
        self.apps = [aui, system, city, listings, shopping, cab]

    def build_events_flow(self) -> None:
        """Defines the event flow showing user interacting with the ecosystem of apps."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        city = self.get_typed_app(CityApp)
        listings = self.get_typed_app(ApartmentListingApp)
        shopping = self.get_typed_app(ShoppingApp)
        cab = self.get_typed_app(CabApp)

        with EventRegisterer.capture_mode():
            # Step 1: User asks assistant to help find a new apartment
            event0 = aui.send_message_to_agent(
                content="Hi! I'm looking for a 2-bedroom apartment around downtown with a low crime rate."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent searches available apartments
            search_apartments = (
                listings.search_apartments(location="Downtown", number_of_bedrooms=2, max_price=2000)
                .oracle()
                .depends_on(event0, delay_seconds=1)
            )

            # Step 3: Agent checks city crime rate for a candidate zip code
            get_crime = city.get_crime_rate(zip_code="94107").oracle().depends_on(search_apartments, delay_seconds=1)

            # Step 4: Agent saves the apartment to favorites
            save_apartment = (
                listings.save_apartment(apartment_id="apt_94107_A").oracle().depends_on(get_crime, delay_seconds=1)
            )

            # Step 5: Agent lists saved apartments for user summary
            list_favorites = listings.list_saved_apartments().oracle().depends_on(save_apartment, delay_seconds=1)

            # Step 6: Agent proposes booking a cab proactively
            proposal = aui.send_message_to_user(
                content="I found a nice 2-bedroom apartment with a good safety score near downtown. "
                "Would you like me to book a ride there tomorrow morning to visit it?"
            ).depends_on(list_favorites, delay_seconds=1)

            # Step 7: User approves the proposal
            approval = aui.send_message_to_agent(
                content="Yes, please book a premium ride to that apartment tomorrow at 10 AM."
            ).depends_on(proposal, delay_seconds=2)

            # Step 8: Agent checks the current time to set booking schedule
            now = system.get_current_time().oracle().depends_on(approval, delay_seconds=1)

            # Step 9: Agent books a cab ride using the CabApp
            book_ride = (
                cab.order_ride(
                    start_location="User Home, 123 Main St",
                    end_location="Downtown Apartment 94107",
                    service_type="Premium",
                    ride_time="2024-05-02 10:00:00",
                )
                .oracle()
                .depends_on(now, delay_seconds=1)
            )

            # Step 10: Agent looks for basic home items to buy before moving in
            search_items = (
                shopping.search_product(product_name="kitchen set").oracle().depends_on(book_ride, delay_seconds=2)
            )

            # Step 11: Agent adds found product to shopping cart
            add_to_cart = (
                shopping.add_to_cart(item_id="kit_001", quantity=1).oracle().depends_on(search_items, delay_seconds=1)
            )

            # Step 12: Agent retrieves available discount codes
            get_discounts = shopping.get_all_discount_codes().oracle().depends_on(add_to_cart, delay_seconds=1)

            # Step 13: Checkout the order applying a discount
            checkout = shopping.checkout(discount_code="HOME10").oracle().depends_on(get_discounts, delay_seconds=1)

            # Step 14: Agent confirms the sequence of actions done
            summary = aui.send_message_to_user(
                content=(
                    "I've booked the premium cab for your visit tomorrow, and your kitchen set has been ordered "
                    "with a 10% discount. The apartment in 94107 is now saved to favorites."
                )
            ).depends_on(checkout, delay_seconds=2)

            # Step 15: Agent waits for any follow-up user message
            idle_pause = system.wait_for_notification(timeout=5).depends_on(summary, delay_seconds=1)

        self.events = [
            event0,
            search_apartments,
            get_crime,
            save_apartment,
            list_favorites,
            proposal,
            approval,
            now,
            book_ride,
            search_items,
            add_to_cart,
            get_discounts,
            checkout,
            summary,
            idle_pause,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure all key actions were performed in the expected logical order."""
        try:
            log = env.event_log.list_view()
            # Confirm that ride was booked
            ride_confirmed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
                for e in log
            )

            # Confirm shopping checkout occurred with a discount
            discount_used = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "HOME10"
                for e in log
            )

            # Confirm apartment saved to favorites
            apt_saved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ApartmentListingApp"
                and e.action.function_name == "save_apartment"
                for e in log
            )

            # Confirm proactive proposal message was sent
            agent_proposed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "book a ride" in e.action.args.get("content", "").lower()
                for e in log
            )

            return ScenarioValidationResult(success=(ride_confirmed and discount_used and apt_saved and agent_proposed))
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
