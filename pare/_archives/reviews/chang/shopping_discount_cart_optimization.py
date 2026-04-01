from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("shopping_discount_cart_optimization")
class ShoppingDiscountCartOptimization(PASScenario):
    """Agent applies promotional discount code to optimize cart checkout after user receives discount notification.

    The user has items already in their shopping cart. They receive a promotional notification announcing a discount code "SAVE20" that applies to specific products. The agent must:
    1. Detect the incoming discount notification containing the code and applicable items
    2. Check current cart contents using list_cart()
    3. Verify which items in the cart are eligible for the discount code using get_discount_code_info()
    4. Propose applying the discount to eligible items
    5. Proceed to checkout with the discount code applied

    This scenario exercises cross-app reasoning (shopping notifications -> cart management), discount eligibility verification, proactive cost optimization, and conditional discount application following the all-or-nothing discount policy..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create products and items in the catalog
        # Product 1: Wireless Headphones
        headphones_product_id = self.shopping.add_product("Wireless Headphones")
        self.headphones_black_item_id = self.shopping.add_item_to_product(
            product_id=headphones_product_id,
            price=79.99,
            options={"color": "black"},
            available=True,
        )
        self.headphones_white_item_id = self.shopping.add_item_to_product(
            product_id=headphones_product_id,
            price=79.99,
            options={"color": "white"},
            available=True,
        )

        # Product 2: Laptop Stand
        stand_product_id = self.shopping.add_product("Laptop Stand")
        self.stand_aluminum_item_id = self.shopping.add_item_to_product(
            product_id=stand_product_id,
            price=35.99,
            options={"material": "aluminum"},
            available=True,
        )

        # Product 3: USB-C Cable
        cable_product_id = self.shopping.add_product("USB-C Cable")
        self.cable_6ft_item_id = self.shopping.add_item_to_product(
            product_id=cable_product_id,
            price=12.99,
            options={"length": "6ft"},
            available=True,
        )

        # Add items to cart (user has already browsed and added items before scenario starts)
        self.shopping.add_to_cart(self.headphones_black_item_id, quantity=1)
        self.shopping.add_to_cart(self.stand_aluminum_item_id, quantity=1)
        self.shopping.add_to_cart(self.cable_6ft_item_id, quantity=2)

        # Note: Discount codes will be added via environment event (Event 1) to simulate promotional notification

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Event 1: Promotional discount notification arrives (environment event)
            # This notification announces the SAVE20 discount code for eligible items (headphones and laptop stand)
            discount_notification_event_headphones = shopping_app.add_discount_code(
                item_id=self.headphones_black_item_id,
                discount_code={"SAVE20": 20.0},
            ).delayed(10)

            discount_notification_event_stand = shopping_app.add_discount_code(
                item_id=self.stand_aluminum_item_id,
                discount_code={"SAVE20": 20.0},
            ).delayed(10)

            # Use the first event as the trigger for agent actions
            discount_notification_event = discount_notification_event_headphones

            # Event 2: Agent checks current cart contents (oracle)
            # Agent needs to see what items are in the cart to evaluate discount applicability
            list_cart_event = shopping_app.list_cart().oracle().depends_on(discount_notification_event, delay_seconds=2)

            # Event 3: Agent checks discount code eligibility (oracle)
            # Agent verifies which cart items are eligible for the SAVE20 discount code
            check_discount_event = (
                shopping_app.get_discount_code_info(discount_code="SAVE20")
                .oracle()
                .depends_on(list_cart_event, delay_seconds=1)
            )

            # Event 4: Agent proposes discount optimization strategy (oracle)
            # Based on findings, agent proposes removing ineligible items and applying discount
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed a SAVE20 discount code is available for some items in your cart (Wireless Headphones and Laptop Stand). However, the USB-C Cable doesn't qualify. To use the discount, we can either: (1) Remove the cable and checkout with 20% off the other items, saving $23.20, or (2) Keep all items but checkout without the discount. Would you like to apply the discount?"
                )
                .oracle()
                .depends_on(check_discount_event, delay_seconds=2)
            )

            # Event 5: User accepts discount optimization (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Yes, remove the cable and apply the discount at checkout to save money.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 6: Agent removes ineligible items from cart (oracle)
            # Agent removes the USB-C Cable to meet the all-or-nothing discount policy
            remove_cable_event = (
                shopping_app.remove_from_cart(
                    item_id=self.cable_6ft_item_id,
                    quantity=2,
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Event 7: Agent completes checkout with discount code (oracle)
            # Agent applies the SAVE20 discount code and completes the purchase
            checkout_event = (
                shopping_app.checkout(discount_code="SAVE20").oracle().depends_on(remove_cable_event, delay_seconds=1)
            )

        # Register ALL events in self.events
        self.events = [
            discount_notification_event_headphones,
            discount_notification_event_stand,
            list_cart_event,
            check_discount_event,
            proposal_event,
            acceptance_event,
            remove_cable_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent checked cart contents
            list_cart_found = any(
                e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "list_cart"
                for e in agent_events
            )

            # STRICT Check 2: Agent verified discount code eligibility
            check_discount_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_discount_code_info"
                and e.action.args.get("discount_code") == "SAVE20"
                for e in agent_events
            )

            # STRICT Check 3: Agent sent proposal to user (flexible on message content)
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent removed ineligible items from cart
            remove_cable_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "remove_from_cart"
                and e.action.args.get("item_id") == self.cable_6ft_item_id
                for e in agent_events
            )

            # STRICT Check 5: Agent completed checkout with discount code
            checkout_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "SAVE20"
                for e in agent_events
            )

            # Determine success based on all strict checks
            success = (
                list_cart_found and check_discount_found and proposal_found and remove_cable_found and checkout_found
            )

            # Build rationale if validation fails
            if not success:
                missing_checks = []
                if not list_cart_found:
                    missing_checks.append("agent did not check cart contents")
                if not check_discount_found:
                    missing_checks.append("agent did not verify discount code eligibility")
                if not proposal_found:
                    missing_checks.append("agent did not send optimization proposal to user")
                if not remove_cable_found:
                    missing_checks.append("agent did not remove ineligible cable item")
                if not checkout_found:
                    missing_checks.append("agent did not complete checkout with discount code")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
