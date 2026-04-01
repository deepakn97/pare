from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.messaging_v2 import ConversationV2
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


@register_scenario("event_prep_shopping_from_message")
class EventPrepShoppingFromMessage(PASScenario):
    """Agent identifies user's unmet shopping need from friend's event reminder message and assists with purchase.

    Friend Sam Chen messages: "Excited for the hiking trip this Saturday! I just got my new trail boots. Have you gotten your gear ready?" The user has no recent orders for hiking equipment and the cart is empty. The agent must: 1. Parse Sam's message to identify the upcoming event (hiking trip this Saturday). 2. Infer from Sam's question that the user needs to prepare hiking gear. 3. Search the shopping catalog for essential hiking items like boots, backpack, or water bottle. 4. Recognize the time constraint (trip is in a few days) and propose adding hiking essentials to the cart. 5. After user acceptance, add recommended items to cart and proceed to checkout.

    This scenario exercises event and commitment extraction from casual messaging, inference of unmet preparation needs from conversational context, time-sensitive shopping assistance before a deadline, catalog search for activity-specific products, and proactive goal completion to fulfill social commitments.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data for hiking trip preparation scenario.

        Baseline state:
        - Messaging: User "Me" and contact Sam Chen (with phone and user ID mapping)
        - Shopping: Empty cart, no recent hiking-related orders
        - System: Standard home screen
        - Agent UI: Standard interface
        """
        # Initialize core apps
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app with user and contact
        self.messaging = StatefulMessagingApp(name="Messages")
        # Add Sam Chen as a contact in messaging app
        self.messaging.add_contacts([("Sam Chen", "555-123-4567")])

        # Create conversation with Sam Chen for messages to arrive
        sam_id = self.messaging.name_to_id["Sam Chen"]
        sam_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, sam_id],
            title="Sam Chen",
        )
        self.messaging.add_conversation(sam_conv)
        self.sam_conversation_id = sam_conv.conversation_id

        # Initialize shopping app with empty cart, no orders, and a small hiking catalog
        self.shopping = StatefulShoppingApp(name="Shopping")
        # Seed catalog with hiking products whose IDs are used later in build_events_flow.
        # This keeps the catalog realistic while ensuring search_product, get_product_details,
        # and add_to_cart calls all operate on existing products/items.
        hiking_products: dict[str, dict[str, Any]] = {
            "prod-hiking-boots-001": {
                "name": "Trail Hiking Boots",
                "product_id": "prod-hiking-boots-001",
                "variants": {
                    "item-hiking-boots-001": {
                        "price": 120.0,
                        "available": True,
                        "item_id": "item-hiking-boots-001",
                        "options": {"category": "boots", "terrain": "trail"},
                    }
                },
            },
            "prod-hiking-backpack-001": {
                "name": "Hiking Backpack 30L",
                "product_id": "prod-hiking-backpack-001",
                "variants": {
                    "item-hiking-backpack-001": {
                        "price": 80.0,
                        "available": True,
                        "item_id": "item-hiking-backpack-001",
                        "options": {"category": "backpack", "capacity_liters": 30},
                    }
                },
            },
        }
        # Load products directly into the underlying Meta-ARE ShoppingApp so that:
        # - search_product("hiking"/"boots"/"backpack") returns matching products
        # - get_product_details("prod-hiking-boots-001") succeeds
        # - add_to_cart("item-hiking-...") sees valid, available items
        self.shopping.load_products_from_dict(hiking_products)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize app references
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Sam Chen sends message about hiking trip
            sam_id = messaging_app.name_to_id["Sam Chen"]
            message_event = messaging_app.create_and_add_message(
                conversation_id=self.sam_conversation_id,
                sender_id=sam_id,
                content="Excited for the hiking trip this Saturday! I just got my new trail boots. Have you gotten your gear ready?",
            ).delayed(15)

            # Oracle Event 1: Agent checks recent orders to verify no hiking gear purchased
            check_orders_event = shopping_app.list_orders().oracle().depends_on(message_event, delay_seconds=2)

            # Oracle Event 2: Agent checks cart to verify it's empty
            check_cart_event = shopping_app.list_cart().oracle().depends_on(check_orders_event, delay_seconds=1)

            # Oracle Event 3: Agent searches shopping catalog for hiking gear
            search_hiking_event = (
                shopping_app.search_product(product_name="hiking", offset=0, limit=10)
                .oracle()
                .depends_on(check_cart_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent sends proposal to user
            proposal_event = (
                aui.send_message_to_user(
                    content="Sam reminded you about the hiking trip this Saturday and asked if you've gotten your gear ready. I checked your recent orders and cart - you haven't purchased any hiking equipment yet. Would you like me to help you find and purchase essential hiking gear before Saturday?"
                )
                .oracle()
                .depends_on(search_hiking_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please help me get hiking gear.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent lists available hiking products to choose from
            list_products_event = (
                shopping_app.list_all_products(offset=0, limit=10)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent searches for specific hiking items (boots)
            search_boots_event = (
                shopping_app.search_product(product_name="boots", offset=0, limit=5)
                .oracle()
                .depends_on(list_products_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent gets details of a hiking boots product
            # Note: This uses a placeholder product_id that must exist in the catalog
            # In a real scenario, this would be extracted from search results
            get_boots_details_event = (
                shopping_app.get_product_details(product_id="prod-hiking-boots-001")
                .oracle()
                .depends_on(search_boots_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent adds hiking boots item to cart
            # Note: item_id must be extracted from product details
            add_boots_event = (
                shopping_app.add_to_cart(item_id="item-hiking-boots-001", quantity=1)
                .oracle()
                .depends_on(get_boots_details_event, delay_seconds=1)
            )

            # Oracle Event 10: Agent searches for backpack
            search_backpack_event = (
                shopping_app.search_product(product_name="backpack", offset=0, limit=5)
                .oracle()
                .depends_on(add_boots_event, delay_seconds=1)
            )

            # Oracle Event 11: Agent adds backpack to cart
            add_backpack_event = (
                shopping_app.add_to_cart(item_id="item-hiking-backpack-001", quantity=1)
                .oracle()
                .depends_on(search_backpack_event, delay_seconds=1)
            )

            # Oracle Event 12: Agent checks cart before checkout
            verify_cart_event = shopping_app.list_cart().oracle().depends_on(add_backpack_event, delay_seconds=1)

            # Oracle Event 13: Agent proceeds with checkout
            checkout_event = shopping_app.checkout().oracle().depends_on(verify_cart_event, delay_seconds=2)

            # Oracle Event 14: Agent confirms completion to user
            completion_event = (
                aui.send_message_to_user(
                    content="I've successfully ordered hiking boots and a backpack for your Saturday hiking trip with Sam. The order has been placed and you're all set!"
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            message_event,
            check_orders_event,
            check_cart_event,
            search_hiking_event,
            proposal_event,
            acceptance_event,
            list_products_event,
            search_boots_event,
            get_boots_details_event,
            add_boots_event,
            search_backpack_event,
            add_backpack_event,
            verify_cart_event,
            checkout_event,
            completion_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT CHECK 1: Agent sent proposal to user about hiking trip preparation
            # Must reference Sam's message about the hiking trip and the user's preparation need
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "hiking" in e.action.args.get("content", "").lower()
                and (
                    "sam" in e.action.args.get("content", "").lower()
                    or "saturday" in e.action.args.get("content", "").lower()
                    or "trip" in e.action.args.get("content", "").lower()
                )
                for e in agent_events
            )

            # STRICT CHECK 2: Agent searched for hiking-related products
            # Must perform catalog search with hiking-relevant terms
            search_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
                and "product_name" in e.action.args
                and e.action.args["product_name"]  # Non-empty search term
                for e in agent_events
            )

            # STRICT CHECK 3: Agent added at least one item to cart
            # Must use add_to_cart with non-empty item_id
            add_to_cart_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and "item_id" in e.action.args
                and e.action.args["item_id"]  # Non-empty item_id
                for e in agent_events
            )

            # STRICT CHECK 4: Agent completed checkout
            # Must call checkout method to finalize purchase
            checkout_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                for e in agent_events
            )

            # Build rationale for failures
            failed_checks = []
            if not proposal_found:
                failed_checks.append("no proposal message to user about hiking trip preparation")
            if not search_found:
                failed_checks.append("no product search performed")
            if not add_to_cart_found:
                failed_checks.append("no items added to cart")
            if not checkout_found:
                failed_checks.append("no checkout completed")

            success = proposal_found and search_found and add_to_cart_found and checkout_found
            rationale = "; ".join(failed_checks) if failed_checks else None

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
