"""Agent purchases Secret Santa gift by cross-referencing coworker notes with shopping products."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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


@register_scenario("secret_santa_gift_from_notes")
class SecretSantaGiftFromNotes(PASScenario):
    """Agent purchases Secret Santa gift by cross-referencing coworker notes with shopping products.

    The user drew Sarah's name for the office Secret Santa. They have a note with a table
    of coworker gift preferences collected over time. Alex, a coworker also participating
    in Secret Santa, messages to check if the user has figured out what to get Sarah yet,
    mentioning the $30-40 budget.

    The agent must:
    1. Detect Alex's message asking about the Secret Santa gift
    2. Search Notes for Sarah's gift preferences
    3. Read the coworker notes table to identify Sarah prefers herbal tea
    4. Search Shopping for matching products within budget
    5. Propose purchasing the herbal tea sampler ($34.99)
    6. After user approval, complete the purchase
    7. Reply to Alex confirming the gift is sorted (without revealing what it is)

    This scenario exercises cross-app information retrieval where Notes contains personal
    knowledge (coworker preferences) that Shopping cannot provide, triggered by a messaging
    event that creates urgency for action.
    """

    start_time = datetime(2025, 12, 15, 10, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes app with coworker gift preferences
        self.notes = StatefulNotesApp(name="Notes")

        # Create note with Secret Santa gift ideas table
        gift_note_content = """Secret Santa Gift Ideas:

| Name   | Gift Category   | Notes                                        |
|--------|-----------------|----------------------------------------------|
| Sarah  | Tea/Beverages   | Prefers herbal tea, wants to try new flavors |
| Mike   | Sports          | Big basketball fan, watches every game       |
| Lisa   | Outdoor/Hiking  | Goes hiking every weekend                    |
| Tom    | Books           | Loves mystery novels                         |"""

        self.gift_note_id = self.notes.create_note_with_time(
            folder="Work",
            title="Secret Santa Gift Ideas",
            content=gift_note_content,
            pinned=False,
            created_at="2025-12-01 09:00:00",
            updated_at="2025-12-01 09:00:00",
        )

        # Initialize Messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add Alex as a user
        self.messaging.add_users(["Alex Thompson"])
        self.alex_id = self.messaging.name_to_id["Alex Thompson"]

        # Create conversation by having user send first message to Alex
        # send_message auto-creates conversation and returns conversation_id
        self.alex_convo_id = self.messaging.send_message(
            user_id=self.alex_id,
            content="I got Sarah for Secret Santa!",
        )

        # Initialize Shopping app with products
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add herbal tea sampler (matches Sarah's preference AND budget)
        tea_prod_id = self.shopping.add_product(name="Premium Herbal Tea Sampler Set")
        self.tea_item_id = self.shopping.add_item_to_product(
            product_id=tea_prod_id,
            price=34.99,
            options={"variety": "12 flavors", "category": "beverages"},
            available=True,
        )

        # Add coffee beans (beverages but not herbal tea - Sarah's stated preference)
        coffee_prod_id = self.shopping.add_product(name="Gourmet Coffee Beans")
        self.shopping.add_item_to_product(
            product_id=coffee_prod_id,
            price=28.99,
            options={"roast": "medium", "category": "beverages"},
            available=True,
        )

        # Add basketball jersey (outside $30-40 budget, matches Mike)
        jersey_prod_id = self.shopping.add_product(name="Basketball Jersey")
        self.shopping.add_item_to_product(
            product_id=jersey_prod_id,
            price=55.99,
            options={"team": "Lakers", "category": "sports"},
            available=True,
        )

        # Add hiking water bottle (outside budget, matches Lisa)
        bottle_prod_id = self.shopping.add_product(name="Hiking Water Bottle")
        self.shopping.add_item_to_product(
            product_id=bottle_prod_id,
            price=45.99,
            options={"capacity": "32oz", "category": "outdoor"},
            available=True,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.notes, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        notes_app = self.get_typed_app(StatefulNotesApp, "Notes")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event: Alex asks if user figured out Sarah's gift
            alex_message_event = messaging_app.create_and_add_message(
                conversation_id=self.alex_convo_id,
                sender_id=self.alex_id,
                content="Nice! Have you figured out what to get her yet? Remember the budget is $30-40",
            ).delayed(10)

            # Oracle Event 1: Agent searches notes for Sarah's gift preferences
            search_notes_event = (
                notes_app.search_notes(query="Sarah").oracle().depends_on(alex_message_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent reads the gift ideas note
            read_note_event = (
                notes_app.get_note_by_id(note_id=self.gift_note_id)
                .oracle()
                .depends_on(search_notes_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent searches shopping for herbal tea
            search_shopping_event = (
                shopping_app.search_product(product_name="herbal tea")
                .oracle()
                .depends_on(read_note_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent proposes purchasing the tea sampler
            proposal_event = (
                aui.send_message_to_user(
                    content="I found your Secret Santa notes - Sarah prefers herbal tea. I found a Premium Herbal Tea Sampler Set for $34.99, which fits the $30-40 budget. Would you like me to order it?"
                )
                .oracle()
                .depends_on([alex_message_event, search_shopping_event], delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please order the tea sampler.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent adds item to cart
            add_to_cart_event = (
                shopping_app.add_to_cart(item_id=self.tea_item_id, quantity=1)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent completes checkout
            checkout_event = shopping_app.checkout().oracle().depends_on(add_to_cart_event, delay_seconds=1)

            # Oracle Event 8: Agent replies to Alex (without revealing the gift)
            reply_to_alex_event = (
                messaging_app.send_message(
                    user_id=self.alex_id,
                    content="All sorted! Got her gift taken care of.",
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent confirms to user
            confirmation_event = (
                aui.send_message_to_user(
                    content="Done! I've ordered the Premium Herbal Tea Sampler Set ($34.99) for Sarah's Secret Santa gift and let Alex know it's sorted."
                )
                .oracle()
                .depends_on(reply_to_alex_event, delay_seconds=1)
            )

        self.events = [
            alex_message_event,
            search_notes_event,
            read_note_event,
            search_shopping_event,
            proposal_event,
            acceptance_event,
            add_to_cart_event,
            checkout_event,
            reply_to_alex_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate essential outcomes: notes accessed, proposal sent, checkout completed, and reply sent to Alex."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Essential outcome 1: Agent accessed notes for gift preferences
            notes_accessed = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["search_notes", "get_note_by_id"]
                for e in agent_events
            )

            # Essential outcome 2: Agent proposed purchasing a gift
            proposal_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Essential outcome 3: Agent added herbal tea to cart and completed checkout
            tea_added_to_cart = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == self.tea_item_id
                for e in agent_events
            )

            checkout_completed = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                for e in agent_events
            )

            # Essential outcome 4: Agent replied to Alex
            reply_to_alex = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                for e in agent_events
            )

            success = notes_accessed and proposal_sent and tea_added_to_cart and checkout_completed and reply_to_alex

            if not success:
                missing = []
                if not notes_accessed:
                    missing.append("notes not accessed for gift preferences")
                if not proposal_sent:
                    missing.append("proposal to purchase gift not sent")
                if not tea_added_to_cart:
                    missing.append("herbal tea not added to cart")
                if not checkout_completed:
                    missing.append("checkout not completed")
                if not reply_to_alex:
                    missing.append("reply to Alex not sent")

                rationale = f"Validation failed: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
