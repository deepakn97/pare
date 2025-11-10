from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("online_order_pickup_trip")
class OnlineOrderPickupTrip(Scenario):
    """Scenario: The user buys gifts online and the agent arranges a cab for pickup at the store.

    This scenario demonstrates:
    1. Multi-app coordination between shopping, system, cab, and user interface apps.
    2. Proactive interaction pattern: agent proposes to arrange a cab; user confirms; agent books the ride.
    3. Agent uses system time to align shopping checkout and cab scheduling workflows.
    4. Validation ensures both successful checkout and cab booking after user consent.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate applications for this e-commerce cab synergy test."""
        self.aui = AgentUserInterface()
        self.system = SystemApp(name="core_system")
        self.shopping = ShoppingApp()
        self.cab = CabApp()

        # prepopulate data using shopping tools
        self.shopping.list_all_products(offset=0, limit=5)
        self.shopping.search_product(product_name="gift", offset=0, limit=3)
        self.shopping.get_all_discount_codes()

        # List all initialized applications
        self.apps = [self.aui, self.system, self.shopping, self.cab]

    def build_events_flow(self) -> None:
        """Define the workflow events including proactive confirmation and checkout + cab sequence."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        shop = self.get_typed_app(ShoppingApp)
        cab = self.get_typed_app(CabApp)

        with EventRegisterer.capture_mode():
            # User initiates request for buying and collecting items
            user_msg = aui.send_message_to_agent(
                content="I want to order a few gift items and pick them up from the store myself today."
            ).depends_on(None, delay_seconds=1)

            # Agent fetches current system time for contextual planning
            time_fetch = system.get_current_time().depends_on(user_msg, delay_seconds=1)

            # Agent searches relevant products and adds to cart as oracle
            search = shop.search_product(product_name="gift basket", offset=0, limit=5).depends_on(
                time_fetch, delay_seconds=1
            )
            add_item = shop.add_to_cart(item_id="gift_basket_001", quantity=1).depends_on(search, delay_seconds=1)
            cart_view = shop.list_cart().depends_on(add_item, delay_seconds=1)

            # Retrieve discount code info before checkout
            disc_codes = shop.get_all_discount_codes().depends_on(cart_view, delay_seconds=1)
            discount_info = shop.get_discount_code_info(discount_code="HOLIDAY10").depends_on(
                disc_codes, delay_seconds=1
            )

            # Perform checkout (oracle event)
            checkout = shop.checkout(discount_code="HOLIDAY10").depends_on(discount_info, delay_seconds=1).oracle()

            # After checkout, agent proactively asks if user wants a cab arranged
            propose_cab = aui.send_message_to_user(
                content="Your order is confirmed. Would you like me to book a cab to pick you up from home to the store?"
            ).depends_on(checkout, delay_seconds=1)

            # User approves proactively with contextual intention
            user_confirmation = aui.send_message_to_agent(
                content="Yes please, book a comfortable ride from my apartment to the downtown store."
            ).depends_on(propose_cab, delay_seconds=1)

            # Agent queries possible rides, fetches quotation, and finally confirms booking (oracle)
            available_rides = cab.list_rides(
                start_location="User Apartment", end_location="Downtown Store", ride_time=None
            ).depends_on(user_confirmation, delay_seconds=1)

            quote = cab.get_quotation(
                start_location="User Apartment", end_location="Downtown Store", service_type="Premium", ride_time=None
            ).depends_on(available_rides, delay_seconds=1)

            # Book the ride as oracle action
            ride_order = (
                cab.order_ride(
                    start_location="User Apartment",
                    end_location="Downtown Store",
                    service_type="Premium",
                    ride_time=None,
                )
                .depends_on(quote, delay_seconds=1)
                .oracle()
            )

            # System waits until all notifications or final confirmation
            wait_step = system.wait_for_notification(timeout=5).depends_on(ride_order, delay_seconds=1)

        # Store all events for the scenario
        self.events = [
            user_msg,
            time_fetch,
            search,
            add_item,
            cart_view,
            disc_codes,
            discount_info,
            checkout,
            propose_cab,
            user_confirmation,
            available_rides,
            quote,
            ride_order,
            wait_step,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate success of both shopping checkout and cab order."""
        try:
            log = env.event_log.list_view()
            checkout_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ShoppingApp"
                and e.action.function_name == "checkout"
                for e in log
            )
            cab_booked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
                for e in log
            )
            proactive_pattern = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "book a cab" in e.action.args.get("content", "").lower()
                for e in log
            )
            user_consent = any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "yes please" in e.action.args.get("content", "").lower()
                for e in log
            )
            return ScenarioValidationResult(
                success=(checkout_done and cab_booked and proactive_pattern and user_consent)
            )
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
