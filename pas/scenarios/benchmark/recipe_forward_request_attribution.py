from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
    StatefulMessagingApp,
)
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("recipe_forward_request_attribution")
class RecipeForwardRequestAttribution(PASScenario):
    """Agent forwards previously shared content to a new contact based on third-party request.

    The user receives a message from their friend Jessica Lee saying "Hey! Remember that chocolate cake recipe you sent me last month? It was amazing and my cousin Sarah loved the photo I showed her. Can you send it to her too? Her number is +1-650-555-0199." The agent must:
    1. Parse the forwarding request identifying the content (chocolate cake recipe) and the new recipient (Sarah, Jessica's cousin, with phone number)
    2. Search message history with Jessica Lee to locate the original recipe content that was shared
    3. Search notes for any saved version of the recipe to ensure complete information
    4. Add Sarah to contacts with appropriate context (Jessica's cousin, requested chocolate cake recipe)
    5. Send the recipe content to Sarah via message with introduction
    6. Create or update a note documenting recipe distribution history (who received it and when)

    This scenario exercises retrospective content search across apps (messaging history + notes), third-party information forwarding with proper attribution, relationship-aware contact creation (cousin of existing contact), and distribution tracking for future reference..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts app
        self.contacts = StatefulContactsApp(name="Contacts")

        # Add user contact
        user_contact = Contact(
            first_name="Alex",
            last_name="Johnson",
            phone="+1-555-0100",
            email="alex.johnson@email.com",
            is_user=True,
        )
        self.contacts.add_contact(user_contact)

        # Add Jessica Lee contact
        jessica_contact = Contact(
            first_name="Jessica",
            last_name="Lee",
            phone="+1-555-0150",
            email="jessica.lee@email.com",
            description="Friend from college",
        )
        self.contacts.add_contact(jessica_contact)

        # Initialize Messaging app
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.current_user_name = f"{user_contact.first_name} {user_contact.last_name}"

        # Add contacts to messaging app
        self.messaging.add_contacts([
            (f"{user_contact.first_name} {user_contact.last_name}", user_contact.phone),
            (f"{jessica_contact.first_name} {jessica_contact.last_name}", jessica_contact.phone),
        ])

        # Create conversation with Jessica Lee containing the chocolate cake recipe
        # This happened approximately one month ago (October 18, 2025)
        recipe_timestamp = datetime(2025, 10, 18, 14, 30, 0, tzinfo=UTC).timestamp()

        jessica_conv = ConversationV2(
            conversation_id="jessica_conv_001",
            participant_ids=[user_contact.phone, jessica_contact.phone],
            title="Jessica Lee",
            last_updated=recipe_timestamp,
        )

        # Jessica initially asked for a recipe
        jessica_conv.messages.append(
            MessageV2(
                sender_id=jessica_contact.phone,
                content="Hey! Do you have that amazing chocolate cake recipe you mentioned? I'd love to try making it!",
                timestamp=recipe_timestamp - 300,  # 5 minutes before
            )
        )

        # User sent the chocolate cake recipe
        recipe_content = """Here's my famous chocolate cake recipe:

Ingredients:
- 2 cups all-purpose flour
- 2 cups sugar
- 3/4 cup unsweetened cocoa powder
- 2 tsp baking soda
- 1 tsp baking powder
- 1 tsp salt
- 2 eggs
- 1 cup strong black coffee (cooled)
- 1 cup buttermilk
- 1/2 cup vegetable oil
- 1 tsp vanilla extract

Instructions:
1. Preheat oven to 350°F (175°C). Grease two 9-inch round cake pans.
2. Mix dry ingredients (flour, sugar, cocoa, baking soda, baking powder, salt).
3. Add eggs, coffee, buttermilk, oil, and vanilla. Beat for 2 minutes.
4. Pour batter into prepared pans.
5. Bake for 30-35 minutes until toothpick comes out clean.
6. Cool in pans for 10 minutes, then remove to wire racks.
7. Frost when completely cool.

The secret is the coffee - it enhances the chocolate flavor!"""

        jessica_conv.messages.append(
            MessageV2(
                sender_id=user_contact.phone,
                content=recipe_content,
                timestamp=recipe_timestamp,
            )
        )

        # Jessica thanked the user
        jessica_conv.messages.append(
            MessageV2(
                sender_id=jessica_contact.phone,
                content="Thank you so much! This looks amazing. Can't wait to try it this weekend!",
                timestamp=recipe_timestamp + 180,  # 3 minutes after
            )
        )

        self.messaging.add_conversation(jessica_conv)

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Add a saved version of the recipe in notes
        recipe_note_content = """My Famous Chocolate Cake Recipe

