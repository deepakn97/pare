"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("cart_order_discount_consolidation")
class CartOrderDiscountConsolidation(PASScenario):
    """Agent identifies discount savings opportunity by consolidating cart with pending orders.

    The user receives a shopping notification about a new 20% discount code ("BULK20") that applies to orders of 3 or more electronics items. The user currently has 2 electronics items in their cart ("Wireless Mouse - Black" and "USB-C Cable - White") and an existing pending order (#5431) containing 1 electronics item ("Laptop Stand - Silver") with status "processing" (not yet shipped). The agent must:
    1. Parse the discount notification to identify the code, threshold requirement, and applicable category
    2. List current cart contents and identify qualifying items
    3. Search order history for pending orders containing items in the same eligible category
    4. Recognize that canceling the pending order and re-adding its item to the cart would meet the 3-item threshold
    5. Propose canceling order #5431, adding the laptop stand back to the cart, and checking out with the discount code
    6. If accepted, cancel the order, add the item to cart, and checkout with BULK20

    This scenario exercises notification-triggered multi-app reasoning (shopping → shopping history), threshold-based optimization logic, order cancellation for re-consolidation, and proactive cost-saving coordination within a single app's ecosystem.

    ---.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for cart-order discount consolidation scenario.

        Baseline state:
        - Shopping catalog contains 3 electronics products (Wireless Mouse, USB-C Cable, Laptop Stand)
        - User's cart contains 2 items (mouse and cable)
        - User has 1 pending order (#5431) with laptop stand in "processing" status
        - Discount code "BULK20" (20% off) exists and applies to all 3 electronics items
        """
        from are.simulation.apps.shopping import CartItem, Order

        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create products and variants in shopping catalog
        # Product 1: Wireless Mouse - Black ($25.99)
        mouse_product_id = self.shopping.add_product("Wireless Mouse")
        mouse_item_id = self.shopping.add_item_to_product(
            product_id=mouse_product_id,
            price=25.99,
            options={"color": "Black"},
            available=True,
        )

        # Product 2: USB-C Cable - White ($12.50)
        cable_product_id = self.shopping.add_product("USB-C Cable")
        cable_item_id = self.shopping.add_item_to_product(
            product_id=cable_product_id,
            price=12.50,
            options={"color": "White"},
            available=True,
        )

        # Product 3: Laptop Stand - Silver ($45.00)
        stand_product_id = self.shopping.add_product("Laptop Stand")
        stand_item_id = self.shopping.add_item_to_product(
            product_id=stand_product_id,
            price=45.00,
            options={"color": "Silver"},
            available=True,
        )

        # Add discount code "BULK20" (20% off) to all three electronics items
        self.shopping.add_discount_code(mouse_item_id, {"BULK20": 20.0})
        self.shopping.add_discount_code(cable_item_id, {"BULK20": 20.0})
        self.shopping.add_discount_code(stand_item_id, {"BULK20": 20.0})

        # Add 2 items to cart (mouse and cable)
        self.shopping.add_to_cart(mouse_item_id, quantity=1)
        self.shopping.add_to_cart(cable_item_id, quantity=1)

        # Create existing pending order #5431 with laptop stand (processing status)
        # Order placed 2 days before scenario start_time
        # We construct the Order directly to avoid the add_order bug with CartItem name field
        order_date = self.start_time - (2 * 24 * 60 * 60)  # 2 days ago
        pending_order = Order(
            order_id="5431",
            order_status="processing",
            order_date=datetime.fromtimestamp(order_date, tz=UTC),
            order_total=45.00,
            order_items={
                stand_item_id: CartItem(
                    item_id=stand_item_id,
                    quantity=1,
                    price=45.00,
                    available=True,
                    options={"color": "Silver"},
                )
            },
        )
        self.shopping.orders["5431"] = pending_order

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Shopping app notifies about new BULK20 discount code
            # Requires 3+ electronics items for 20% off
            discount_notification = shopping_app.add_discount_code(
                item_id="dummy_item_for_notification", discount_code={"BULK20": 20.0}
            ).delayed(10)

            # Agent checks current cart contents to see what items are already there
            # Motivated by: discount notification mentions item count threshold, agent needs to verify current cart state
            check_cart = shopping_app.list_cart().oracle().depends_on(discount_notification, delay_seconds=2)

            # Agent checks discount code details to understand which items qualify
            # Motivated by: notification mentioned BULK20, agent needs to verify which items it applies to
            check_discount_info = (
                shopping_app.get_discount_code_info(discount_code="BULK20")
                .oracle()
                .depends_on(check_cart, delay_seconds=1)
            )

            # Agent lists orders to find any pending orders with eligible items
            # Motivated by: cart has only 2 items but discount requires 3+, agent checks if pending orders contain qualifying items
            list_orders = shopping_app.list_orders().oracle().depends_on(check_discount_info, delay_seconds=2)

            # Agent gets details of order #5431 to verify its status and contents
            # Motivated by: list_orders revealed order "5431" exists, agent needs details to confirm it's cancellable (status "processing") and contains eligible items
            get_order_details = (
                shopping_app.get_order_details(order_id="5431").oracle().depends_on(list_orders, delay_seconds=1)
            )

            # Agent proposes consolidation strategy to user
            # Motivated by: discovered cart has 2 items + order #5431 has 1 eligible item = 3 total, meets threshold
            proposal = (
                aui.send_message_to_user(
                    content="I noticed you received a BULK20 discount code (20% off) that applies to orders of 3+ electronics items. "
                    "You currently have 2 items in your cart (Wireless Mouse and USB-C Cable), and your pending order #5431 "
                    "contains a Laptop Stand that also qualifies. If we cancel order #5431, add the stand to your cart, and "
                    "checkout with BULK20, you'll save 20% on all 3 items. Would you like me to do this?"
                )
                .oracle()
                .depends_on(get_order_details, delay_seconds=3)
            )

            # User accepts the consolidation proposal
            acceptance = (
                aui.accept_proposal(
                    content="Yes, please consolidate and apply the discount. Also please help me checkout directly."
                )
                .oracle()
                .depends_on(proposal, delay_seconds=5)
            )

            # Agent cancels the pending order #5431
            # Motivated by: user accepted the proposal to cancel order #5431
            cancel_order = shopping_app.cancel_order(order_id="5431").oracle().depends_on(acceptance, delay_seconds=2)

            # Agent adds the laptop stand item back to the cart
            # Motivated by: order #5431 contained the laptop stand (revealed by get_order_details), need to re-add it to cart
            add_stand_to_cart = (
                shopping_app.add_to_cart(item_id=next(iter(self.shopping.orders["5431"].order_items)), quantity=1)
                .oracle()
                .depends_on(cancel_order, delay_seconds=1)
            )

            # Agent verifies cart now has 3 items before checkout
            # Motivated by: before applying discount code, verify cart consolidation worked correctly
            verify_cart = shopping_app.list_cart().oracle().depends_on(add_stand_to_cart, delay_seconds=1)

            # Agent checks out with BULK20 discount code
            # Motivated by: cart now has 3+ items (verified by verify_cart), can apply BULK20 discount
            checkout = shopping_app.checkout(discount_code="BULK20").oracle().depends_on(verify_cart, delay_seconds=2)

            # Agent confirms completion to user
            # Motivated by: checkout succeeded, inform user of savings achieved
            completion = (
                aui.send_message_to_user(
                    content="Done! I've consolidated your order and applied the BULK20 discount. You saved 20% on all 3 items."
                )
                .oracle()
                .depends_on(checkout, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            discount_notification,
            check_cart,
            check_discount_info,
            list_orders,
            get_order_details,
            proposal,
            acceptance,
            cancel_order,
            add_stand_to_cart,
            verify_cart,
            checkout,
            completion,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal to user about consolidation strategy
            # Must mention the discount opportunity and consolidation plan
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent checked cart contents
            # Must use list_cart to understand current cart state
            cart_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_cart"
                for e in log_entries
            )

            # STRICT Check 3: Agent checked order history
            # Must use list_orders or get_order_details to find pending orders
            order_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name in ["list_orders", "get_order_details"]
                for e in log_entries
            )

            # STRICT Check 4: Agent cancelled order #5431
            # Must cancel the pending order to consolidate items
            order_cancelled = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "cancel_order"
                and e.action.args.get("order_id") == "5431"
                for e in log_entries
            )

            # STRICT Check 5: Agent added item back to cart
            # Must re-add the laptop stand to cart after cancellation
            item_added_to_cart = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                for e in log_entries
            )

            # STRICT Check 6: Agent completed checkout with BULK20 discount
            # Must checkout with the discount code to achieve savings
            checkout_with_discount = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "BULK20"
                for e in log_entries
            )

            # All strict checks must pass for success
            success = (
                proposal_found
                and cart_check_found
                and order_check_found
                and order_cancelled
                and item_added_to_cart
                and checkout_with_discount
            )

            # Build rationale if validation fails
            if not success:
                missing = []
                if not proposal_found:
                    missing.append("agent proposal message")
                if not cart_check_found:
                    missing.append("cart contents check")
                if not order_check_found:
                    missing.append("order history check")
                if not order_cancelled:
                    missing.append("order #5431 cancellation")
                if not item_added_to_cart:
                    missing.append("item re-added to cart")
                if not checkout_with_discount:
                    missing.append("checkout with BULK20 discount")

                rationale = f"Missing required actions: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
