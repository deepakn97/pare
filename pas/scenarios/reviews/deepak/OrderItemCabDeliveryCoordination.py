"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.shopping import CartItem, Order
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulEmailApp,
    StatefulShoppingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("order_item_cab_delivery_coordination")
class OrderItemCabDeliveryCoordination(PASScenario):
    """Agent coordinates urgent item retrieval by ordering a cab after shopping order becomes unavailable for delivery.

    The user has placed a shopping order for a gift item that was expected to be delivered to their home address. An email notification arrives from the shopping platform stating that the ordered item is no longer available for home delivery but can be picked up from a store location at "456 Market Street" today before 6:00 PM. The agent must: 1. Detect the delivery cancellation email and extract the pickup location and deadline. 2. Check the current time to determine urgency. 3. Propose ordering a cab to retrieve the item from the store. 4. List available cab services and calculate quotations for the route from the user's current location to the pickup address. 5. Order the appropriate cab ride when the user accepts. 6. Retrieve and confirm the ride details including estimated arrival time.

    This scenario exercises email monitoring for order status changes, cross-app coordination between shopping notifications and ride services, location extraction from unstructured text, time-sensitive decision making, and ride booking with quotation validation..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")
        # Seed a shopping order that was placed earlier (this will be referenced in the delivery cancellation email)
        product_id = self.shopping.add_product(name="Wireless Headphones")
        item_id = self.shopping.add_item_to_product(
            product_id=product_id,
            price=79.99,
            options={"color": "black", "size": "standard"},
            available=True,
        )
        # Create an order that was placed yesterday (seeded as baseline state)
        order_time = datetime(2025, 11, 17, 14, 30, 0, tzinfo=UTC)
        order_id = "order_20251117_wireless_headphones"
        self.shopping.orders[order_id] = Order(
            order_id=order_id,
            order_status="processed",
            order_date=order_time,
            order_total=79.99,
            order_items={
                item_id: CartItem(
                    item_id=item_id,
                    quantity=1,
                    price=79.99,
                    available=True,
                    options={"color": "black", "size": "standard"},
                )
            },
        )

        # Initialize email app with user email
        self.email = StatefulEmailApp(name="Emails")
        # No baseline emails needed - the delivery cancellation email will arrive as an environment event in Step 3

        # Initialize cab app with service configuration
        self.cab = StatefulCabApp(name="Cab")
        # No baseline cab history needed for this scenario

        # Set up user contact for address information
        user_contact = Contact(
            first_name="Alex",
            last_name="Johnson",
            is_user=True,
            email="user@meta.com",
            phone="+1-555-0100",
            address="123 Main Street, San Francisco, CA 94102",
        )
        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.email, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment event: Shopping platform sends delivery cancellation email
            # This email notifies the user that their order can no longer be delivered
            # and must be picked up from a store location before 6 PM today
            email_event = email_app.send_email_to_user_with_id(
                email_id="email_delivery_cancellation",
                sender="notifications@shopplatform.com",
                subject="Order #order_20251117_wireless_headphones - Delivery Update",
                content=(
                    "Dear Customer,\n\n"
                    "We regret to inform you that your order #order_20251117_wireless_headphones "
                    "(Wireless Headphones) is no longer available for home delivery due to a logistics issue.\n\n"
                    "However, your item is ready for pickup at our store location:\n"
                    "456 Market Street, San Francisco, CA 94103\n\n"
                    "Please collect your order today before 6:00 PM to avoid cancellation.\n\n"
                    "We apologize for any inconvenience.\n\n"
                    "Best regards,\n"
                    "ShopPlatform Team"
                ),
            ).delayed(10)

            # Oracle event: Agent checks order details to confirm which order is affected
            # Motivation: The email notification references order_20251117_wireless_headphones, so the agent retrieves details
            get_order_event = (
                shopping_app.get_order_details(order_id="order_20251117_wireless_headphones")
                .oracle()
                .depends_on([email_event], delay_seconds=2)
            )

            # Oracle event: Agent proposes ordering a cab to retrieve the item
            # Motivation: The email indicates pickup is needed from 456 Market Street before 6 PM today
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I noticed your Wireless Headphones order can no longer be delivered to your home. "
                        "The item needs to be picked up from 456 Market Street before 6:00 PM today. "
                        "Would you like me to order a cab to retrieve it for you?"
                    )
                )
                .oracle()
                .depends_on([get_order_event], delay_seconds=2)
            )

            # Oracle event: User accepts the agent's proposal
            # Motivation: User agrees to the cab booking proposal
            accept_event = (
                aui.accept_proposal(content="Yes, please book a cab for me to pick up the order.")
                .oracle()
                .depends_on([proposal_event], delay_seconds=5)
            )

            # Oracle event: Agent lists available cab services and gets quotations
            # Motivation: User accepted the proposal, so the agent needs to find available rides
            list_rides_event = (
                cab_app.list_rides(
                    start_location="123 Main Street, San Francisco, CA 94102",
                    end_location="456 Market Street, San Francisco, CA 94103",
                    ride_time=None,
                )
                .oracle()
                .depends_on([accept_event], delay_seconds=2)
            )

            # Oracle event: Agent orders a cab ride (Default service type)
            # Motivation: After listing rides, the agent selects the Default service option to book
            order_ride_event = (
                cab_app.order_ride(
                    start_location="123 Main Street, San Francisco, CA 94102",
                    end_location="456 Market Street, San Francisco, CA 94103",
                    service_type="Default",
                    ride_time=None,
                )
                .oracle()
                .depends_on([list_rides_event], delay_seconds=2)
            )

            # Oracle event: Agent retrieves the booked ride details
            # Motivation: After ordering the ride, the agent checks the status and details
            get_ride_status_event = (
                cab_app.get_current_ride_status().oracle().depends_on([order_ride_event], delay_seconds=1)
            )

            # Oracle event: Agent confirms booking to user
            # Motivation: After successfully booking the cab, the agent notifies the user with details
            confirm_event = (
                aui.send_message_to_user(
                    content=(
                        "I've booked a cab for you to pick up your Wireless Headphones from 456 Market Street. "
                        "The cab will arrive shortly. Please make sure to collect the item before 6:00 PM today."
                    )
                )
                .oracle()
                .depends_on([get_ride_status_event], delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            email_event,
            get_order_event,
            proposal_event,
            accept_event,
            list_rides_event,
            order_ride_event,
            get_ride_status_event,
            confirm_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT CHECK 1: Agent sent a proposal message referencing the order issue
            # The agent must detect the delivery cancellation and propose cab booking
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT CHECK 2: Agent checked order details from shopping app
            # This proves the agent correlated the email with the seeded order
            order_check_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                for e in agent_events
            )

            # STRICT CHECK 3: Agent listed available rides
            # This shows the agent explored ride options with correct locations
            list_rides_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "list_rides"
                for e in agent_events
            )

            # STRICT CHECK 4: Agent ordered a cab ride
            # This is the core action - booking transportation to retrieve the item
            order_ride_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                for e in agent_events
            )

            # Build rationale for any failures
            missing_checks = []
            if not proposal_found:
                missing_checks.append("agent proposal message mentioning pickup location and cab/ride")
            if not order_check_found:
                missing_checks.append("order details verification for order_20251117_wireless_headphones")
            if not list_rides_found:
                missing_checks.append("listing available rides to 456 Market Street")
            if not order_ride_found:
                missing_checks.append("cab booking to pickup location")

            success = proposal_found and order_check_found and list_rides_found and order_ride_found

            if not success:
                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
