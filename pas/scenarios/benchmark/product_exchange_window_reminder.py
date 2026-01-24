from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("product_exchange_window_reminder")
class ProductExchangeWindowReminder(PASScenario):
    """Agent coordinates product exchange based on a reminder and order history.

    The user receives a reminder notification for "Return window ends today for laptop order" scheduled for today at 9:00 AM. The user had previously purchased a "Professional Laptop 15-inch" two weeks ago and created this reminder to track the 14-day return deadline. Shortly after, the user receives a shopping app notification that a new model "Professional Laptop 15-inch Pro" with upgraded specs is now available at the same price. The agent must:
    1. Detect the return window reminder notification (time-driven; emitted automatically when the reminder is due)
    2. Search shopping order history using `list_orders()` and identify the laptop order by matching product name from the reminder title
    3. Retrieve full order details using `get_order_details(order_id)` to verify return eligibility and deadline
    4. Detect the new product availability notification and search for the upgraded laptop using `search_product()`
    5. Infer that exchanging the current laptop for the upgraded model within the return window is beneficial
    6. Propose canceling the original order via `cancel_order()` and purchasing the new upgraded laptop
    7. After user acceptance, execute the cancellation and add the new laptop to cart using `add_to_cart()`
    8. Search contacts via `search_contacts()` to verify shipping address matches current user details using `get_current_user_details()`
    9. Complete checkout with `checkout()` using any available discount code from the product notification

    This scenario exercises deadline-sensitive reasoning (return window urgency), cross-app temporal coordination (reminder → order history lookup → new product evaluation), opportunistic upgrade detection, multi-step transactional workflow (cancel + repurchase), and contact information verification for order fulfillment.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
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

        # Seed catalog via public APIs (avoid mutating internal dicts directly).
        original_product_id = self.shopping.add_product("Professional Laptop 15-inch")
        self.original_laptop_item_id = self.shopping.add_item_to_product(
            product_id=original_product_id,
            price=1299.99,
            options={"color": "Space Gray", "storage": "512GB", "ram": "16GB"},
            available=True,
        )

        upgraded_product_id = self.shopping.add_product("Professional Laptop 15-inch Pro")
        self.upgraded_laptop_item_id = self.shopping.add_item_to_product(
            product_id=upgraded_product_id,
            price=1299.99,
            options={"color": "Space Gray", "storage": "1TB", "ram": "32GB", "processor": "M3 Pro"},
            available=True,
        )

        # Add discount code for the upgraded laptop (also arrives later as an observable notification).
        self.shopping.add_discount_code(self.upgraded_laptop_item_id, {"UPGRADE2025": 10.0})

        # Create existing order from 2 weeks ago (14 days before start_time)
        # Order date: 2025-11-04 09:00:00 UTC
        order_date = datetime(2025, 11, 4, 9, 0, 0, tzinfo=UTC)
        self.shopping.add_order(
            order_id="order_laptop_20251104",
            order_status="delivered",
            order_date=order_date.timestamp(),
            order_total=1299.99,
            item_id=self.original_laptop_item_id,
            quantity=1,
        )

        # Initialize Reminder App
        self.reminder = StatefulReminderApp(name="Reminders")

        # Seed a time-driven reminder that will automatically notify the user+agent when due.
        # Following benchmark convention, we set it shortly after start_time so it fires once the runner advances time.
        self.reminder.add_reminder(
            title="Cancel order window ends today for laptop order",
            due_datetime="2025-11-18 09:01:00",
            description=(
                "Return/cancel window ends today for the Professional Laptop 15-inch (ordered 2025-11-04).\n"
                "Order ID: order_laptop_20251104\n\n"
                "If there's a newer model or a discount, check Shopping.\n"
                "Before ordering anything, double-check the shipping address in Contacts."
            ),
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.shopping, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # NOTE: Reminder notifications are time-driven in the Reminders app.
            # The reminder seeded in init (`due_datetime="2025-11-18 09:01:00"`) will automatically notify user+agent.
            # The agent does NOT need to poll reminders; we model reaction time by delaying the first oracle action.

            # Environment event 1: Shopping notification about upgraded laptop (5 seconds later)
            env_event_2 = shopping_app.add_product(name="Professional Laptop 15-inch Pro").delayed(5)

            # Environment event 2: Shopping notification that a discount code is available for the upgraded laptop
            # This provides an explicit cue for the agent to look up and apply the discount code.
            env_event_3 = shopping_app.add_discount_code(
                item_id=self.upgraded_laptop_item_id,
                discount_code={"UPGRADE2025": 10.0},
            ).delayed(10)

            # Agent oracle event: Agent lists orders to identify the laptop order mentioned in the reminder
            # Evidence: reminder description explicitly mentions "Order ID: order_laptop_20251104"
            oracle_event_2 = shopping_app.list_orders().oracle().delayed(70)

            # Agent oracle event: Agent retrieves detailed order info to verify return eligibility
            # Evidence: order_id was revealed in reminder description and confirmed via list_orders
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
            # Evidence: reminder notification fired (time-driven), agent checked order history (oracle_event_2/3),
            # found upgraded model (oracle_event_4), and verified discount (oracle_event_5).
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your laptop cancel window ends today. There's a new upgraded model (Professional Laptop 15-inch Pro) with 1TB storage and 32GB RAM available at the same price, plus a 10% discount code (UPGRADE2025). Would you like me to cancel your current order, purchase the upgraded model, and send you the updated order confirmation details?"
                )
                .oracle()
                .depends_on([oracle_event_3, oracle_event_5], delay_seconds=10)
            )

            # User accepts the proposal
            user_acceptance = aui.accept_proposal(content="Yes, please do that.").depends_on(
                [proposal_event], delay_seconds=30
            )

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
                shopping_app.add_to_cart(item_id=self.upgraded_laptop_item_id, quantity=1)
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
            env_event_2,
            env_event_3,
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

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
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

            # STRICT Check 2: Agent cancelled the original order
            cancel_order_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "cancel_order"
                and e.action.args.get("order_id") == "order_laptop_20251104"
                for e in log_entries
            )

            # STRICT Check 3: Agent added upgraded laptop to cart
            add_to_cart_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == self.upgraded_laptop_item_id
                for e in log_entries
            )

            # STRICT Check 4: Agent completed checkout with discount code
            checkout_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "UPGRADE2025"
                for e in log_entries
            )

            # All checks must pass for success
            success = proposal_found and cancel_order_found and add_to_cart_found and checkout_found

            # Generate rationale if any checks failed
            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("no proposal message to user found")
                if not cancel_order_found:
                    failed_checks.append("original order not cancelled")
                if not add_to_cart_found:
                    failed_checks.append("upgraded laptop not added to cart")
                if not checkout_found:
                    failed_checks.append("checkout with discount not completed")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
