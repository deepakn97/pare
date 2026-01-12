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
    StatefulContactsApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("duplicate_order_cancellation_check")
class DuplicateOrderCancellationCheck(PASScenario):
    """Agent detects and prevents duplicate orders by proactively canceling redundant purchases.

    The user has an existing order (#4521) for "Wireless Headphones - Black" placed three days ago with status "processing" (not yet delivered). The user receives a shopping notification about a new order confirmation (#4522) for the identical product "Wireless Headphones - Black" just placed moments ago, likely by accident. The agent must:
    1. Parse the new order confirmation notification to identify the product
    2. Search order history to find the earlier pending order containing the same product
    3. Compare order details and detect the duplication (same product, both undelivered)
    4. Propose canceling the newer duplicate order (#4522) to avoid unnecessary charges
    5. If the user accepts, cancel the newer order using the shopping app

    This scenario exercises notification-triggered anomaly detection, historical order comparison within a single app, duplicate detection logic, and proactive cancellation to prevent user error.

    ---.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        from are.simulation.apps.shopping import CartItem, Order

        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create the product "Wireless Headphones - Black"
        product_id = self.shopping.add_product(name="Wireless Headphones - Black")
        item_id = self.shopping.add_item_to_product(
            product_id=product_id, price=79.99, options={"color": "black"}, available=True
        )

        # Seed the OLDER existing order (#4521) placed three days ago
        # This order was placed at start_time - 3 days and has status "processing"
        # We construct the Order directly to avoid the add_order bug with CartItem name field
        older_order_timestamp = self.start_time - (3 * 24 * 60 * 60)
        older_order = Order(
            order_id="4521",
            order_status="processing",
            order_date=datetime.fromtimestamp(older_order_timestamp, tz=UTC),
            order_total=79.99,
            order_items={
                item_id: CartItem(item_id=item_id, quantity=1, price=79.99, available=True, options={"color": "black"})
            },
        )
        self.shopping.orders["4521"] = older_order

        # Seed the NEWER duplicate order (#4522) placed just now (at start_time)
        # This will be the order that triggers the notification and should be canceled
        newer_order = Order(
            order_id="4522",
            order_status="processed",
            order_date=datetime.fromtimestamp(self.start_time, tz=UTC),
            order_total=79.99,
            order_items={
                item_id: CartItem(item_id=item_id, quantity=1, price=79.99, available=True, options={"color": "black"})
            },
        )
        self.shopping.orders["4522"] = newer_order

        # Initialize Contacts app
        self.contacts = StatefulContactsApp(name="Contacts")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.contacts]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: New order status notification for the duplicate order #4522
            # This triggers the agent to notice the new order
            new_order_notification = shopping_app.update_order_status(order_id="4522", status="processed").delayed(10)

            # Oracle Event 1: Agent lists all orders to see order history
            # Motivation: The new order notification mentions order #4522, prompting the agent
            # to check what other orders exist to detect potential duplicates
            list_orders_event = shopping_app.list_orders().oracle().depends_on(new_order_notification, delay_seconds=2)

            # Oracle Event 2: Agent gets details of the newer order #4522
            # Motivation: After seeing order #4522 in the list, agent needs details to identify
            # the product and compare with other orders
            get_new_order_details = (
                shopping_app.get_order_details(order_id="4522").oracle().depends_on(list_orders_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent gets details of the older order #4521
            # Motivation: After listing orders, agent saw order #4521 also exists with "processing"
            # status and needs to compare its contents with #4522
            get_old_order_details = (
                shopping_app.get_order_details(order_id="4521")
                .oracle()
                .depends_on(get_new_order_details, delay_seconds=1)
            )

            # Oracle Event 4: Agent proposes canceling the duplicate order
            # Motivation: After comparing both order details, agent detected they contain the same
            # product (Wireless Headphones - Black) and both are undelivered
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you just placed order #4522 for Wireless Headphones - Black ($79.99). However, you already have order #4521 for the same product placed 3 days ago that is still processing. This appears to be a duplicate order. Would you like me to cancel order #4522 to avoid being charged twice?"
                )
                .oracle()
                .depends_on(get_old_order_details, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal to cancel duplicate order
            acceptance_event = (
                aui.accept_proposal(content="Yes, please cancel the duplicate order #4522.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent cancels the newer duplicate order
            # Motivation: User accepted the proposal, so agent executes the cancellation
            cancel_order_event = (
                shopping_app.cancel_order(order_id="4522").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            new_order_notification,
            list_orders_event,
            get_new_order_details,
            get_old_order_details,
            proposal_event,
            acceptance_event,
            cancel_order_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check Step 1: Agent listed orders to detect potential duplicates
            # This is critical reasoning - agent must check order history
            list_orders_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_orders"
                for e in agent_events
            )

            # STRICT Check Step 2: Agent retrieved details of newer order #4522
            # This is critical reasoning - agent must investigate the new order
            get_new_order_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                and e.action.args.get("order_id") == "4522"
                for e in agent_events
            )

            # STRICT Check Step 3: Agent retrieved details of older order #4521
            # This is critical reasoning - agent must compare with existing order
            get_old_order_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                and e.action.args.get("order_id") == "4521"
                for e in agent_events
            )

            # FLEXIBLE Check Step 4: Agent proposed canceling the duplicate order
            # Content is flexible (wording may vary), but the proposal must happen
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check Step 5: Agent canceled the newer duplicate order #4522
            # This is critical action - agent must cancel the correct order
            cancel_order_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "cancel_order"
                for e in agent_events
            )

            # All strict checks must pass for success
            success = (
                list_orders_found
                and get_new_order_found
                and get_old_order_found
                and proposal_found
                and cancel_order_found
            )

            if not success:
                # Build rationale for which critical checks failed
                missing_checks = []
                if not list_orders_found:
                    missing_checks.append("agent did not list orders to detect duplicates")
                if not get_new_order_found:
                    missing_checks.append("agent did not retrieve details of new order #4522")
                if not get_old_order_found:
                    missing_checks.append("agent did not retrieve details of old order #4521")
                if not proposal_found:
                    missing_checks.append("agent did not propose cancellation to user")
                if not cancel_order_found:
                    missing_checks.append("agent did not cancel duplicate order #4522")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
