"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.apps.shopping import Item, Product
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


@register_scenario("shopping_discount_from_message")
class ShoppingDiscountFromMessage(PASScenario):
    """Agent applies a discount code shared via messaging to items already in the shopping cart.

    The user has added a "Wireless Mouse" and "USB-C Cable" to their shopping cart but hasn't checked out yet. A friend sends a message with a discount code "TECH20" that they mention works on electronics. The agent must:
    1. Detect the incoming message containing the discount code
    2. Check the current shopping cart contents
    3. Verify that the discount code applies to the items in the cart
    4. Propose applying the discount code before checkout
    5. Apply the discount code during checkout after user acceptance
    6. Send a confirmation message back to the friend thanking them for the code

    This scenario exercises cross-app coordination (messaging → shopping), discount code validation, contextual shopping assistance, and social acknowledgment through messaging..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add friend contact to messaging
        friend_name = "Alex Chen"
        friend_phone = "+1-555-0123"
        self.messaging.add_contacts([(friend_name, friend_phone)])

        # Create conversation with friend (baseline history - older messages exist before start_time)
        friend_id = self.messaging.name_to_id[friend_name]
        user_id = "user_001"  # The current user ID
        self.messaging.current_user_id = user_id
        self.messaging.current_user_name = "Me"

        # Create baseline conversation with some prior context
        conversation = ConversationV2(
            participant_ids=[user_id, friend_id],
            title=friend_name,
        )
        # Add one older message from yesterday (baseline state)
        yesterday_timestamp = self.start_time - 86400  # 1 day before
        old_message = MessageV2(
            sender_id=friend_id,
            content="Hey! How are you doing?",
            timestamp=yesterday_timestamp,
        )
        conversation.messages.append(old_message)
        conversation.update_last_updated(yesterday_timestamp)

        self.messaging.add_conversation(conversation)

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create products with items
        # Product 1: Wireless Mouse
        mouse_product = Product(name="Wireless Mouse")
        mouse_item = Item(price=29.99, available=True, options={"color": "black"})
        mouse_product.variants[mouse_item.item_id] = mouse_item
        self.shopping.products[mouse_product.product_id] = mouse_product

        # Product 2: USB-C Cable
        cable_product = Product(name="USB-C Cable")
        cable_item = Item(price=12.99, available=True, options={"length": "6ft"})
        cable_product.variants[cable_item.item_id] = cable_item
        self.shopping.products[cable_product.product_id] = cable_product

        # Add items to cart (baseline state - user already added these before scenario starts)
        from are.simulation.apps.shopping import CartItem

        self.shopping.cart[mouse_item.item_id] = CartItem(
            item_id=mouse_item.item_id,
            price=mouse_item.price,
            quantity=1,
            available=mouse_item.available,
            options=mouse_item.options,
        )
        self.shopping.cart[cable_item.item_id] = CartItem(
            item_id=cable_item.item_id,
            price=cable_item.price,
            quantity=1,
            available=cable_item.available,
            options=cable_item.options,
        )

        # Add discount code that applies to both items
        self.shopping.discount_codes[mouse_item.item_id] = {"TECH20": 20.0}
        self.shopping.discount_codes[cable_item.item_id] = {"TECH20": 20.0}

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        # Get conversation ID BEFORE entering capture_mode (outside event registration)
        friend_name = "Alex Chen"
        friend_id = messaging_app.name_to_id[friend_name]
        user_id = messaging_app.current_user_id
        conversation_ids = messaging_app.get_existing_conversation_ids([friend_id])
        conversation_id = conversation_ids[0]

        with EventRegisterer.capture_mode():
            # Environment event 1: Friend shares discount code via message
            env_event_1 = messaging_app.create_and_add_message(
                conversation_id=conversation_id,
                sender_id=friend_id,
                content="Hey! I just found this discount code TECH20 that gives 20% off electronics. Thought you might want to use it!",
            )

            # Agent detects the message and checks cart contents
            # Evidence: incoming message notification contains "TECH20" discount code
            oracle_event_1 = (
                messaging_app.read_conversation(
                    conversation_id=conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(env_event_1, delay_seconds=5)
            )

            # Agent checks current cart to see what items are there
            # Evidence: message mentions discount code for electronics; agent needs to verify cart contents
            oracle_event_2 = shopping_app.list_cart().oracle().depends_on(oracle_event_1, delay_seconds=2)

            # Agent checks if discount code applies to cart items
            # Evidence: agent has seen "TECH20" code in message and knows cart contents
            oracle_event_3 = (
                shopping_app.get_discount_code_info(discount_code="TECH20")
                .oracle()
                .depends_on(oracle_event_2, delay_seconds=2)
            )

            # Agent proposes applying the discount code
            # Evidence: agent confirmed TECH20 applies to both cart items (mouse + cable)
            oracle_event_4 = (
                aui.send_message_to_user(
                    content="I noticed your friend Alex shared a discount code TECH20 for electronics. You have a Wireless Mouse and USB-C Cable in your cart, and this code gives 20% off both items. Would you like me to apply it during checkout?"
                )
                .oracle()
                .depends_on(oracle_event_3, delay_seconds=3)
            )

            # User accepts the proposal
            user_event_1 = (
                aui.accept_proposal(content="Yes, please apply the discount code!")
                .oracle()
                .depends_on(oracle_event_4, delay_seconds=10)
            )

            # Agent proceeds with checkout using the discount code
            # Evidence: user accepted the proposal to apply TECH20
            oracle_event_5 = (
                shopping_app.checkout(discount_code="TECH20").oracle().depends_on(user_event_1, delay_seconds=2)
            )

            # Agent sends confirmation message to the friend
            # Evidence: checkout completed successfully with the code; social acknowledgment is appropriate
            oracle_event_6 = (
                messaging_app.send_message(
                    user_id=friend_id,
                    content="Thanks for the discount code! I just used it and saved 20%. Really appreciate it!",
                )
                .oracle()
                .depends_on(oracle_event_5, delay_seconds=3)
            )

        # Register ALL events
        self.events = [
            env_event_1,
            oracle_event_1,
            oracle_event_2,
            oracle_event_3,
            oracle_event_4,
            user_event_1,
            oracle_event_5,
            oracle_event_6,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to user about applying discount code
            # STRICT: Proposal must mention the discount code and cart items
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 2a: Agent read the conversation with the friend to detect discount code
            # STRICT: Agent must have read the conversation containing the discount code
            friend_name = "Alex Chen"
            friend_id = self.messaging.name_to_id[friend_name]
            conversation_ids = self.messaging.get_existing_conversation_ids([friend_id])
            conversation_id = conversation_ids[0] if conversation_ids else None

            read_conversation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                for e in log_entries
            )

            # Check Step 2b: Agent checked the shopping cart contents
            # STRICT: Agent must verify what items are in the cart
            list_cart_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_cart"
                for e in log_entries
            )

            # Check Step 2c: Agent verified the discount code applicability
            # STRICT: Agent must check if TECH20 applies to cart items
            discount_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_discount_code_info"
                and e.action.args.get("discount_code") == "TECH20"
                for e in log_entries
            )

            # Check Step 3a: Agent completed checkout with the discount code
            # STRICT: After user acceptance, agent must apply TECH20 during checkout
            checkout_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "TECH20"
                for e in log_entries
            )

            # Check Step 3b: Agent sent thank-you message to friend
            # STRICT: Agent must acknowledge the friend who shared the discount code
            # FLEXIBLE: Exact wording of thank-you can vary
            thank_you_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == friend_id
                for e in log_entries
            )

            # All checks must pass for success
            success = (
                proposal_found
                and read_conversation_found
                and list_cart_found
                and discount_check_found
                and checkout_found
                and thank_you_found
            )

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal about discount code")
                if not read_conversation_found:
                    missing_checks.append("read conversation with friend")
                if not list_cart_found:
                    missing_checks.append("list cart contents")
                if not discount_check_found:
                    missing_checks.append("verify discount code TECH20")
                if not checkout_found:
                    missing_checks.append("checkout with TECH20 discount")
                if not thank_you_found:
                    missing_checks.append("thank-you message to friend")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
