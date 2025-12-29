"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.cab import Ride
from are.simulation.apps.contacts import Contact
from are.simulation.apps.shopping import CartItem, Item, Order, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulEmailApp,
    StatefulShoppingApp,
)
from pas.apps.contacts import StatefulContactsApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("cab_lost_item_recovery")
class CabLostItemRecovery(PASScenario):
    """Agent coordinates lost item recovery after detecting left-behind item notification from completed cab ride.

    The user has completed a cab ride from a shopping store pickup location back home, carrying a recently purchased item "Wireless Noise Cancelling Headphones". After the ride ends, a notification arrives from the cab service stating "You may have left an item in the vehicle. Please contact us if you need assistance recovering lost items." The agent must: 1. Detect the lost-item notification from the completed ride. 2. Retrieve recent ride history to identify the specific ride details (driver, vehicle, route). 3. Search recent shopping order history to identify what item was likely left behind based on the pickup location matching the ride's start location. 4. Compose and send an email to the cab company's lost-and-found service with ride details, item description from the shopping order, and user contact information. 5. Confirm to the user that the recovery request has been submitted.

    This scenario exercises cab notification monitoring, cross-app correlation between ride history and shopping order details, location-based inference to match orders with rides, automated lost-item reporting via email composition, and multi-source information synthesis for recovery coordination..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for cab lost item recovery scenario."""
        # Initialize all required apps
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")
        self.cab = StatefulCabApp(name="Cab")
        self.shopping = StatefulShoppingApp(name="Shopping")
        self.email = StatefulEmailApp(name="Emails")
        self.contacts = StatefulContactsApp(name="Contacts")

        # Populate contacts - User contact and cab company lost-and-found contact
        self.user_contact = Contact(
            first_name="John",
            last_name="Doe",
            contact_id="user-john-doe",
            phone="555-123-4567",
            email="user@example.com",
            is_user=True,
        )
        self.contacts.add_contact(self.user_contact)

        self.cab_lostandfound_contact = Contact(
            first_name="Lost and Found",
            last_name="Support",
            contact_id="cab-lostandfound",
            phone="555-CAB-LOST",
            email="lostandfound@cabservice.com",
        )
        self.contacts.add_contact(self.cab_lostandfound_contact)

        # Populate shopping - Headphones product and recent completed order for store pickup
        headphones_product = Product(
            name="Wireless Noise Cancelling Headphones",
            product_id="product-headphones-001",
        )
        headphones_item = Item(
            item_id="item-headphones-black",
            price=299.99,
            available=True,
            options={"color": "Black", "size": "One Size"},
        )
        headphones_product.variants["Black"] = headphones_item
        self.shopping.products[headphones_product.product_id] = headphones_product

        # Create completed order (pickup from store at "123 Tech Plaza")
        headphones_cart_item = CartItem(
            item_id=headphones_item.item_id,
            quantity=1,
            price=299.99,
            available=True,
            options={"color": "Black", "size": "One Size", "pickup_location": "123 Tech Plaza"},
        )

        completed_order = Order(
            order_id="order-headphones-pickup",
            order_status="completed",
            order_date=datetime(2025, 11, 18, 8, 30, 0, tzinfo=UTC),
            order_total=299.99,
            order_items={"item-headphones-black": headphones_cart_item},
        )
        self.shopping.orders[completed_order.order_id] = completed_order

        # Populate cab - Recent completed ride from store pickup location to home
        completed_ride = Ride(
            ride_id="ride-store-to-home-001",
            status="COMPLETED",
            service_type="Default",
            start_location="123 Tech Plaza",
            end_location="456 Home Avenue",
            price=18.50,
            duration=900.0,  # 15 minutes
            time_stamp=datetime(2025, 11, 18, 8, 45, 0, tzinfo=UTC).timestamp(),
            distance_km=12.5,
            delay=0.0,
        )
        self.cab.ride_history.append(completed_ride)
        self.completed_ride_id = completed_ride.ride_id

        # Register all apps in the scenario
        self.apps = [self.agent_ui, self.system_app, self.cab, self.shopping, self.email, self.contacts]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Cab service sends a lost-item notification after ride completion
            # This is the primary environment trigger - a status update message about a potentially lost item
            lost_item_notification = cab_app.update_ride_status(
                status="COMPLETED",
                message="You may have left a Wireless Noise Cancelling Headphones in the vehicle. Please contact us if you need assistance recovering lost items by emailing to lostandfound@cabservice.com.",
            ).delayed(30)

            # Oracle Event 1: Agent retrieves ride history to identify the specific ride details
            # Evidence: lost-item notification triggered above alerts agent to check ride history
            get_ride_history_event = (
                cab_app.get_ride_history(offset=0, limit=5).oracle().depends_on(lost_item_notification, delay_seconds=2)
            )

            # Oracle Event 2: Agent retrieves shopping order history to identify what was picked up
            # Evidence: ride history shows start_location "123 Tech Plaza" which suggests a shopping pickup
            list_orders_event = shopping_app.list_orders().oracle().depends_on(get_ride_history_event, delay_seconds=1)

            # Oracle Event 3: Agent gets specific order details to extract item description
            # Evidence: order list reveals order-headphones-pickup which needs detailed item info for the report
            get_order_details_event = (
                shopping_app.get_order_details(order_id="order-headphones-pickup")
                .oracle()
                .depends_on(list_orders_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent proposes to submit lost-item recovery request to cab company
            # Evidence: synthesized ride details + shopping order item description enables recovery coordination
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed a lost-item alert from your recent cab ride from 123 Tech Plaza to home. Based on your shopping order, you picked up Wireless Noise Cancelling Headphones at that location. Would you like me to contact the cab company's lost-and-found service to report this and request recovery?"
                )
                .oracle()
                .depends_on(get_order_details_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal to submit recovery request
            acceptance_event = (
                aui.accept_proposal(content="Yes, please contact them with all the details.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent composes and sends email to cab company lost-and-found
            # Evidence: user acceptance + prior tool outputs (ride ID, locations, item description) provide all needed info
            send_recovery_email_event = (
                email_app.send_email(
                    recipients=["lostandfound@cabservice.com"],
                    subject="Lost Item Report - Ride ride-store-to-home-001",
                    content="I am writing to report a lost item from a recent ride.\n\nRide Details:\n- Ride ID: ride-store-to-home-001\n- Date: November 18, 2025\n- Route: 123 Tech Plaza to 456 Home Avenue\n- Service Type: Default\n\nLost Item:\n- Item: Wireless Noise Cancelling Headphones\n- Color: Black\n- Description: Recently purchased from store at pickup location\n\nContact Information:\n- Name: John Doe\n- Phone: 555-123-4567\n- Email: user@example.com\n\nPlease contact me if the item is found. Thank you for your assistance.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent confirms to user that recovery request has been submitted
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've submitted a lost-item report to the cab company with your ride details and item description. They should contact you at 555-123-4567 or user@example.com if the headphones are found."
                )
                .oracle()
                .depends_on(send_recovery_email_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            lost_item_notification,
            get_ride_history_event,
            list_orders_event,
            get_order_details_event,
            proposal_event,
            acceptance_event,
            send_recovery_email_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: STRICT - Agent retrieved ride history to identify specific ride details
            # Expects: StatefulCabApp.get_ride_history() with appropriate offset/limit parameters
            ride_history_retrieved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_ride_history"
                for e in log_entries
            )

            # Check 2: STRICT - Agent retrieved shopping order history to correlate pickup location
            # Expects: StatefulShoppingApp.list_orders() was called
            shopping_orders_retrieved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_orders"
                for e in log_entries
            )

            # Check 3: STRICT - Agent retrieved specific order details to extract item description
            # Expects: StatefulShoppingApp.get_order_details() with order_id matching the headphones order
            order_details_retrieved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                and e.action.args.get("order_id") == "order-headphones-pickup"
                for e in log_entries
            )

            # Check 4: STRICT - Agent sent proposal to user about lost-item recovery
            # Expects: PASAgentUserInterface.send_message_to_user() mentioning key parties/items
            # FLEXIBLE: exact wording can vary, but must reference cab/ride and headphones/item
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 5: STRICT - Agent sent email to cab company lost-and-found service
            # Expects: StatefulEmailApp.send_email() with recipient lostandfound@cabservice.com
            # STRICT on: recipient email, presence of ride ID, presence of item reference
            # FLEXIBLE on: exact subject/content wording (as long as structural elements are present)
            lost_item_email_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "lostandfound@cabservice.com" in e.action.args.get("recipients", [])
                for e in log_entries
            )

            # Evaluate success: all strict checks must pass
            success = (
                ride_history_retrieved
                and shopping_orders_retrieved
                and order_details_retrieved
                and proposal_found
                and lost_item_email_sent
            )

            # Build rationale for failures
            if not success:
                missing = []
                if not ride_history_retrieved:
                    missing.append("ride history retrieval")
                if not shopping_orders_retrieved:
                    missing.append("shopping orders retrieval")
                if not order_details_retrieved:
                    missing.append("order details retrieval for headphones order")
                if not proposal_found:
                    missing.append("proposal to user mentioning lost item and ride details")
                if not lost_item_email_sent:
                    missing.append("email to cab company lost-and-found with ride ID and item description")

                rationale = f"Missing required agent actions: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