Ingredients:
- 2 cups all-purpose flour
- 2 cups sugar
- 3/4 cup unsweetened cocoa powder
- 2 tsp baking soda
- 1 tsp baking powder
- 1 tsp salt
- 2 eggs
- 1 cup strong black coffee (cooled)
- 1 cup buttermilk
- 1/2 cup vegetable oil
- 1 tsp vanilla extract

Instructions:
1. Preheat oven to 350°F (175°C). Grease two 9-inch round cake pans.
2. Mix dry ingredients (flour, sugar, cocoa, baking soda, baking powder, salt).
3. Add eggs, coffee, buttermilk, oil, and vanilla. Beat for 2 minutes.
4. Pour batter into prepared pans.
5. Bake for 30-35 minutes until toothpick comes out clean.
6. Cool in pans for 10 minutes, then remove to wire racks.
7. Frost when completely cool.

Notes: The coffee is the secret ingredient that makes the chocolate flavor so rich!

Shared with: Jessica Lee (October 2025)"""

        recipe_note_id = self.note.create_note_with_time(
            folder="Personal",
            title="Chocolate Cake Recipe",
            content=recipe_note_content,
            created_at="2025-10-18 15:00:00",
            updated_at="2025-10-18 15:00:00",
        )
        self.recipe_note_id = recipe_note_id

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.messaging, self.note]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # Environment event: Jessica sends a message requesting recipe forwarding to her cousin Sarah
            # Get Jessica's phone number from messaging app
            jessica_phone = messaging_app.name_to_id["Jessica Lee"]
            jessica_conv_id = "jessica_conv_001"

            # Jessica sends the forwarding request message
            forward_request = messaging_app.create_and_add_message(
                conversation_id=jessica_conv_id,
                sender_id=jessica_phone,
                content="Hey! Remember that chocolate cake recipe in your notes you messaged me last month? It was amazing and my cousin Sarah loved the photo I showed her. Can you send it to her too? Her number is +1-650-555-0199, with full name as Sarah Lee if you want to save her in your contacts. Btw that's a really good notes!",
            ).delayed(5)

            # Agent reads the conversation to understand the forwarding request
            # Evidence: Jessica's message explicitly requests forwarding the chocolate cake recipe to Sarah at +1-650-555-0199
            read_request = (
                messaging_app.read_conversation(conversation_id=jessica_conv_id, offset=0, limit=10)
                .oracle()
                .depends_on(forward_request, delay_seconds=3)
            )

            # Agent searches message history with Jessica to find the original recipe content
            # Evidence: The request mentions "you sent me last month", so agent needs to find this in conversation history
            search_recipe = (
                messaging_app.search(query="chocolate cake recipe").oracle().depends_on(read_request, delay_seconds=2)
            )

            # Agent searches notes for any saved version of the recipe
            # Evidence: Best practice to check if recipe is documented in notes for complete information
            search_notes = (
                note_app.search_notes(query="chocolate cake").oracle().depends_on(read_request, delay_seconds=2)
            )

            # Agent sends proposal to user about forwarding the recipe
            # Evidence: Jessica's message explicitly requests this action with specific recipient details
            proposal = (
                aui.send_message_to_user(
                    content="I see Jessica Lee asked you to share your chocolate cake recipe with her cousin Sarah (+1-650-555-0199). I found the recipe in your past messages with Jessica and in your notes. Would you like me to send it to Sarah and add her to your contacts?"
                )
                .oracle()
                .depends_on([search_recipe, search_notes], delay_seconds=3)
            )

            # User accepts the proposal
            user_accept = aui.accept_proposal(content="Yes, please do that!").depends_on(proposal, delay_seconds=5)

            # Agent adds Sarah to contacts with relationship context
            # Evidence: Jessica's message identifies Sarah as "my cousin" and provides her phone number
            add_sarah = (
                contacts_app.add_new_contact(
                    first_name="Sarah",
                    last_name="Lee",
                    phone="+1-650-555-0199",
                    description="Jessica Lee's cousin, requested chocolate cake recipe",
                )
                .oracle()
                .depends_on(user_accept, delay_seconds=2)
            )

            # Agent sends the recipe to Sarah via message
            # Evidence: User accepted the proposal, and we have Sarah's phone number from Jessica's message
            send_recipe = (
                messaging_app.send_message(
                    user_id="+1-650-555-0199",
                    content="Hi Sarah! Jessica asked me to share my chocolate cake recipe with you. Here it is:\n\nIngredients:\n- 2 cups all-purpose flour\n- 2 cups sugar\n- 3/4 cup unsweetened cocoa powder\n- 2 tsp baking soda\n- 1 tsp baking powder\n- 1 tsp salt\n- 2 eggs\n- 1 cup strong black coffee (cooled)\n- 1 cup buttermilk\n- 1/2 cup vegetable oil\n- 1 tsp vanilla extract\n\nInstructions:\n1. Preheat oven to 350°F (175°C). Grease two 9-inch round cake pans.\n2. Mix dry ingredients.\n3. Add eggs, coffee, buttermilk, oil, and vanilla. Beat for 2 minutes.\n4. Pour into pans and bake for 30-35 minutes.\n5. Cool completely before frosting.\n\nThe secret is the coffee - it enhances the chocolate flavor! Enjoy!",
                )
                .oracle()
                .depends_on(add_sarah, delay_seconds=3)
            )

            # Agent retrieves the recipe note to update distribution history
            # Evidence: Recipe was successfully sent to Sarah, and the note should track who received it and when
            get_recipe_note = (
                note_app.get_note_by_id(note_id=self.recipe_note_id).oracle().depends_on(send_recipe, delay_seconds=1)
            )

            # Agent updates the recipe note to document distribution history
            # Evidence: Recipe was successfully sent to Sarah, and the note should track who received it and when
            update_note = (
                note_app.update_note(
                    note_id=self.recipe_note_id,
                    content="""My Famous Chocolate Cake Recipe

