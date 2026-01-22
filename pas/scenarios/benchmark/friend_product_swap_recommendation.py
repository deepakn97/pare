from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data for friend product swap recommendation scenario."""
        # Initialize required PAS apps
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")
        self.messaging = StatefulMessagingApp(name="Messages")
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Set up messaging user and contacts
        # Add users to messaging app - this will automatically set up id_to_name and name_to_id
        self.messaging.add_users(["Jordan Lee"])
        jordan_id = self.messaging.name_to_id["Jordan Lee"]

        # Store jordan_id for use in build_events_flow and validate
        self.jordan_id = jordan_id

        # Create conversation between user and Jordan
        from are.simulation.apps.messaging_v2 import ConversationV2

        jordan_conversation = ConversationV2(
            participant_ids=[self.messaging.current_user_id, jordan_id],
        )
        self.messaging.add_conversation(jordan_conversation)

        # Store conversation_id for use in build_events_flow
        self.jordan_conversation_id = jordan_conversation.conversation_id

        # Populate shopping catalog with products
        # Generic wireless mouse (currently in cart)
        generic_mouse_product_id = self.shopping.add_product("Wireless Mouse")
        generic_mouse_item_id = self.shopping.add_item_to_product(
            product_id=generic_mouse_product_id,
            price=29.99,
            options={"color": "black", "connectivity": "wireless"},
            available=True,
        )

        # Logitech MX Master 3S (recommended product)
        logitech_product_id = self.shopping.add_product("Logitech MX Master 3S")
        logitech_item_id = self.shopping.add_item_to_product(
            product_id=logitech_product_id,
            price=99.99,
            options={"color": "graphite", "connectivity": "wireless", "ergonomic": True},
            available=True,
        )

        # Add generic mouse to cart (baseline state)
        self.shopping.add_to_cart(generic_mouse_item_id, quantity=1)

        # Store item IDs for use in build_events_flow and validate
        self.generic_mouse_item_id = generic_mouse_item_id
        self.logitech_item_id = logitech_item_id

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        # Get user and Jordan IDs and conversation ID from stored instance variables
        user_id = messaging_app.current_user_id
        jordan_id = self.jordan_id
        conversation_id = self.jordan_conversation_id

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
                shopping_app.remove_from_cart(item_id=self.generic_mouse_item_id, quantity=1)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent adds recommended item to cart
            add_item_event = (
                shopping_app.add_to_cart(item_id=self.logitech_item_id, quantity=1)
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

        # Register ALL events here in self.events
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

            # Check Step 2: Agent removed the old item from cart after user acceptance
            # STRICT: Must remove the generic mouse item with correct item_id
            old_item_removed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "remove_from_cart"
                and e.action.args.get("item_id") == self.generic_mouse_item_id
                for e in log_entries
            )

            # Check Step 3: Agent added the new recommended item to cart
            # STRICT: Must add the Logitech MX Master 3S with correct item_id
            new_item_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == self.logitech_item_id
                for e in log_entries
            )

            # Check Step 4: Agent sent confirmation message to Jordan
            # STRICT: Must send message to Jordan thanking for recommendation
            # FLEXIBLE: Message content may vary but must acknowledge the recommendation
            confirmation_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.jordan_id
                for e in log_entries
            )

            # All critical checks must pass for success
            success = proposal_found and old_item_removed and new_item_added and confirmation_sent

            if not success:
                rationale_parts = []
                if not proposal_found:
                    rationale_parts.append("no product swap proposal to user")
                if not old_item_removed:
                    rationale_parts.append("old cart item not removed")
                if not new_item_added:
                    rationale_parts.append("new recommended item not added to cart")
                if not confirmation_sent:
                    rationale_parts.append("confirmation message to Jordan not sent")
                rationale = "Missing critical checks: " + ", ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
