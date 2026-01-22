"""Scenario: Agent accommodates dietary restrictions by replacing order items with GF/DF alternatives."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.note import StatefulNotesApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("dietary_accommodation_dinner_party")
class DietaryAccommodationDinnerParty(PASScenario):
    """Agent accommodates dietary restrictions by replacing shopping order with GF/DF alternatives.

    The user is hosting a dinner party and has a grocery list note with planned items. They have
    already placed a shopping order with regular ingredients. Rachel Foster, one of the guests,
    sends a message explaining she has recently developed lactose intolerance and celiac disease,
    and asks if they can use dairy-free and gluten-free ingredients for dinner.

    The agent must:
    1. Detect Rachel's message about dietary restrictions
    2. Check the grocery list note to understand what's planned for the dinner party
    3. Check recent orders to find items that conflict with Rachel's restrictions
    4. Propose canceling the current order and replacing with GF/DF alternatives
    5. After user acceptance, cancel the order and place a new one with GF/DF items

    This scenario exercises cross-app coordination (messaging → notes → shopping), dietary
    accommodation reasoning, and order modification workflow.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize MessagingApp with Rachel Foster
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.add_users(["Rachel Foster"])
        self.rachel_id = self.messaging.name_to_id["Rachel Foster"]

        # Create conversation with Rachel
        rachel_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, self.rachel_id],
            messages=[
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Hey Rachel! Looking forward to the dinner party this Saturday!",
                ),
                MessageV2(
                    sender_id=self.rachel_id,
                    content="Me too! Can't wait to catch up with everyone.",
                ),
            ],
        )
        self.messaging.add_conversation(rachel_conv)
        self.rachel_conversation_id = rachel_conv.conversation_id

        # Initialize NotesApp with grocery list
        self.notes = StatefulNotesApp(name="Notes")
        self.grocery_note_id = self.notes.create_note(
            folder="Personal",
            title="Dinner Party Grocery List",
            content="""Dinner Party - Saturday
Guests: Rachel Foster, David Martinez, Sarah Chen

Menu:
- Main: Lasagna
- Appetizer: Cheese platter with crackers
- Side: Garlic bread
- Dessert: Tiramisu

Shopping list:
1. Classic Beef Lasagna (family size)
2. Artisan Cheese Platter
3. Garlic Bread
4. Tiramisu Dessert""",
        )

        # Initialize ShoppingApp with products
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Product 1: Lasagna - two variants
        lasagna_id = self.shopping.add_product("Lasagna")
        self.item_lasagna_regular = self.shopping.add_item_to_product(
            lasagna_id, price=18.99, options={"size": "family", "contains": "wheat, dairy, beef"}
        )
        self.item_lasagna_gf_df = self.shopping.add_item_to_product(
            lasagna_id,
            price=21.99,
            options={
                "size": "family",
                "contains": "rice pasta, vegan cheese, beef",
                "gluten_free": True,
                "dairy_free": True,
            },
        )

        # Product 2: Cheese Platter - two variants
        cheese_id = self.shopping.add_product("Cheese Platter")
        self.item_cheese_regular = self.shopping.add_item_to_product(
            cheese_id, price=24.50, options={"variety": "mixed", "contains": "dairy"}
        )
        self.item_cheese_df = self.shopping.add_item_to_product(
            cheese_id,
            price=26.50,
            options={"variety": "vegan assortment", "contains": "cashew, almond", "dairy_free": True},
        )

        # Product 3: Garlic Bread - two variants
        bread_id = self.shopping.add_product("Garlic Bread")
        self.item_bread_regular = self.shopping.add_item_to_product(
            bread_id, price=6.99, options={"type": "sourdough", "contains": "wheat, butter"}
        )
        self.item_bread_gf_df = self.shopping.add_item_to_product(
            bread_id,
            price=8.99,
            options={
                "type": "rice flour",
                "contains": "rice flour, olive oil",
                "gluten_free": True,
                "dairy_free": True,
            },
        )

        # Product 4: Dessert - two variants
        dessert_id = self.shopping.add_product("Tiramisu")
        self.item_dessert_regular = self.shopping.add_item_to_product(
            dessert_id, price=12.99, options={"size": "large", "contains": "wheat, dairy, eggs, coffee"}
        )
        self.item_dessert_gf_df = self.shopping.add_item_to_product(
            dessert_id,
            price=14.99,
            options={
                "size": "large",
                "type": "chocolate mousse",
                "contains": "coconut cream, cocoa",
                "gluten_free": True,
                "dairy_free": True,
            },
        )

        # Extra products not in grocery list
        wine_id = self.shopping.add_product("Red Wine")
        self.shopping.add_item_to_product(
            wine_id, price=15.99, options={"type": "Cabernet Sauvignon", "volume": "750ml"}
        )

        salad_id = self.shopping.add_product("Caesar Salad Kit")
        self.shopping.add_item_to_product(salad_id, price=9.99, options={"contains": "romaine, parmesan, croutons"})
        self.shopping.add_item_to_product(
            salad_id,
            price=11.99,
            options={"contains": "romaine, nutritional yeast", "gluten_free": True, "dairy_free": True},
        )

        # Create existing order with regular items
        order_date = datetime(2025, 11, 16, 10, 0, 0, tzinfo=UTC)
        self.order_id = self.shopping.add_order_multiple_items(
            order_id="order_dinner_001",
            order_status="processed",
            order_date=order_date.timestamp(),
            order_total=63.47,
            items={
                self.item_lasagna_regular: 1,
                self.item_cheese_regular: 1,
                self.item_bread_regular: 1,
                self.item_dessert_regular: 1,
            },
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.notes, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - Rachel's message triggers dietary accommodation workflow."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        notes_app = self.get_typed_app(StatefulNotesApp, "Notes")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # ENV: Rachel sends message about dietary restrictions
            rachel_message_event = messaging_app.create_and_add_message(
                conversation_id=self.rachel_conversation_id,
                sender_id=self.rachel_id,
                content="Hey! I wanted to give you a heads up - I've recently been diagnosed with lactose intolerance and celiac disease. Can we use dairy-free and gluten-free ingredients for dinner?",
            ).delayed(5)

            # Oracle: Agent reads the conversation to understand the request
            read_conversation_event = (
                messaging_app.read_conversation(conversation_id=self.rachel_conversation_id, offset=0, limit=10)
                .oracle()
                .depends_on(rachel_message_event, delay_seconds=2)
            )

            # Oracle: Agent checks grocery list note
            check_notes_event = (
                notes_app.search_notes(query="dinner party")
                .oracle()
                .depends_on(read_conversation_event, delay_seconds=1)
            )

            # Oracle: Agent checks existing orders
            check_orders_event = shopping_app.list_orders().oracle().depends_on(check_notes_event, delay_seconds=1)

            # Oracle: Agent gets order details
            order_details_event = (
                shopping_app.get_order_details(order_id=self.order_id)
                .oracle()
                .depends_on(check_orders_event, delay_seconds=1)
            )

            # Oracle: Agent proposes replacing order with GF/DF items
            proposal_event = (
                aui.send_message_to_user(
                    content="Rachel mentioned she needs dairy-free and gluten-free options for dinner. I checked your existing order for the dinner party and found items containing gluten and dairy. Would you like me to cancel the current order and replace it with gluten-free, dairy-free alternatives?"
                )
                .oracle()
                .depends_on(order_details_event, delay_seconds=2)
            )

            # Oracle: User accepts
            acceptance_event = (
                aui.accept_proposal(content="Yes, please update the order.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle: Agent cancels the existing order
            cancel_order_event = (
                shopping_app.cancel_order(order_id=self.order_id).oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle: Agent adds GF/DF lasagna to cart
            add_lasagna_event = (
                shopping_app.add_to_cart(item_id=self.item_lasagna_gf_df, quantity=1)
                .oracle()
                .depends_on(cancel_order_event, delay_seconds=1)
            )

            # Oracle: Agent adds dairy-free cheese to cart
            add_cheese_event = (
                shopping_app.add_to_cart(item_id=self.item_cheese_df, quantity=1)
                .oracle()
                .depends_on(add_lasagna_event, delay_seconds=1)
            )

            # Oracle: Agent adds GF/DF bread to cart
            add_bread_event = (
                shopping_app.add_to_cart(item_id=self.item_bread_gf_df, quantity=1)
                .oracle()
                .depends_on(add_cheese_event, delay_seconds=1)
            )

            # Oracle: Agent adds GF/DF dessert to cart
            add_dessert_event = (
                shopping_app.add_to_cart(item_id=self.item_dessert_gf_df, quantity=1)
                .oracle()
                .depends_on(add_bread_event, delay_seconds=1)
            )

            # Oracle: Agent completes checkout
            checkout_event = shopping_app.checkout().oracle().depends_on(add_dessert_event, delay_seconds=1)

        self.events = [
            rachel_message_event,
            read_conversation_event,
            check_notes_event,
            check_orders_event,
            order_details_event,
            proposal_event,
            acceptance_event,
            cancel_order_event,
            add_lasagna_event,
            add_cheese_event,
            add_bread_event,
            add_dessert_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent achieved the essential outcomes for this scenario.

        Essential outcomes (what we check):
        - Agent sent proposal to user about replacing items
        - Agent cancelled the original order
        - Agent completed checkout with new items

        Not checked (intermediate steps the agent might do differently):
        - How agent read messages (read_conversation, etc.)
        - How agent found notes (search_notes, list_notes, etc.)
        - How agent checked orders (list_orders, get_order_details, etc.)
        - Which specific items agent added (as long as checkout completed)
        """
        try:
            log_entries = env.event_log.list_view()

            # CHECK 1: Agent sent proposal to user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # CHECK 2: Agent cancelled the original order
            order_cancelled = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "cancel_order"
                and e.action.args.get("order_id") == self.order_id
                for e in log_entries
            )

            # CHECK 3: Agent completed checkout
            checkout_completed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                for e in log_entries
            )

            success = proposal_found and order_cancelled and checkout_completed

            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not send proposal to user")
                if not order_cancelled:
                    failed_checks.append(f"agent did not cancel original order ({self.order_id})")
                if not checkout_completed:
                    failed_checks.append("agent did not complete checkout with new items")
                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
