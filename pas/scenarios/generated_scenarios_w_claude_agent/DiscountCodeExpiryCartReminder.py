"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.shopping import CartItem, Item, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("discount_code_expiry_cart_reminder")
class DiscountCodeExpiryCartReminder(PASScenario):
    """Agent proactively reminds user to complete checkout before discount code expires based on shopping cart contents and timing.

    The user receives a shopping notification about a time-sensitive discount code "HOLIDAY30" that provides 30% off on electronics and expires in 24 hours. The user has previously added a "Wireless Keyboard" and "USB-C Hub" to their shopping cart but has not yet checked out. The agent must:
    1. Detect the incoming discount notification with expiry timing
    2. Check the current shopping cart contents
    3. Verify that the discount code applies to items in the cart (using `get_discount_code_info()`)
    4. Calculate time remaining until expiry
    5. Proactively remind the user about the pending cart and expiring discount
    6. Offer to complete the checkout with the discount code

    This scenario exercises discount code verification, cart state monitoring, time-sensitive coordination (shopping notification → cart analysis), expiry calculation, and proactive purchase completion assistance..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize shopping app with baseline products and cart
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create product: Wireless Keyboard
        keyboard_product_id = "prod_keyboard_001"
        keyboard_product = Product(
            name="Wireless Keyboard - Mechanical RGB",
            product_id=keyboard_product_id,
        )
        keyboard_item_id = "item_keyboard_001"
        keyboard_product.variants[keyboard_item_id] = Item(
            item_id=keyboard_item_id,
            price=89.99,
            available=True,
            options={"color": "black", "switch_type": "blue"},
        )
        self.shopping.products[keyboard_product_id] = keyboard_product

        # Create product: USB-C Hub
        hub_product_id = "prod_hub_001"
        hub_product = Product(
            name="USB-C Hub 7-in-1",
            product_id=hub_product_id,
        )
        hub_item_id = "item_hub_001"
        hub_product.variants[hub_item_id] = Item(
            item_id=hub_item_id,
            price=45.99,
            available=True,
            options={"ports": "7", "power_delivery": "100W"},
        )
        self.shopping.products[hub_product_id] = hub_product

        # Add both items to cart (user has already added these)
        self.shopping.cart[keyboard_item_id] = CartItem(
            item_id=keyboard_item_id,
            price=89.99,
            quantity=1,
            available=True,
            options={"color": "black", "switch_type": "blue"},
        )
        self.shopping.cart[hub_item_id] = CartItem(
            item_id=hub_item_id,
            price=45.99,
            quantity=1,
            available=True,
            options={"ports": "7", "power_delivery": "100W"},
        )

        # Register discount code "HOLIDAY30" (30% off) for both electronics items
        # This discount exists but user doesn't know about it yet (notification will arrive)
        self.shopping.discount_codes[keyboard_item_id] = {"HOLIDAY30": 30.0}
        self.shopping.discount_codes[hub_item_id] = {"HOLIDAY30": 30.0}

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Event 1: Environment event - discount code notification arrives (non-oracle)
            # This represents the exogenous trigger from the shopping platform
            discount_notification_event = shopping_app.add_discount_code(
                item_id="item_keyboard_001", discount_code={"HOLIDAY30": 30.0}
            ).delayed(10)

            # Event 2: Agent checks discount code info to see which items it applies to (oracle)
            check_discount_event = (
                shopping_app.get_discount_code_info(discount_code="HOLIDAY30")
                .oracle()
                .depends_on(discount_notification_event, delay_seconds=2)
            )

            # Event 3: Agent checks cart contents to verify discount applicability (oracle)
            check_cart_event = shopping_app.list_cart().oracle().depends_on(check_discount_event, delay_seconds=1)

            # Event 4: Agent sends proposal to user about discount and cart (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you have items in your cart (Wireless Keyboard and USB-C Hub) and a 30% discount code 'HOLIDAY30' is available for them. Would you like me to complete the checkout with this discount code?"
                )
                .oracle()
                .depends_on(check_cart_event, delay_seconds=2)
            )

            # Event 5: User accepts the proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Yes, please complete the checkout with the discount.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Event 6: Agent completes checkout with discount code (oracle)
            checkout_event = (
                shopping_app.checkout(discount_code="HOLIDAY30").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            discount_notification_event,
            check_discount_event,
            check_cart_event,
            proposal_event,
            acceptance_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent checked discount code info (STRICT)
            discount_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_discount_code_info"
                and e.action.args.get("discount_code") == "HOLIDAY30"
                for e in log_entries
            )

            # Check 2: Agent checked cart contents (STRICT)
            cart_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_cart"
                for e in log_entries
            )

            # Check 3: Agent sent proposal message to user (STRICT - must exist, content flexible)
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 4: User accepted the proposal (STRICT)
            acceptance_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "accept_proposal"
                for e in log_entries
            )

            # Check 5: Agent completed checkout with discount code (STRICT)
            checkout_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "HOLIDAY30"
                for e in log_entries
            )

            success = (
                discount_check_found and cart_check_found and proposal_found and acceptance_found and checkout_found
            )

            if not success:
                rationale_parts = []
                if not discount_check_found:
                    rationale_parts.append("agent did not check discount code info")
                if not cart_check_found:
                    rationale_parts.append("agent did not check cart contents")
                if not proposal_found:
                    rationale_parts.append("agent did not send proposal message")
                if not acceptance_found:
                    rationale_parts.append("user did not accept proposal")
                if not checkout_found:
                    rationale_parts.append("agent did not complete checkout with HOLIDAY30 discount")
                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