Ingredients:
- 2 cups all-purpose flour
- 2 cups sugar
- 3/4 cup unsweetened cocoa powder
- 2 tsp baking soda
- 1 tsp baking powder
- 1 tsp salt
- 2 eggs
- 1 cup strong black coffee (cooled)
- 1 cup buttermilk
- 1/2 cup vegetable oil
- 1 tsp vanilla extract

Instructions:
1. Preheat oven to 350°F (175°C). Grease two 9-inch round cake pans.
2. Mix dry ingredients (flour, sugar, cocoa, baking soda, baking powder, salt).
3. Add eggs, coffee, buttermilk, oil, and vanilla. Beat for 2 minutes.
4. Pour batter into prepared pans.
5. Bake for 30-35 minutes until toothpick comes out clean.
6. Cool in pans for 10 minutes, then remove to wire racks.
7. Frost when completely cool.

Notes: The coffee is the secret ingredient that makes the chocolate flavor so rich!

Shared with: Jessica Lee (October 2025), Sarah Lee (November 2025)""",
                )
                .oracle()
                .depends_on(get_recipe_note, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            forward_request,
            read_request,
            search_recipe,
            search_notes,
            proposal,
            user_accept,
            add_sarah,
            send_recipe,
            get_recipe_note,
            update_note,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent/oracle events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent must propose the forwarding action to the user
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 2: Agent must add Sarah to contacts with appropriate context
            # Check that add_new_contact was called with Sarah's phone number
            add_sarah_found = any(
                e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "add_new_contact"
                and "650-555-0199" in str(e.action.args.get("phone", ""))
                for e in agent_events
            )

            # STRICT Check 3: Agent must send the recipe to Sarah
            # Accept either send_message or create_and_add_message as valid message-sending methods
            send_to_sarah_found = any(
                (
                    e.action.class_name == "StatefulMessagingApp"
                    and e.action.function_name in ["send_message", "create_and_add_message"]
                    and "+1-650-555-0199" in str(e.action.args.get("user_id", ""))
                )
                or "+1-650-555-0199" in str(e.action.args)
                for e in agent_events
            )

            # STRICT Check 4: Agent must update the recipe note to document distribution history
            # Check that update_note was called on the recipe note
            note_updated_found = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "update_note"
                and str(e.action.args.get("note_id", "")) == str(self.recipe_note_id)
                for e in agent_events
            )

            # Build success result and rationale
            all_checks = {
                "proposal": proposal_found,
                "add_sarah_contact": add_sarah_found,
                "send_recipe_to_sarah": send_to_sarah_found,
                "update_note_distribution_history": note_updated_found,
            }

            success = all(all_checks.values())

            if not success:
                # Build rationale explaining which checks failed
                failed_checks = [name for name, passed in all_checks.items() if not passed]
                rationale = f"Missing required agent actions: {', '.join(failed_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
