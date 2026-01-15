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
    StatefulMessagingApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("cart_remove_low_quality_items")
class CartRemoveLowQualityItems(PASScenario):
    """Agent removes low-quality items from the shopping cart after a trusted friend warns about them.

    The user has wireless headphones and a phone case in their shopping cart from earlier browsing. Friend Jordan Lee sends a message warning that these exact items are low quality (Jordan bought the same ones) and recommends removing them from the cart and looking for alternatives. The agent must: 1. Parse Jordan's message to identify which items to avoid. 2. Check the user's shopping cart and confirm whether the warned-about items are present. 3. Propose removing those items from the cart. 4. After user acceptance, remove the cart items. 5. Optionally message Jordan to acknowledge the tip and ask for better alternatives.

    This scenario exercises social signal grounding (friend recommendation as trigger), cross-app coordination (message → cart inspection → cart update), and user-gated write actions (remove_from_cart).
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Shopping App with cart items
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create wireless headphones product
        headphones_product = Product(name="Wireless Headphones", product_id="prod_headphones_001")
        headphones_item = Item(
            price=45.99, available=True, item_id="item_headphones_001", options={"color": "black", "type": "over-ear"}
        )
        headphones_product.variants["item_headphones_001"] = headphones_item
        self.shopping.products["prod_headphones_001"] = headphones_product

        # Create phone case product
        case_product = Product(name="Phone Case", product_id="prod_case_001")
        case_item = Item(
            price=19.99, available=True, item_id="item_case_001", options={"color": "blue", "material": "silicone"}
        )
        case_product.variants["item_case_001"] = case_item
        self.shopping.products["prod_case_001"] = case_product

        # Add both items to cart (simulating earlier browsing)
        self.shopping.cart["item_headphones_001"] = CartItem(
            item_id="item_headphones_001",
            quantity=1,
            price=45.99,
            available=True,
            options={"color": "black", "type": "over-ear"},
        )
        self.shopping.cart["item_case_001"] = CartItem(
            item_id="item_case_001",
            quantity=1,
            price=19.99,
            available=True,
            options={"color": "blue", "material": "silicone"},
        )

        # Initialize Messaging App with friend Jordan Lee
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.current_user_id = "user_self"
        self.messaging.current_user_name = "Me"

        # Add friend Jordan Lee as a contact
        jordan_id = "contact_jordan_001"
        self.messaging.name_to_id["Jordan Lee"] = jordan_id
        self.messaging.id_to_name[jordan_id] = "Jordan Lee"

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Friend Jordan warns that the cart items are low quality
            # This creates the trigger for the agent to inspect the user's cart and propose removal.
            quality_warning_event = messaging_app.create_and_add_message(
                conversation_id="conv_jordan_001",
                sender_id="contact_jordan_001",
                content=(
                    "Quick heads-up: I bought the AudioPro wireless headphones and that blue silicone phone case "
                    "recently, and both were pretty low quality. If you happen to have those in your cart, I'd remove "
                    "them and look for alternatives—happy to recommend better ones."
                ),
            ).delayed(15)

            # Oracle Event 1: Agent checks shopping cart to understand current items
            # The agent needs to observe what's in the cart before proposing changes
            check_cart_event = shopping_app.list_cart().oracle().depends_on(quality_warning_event, delay_seconds=2)

            # Oracle Event 2: Agent sends proposal to user about removing the warned-about items
            # Evidence: Jordan explicitly warns that the headphones/phone case are low quality and suggests removing them
            # if they're in the user's cart.
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "Jordan messaged that the AudioPro wireless headphones and the blue silicone phone case are low "
                        "quality and suggested removing them if they're in your cart. You currently have wireless "
                        "headphones ($45.99) and a phone case ($19.99) in your cart.\n\n"
                        "Would you like me to remove those two items from your cart?"
                    )
                )
                .oracle()
                .depends_on(check_cart_event, delay_seconds=3)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please remove those two items from my cart.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent removes headphones from cart
            remove_headphones_event = (
                shopping_app.remove_from_cart(item_id="item_headphones_001", quantity=1)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent removes phone case from cart
            remove_case_event = (
                shopping_app.remove_from_cart(item_id="item_case_001", quantity=1)
                .oracle()
                .depends_on(remove_headphones_event, delay_seconds=1)
            )

        # Register ALL events in order
        self.events = [
            quality_warning_event,
            check_cart_event,
            proposal_event,
            acceptance_event,
            remove_headphones_event,
            remove_case_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent checked the shopping cart to understand current items
            check_cart_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_cart"
                for e in log_entries
            )

            # Check 2: Agent sent proposal to remove the warned-about cart items
            # FLEXIBLE on exact wording; proposal existence is sufficient here.
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 3: Agent removed headphones from cart (STRICT on item_id)
            remove_headphones_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "remove_from_cart"
                and e.action.args.get("item_id") == "item_headphones_001"
                for e in log_entries
            )

            # Check 4: Agent removed phone case from cart (STRICT on item_id)
            remove_case_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "remove_from_cart"
                and e.action.args.get("item_id") == "item_case_001"
                for e in log_entries
            )

            # Combine checks: all must pass for success
            success = check_cart_found and proposal_found and remove_headphones_found and remove_case_found

            # Build rationale for failure
            if not success:
                missing_checks = []
                if not check_cart_found:
                    missing_checks.append("agent did not check shopping cart")
                if not proposal_found:
                    missing_checks.append("agent did not propose removing the warned-about items")
                if not remove_headphones_found:
                    missing_checks.append("agent did not remove headphones from cart")
                if not remove_case_found:
                    missing_checks.append("agent did not remove phone case from cart")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
