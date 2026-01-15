"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.shopping import CartItem, Item, Order, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("product_exchange_window_reminder")
class ProductExchangeWindowReminder(PASScenario):
    """Agent coordinates product exchange based on calendar reminder and order history.

    The user receives a calendar notification for "Return window ends today for laptop order" scheduled for today at 9:00 AM. The user had previously purchased a "Professional Laptop 15-inch" two weeks ago and created this calendar reminder to track the 14-day return deadline. Shortly after, the user receives a shopping app notification that a new model "Professional Laptop 15-inch Pro" with upgraded specs is now available at the same price. The agent must:
    1. Detect the return window reminder from calendar and read the event details via `get_calendar_event()` or `read_today_calendar_events()`
    2. Search shopping order history using `list_orders()` and identify the laptop order by matching product name from calendar event title
    3. Retrieve full order details using `get_order_details(order_id)` to verify return eligibility and deadline
    4. Detect the new product availability notification and search for the upgraded laptop using `search_product()`
    5. Infer that exchanging the current laptop for the upgraded model within the return window is beneficial
    6. Propose canceling the original order via `cancel_order()` and purchasing the new upgraded laptop
    7. After user acceptance, execute the cancellation and add the new laptop to cart using `add_to_cart()`
    8. Search contacts via `search_contacts()` to verify shipping address matches current user details using `get_current_user_details()`
    9. Complete checkout with `checkout()` using any available discount code from the product notification

    This scenario exercises deadline-sensitive reasoning (return window urgency), cross-app temporal coordination (calendar reminder → order history lookup → new product evaluation), opportunistic upgrade detection, multi-step transactional workflow (cancel + repurchase), and contact information verification for order fulfillment.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts App
        self.contacts = StatefulContactsApp(name="Contacts")

        # Create user contact with shipping address
        user_contact = Contact(
            first_name="Alex",
            last_name="Chen",
            is_user=True,
            email="alex.chen@email.com",
            phone="+1-555-0123",
            address="123 Market Street, San Francisco, CA 94102",
        )
        self.contacts.add_contact(user_contact)

        # Initialize Shopping App
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create original laptop product that was purchased 2 weeks ago
        original_laptop = Product(name="Professional Laptop 15-inch", product_id="laptop_original_001")
        original_laptop_item = Item(
            item_id="laptop_item_original_001",
            price=1299.99,
            available=True,
            options={"color": "Space Gray", "storage": "512GB", "ram": "16GB"},
        )
        original_laptop.variants["laptop_item_original_001"] = original_laptop_item
        self.shopping.products["laptop_original_001"] = original_laptop

        # Create upgraded laptop product (new model)
        upgraded_laptop = Product(name="Professional Laptop 15-inch Pro", product_id="laptop_pro_002")
        upgraded_laptop_item = Item(
            item_id="laptop_item_pro_002",
            price=1299.99,
            available=True,
            options={"color": "Space Gray", "storage": "1TB", "ram": "32GB", "processor": "M3 Pro"},
        )
        upgraded_laptop.variants["laptop_item_pro_002"] = upgraded_laptop_item
        self.shopping.products["laptop_pro_002"] = upgraded_laptop

        # Add discount code for the new laptop (will arrive in notification)
        self.shopping.discount_codes["laptop_item_pro_002"] = {"UPGRADE2025": 10.0}

        # Create existing order from 2 weeks ago (14 days before start_time)
        # Order date: 2025-11-04 09:00:00 UTC
        order_date = datetime(2025, 11, 4, 9, 0, 0, tzinfo=UTC)
        laptop_cart_item = CartItem(
            item_id="laptop_item_original_001",
            quantity=1,
            price=1299.99,
            available=True,
            options={"color": "Space Gray", "storage": "512GB", "ram": "16GB"},
        )
        past_order = Order(
            order_id="order_laptop_20251104",
            order_status="delivered",
            order_date=order_date,
            order_total=1299.99,
            order_items={"laptop_item_original_001": laptop_cart_item},
        )
        self.shopping.orders["order_laptop_20251104"] = past_order

        # Initialize Calendar App
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Create calendar reminder for return window deadline (today at 9:00 AM)
        reminder_event = CalendarEvent(
            event_id="event_return_reminder_001",
            title="Return window ends today for laptop order",
            start_datetime=self.start_time,
            end_datetime=self.start_time + 3600,  # 1 hour duration
            tag="reminder",
            description="Last day to return Professional Laptop 15-inch ordered on 2025-11-04. Order ID: order_laptop_20251104",
            location=None,
            attendees=[],
        )
        self.calendar.set_calendar_event(reminder_event)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.shopping, self.calendar]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment event 1: Calendar reminder notification triggers at start_time
            env_event_1 = calendar_app.add_calendar_event_by_attendee(
                who_add="Alex Chen",
                title="Cancel order window ends today for laptop order",
                start_datetime="2025-11-18 09:00:00",
                end_datetime="2025-11-18 10:00:00",
                tag="reminder",
                description=(
                    "Last day to cancel/return Professional Laptop 15-inch ordered on 2025-11-04.\n"
                    "Order ID: order_laptop_20251104\n\n"
                    "If you still want a laptop but are considering an upgrade, check Shopping for any notifications "
                    "about a newer model and any discount codes.\n"
                    "Before placing a replacement order, confirm the shipping address in Contacts."
                ),
            )

            # Environment event 2: Shopping notification about upgraded laptop (5 seconds later)
            env_event_2 = shopping_app.add_product(name="Professional Laptop 15-inch Pro").delayed(5)

            # Environment event 3: Shopping notification that a discount code is available for the upgraded laptop
            # This provides an explicit cue for the agent to look up and apply the discount code.
            env_event_3 = shopping_app.add_discount_code(
                item_id="laptop_item_pro_002",
                discount_code={"UPGRADE2025": 10.0},
            ).delayed(10)

            # Agent oracle event: Agent retrieves calendar events to observe the return window reminder
            # Evidence: env_event_1 delivered a calendar notification that should trigger agent inspection
            oracle_event_1 = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 00:00:00", end_datetime="2025-11-18 23:59:59"
                )
                .oracle()
                .depends_on([env_event_1], delay_seconds=10)
            )

            # Agent oracle event: Agent lists orders to identify the laptop order mentioned in calendar event
            # Evidence: calendar event description explicitly mentions "Order ID: order_laptop_20251104"
            oracle_event_2 = shopping_app.list_orders().oracle().depends_on([oracle_event_1], delay_seconds=5)

            # Agent oracle event: Agent retrieves detailed order info to verify return eligibility
            # Evidence: order_id was revealed in calendar event description and confirmed via list_orders
            oracle_event_3 = (
                shopping_app.get_order_details(order_id="order_laptop_20251104")
                .oracle()
                .depends_on([oracle_event_2], delay_seconds=5)
            )

            # Agent oracle event: Agent searches for the upgraded laptop mentioned in the shopping notification
            # Evidence: env_event_2 delivered notification about "Professional Laptop 15-inch Pro"
            oracle_event_4 = (
                shopping_app.search_product(product_name="Professional Laptop 15-inch Pro")
                .oracle()
                .depends_on([env_event_2, env_event_3], delay_seconds=10)
            )

            # Agent oracle event: Agent retrieves discount code info for the upgraded laptop
            # Evidence: env_event_3 is a discount-code notification; agent looks up details before proposing/applying it.
            oracle_event_5 = (
                shopping_app.get_discount_code_info(discount_code="UPGRADE2025")
                .oracle()
                .depends_on([oracle_event_4, env_event_3], delay_seconds=5)
            )

            # Agent sends proposal to user about the exchange opportunity
            # Evidence: agent observed return window deadline (oracle_event_1), identified order (oracle_event_2/3), found upgraded model (oracle_event_4), and verified discount (oracle_event_5)
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your laptop cancel window ends today. There's a new upgraded model (Professional Laptop 15-inch Pro) with 1TB storage and 32GB RAM available at the same price, plus a 10% discount code (UPGRADE2025). Would you like me to cancel your current order and purchase the upgraded model?"
                )
                .oracle()
                .depends_on([oracle_event_5], delay_seconds=10)
            )

            # User accepts the proposal
            user_acceptance = aui.accept_proposal(
                content="Yes, please go ahead with the exchange and send the confirmation information to me with the detailed shipping address."
            ).depends_on([proposal_event], delay_seconds=30)

            # Agent oracle event: Agent cancels the original order
            # Evidence: user accepted the proposal to cancel and repurchase
            oracle_event_6 = (
                shopping_app.cancel_order(order_id="order_laptop_20251104")
                .oracle()
                .depends_on([user_acceptance], delay_seconds=5)
            )

            # Agent oracle event: Agent adds upgraded laptop to cart
            # Evidence: user accepted proposal and cancellation completed; item_id was revealed via search_product (oracle_event_4)
            oracle_event_7 = (
                shopping_app.add_to_cart(item_id="laptop_item_pro_002", quantity=1)
                .oracle()
                .depends_on([oracle_event_6], delay_seconds=5)
            )

            # Agent oracle event: Agent searches contacts to verify shipping address
            # Evidence: standard practice before checkout to confirm delivery information
            oracle_event_8 = (
                contacts_app.search_contacts(query="Alex Chen").oracle().depends_on([oracle_event_7], delay_seconds=5)
            )

            # Agent oracle event: Agent completes checkout with discount code
            # Evidence: discount code "UPGRADE2025" was verified in oracle_event_5
            oracle_event_9 = (
                shopping_app.checkout(discount_code="UPGRADE2025")
                .oracle()
                .depends_on([oracle_event_8], delay_seconds=5)
            )

            # Agent sends completion summary to user
            # Evidence: all steps completed successfully; agent can now summarize the exchange
            summary_event = (
                aui.send_message_to_user(
                    content="Exchange completed! Your original order has been cancelled and the upgraded laptop (Professional Laptop 15-inch Pro) has been ordered with the 10% discount. The new order will be shipped to your address at 123 Market Street, San Francisco, CA 94102."
                )
                .oracle()
                .depends_on([oracle_event_9], delay_seconds=10)
            )

        # Register ALL events
        self.events = [
            env_event_1,
            env_event_2,
            env_event_3,
            oracle_event_1,
            oracle_event_2,
            oracle_event_3,
            oracle_event_4,
            oracle_event_5,
            proposal_event,
            user_acceptance,
            oracle_event_6,
            oracle_event_7,
            oracle_event_8,
            oracle_event_9,
            summary_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal to user about exchange opportunity
            # Must mention both the return window deadline and the upgraded model
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent retrieved calendar events to observe return window reminder
            # Accepts either get_calendar_events_from_to or read_today_calendar_events
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name in ["get_calendar_events_from_to", "read_today_calendar_events"]
                for e in log_entries
            )

            # STRICT Check 3: Agent listed orders to find the laptop order
            orders_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_orders"
                for e in log_entries
            )

            # STRICT Check 4: Agent searched for the upgraded laptop product
            product_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
                for e in log_entries
            )

            # STRICT Check 5: Agent cancelled the original order
            cancel_order_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "cancel_order"
                and e.action.args.get("order_id") == "order_laptop_20251104"
                for e in log_entries
            )

            # STRICT Check 6: Agent added upgraded laptop to cart
            add_to_cart_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == "laptop_item_pro_002"
                for e in log_entries
            )

            # STRICT Check 7: Agent searched contacts to verify shipping address
            # Accepts either search_contacts or get_current_user_details
            contact_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name in ["search_contacts", "get_current_user_details"]
                for e in log_entries
            )

            # STRICT Check 8: Agent completed checkout with discount code
            checkout_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "UPGRADE2025"
                for e in log_entries
            )

            # All checks must pass for success
            success = (
                proposal_found
                and calendar_check_found
                and orders_check_found
                and product_search_found
                and cancel_order_found
                and add_to_cart_found
                and contact_check_found
                and checkout_found
            )

            # Generate rationale if any checks failed
            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("no proposal message to user found")
                if not calendar_check_found:
                    failed_checks.append("calendar events not retrieved")
                if not orders_check_found:
                    failed_checks.append("order history not checked")
                if not product_search_found:
                    failed_checks.append("upgraded product not searched")
                if not cancel_order_found:
                    failed_checks.append("original order not cancelled")
                if not add_to_cart_found:
                    failed_checks.append("upgraded laptop not added to cart")
                if not contact_check_found:
                    failed_checks.append("shipping address not verified")
                if not checkout_found:
                    failed_checks.append("checkout with discount not completed")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
