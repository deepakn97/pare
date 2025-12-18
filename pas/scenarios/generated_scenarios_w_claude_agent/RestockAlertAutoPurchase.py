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


@register_scenario("restock_alert_auto_purchase")
class RestockAlertAutoPurchase(PASScenario):
    """Agent monitors shopping app for restocked out-of-stock items and completes purchase automatically. The user previously attempted to purchase a popular electronics item (wireless earbuds) that was out of stock, leaving it in their cart as unavailable. Days later, the store's inventory system updates and the item becomes available again at the original price. The agent must: 1. Detect the restocking event by monitoring cart item availability status changes. 2. Recognize this matches a previously failed purchase attempt. 3. Verify the item price and availability haven't changed unfavorably. 4. Propose completing the checkout now that the item is back in stock. 5. After user acceptance, apply any valid discount codes that work with the restocked item. 6. Complete the checkout and confirm the order was placed successfully.

    This scenario exercises pure shopping-app state monitoring without cross-app coordination, inventory availability tracking over time, price stability validation, opportunistic discount application during checkout, and transactional completion triggered by backend inventory updates rather than incoming messages..
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

        # Populate shopping app with baseline data
        # Add wireless earbuds product with a single variant
        product_id = self.shopping.add_product(name="Premium Wireless Earbuds")
        item_id = self.shopping.add_item_to_product(
            product_id=product_id,
            price=129.99,
            options={"color": "Midnight Black", "model": "Pro Max 2024"},
            available=False,  # Out of stock initially
        )

        # Add the unavailable item to the user's cart (simulating previous failed attempt)
        # Note: We need to temporarily make it available to add to cart, then mark unavailable
        self.shopping.update_item(item_id=item_id, new_availability=True)
        self.shopping.add_to_cart(item_id=item_id, quantity=1)
        self.shopping.update_item(item_id=item_id, new_availability=False)

        # Update cart item availability to reflect out-of-stock status
        if item_id in self.shopping.cart:
            self.shopping.cart[item_id].available = False

        # Add a discount code that works for this item
        self.shopping.add_discount_code(
            item_id=item_id,
            discount_code={"WELCOME10": 10.0},
        )

        # Store item_id for use in events flow
        self.item_id = item_id

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
            # Event 1: Restocking notification - item becomes available again (environment event)
            restock_event = shopping_app.update_item(
                item_id=self.item_id,
                new_availability=True,
            ).delayed(30)

            # Event 2: Agent checks cart to see item status (oracle)
            check_cart_event = shopping_app.list_cart().oracle().depends_on(restock_event, delay_seconds=2)

            # Event 3: Agent checks discount codes available for the item (oracle)
            check_discount_event = (
                shopping_app.get_discount_code_info(discount_code="WELCOME10")
                .oracle()
                .depends_on(check_cart_event, delay_seconds=1)
            )

            # Event 4: Agent proposes completing the purchase (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="Good news! The Premium Wireless Earbuds in your cart are back in stock at $129.99. I can complete your purchase now and apply the WELCOME10 discount code for 10% off. Would you like me to proceed with checkout?"
                )
                .oracle()
                .depends_on(check_discount_event, delay_seconds=2)
            )

            # Event 5: User accepts proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Yes, please complete the purchase with the discount code.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 6: Agent completes checkout with discount code (oracle)
            checkout_event = (
                shopping_app.checkout(discount_code="WELCOME10").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # Event 7: Agent confirms order completion (oracle)
            confirmation_event = (
                aui.send_message_to_user(
                    content="Order completed successfully! Your Premium Wireless Earbuds have been ordered with the 10% discount applied. Total: $116.99."
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            restock_event,
            check_cart_event,
            check_discount_event,
            proposal_event,
            acceptance_event,
            checkout_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal to user about the restocked item
            # Must reference the restocked item (flexible on exact wording)
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Wireless Earbuds" in e.action.args.get("content", "")
                for e in log_entries
            )

            # STRICT Check 2: Agent checked cart status (list_cart tool call)
            cart_check_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_cart"
                for e in log_entries
            )

            # FLEXIBLE Check 3: Agent checked discount code info (optional but expected)
            discount_check_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_discount_code_info"
                for e in log_entries
            )

            # STRICT Check 4: Agent completed checkout with discount code
            checkout_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "WELCOME10"
                for e in log_entries
            )

            # Build success criteria and rationale
            success = proposal_found and cart_check_found and checkout_found

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal about restocked item")
                if not cart_check_found:
                    missing_checks.append("cart status check (list_cart)")
                if not checkout_found:
                    missing_checks.append("checkout with discount code WELCOME10")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
