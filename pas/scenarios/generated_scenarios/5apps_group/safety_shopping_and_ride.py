from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.city import CityApp
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("safety_shopping_and_ride")
class SafetyShoppingAndRide(Scenario):
    """A lifestyle assistant scenario where the agent checks city safety, helps with shopping.

    The agent helps with shopping and books a safe ride to the pickup location.

    Demonstrates use of all available apps (AgentUserInterface, SystemApp, ShoppingApp, CityApp, CabApp)
    and includes a proactive agent proposal pattern.
    """

    start_time: float | None = 0
    duration: float | None = 45

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and prepare all apps with a coherent setup for the scenario."""
        aui = AgentUserInterface()
        system = SystemApp(name="system")
        shopping = ShoppingApp()
        cab = CabApp()
        city = CityApp()

        # The environment now holds all apps used in this scenario
        self.apps = [aui, system, shopping, cab, city]

    def build_events_flow(self) -> None:
        """Define the flow of events representing the user-agent interaction."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        shopping = self.get_typed_app(ShoppingApp)
        city = self.get_typed_app(CityApp)
        cab = self.get_typed_app(CabApp)

        with EventRegisterer.capture_mode():
            # User initiates a conversation about buying new running shoes and going to pick them up
            user_start = (
                aui.send_message_to_agent(
                    content=(
                        "Hi assistant, I need to buy new running shoes online and then pick them up at the store later today."
                    )
                )
                .depends_on(None, delay_seconds=1)
                .with_id("user_start")
            )

            # Agent checks current system time to plan the schedule
            agent_time_check = (
                system.get_current_time().oracle().depends_on(user_start, delay_seconds=1).with_id("check_time")
            )

            # Agent searches for the requested product
            agent_search_item = (
                shopping.search_product(product_name="running shoes", limit=3)
                .oracle()
                .depends_on(agent_time_check, delay_seconds=1)
                .with_id("search_shoes")
            )

            # Agent proposes action to the user: “Would you like me to add the top result to your cart?”
            proactive_proposal = (
                aui.send_message_to_user(
                    content=(
                        "I've found several running shoes that match your description. "
                        "Would you like me to add the first pair to your cart and apply the best discount code?"
                    )
                )
                .depends_on(agent_search_item, delay_seconds=1)
                .with_id("agent_offer")
            )

            # User confirms the proactive proposal
            user_confirms = (
                aui.send_message_to_agent(content="Yes, please add the best option with an available discount.")
                .depends_on(proactive_proposal, delay_seconds=1)
                .with_id("user_confirms")
            )

            # Agent retrieves available discounts
            agent_get_discounts = (
                shopping.get_all_discount_codes()
                .oracle()
                .depends_on(user_confirms, delay_seconds=1)
                .with_id("get_discounts")
            )

            # Agent adds product to cart and applies discount during checkout
            agent_add_to_cart = (
                shopping.add_to_cart(item_id="item_123", quantity=1)
                .oracle()
                .depends_on(agent_get_discounts, delay_seconds=1)
                .with_id("add_to_cart")
            )

            agent_checkout = (
                shopping.checkout(discount_code="SAVE10")
                .oracle()
                .depends_on(agent_add_to_cart, delay_seconds=1)
                .with_id("checkout_order")
            )

            # After order, the user wants to pick it up, so the agent evaluates safety of the store location
            user_pickup = (
                aui.send_message_to_agent(
                    content="I'll go pick up the shoes at the downtown store. Can you book me a cab?"
                )
                .depends_on(agent_checkout, delay_seconds=1)
                .with_id("pickup_request")
            )

            # Agent checks the crime rate for that ZIP to ensure safety
            agent_safety_check = (
                city.get_crime_rate(zip_code="90210")
                .oracle()
                .depends_on(user_pickup, delay_seconds=1)
                .with_id("check_crime")
            )

            # Agent proposes: "Would you like to proceed with booking a premium ride for safety?"
            proactive_ride_offer = (
                aui.send_message_to_user(
                    content=(
                        "The area around the downtown store has moderate safety levels today. "
                        "Shall I book a Premium ride to ensure a safe and comfortable trip?"
                    )
                )
                .depends_on(agent_safety_check, delay_seconds=1)
                .with_id("ride_offer")
            )

            # User approves the proactive suggestion
            user_approves_ride = (
                aui.send_message_to_agent(content="Yes, book the Premium ride now.")
                .depends_on(proactive_ride_offer, delay_seconds=1)
                .with_id("ride_confirmation")
            )

            # Agent orders the ride after user approval
            agent_booking = (
                cab.order_ride(
                    start_location="Home address", end_location="Downtown sports store", service_type="Premium"
                )
                .oracle()
                .depends_on(user_approves_ride, delay_seconds=1)
                .with_id("book_ride")
            )

            # Wait before validating the ongoing status (simulate ride processing)
            agent_wait = system.wait_for_notification(timeout=5).oracle().depends_on(agent_booking, delay_seconds=1)

            # Agent checks the ride status to confirm progress
            agent_status = (
                cab.get_current_ride_status().oracle().depends_on(agent_wait, delay_seconds=1).with_id("ride_status")
            )

        self.events = [
            user_start,
            agent_time_check,
            agent_search_item,
            proactive_proposal,
            user_confirms,
            agent_get_discounts,
            agent_add_to_cart,
            agent_checkout,
            user_pickup,
            agent_safety_check,
            proactive_ride_offer,
            user_approves_ride,
            agent_booking,
            agent_wait,
            agent_status,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Checks that all key steps were executed correctly."""
        try:
            events = env.event_log.list_view()

            # Check that the agent made both proactive proposals
            proactive_messages = [
                e
                for e in events
                if e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and (
                    "premium ride" in e.action.args.get("content", "").lower()
                    or "add the first pair" in e.action.args.get("content", "").lower()
                )
            ]
            has_proactive = len(proactive_messages) >= 2

            # Ensure checkout and booking actions occurred
            did_checkout = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ShoppingApp"
                and e.action.function_name == "checkout"
                for e in events
            )
            did_order_ride = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
                for e in events
            )

            return ScenarioValidationResult(success=(has_proactive and did_checkout and did_order_ride))
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
