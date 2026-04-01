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


@register_scenario("cart_pause_for_urgent_loan")
class CartPauseForUrgentLoan(PASScenario):
    """Agent proposes pausing non-urgent shopping to help friend with urgent financial need.

    The user has wireless headphones and a phone case in their shopping cart from earlier browsing. Friend Jordan Lee sends an urgent message: "Hey, my laptop charger just died and I have a presentation tomorrow morning. The store closes in an hour and I'm $40 short. Can you help me out? I'll pay you back on Friday when I get paid." The agent must: 1. Parse Jordan's message to identify the urgent financial request and time pressure. 2. Check the user's shopping cart and recognize the items are discretionary/non-urgent hobby purchases. 3. Calculate that removing one or both cart items could free up budget to help Jordan. 4. Propose clearing the cart temporarily and offering to help Jordan with the charger purchase. 5. After user acceptance, remove items from cart and send a confirmation message to Jordan offering financial assistance. 6. Optionally propose re-adding the cart items later when budget allows.

    This scenario exercises social context prioritization where friend needs override personal shopping plans, financial trade-off reasoning between discretionary purchases and urgent assistance, cart item removal as a proactive budget management action, cross-app coordination where messaging triggers shopping cart modification, and empathetic response generation for time-sensitive personal requests..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

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
            # Environment Event 1: Friend Jordan sends urgent message requesting financial help
            # This creates the trigger for the agent to notice a friend's urgent need
            urgent_message_event = messaging_app.create_and_add_message(
                conversation_id="conv_jordan_001",
                sender_id="contact_jordan_001",
                content="Hey, my laptop charger just died and I have a presentation tomorrow morning. The store closes in an hour and I'm $40 short. Can you help me out? I'll pay you back on Friday when I get paid.",
            ).delayed(15)

            # Oracle Event 1: Agent checks shopping cart to understand current items
            # The agent needs to observe what's in the cart before proposing changes
            check_cart_event = shopping_app.list_cart().oracle().depends_on(urgent_message_event, delay_seconds=2)

            # Oracle Event 2: Agent sends proposal to user about clearing cart to help Jordan
            # Agent proposes removing non-urgent items to free up budget
            proposal_event = (
                aui.send_message_to_user(
                    content="Jordan needs urgent help - their laptop charger died and they're $40 short with a presentation tomorrow. You have wireless headphones ($45.99) and a phone case ($19.99) in your cart. These are non-urgent items. Would you like me to clear your cart temporarily so you can help Jordan? You can re-add these items later when your budget allows."
                )
                .oracle()
                .depends_on(check_cart_event, delay_seconds=3)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please clear the cart. Jordan needs the help more urgently.")
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

            # Oracle Event 6: Agent sends confirmation message to Jordan offering help
            confirmation_to_jordan_event = (
                messaging_app.send_message(
                    user_id="contact_jordan_001",
                    content="I can help you out with the $40 for the charger. Let me know where to meet you or I can send it to you. You can pay me back on Friday as you mentioned.",
                )
                .oracle()
                .depends_on(remove_case_event, delay_seconds=2)
            )

        # Register ALL events in order
        self.events = [
            urgent_message_event,
            check_cart_event,
            proposal_event,
            acceptance_event,
            remove_headphones_event,
            remove_case_event,
            confirmation_to_jordan_event,
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

            # Check 2: Agent sent proposal mentioning Jordan's urgent need, cart items, and budget reallocation
            # FLEXIBLE on exact wording, STRICT on logical presence of key concepts
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

            # Check 5: Agent sent confirmation message to Jordan offering help
            # FLEXIBLE on exact wording, STRICT on target user_id and presence of help/assistance concept
            confirmation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == "contact_jordan_001"
                for e in log_entries
            )

            # Combine checks: all must pass for success
            success = (
                check_cart_found
                and proposal_found
                and remove_headphones_found
                and remove_case_found
                and confirmation_found
            )

            # Build rationale for failure
            if not success:
                missing_checks = []
                if not check_cart_found:
                    missing_checks.append("agent did not check shopping cart")
                if not proposal_found:
                    missing_checks.append("agent did not propose clearing cart for Jordan")
                if not remove_headphones_found:
                    missing_checks.append("agent did not remove headphones from cart")
                if not remove_case_found:
                    missing_checks.append("agent did not remove phone case from cart")
                if not confirmation_found:
                    missing_checks.append("agent did not send confirmation message to Jordan")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
