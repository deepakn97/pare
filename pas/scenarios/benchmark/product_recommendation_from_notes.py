"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2
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


@register_scenario("product_recommendation_from_notes")
class ProductRecommendationFromNotes(PASScenario):
    """Agent provides personalized product recommendation by combining shopping catalog search with user's saved research notes.

    The user has a note in their "Shopping Research" folder titled "Running Shoes Comparison" containing personal evaluations: "CloudRunner Pro: Great cushioning but too narrow. TrailBlazer X: Perfect fit, excellent for trails." The user receives a message from their friend Sarah Chen asking "Hey! I'm looking for good running shoes for trail running. Any recommendations?" The agent must:
    1. Detect the product recommendation request in the incoming message
    2. Search the Notes app for relevant user research (query: "running shoes")
    3. Read the comparison note to understand the user's prior evaluation
    4. Search the Shopping app catalog to verify TrailBlazer X availability and get current details
    5. Reply to Sarah with a personalized recommendation citing the user's positive experience with TrailBlazer X for trail running

    This scenario exercises question detection in messaging, cross-app information synthesis (Notes + Shopping), personal context retrieval, product catalog lookup, and contextual reply generation based on the user's own documented preferences..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")
        # Create "Shopping Research" folder and seed the running shoes comparison note
        self.note.new_folder("Shopping Research")
        self.note.create_note_with_time(
            folder="Shopping Research",
            title="Running Shoes Comparison",
            content="CloudRunner Pro: Great cushioning but too narrow. TrailBlazer X: Perfect fit, excellent for trails.",
            pinned=False,
            created_at="2025-11-15 14:30:00",
            updated_at="2025-11-15 14:30:00",
        )

        # Initialize Shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")
        # Seed shopping catalog with TrailBlazer X and other running shoes
        from are.simulation.apps.shopping import Item, Product
        from are.simulation.types import disable_events

        with disable_events():
            # TrailBlazer X product
            trailblazer_product = Product(
                name="TrailBlazer X",
                product_id="tb_x_001",
                variants={
                    "Men's Size 10": Item(price=129.99, available=True, item_id="tb_x_m10"),
                    "Men's Size 11": Item(price=129.99, available=True, item_id="tb_x_m11"),
                    "Women's Size 8": Item(price=129.99, available=True, item_id="tb_x_w8"),
                },
            )
            self.shopping.products["tb_x_001"] = trailblazer_product

            # CloudRunner Pro product
            cloudrunner_product = Product(
                name="CloudRunner Pro",
                product_id="cr_pro_001",
                variants={
                    "Men's Size 10": Item(price=139.99, available=True, item_id="cr_pro_m10"),
                    "Men's Size 11": Item(price=139.99, available=True, item_id="cr_pro_m11"),
                },
            )
            self.shopping.products["cr_pro_001"] = cloudrunner_product

        # Initialize Messaging app
        self.messaging = StatefulMessagingApp(name="Messages")
        # Add Sarah Chen as a contact
        sarah_contact = Contact(
            first_name="Sarah",
            last_name="Chen",
            contact_id="sarah_chen_001",
            phone="+1234567890",
            email="sarah.chen@example.com",
        )
        self.messaging.add_users(["Sarah Chen"])
        sarah_user_id = self.messaging.name_to_id.get("Sarah Chen")

        # Create an existing conversation with Sarah (but no messages yet - the trigger will arrive as an event)
        if sarah_user_id:
            conversation = ConversationV2(
                participant_ids=[self.messaging.current_user_id, sarah_user_id],
                conversation_id="conv_sarah_001",
                title="Sarah Chen",
                messages=[],
                last_updated=self.start_time - 86400,  # 1 day ago
            )
            self.messaging.add_conversation(conversation)

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.shopping, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        # Retrieve Sarah's user_id from seeded data
        sarah_user_id = self.messaging.name_to_id.get("Sarah Chen")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Sarah sends a message asking for running shoe recommendations
            message_event = messaging_app.create_and_add_message(
                conversation_id="conv_sarah_001",
                sender_id=sarah_user_id,
                content="Hey! I'm looking for good running shoes for trail running. Any recommendations? I think you might have a good one in your notes.",
            ).delayed(10)

            # Oracle Event 1: Agent searches notes for "running shoes" (motivated by Sarah's question about running shoes)
            search_notes_event = (
                note_app.search_notes(query="running shoes").oracle().depends_on(message_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent reads the specific note to get full details (motivated by search results revealing a "Running Shoes Comparison" note)
            read_note_event = (
                note_app.get_note_by_id(
                    note_id=next(iter(self.note.folders["Shopping Research"].notes.values())).note_id
                )
                .oracle()
                .depends_on(search_notes_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent lists products to find TrailBlazer X (motivated by note content mentioning "TrailBlazer X")
            list_products_event = (
                shopping_app.list_all_products(offset=0, limit=10).oracle().depends_on(read_note_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent gets TrailBlazer X details (motivated by product listing revealing TrailBlazer X product_id)
            get_product_event = (
                shopping_app.get_product_details(product_id="tb_x_001")
                .oracle()
                .depends_on(list_products_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent sends proposal to user offering to recommend TrailBlazer X to Sarah
            proposal_event = (
                aui.send_message_to_user(
                    content="Sarah Chen is asking for trail running shoe recommendations. Based on your notes, you found the TrailBlazer X to be perfect for trails. Would you like me to recommend it to her?"
                )
                .oracle()
                .depends_on(get_product_event, delay_seconds=2)
            )

            # Oracle Event 6: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please share that recommendation with Sarah.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 7: Agent sends reply to Sarah with the recommendation (motivated by user acceptance)
            reply_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id="conv_sarah_001",
                    content="I'd recommend the TrailBlazer X! I found them to have a perfect fit and they're excellent for trail running. They're available for $129.99.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            message_event,
            search_notes_event,
            read_note_event,
            list_products_event,
            get_product_event,
            proposal_event,
            acceptance_event,
            reply_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1 (STRICT): Agent searched notes for relevant information
            notes_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "search_notes"
                for e in log_entries
            )

            # Check 2 (STRICT): Agent read the specific note to understand user's evaluation
            note_read_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "get_note_by_id"
                for e in log_entries
            )

            # Check 3 (STRICT): Agent searched shopping catalog (using list_all_products or similar)
            shopping_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name in ["list_all_products", "get_product_details"]
                for e in log_entries
            )

            # Check 4 (STRICT): Agent sent proposal to user referencing Sarah Chen and TrailBlazer X
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 5 (STRICT): Agent received user acceptance
            acceptance_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "accept_proposal"
                for e in log_entries
            )

            # Check 6 (FLEXIBLE): Agent sent message to Sarah (content flexibility allowed)
            reply_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name
                in ["send_message_to_user", "send_message_to_group_conversation", "send_message"]
                for e in log_entries
            )

            # Build rationale if strict checks fail
            if not (
                notes_search_found
                and note_read_found
                and shopping_search_found
                and proposal_found
                and acceptance_found
                and reply_sent
            ):
                missing = []
                if not notes_search_found:
                    missing.append("notes search for running shoes")
                if not note_read_found:
                    missing.append("reading the comparison note")
                if not shopping_search_found:
                    missing.append("shopping catalog search")
                if not proposal_found:
                    missing.append("proposal to user about recommending TrailBlazer X to Sarah")
                if not acceptance_found:
                    missing.append("user acceptance event")
                if not reply_sent:
                    missing.append("reply message sent to Sarah Chen")

                rationale = f"Missing critical agent actions: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
