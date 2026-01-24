"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
    StatefulShoppingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("duplicate_order_detection_cancellation")
class DuplicateOrderDetectionCancellation(PASScenario):
    """Agent detects duplicate shopping orders and proactively cancels the redundant one to prevent double-charging.

    The user receives two order confirmation emails within minutes of each other from the shopping platform. The first email confirms "Order #ORD-5531 placed successfully: 2x Organic Coffee Beans, 1x Stainless Steel Mug, total $47.99, delivery Tuesday 2-4 PM." The second email confirms "Order #ORD-5538 placed successfully: 2x Organic Coffee Beans, 1x Stainless Steel Mug, total $47.99, delivery Tuesday 2-4 PM." The agent must: 1. Detect the two confirmation emails arriving in close succession. 2. Search the shopping order history to retrieve full details for both orders using the order numbers mentioned in the emails. 3. Compare the order contents, quantities, prices, and delivery windows to determine they are exact duplicates. 4. Infer this is likely an accidental double-submission rather than intentional reordering. 5. Propose canceling the second order (later timestamp) to prevent duplicate delivery and double-charging. 6. Cancel the redundant order when the user approves.

    This scenario exercises duplicate detection across multiple emails, shopping order retrieval using email-provided order numbers, detailed order comparison logic, accidental vs. intentional reorder inference, and proactive order management to prevent user errors from causing financial/logistical issues..
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

        # Initialize shopping app with product catalog
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add Organic Coffee Beans product with variant
        coffee_product_id = self.shopping.add_product(name="Organic Coffee Beans")
        coffee_item_id = self.shopping.add_item_to_product(
            product_id=coffee_product_id, price=19.99, options={"weight": "1lb", "roast": "medium"}, available=True
        )

        # Add Stainless Steel Mug product with variant
        mug_product_id = self.shopping.add_product(name="Stainless Steel Mug")
        mug_item_id = self.shopping.add_item_to_product(
            product_id=mug_product_id, price=8.01, options={"size": "16oz", "color": "silver"}, available=True
        )

        # Store item IDs for use in events
        self.coffee_item_id = coffee_item_id
        self.mug_item_id = mug_item_id

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: First order confirmation email arrives
            email1_event = email_app.send_email_to_user_with_id(
                email_id="email-order-5531",
                sender="orders@shoppingplatform.com",
                subject="Order Confirmation - Order #ORD-5531",
                content="Your order has been placed successfully!\n\nOrder #ORD-5531\nItems:\n- 2x Organic Coffee Beans ($19.99 each)\n- 1x Stainless Steel Mug ($8.01)\n\nTotal: $47.99\nDelivery: Tuesday, November 19, 2-4 PM\n\nThank you for your purchase!",
            ).delayed(10)

            # Environment Event 2: Second (duplicate) order confirmation email arrives shortly after
            email2_event = email_app.send_email_to_user_with_id(
                email_id="email-order-5538",
                sender="orders@shoppingplatform.com",
                subject="Order Confirmation - Order #ORD-5538",
                content="Your order has been placed successfully!\n\nOrder #ORD-5538\nItems:\n- 2x Organic Coffee Beans ($19.99 each)\n- 1x Stainless Steel Mug ($8.01)\n\nTotal: $47.99\nDelivery: Tuesday, November 19, 2-4 PM\n\nThank you for your purchase!",
            ).delayed(3)

            # Oracle Event 3: Agent lists orders to check for duplicates
            # Motivated by: Two order confirmation emails arrived in quick succession with identical contents
            list_orders_event = shopping_app.list_orders().oracle().depends_on(email2_event, delay_seconds=2)

            # Oracle Event 4: Agent retrieves details for first order
            # Motivated by: list_orders revealed order IDs; need to compare full details
            get_order1_event = (
                shopping_app.get_order_details(order_id="ORD-5531")
                .oracle()
                .depends_on(list_orders_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent retrieves details for second order
            # Motivated by: Need second order's details to complete the comparison
            get_order2_event = (
                shopping_app.get_order_details(order_id="ORD-5538")
                .oracle()
                .depends_on(list_orders_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent proposes canceling the duplicate order
            # Motivated by: Comparison of get_order_details results shows identical items, quantities, prices, and delivery windows
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you received two identical order confirmations (ORD-5531 and ORD-5538) within minutes. Both orders contain 2x Organic Coffee Beans and 1x Stainless Steel Mug for $47.99 with Tuesday 2-4 PM delivery. This appears to be an accidental duplicate submission. Would you like me to cancel the second order (ORD-5538) to prevent double-charging?"
                )
                .oracle()
                .depends_on([get_order1_event, get_order2_event], delay_seconds=2)
            )

            # Oracle Event 7: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please cancel the duplicate order.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent cancels the redundant order
            # Motivated by: User accepted the proposal to cancel ORD-5538
            cancel_event = (
                shopping_app.cancel_order(order_id="ORD-5538").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            email1_event,
            email2_event,
            list_orders_event,
            get_order1_event,
            get_order2_event,
            proposal_event,
            acceptance_event,
            cancel_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal identifying duplicate orders
            # Must reference both order IDs (ORD-5531 and ORD-5538) and indicate they are duplicates
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent listed orders to detect the duplicates
            list_orders_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_orders"
                for e in log_entries
            )

            # STRICT Check 3: Agent retrieved details for both orders to compare them
            # Must get details for both ORD-5531 and ORD-5538
            get_order_5531_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                and e.action.args.get("order_id") == "ORD-5531"
                for e in log_entries
            )

            get_order_5538_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                and e.action.args.get("order_id") == "ORD-5538"
                for e in log_entries
            )

            # STRICT Check 4: Agent canceled the duplicate order (ORD-5538)
            cancel_order_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "cancel_order"
                for e in log_entries
            )

            # All strict checks must pass for success
            success = (
                proposal_found
                and list_orders_found
                and get_order_5531_found
                and get_order_5538_found
                and cancel_order_found
            )

            # Build rationale for failure
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal referencing both ORD-5531 and ORD-5538")
                if not list_orders_found:
                    missing_checks.append("list_orders call to detect duplicates")
                if not get_order_5531_found:
                    missing_checks.append("get_order_details for ORD-5531")
                if not get_order_5538_found:
                    missing_checks.append("get_order_details for ORD-5538")
                if not cancel_order_found:
                    missing_checks.append("cancel_order")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
