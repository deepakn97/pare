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
    StatefulShoppingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("friend_product_swap_recommendation")
class FriendProductSwapRecommendation(PASScenario):
    """Agent substitutes shopping cart item with friend-recommended alternative based on messaging conversation.

    The user has a wireless mouse in their shopping cart from earlier browsing. The user mentions their upcoming purchase to friend Jordan Lee in a one-on-one message conversation, saying "I'm about to buy a new wireless mouse for work." Jordan responds "Oh! Don't get just any wireless mouse - the Logitech MX Master 3S is way better for productivity. It's a game changer, trust me." The agent must: 1. Parse Jordan's recommendation message to extract the specific product name. 2. Search the shopping catalog for "Logitech MX Master 3S" to verify availability. 3. Compare the recommended product with the current cart contents. 4. Propose replacing the existing wireless mouse with Jordan's recommendation. 5. After user acceptance, remove the old item from cart and add the recommended Logitech MX Master 3S. 6. Send a confirmation message to Jordan thanking them for the recommendation.

    This scenario exercises peer recommendation parsing from casual conversation, product search based on natural language mentions, comparative cart analysis, item substitution rather than simple addition, social context awareness where friend input influences shopping decisions, and follow-up messaging to acknowledge helpful advice..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for friend product swap recommendation scenario."""
        # Initialize required PAS apps
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")
        self.messaging = StatefulMessagingApp(name="Messages")
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Set up messaging user and contacts
        user_id = "user_001"
        self.messaging.current_user_id = user_id
        self.messaging.current_user_name = "Me"
        self.messaging.id_to_name[user_id] = "Me"
        self.messaging.name_to_id["Me"] = user_id

        jordan_id = "jordan_001"
        self.messaging.id_to_name[jordan_id] = "Jordan Lee"
        self.messaging.name_to_id["Jordan Lee"] = jordan_id

        # Populate shopping catalog with products
        # Generic wireless mouse (currently in cart)
        generic_mouse_product = Product(name="Wireless Mouse", product_id="product_generic_mouse")
        generic_mouse_item_id = "item_generic_mouse_001"
        generic_mouse_product.variants[generic_mouse_item_id] = Item(
            item_id=generic_mouse_item_id,
            price=29.99,
            available=True,
            options={"color": "black", "connectivity": "wireless"},
        )
        self.shopping.products[generic_mouse_product.product_id] = generic_mouse_product

        # Logitech MX Master 3S (recommended product)
        logitech_product = Product(name="Logitech MX Master 3S", product_id="product_logitech_mx")
        logitech_item_id = "item_logitech_mx_001"
        logitech_product.variants[logitech_item_id] = Item(
            item_id=logitech_item_id,
            price=99.99,
            available=True,
            options={"color": "graphite", "connectivity": "wireless", "ergonomic": True},
        )
        self.shopping.products[logitech_product.product_id] = logitech_product

        # Add generic mouse to cart (baseline state)
        self.shopping.cart[generic_mouse_item_id] = CartItem(
            item_id=generic_mouse_item_id,
            quantity=1,
            price=29.99,
            available=True,
            options={"color": "black", "connectivity": "wireless"},
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        # Get the conversation ID between user and Jordan
        user_id = "user_001"
        jordan_id = "jordan_001"
        conversation_id = None
        for conv_id, conv in messaging_app.conversations.items():
            if set(conv.participant_ids) == {user_id, jordan_id}:
                conversation_id = conv_id
                break

        # If no conversation exists, create one
        if conversation_id is None:
            from are.simulation.apps.messaging_v2 import ConversationV2

            conversation_id = "conv_jordan_001"
            conversation = ConversationV2(participant_ids=[user_id, jordan_id], conversation_id=conversation_id)
            messaging_app.add_conversation(conversation)

        with EventRegisterer.capture_mode():
            # Environment Event 1: User mentions upcoming mouse purchase to Jordan
            user_message_event = messaging_app.create_and_add_message(
                conversation_id=conversation_id,
                sender_id=user_id,
                content="I'm about to buy a new wireless mouse for work.",
            )

            # Environment Event 2: Jordan recommends the Logitech MX Master 3S
            jordan_message_event = messaging_app.create_and_add_message(
                conversation_id=conversation_id,
                sender_id=jordan_id,
                content="Oh! Don't get just any wireless mouse - the Logitech MX Master 3S is way better for productivity. It's a game changer, trust me.",
            ).delayed(3)

            # Oracle Event 3: Agent lists conversations to detect new messages
            list_conversations_event = (
                messaging_app.list_recent_conversations(
                    offset=0,
                    limit=5,
                    offset_recent_messages_per_conversation=0,
                    limit_recent_messages_per_conversation=10,
                )
                .oracle()
                .depends_on(jordan_message_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent views cart to check current contents
            view_cart_event = shopping_app.list_cart().oracle().depends_on(list_conversations_event, delay_seconds=1)

            # Oracle Event 5: Agent searches for the recommended product
            search_product_event = (
                shopping_app.search_product(product_name="Logitech MX Master 3S", offset=0, limit=10)
                .oracle()
                .depends_on(view_cart_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent sends proposal to user
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Jordan Lee recommended the Logitech MX Master 3S as a better wireless mouse for productivity. You currently have a generic Wireless Mouse in your cart. Would you like me to replace it with Jordan's recommendation?"
                )
                .oracle()
                .depends_on(search_product_event, delay_seconds=2)
            )

            # Oracle Event 7: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please swap it out with the Logitech mouse.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent removes old item from cart
            remove_item_event = (
                shopping_app.remove_from_cart(item_id="item_generic_mouse_001", quantity=1)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent adds recommended item to cart
            add_item_event = (
                shopping_app.add_to_cart(item_id="item_logitech_mx_001", quantity=1)
                .oracle()
                .depends_on(remove_item_event, delay_seconds=1)
            )

            # Oracle Event 10: Agent sends confirmation to Jordan
            confirmation_event = (
                messaging_app.send_message(
                    user_id=jordan_id,
                    content="Thanks for the recommendation! I've updated the cart with the Logitech MX Master 3S.",
                )
                .oracle()
                .depends_on(add_item_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            user_message_event,
            jordan_message_event,
            list_conversations_event,
            view_cart_event,
            search_product_event,
            proposal_event,
            acceptance_event,
            remove_item_event,
            add_item_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user suggesting product swap
            # STRICT: Must propose swapping the cart item with Jordan's recommendation
            # FLEXIBLE: Exact wording can vary, but must reference key entities
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 2a: Agent detected the conversation (list_recent_conversations)
            # STRICT: Must check messaging app for recent conversations
            conversations_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "list_recent_conversations"
                for e in log_entries
            )

            # Check Step 2b: Agent checked the shopping cart contents
            # STRICT: Must verify cart contents to know what to replace
            cart_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_cart"
                for e in log_entries
            )

            # Check Step 2c: Agent searched for the recommended product
            # STRICT: Must search for "Logitech MX Master 3S" or similar
            # FLEXIBLE: Search query may vary slightly but must reference the recommended product
            product_searched = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
                and any(
                    keyword in e.action.args.get("product_name", "").lower() for keyword in ["logitech", "mx master"]
                )
                for e in log_entries
            )

            # Check Step 3a: Agent removed the old item from cart after user acceptance
            # STRICT: Must remove the generic mouse item with correct item_id
            old_item_removed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "remove_from_cart"
                and e.action.args.get("item_id") == "item_generic_mouse_001"
                for e in log_entries
            )

            # Check Step 3b: Agent added the new recommended item to cart
            # STRICT: Must add the Logitech MX Master 3S with correct item_id
            new_item_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == "item_logitech_mx_001"
                for e in log_entries
            )

            # All critical checks must pass for success
            success = (
                proposal_found
                and conversations_checked
                and cart_checked
                and product_searched
                and old_item_removed
                and new_item_added
            )

            if not success:
                rationale_parts = []
                if not proposal_found:
                    rationale_parts.append("no product swap proposal to user")
                if not conversations_checked:
                    rationale_parts.append("conversations not checked")
                if not cart_checked:
                    rationale_parts.append("cart not checked")
                if not product_searched:
                    rationale_parts.append("recommended product not searched")
                if not old_item_removed:
                    rationale_parts.append("old cart item not removed")
                if not new_item_added:
                    rationale_parts.append("new recommended item not added to cart")
                rationale = "Missing critical checks: " + ", ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
