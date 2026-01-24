from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.note import StatefulNotesApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("gift_history_tracking_from_order")
class GiftHistoryTrackingFromOrder(PASScenario):
    """Agent creates structured gift history notes from delivered orders and proposes complementary purchases.

    The user receives a shopping delivery notification confirming that an order containing "Premium Dark Chocolate Box" has been delivered. The delivery includes a gift note field mentioning "For Sarah's birthday". The agent must: 1) extract the product details and gift recipient from the order, 2) search the Notes app for an existing "Gift History - Sarah" note, 3) create the note if it doesn't exist or update it with the new gift entry (date, occasion, item, price), 4) search the shopping catalog for complementary gift items (e.g., wine, flowers, greeting cards), 5) add 1-2 complementary items to the cart with quantity 1, 6) propose the complementary purchase to the user with reasoning ("This pairs well with the chocolate gift"), 7) update the gift history note with the proposed complementary items.

    This scenario exercises cross-app synthesis (shopping → notes creation/organization), gift recipient tracking, product complementarity reasoning, and proactive cart management driven by relationship context rather than transactional needs.

    The delivery notification is sent via email, which includes both the product name ("Premium Dark Chocolate Box") and the gift note ("For Sarah's birthday"). The agent extracts this information from the email, then uses list_orders() to find the matching order by product name, retrieves order details to confirm, and proceeds with gift history tracking and complementary purchase recommendations.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.note = StatefulNotesApp(name="Notes")
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Populate Shopping app with gift order and complementary products
        # Gift order: Premium Dark Chocolate Box
        chocolate_product_id = self.shopping.add_product("Premium Dark Chocolate Box")
        chocolate_item_id = self.shopping.add_item_to_product(
            product_id=chocolate_product_id,
            price=34.99,
            options={"size": "Large", "type": "Assorted"},
            available=True,
        )
        chocolate_order_date = datetime(2025, 11, 17, 14, 0, 0, tzinfo=UTC)
        self.chocolate_order_id = "order_chocolate_gift_001"
        self.shopping.add_order(
            order_id=self.chocolate_order_id,
            order_status="delivered",
            order_date=chocolate_order_date.timestamp(),
            order_total=34.99,
            item_id=chocolate_item_id,
            quantity=1,
        )

        # Complementary gift products for recommendation
        # Wine product
        wine_product_id = self.shopping.add_product("Premium Red Wine")
        self.wine_item_id = self.shopping.add_item_to_product(
            product_id=wine_product_id,
            price=29.99,
            options={"type": "Cabernet Sauvignon", "size": "750ml"},
            available=True,
        )

        # Flowers product
        flowers_product_id = self.shopping.add_product("Fresh Flower Bouquet")
        self.flowers_item_id = self.shopping.add_item_to_product(
            product_id=flowers_product_id,
            price=24.99,
            options={"type": "Mixed", "occasion": "Birthday"},
            available=True,
        )

        # Greeting card product
        card_product_id = self.shopping.add_product("Birthday Greeting Card")
        self.card_item_id = self.shopping.add_item_to_product(
            product_id=card_product_id,
            price=4.99,
            options={"type": "Elegant", "occasion": "Birthday"},
            available=True,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.note, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Delivery notification email arrives with gift information
            # The email contains both product name and gift note, allowing agent to extract gift recipient
            delivery_email_event = email_app.send_email_to_user_with_id(
                email_id="delivery_chocolate_gift_001",
                sender="delivery@shop.com",
                subject="Your order has been delivered - Premium Dark Chocolate Box",
                content=(
                    "Your order has been delivered!\n\n"
                    "Order: Premium Dark Chocolate Box\n"
                    "Gift Note: For Sarah's birthday\n"
                    "Order Date: November 17, 2025\n"
                    "Total: $34.99\n\n"
                    "Thank you for your purchase!"
                ),
            ).delayed(5)

            # Oracle Event 1: Agent reads the delivery email to extract product and gift recipient information
            # Motivated by: delivery email notification provides product name and gift note
            read_email_event = (
                email_app.get_email_by_id(email_id="delivery_chocolate_gift_001", folder_name="INBOX")
                .oracle()
                .depends_on([delivery_email_event], delay_seconds=2)
            )

            # Oracle Event 2: Agent lists orders to find the matching order by product name
            # Motivated by: email mentions "Premium Dark Chocolate Box", agent needs to find the order_id
            list_orders_event = shopping_app.list_orders().oracle().depends_on([read_email_event], delay_seconds=1)

            # Oracle Event 3: Agent retrieves order details to confirm product and get price
            # Motivated by: list_orders revealed order_id matching "Premium Dark Chocolate Box"
            get_order_details_event = (
                shopping_app.get_order_details(order_id=self.chocolate_order_id)
                .oracle()
                .depends_on([list_orders_event], delay_seconds=1)
            )

            # Oracle Event 4: Agent searches notes for existing gift history for Sarah
            # Motivated by: email gift note mentions "For Sarah's birthday", agent should track gift history
            search_gift_note_event = (
                note_app.search_notes(query="Gift History Sarah")
                .oracle()
                .depends_on([get_order_details_event], delay_seconds=2)
            )

            # Oracle Event 5: Agent searches shopping catalog for complementary gift items
            # Motivated by: agent identified a birthday gift, should find complementary items (wine, flowers, cards)
            search_complementary_wine = (
                shopping_app.search_product(product_name="wine")
                .oracle()
                .depends_on([search_gift_note_event], delay_seconds=1)
            )

            search_complementary_flowers = (
                shopping_app.search_product(product_name="flowers")
                .oracle()
                .depends_on([search_gift_note_event], delay_seconds=1)
            )

            search_complementary_card = (
                shopping_app.search_product(product_name="greeting card")
                .oracle()
                .depends_on([search_gift_note_event], delay_seconds=1)
            )

            # Oracle Event 6: Agent proposes creating/updating gift history and adding complementary items
            # Motivated by: delivery email with gift note, agent should track gift history and suggest complementary purchases
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your Premium Dark Chocolate Box order was delivered as a gift for Sarah's birthday ($34.99). Would you like me to: 1) create or update a gift history note for Sarah with this gift, and 2) add some complementary items to your cart (like wine, flowers, or a greeting card) that pair well with the chocolate gift?"
                )
                .oracle()
                .depends_on(
                    [search_complementary_wine, search_complementary_flowers, search_complementary_card],
                    delay_seconds=2,
                )
            )

            # Oracle Event 7: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please do that.")
                .oracle()
                .depends_on([proposal_event], delay_seconds=3)
            )

            # Oracle Event 8: Agent adds complementary items to cart (wine and flowers)
            # Motivated by: user accepted proposal to add complementary items
            add_wine_to_cart_event = (
                shopping_app.add_to_cart(item_id=self.wine_item_id, quantity=1)
                .oracle()
                .depends_on([acceptance_event], delay_seconds=1)
            )

            add_flowers_to_cart_event = (
                shopping_app.add_to_cart(item_id=self.flowers_item_id, quantity=1)
                .oracle()
                .depends_on([acceptance_event], delay_seconds=1)
            )

            # Oracle Event 9: Agent creates or updates gift history note for Sarah
            # Motivated by: user accepted proposal, agent should track the gift in notes
            # Agent searched for existing note earlier (search_gift_note_event); if found, would update it,
            # but since no note exists initially, agent creates a new gift history note
            create_or_update_gift_note_event = (
                note_app.create_note(
                    folder="Personal",
                    title="Gift History - Sarah",
                    content=(
                        "Gift History - Sarah\n\n"
                        "## November 17, 2025 - Birthday\n"
                        "- Premium Dark Chocolate Box: $34.99\n"
                        "  Occasion: Birthday\n"
                        "  Status: Delivered\n\n"
                        "## Complementary Items Suggested\n"
                        "- Premium Red Wine: $29.99\n"
                        "- Fresh Flower Bouquet: $24.99\n"
                        "  Note: These pair well with the chocolate gift"
                    ),
                )
                .oracle()
                .depends_on([add_wine_to_cart_event, add_flowers_to_cart_event], delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            delivery_email_event,
            read_email_event,
            list_orders_event,
            get_order_details_event,
            search_gift_note_event,
            search_complementary_wine,
            search_complementary_flowers,
            search_complementary_card,
            proposal_event,
            acceptance_event,
            add_wine_to_cart_event,
            add_flowers_to_cart_event,
            create_or_update_gift_note_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate final outcomes: gift history note created and complementary items added to cart."""
        try:
            log_entries = env.event_log.list_view()

            # Check final outcome 1: Gift history note created/updated for Sarah with chocolate gift
            gift_note_created_or_updated = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["create_note", "update_note"]
                and "content" in e.action.args
                and "sarah" in str(e.action.args.get("content", "")).lower()
                and "chocolate" in str(e.action.args.get("content", "")).lower()
                for e in log_entries
            )

            # Check final outcome 2: Complementary items added to cart
            items_added_to_cart = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") in [self.wine_item_id, self.flowers_item_id, self.card_item_id]
                for e in log_entries
            )

            success = gift_note_created_or_updated and items_added_to_cart

            if not success:
                missing_checks = []
                if not gift_note_created_or_updated:
                    missing_checks.append("gift history note for Sarah not created/updated")
                if not items_added_to_cart:
                    missing_checks.append("complementary items not added to cart")
                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
