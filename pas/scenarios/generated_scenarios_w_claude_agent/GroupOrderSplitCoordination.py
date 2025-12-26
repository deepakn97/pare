"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2
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


@register_scenario("group_order_split_coordination")
class GroupOrderSplitCoordination(PASScenario):
    """Agent coordinates a group bulk purchase by synthesizing individual item requests from multiple participants and managing shared order logistics.

    The user receives separate messages from three friends (Alice, Bob, and Charlie) who each want to order different items from the same online retailer to save on shipping costs. Alice messages asking to include wireless headphones in a shared order, Bob requests a laptop stand, and Charlie asks for a USB hub. The agent must:
    1. Detect incoming messages from multiple participants about item requests
    2. Create a group conversation with all three participants to coordinate the order
    3. Search the shopping catalog for each requested product by name
    4. Add all requested items to the cart (one of each product)
    5. Apply any available discount codes that work for all items in the cart
    6. Complete checkout to create the shared order
    7. Send the order confirmation details to the group conversation

    This scenario exercises multi-participant coordination, product name-based search without prior product IDs, discount code validation across multiple items, group conversation creation, and cross-app synthesis (messaging -> shopping -> group messaging).

    ---.
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
        self.messaging.current_user_id = "user_me"
        self.messaging.current_user_name = "Me"

        # Add contacts Alice, Bob, and Charlie
        alice_id = "alice_123"
        bob_id = "bob_456"
        charlie_id = "charlie_789"

        self.messaging.id_to_name[alice_id] = "Alice"
        self.messaging.name_to_id["Alice"] = alice_id
        self.messaging.id_to_name[bob_id] = "Bob"
        self.messaging.name_to_id["Bob"] = bob_id
        self.messaging.id_to_name[charlie_id] = "Charlie"
        self.messaging.name_to_id["Charlie"] = charlie_id

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create products that match the requests from the friends
        # Product 1: Wireless Headphones (for Alice)
        headphones = Product(name="Wireless Headphones", product_id="prod_headphones_001")
        headphones_item = Item(
            item_id="item_headphones_001", price=79.99, available=True, options={"color": "black", "type": "over-ear"}
        )
        headphones.variants["item_headphones_001"] = headphones_item
        self.shopping.products["prod_headphones_001"] = headphones

        # Product 2: Laptop Stand (for Bob)
        laptop_stand = Product(name="Laptop Stand", product_id="prod_stand_002")
        stand_item = Item(
            item_id="item_stand_002", price=34.99, available=True, options={"material": "aluminum", "adjustable": True}
        )
        laptop_stand.variants["item_stand_002"] = stand_item
        self.shopping.products["prod_stand_002"] = laptop_stand

        # Product 3: USB Hub (for Charlie)
        usb_hub = Product(name="USB Hub", product_id="prod_hub_003")
        hub_item = Item(item_id="item_hub_003", price=24.99, available=True, options={"ports": 7, "usb_version": "3.0"})
        usb_hub.variants["item_hub_003"] = hub_item
        self.shopping.products["prod_hub_003"] = usb_hub

        # Add a discount code that works for all three items
        self.shopping.discount_codes["item_headphones_001"] = {"BULKORDER10": 0.10}
        self.shopping.discount_codes["item_stand_002"] = {"BULKORDER10": 0.10}
        self.shopping.discount_codes["item_hub_003"] = {"BULKORDER10": 0.10}

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

        alice_id = "alice_123"
        bob_id = "bob_456"
        charlie_id = "charlie_789"
        user_id = "user_me"

        # Create individual conversations with each friend in Step 2 to seed baseline state
        alice_conv = ConversationV2(participant_ids=[user_id, alice_id])
        bob_conv = ConversationV2(participant_ids=[user_id, bob_id])
        charlie_conv = ConversationV2(participant_ids=[user_id, charlie_id])

        messaging_app.add_conversation(alice_conv)
        messaging_app.add_conversation(bob_conv)
        messaging_app.add_conversation(charlie_conv)

        with EventRegisterer.capture_mode():
            # Environment Event 1: Alice messages asking to include wireless headphones in shared order
            alice_message_event = messaging_app.create_and_add_message(
                conversation_id=alice_conv.conversation_id,
                sender_id=alice_id,
                content="Hey! I heard you're doing a shared order to save on shipping. Can you add wireless headphones for me?",
            ).delayed(10)

            # Environment Event 2: Bob messages requesting a laptop stand
            bob_message_event = messaging_app.create_and_add_message(
                conversation_id=bob_conv.conversation_id,
                sender_id=bob_id,
                content="Hi! I'd like to join the group order. Could you get me a laptop stand?",
            ).delayed(5)

            # Environment Event 3: Charlie messages asking for a USB hub
            charlie_message_event = messaging_app.create_and_add_message(
                conversation_id=charlie_conv.conversation_id,
                sender_id=charlie_id,
                content="Count me in for the shared order! I need a USB hub. Thanks!",
            ).delayed(5)

            # Oracle Event 1: Agent reads Alice's conversation
            # Motivated by: Alice's message notification about joining shared order
            read_alice_event = (
                messaging_app.read_conversation(
                    conversation_id=alice_conv.conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(alice_message_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent reads Bob's conversation
            # Motivated by: Bob's message notification about joining shared order
            read_bob_event = (
                messaging_app.read_conversation(
                    conversation_id=bob_conv.conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(bob_message_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent reads Charlie's conversation
            # Motivated by: Charlie's message notification about joining shared order
            read_charlie_event = (
                messaging_app.read_conversation(
                    conversation_id=charlie_conv.conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(charlie_message_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends proposal to user
            # Motivated by: three separate messages requesting items for shared order
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Alice, Bob, and Charlie each messaged you requesting items for a shared order. Would you like me to create a group chat, search for their items, and place the order together to save on shipping?",
                )
                .oracle()
                .depends_on(read_charlie_event, delay_seconds=3)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please coordinate the group order for us!")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent creates group conversation with all three participants
            # Motivated by: user accepted proposal to coordinate group order
            group_conv_event = (
                messaging_app.create_group_conversation(
                    user_ids=[alice_id, bob_id, charlie_id],
                    title="Shared Order Group",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent searches for wireless headphones (Alice's request)
            # Motivated by: Alice's message content mentioned "wireless headphones"
            search_headphones_event = (
                shopping_app.search_product(
                    product_name="Wireless Headphones",
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(group_conv_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent searches for laptop stand (Bob's request)
            # Motivated by: Bob's message content mentioned "laptop stand"
            search_stand_event = (
                shopping_app.search_product(
                    product_name="Laptop Stand",
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(search_headphones_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent searches for USB hub (Charlie's request)
            # Motivated by: Charlie's message content mentioned "USB hub"
            search_hub_event = (
                shopping_app.search_product(
                    product_name="USB Hub",
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(search_stand_event, delay_seconds=1)
            )

            # Oracle Event 10: Agent adds wireless headphones to cart
            # Motivated by: search results from search_headphones_event revealed item_headphones_001
            add_headphones_event = (
                shopping_app.add_to_cart(
                    item_id="item_headphones_001",
                    quantity=1,
                )
                .oracle()
                .depends_on(search_hub_event, delay_seconds=2)
            )

            # Oracle Event 11: Agent adds laptop stand to cart
            # Motivated by: search results from search_stand_event revealed item_stand_002
            add_stand_event = (
                shopping_app.add_to_cart(
                    item_id="item_stand_002",
                    quantity=1,
                )
                .oracle()
                .depends_on(add_headphones_event, delay_seconds=1)
            )

            # Oracle Event 12: Agent adds USB hub to cart
            # Motivated by: search results from search_hub_event revealed item_hub_003
            add_hub_event = (
                shopping_app.add_to_cart(
                    item_id="item_hub_003",
                    quantity=1,
                )
                .oracle()
                .depends_on(add_stand_event, delay_seconds=1)
            )

            # Oracle Event 13: Agent checks discount code availability
            # Motivated by: scenario description mentions "apply any available discount codes"
            check_discount_event = (
                shopping_app.get_discount_code_info(discount_code="BULKORDER10")
                .oracle()
                .depends_on(add_hub_event, delay_seconds=2)
            )

            # Oracle Event 14: Agent completes checkout with discount code
            # Motivated by: all items added to cart, discount validated via check_discount_event
            checkout_event = (
                shopping_app.checkout(discount_code="BULKORDER10")
                .oracle()
                .depends_on(check_discount_event, delay_seconds=2)
            )

            # Oracle Event 15: Agent sends order confirmation to group conversation
            # Motivated by: checkout completed successfully, need to inform all participants
            confirmation_event = (
                aui.send_message_to_user(
                    content="Order placed successfully! All three items have been ordered with the BULKORDER10 discount applied. The group order is complete.",
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=3)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            alice_message_event,
            bob_message_event,
            charlie_message_event,
            read_alice_event,
            read_bob_event,
            read_charlie_event,
            proposal_event,
            acceptance_event,
            group_conv_event,
            search_headphones_event,
            search_stand_event,
            search_hub_event,
            add_headphones_event,
            add_stand_event,
            add_hub_event,
            check_discount_event,
            checkout_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent events
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal mentioning group order coordination with all three participants
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(name in e.action.args.get("content", "") for name in ["Alice", "Bob", "Charlie"])
                for e in agent_events
            )

            # STRICT Check 2: Agent read conversations to understand requests
            # Should have at least one read_conversation call (flexible on exact count)
            read_conversations_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                for e in agent_events
            )

            # STRICT Check 3: Agent created group conversation with all three participants
            group_conv_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "create_group_conversation"
                and "alice_123" in e.action.args.get("user_ids", [])
                and "bob_456" in e.action.args.get("user_ids", [])
                and "charlie_789" in e.action.args.get("user_ids", [])
                for e in agent_events
            )

            # STRICT Check 4: Agent searched for all three products by name
            # Look for searches that would find the requested items (flexible on exact search terms)
            headphones_search = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
                and "headphone" in e.action.args.get("product_name", "").lower()
                for e in agent_events
            )

            stand_search = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
                and "stand" in e.action.args.get("product_name", "").lower()
                for e in agent_events
            )

            hub_search = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
                and "hub" in e.action.args.get("product_name", "").lower()
                for e in agent_events
            )

            # STRICT Check 5: Agent added all three items to cart
            headphones_added = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == "item_headphones_001"
                for e in agent_events
            )

            stand_added = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == "item_stand_002"
                for e in agent_events
            )

            hub_added = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == "item_hub_003"
                for e in agent_events
            )

            # STRICT Check 6: Agent checked or used discount code (flexible - either get_discount_code_info or direct checkout with code)
            discount_handled = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and (
                    (
                        e.action.function_name == "get_discount_code_info"
                        and "BULKORDER10" in str(e.action.args.get("discount_code", ""))
                    )
                    or (
                        e.action.function_name == "checkout"
                        and "BULKORDER10" in str(e.action.args.get("discount_code", ""))
                    )
                )
                for e in agent_events
            )

            # STRICT Check 7: Agent completed checkout
            checkout_completed = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                for e in agent_events
            )

            # FLEXIBLE Check 8: Agent sent confirmation message (optional per guidelines)
            # Not enforcing this as strictly required unless scenario explicitly demands it
            confirmation_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Combine all strict checks
            all_products_searched = headphones_search and stand_search and hub_search
            all_products_added = headphones_added and stand_added and hub_added

            success = (
                proposal_found
                and read_conversations_found
                and group_conv_created
                and all_products_searched
                and all_products_added
                and discount_handled
                and checkout_completed
            )

            # Build rationale for failure
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal to coordinate group order")
                if not read_conversations_found:
                    missing_checks.append("reading conversations to understand requests")
                if not group_conv_created:
                    missing_checks.append("group conversation creation with all participants")
                if not all_products_searched:
                    missing_checks.append("product searches for all three items")
                if not all_products_added:
                    missing_checks.append("adding all three products to cart")
                if not discount_handled:
                    missing_checks.append("discount code handling")
                if not checkout_completed:
                    missing_checks.append("checkout completion")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
