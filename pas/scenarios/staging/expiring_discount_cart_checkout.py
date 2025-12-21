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
    StatefulEmailApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("expiring_discount_cart_checkout")
class ExpiringDiscountCartCheckout(PASScenario):
    """Agent applies expiring discount code from email and completes cart checkout before deadline.

    The user receives a promotional email containing a 20% discount code "SAVE20" valid only until midnight on November 20th for select electronics items. The user already has two eligible items in their shopping cart from earlier browsing (wireless headphones and a phone charger) but hasn't checked out yet. The agent must: 1. Parse the incoming promotional email to extract the discount code and expiration deadline. 2. Check the shopping cart contents and verify the discount code applies to the cart items. 3. Recognize the time-sensitive nature of the expiring discount. 4. Propose completing the checkout with the discount code applied before it expires. 5. After user acceptance, apply the discount code and complete the checkout process. 6. Confirm the order was placed successfully with the discount applied.

    This scenario exercises cross-app information extraction (email → shopping), temporal deadline awareness, discount code validation against cart contents, proactive purchase assistance before time-sensitive opportunities expire, and transactional workflow completion that requires user approval before spending money..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize shopping app with baseline products and cart items
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create product: Wireless Headphones
        headphones_product_id = "prod_headphones_001"
        headphones_product = Product(
            name="Wireless Headphones - Premium",
            product_id=headphones_product_id,
        )
        headphones_item_id = "item_headphones_001"
        headphones_product.variants[headphones_item_id] = Item(
            item_id=headphones_item_id,
            price=79.99,
            available=True,
            options={"color": "black", "type": "over-ear"},
        )
        self.shopping.products[headphones_product_id] = headphones_product

        # Create product: Phone Charger
        charger_product_id = "prod_charger_001"
        charger_product = Product(
            name="USB-C Fast Charger",
            product_id=charger_product_id,
        )
        charger_item_id = "item_charger_001"
        charger_product.variants[charger_item_id] = Item(
            item_id=charger_item_id,
            price=24.99,
            available=True,
            options={"wattage": "30W", "cable_included": True},
        )
        self.shopping.products[charger_product_id] = charger_product

        # Add both items to cart (user already browsed and added these)
        self.shopping.cart[headphones_item_id] = CartItem(
            item_id=headphones_item_id,
            price=79.99,
            quantity=1,
            available=True,
            options={"color": "black", "type": "over-ear"},
        )
        self.shopping.cart[charger_item_id] = CartItem(
            item_id=charger_item_id,
            price=24.99,
            quantity=1,
            available=True,
            options={"wattage": "30W", "cable_included": True},
        )

        # Add discount code "SAVE20" (20% off) for both items
        self.shopping.discount_codes[headphones_item_id] = {"SAVE20": 20.0}
        self.shopping.discount_codes[charger_item_id] = {"SAVE20": 20.0}

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Event 1: Incoming promotional email with discount code (environment event)
            promo_email_event = email_app.send_email_to_user_only(
                sender="deals@techstore.com",
                subject="Last Chance: 20% Off Electronics - Expires Tonight!",
                content="Don't miss out! Use code SAVE20 for 20% off select electronics. This offer expires at midnight on November 20th, 2025. Shop now and save on wireless headphones, chargers, and more!",
            ).delayed(10)

            # Event 2: Agent checks cart contents (oracle)
            check_cart_event = shopping_app.list_cart().oracle().depends_on(promo_email_event, delay_seconds=2)

            # Event 3: Agent checks discount code validity (oracle)
            check_discount_event = (
                shopping_app.get_discount_code_info(discount_code="SAVE20")
                .oracle()
                .depends_on(check_cart_event, delay_seconds=1)
            )

            # Event 4: Agent proposes completing checkout with discount (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you have a discount code SAVE20 (20% off) from TechStore that expires tonight at midnight. You have two eligible items in your cart: Wireless Headphones ($79.99) and USB-C Fast Charger ($24.99). With the discount, your total would be $83.98 instead of $104.98. Would you like me to complete the checkout with the discount code applied?"
                )
                .oracle()
                .depends_on(check_discount_event, delay_seconds=2)
            )

            # Event 5: User accepts proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Yes, please complete the checkout with the discount code.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 6: Agent completes checkout with discount code (oracle)
            checkout_event = (
                shopping_app.checkout(discount_code="SAVE20").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            promo_email_event,
            check_cart_event,
            check_discount_event,
            proposal_event,
            acceptance_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal mentioning discount code, expiration, and cart items
            # STRICT: must reference discount code and cart items
            # FLEXIBLE: exact wording can vary
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent checked cart contents before proposing checkout
            # STRICT: must list cart to see what items the user has
            cart_check_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_cart"
                for e in log_entries
            )

            # Check 3: Agent checked discount code validity
            # STRICT: must verify the discount code applies to cart items
            discount_check_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_discount_code_info"
                and e.action.args.get("discount_code") == "SAVE20"
                for e in log_entries
            )

            # Check 4: Agent completed checkout with the discount code
            # STRICT: must complete checkout with correct discount code SAVE20
            checkout_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "SAVE20"
                for e in log_entries
            )

            # Collect missing checks for rationale
            missing_checks = []
            if not proposal_found:
                missing_checks.append("agent proposal mentioning discount code, cart items, and urgency")
            if not cart_check_found:
                missing_checks.append("cart contents check (list_cart)")
            if not discount_check_found:
                missing_checks.append("discount code validation (get_discount_code_info)")
            if not checkout_found:
                missing_checks.append("checkout completion with SAVE20 discount code")

            success = proposal_found and cart_check_found and discount_check_found and checkout_found

            rationale = None if success else f"Missing critical checks: {', '.join(missing_checks)}"
            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
