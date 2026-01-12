"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("composition_assist_notes_injection")
class CompositionAssistNotesInjection(PASScenario):
    """Agent assists ongoing message composition by retrieving and inserting relevant note content.

    The user has a note titled "Restaurant Recommendations - Downtown" in the Personal folder containing a list of 5 restaurants with addresses and cuisine types. The user opens a group conversation with friends Alex Chen and Jordan Martinez to plan a weekend dinner. While typing a message that says "Hey everyone! Let's meet up Saturday night. I wrote down some restaurant suggestions last week but", the user pauses mid-sentence. The agent must:
    1. Detect the incomplete message mentioning "restaurant suggestions" and recognize the user needs supporting information
    2. Search the Notes app for notes containing "restaurant" keywords
    3. Identify the "Restaurant Recommendations - Downtown" note as relevant
    4. Extract the restaurant list from the note content
    5. Proactively offer to complete the message by inserting the restaurant list or provide a summary the user can send
    6. If the user accepts, insert the formatted restaurant information into the message draft

    This scenario exercises proactive composition assistance, real-time context detection during message drafting, cross-app content retrieval triggered by outgoing (not incoming) communication, and intelligent content injection that bridges personal knowledge management with collaborative planning..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Initialize Messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Populate Notes app with baseline data
        # Create a note in the Personal folder containing restaurant recommendations
        restaurant_note_content = """Downtown Restaurant Recommendations:

1. Bella Italia - 123 Main St
   Cuisine: Italian
   Notes: Excellent pasta, romantic atmosphere

2. Sakura Sushi - 456 Oak Ave
   Cuisine: Japanese
   Notes: Fresh fish, great omakase

3. Le Petit Bistro - 789 Elm St
   Cuisine: French
   Notes: Classic dishes, cozy setting

4. Spice Garden - 321 Pine Rd
   Cuisine: Indian
   Notes: Authentic curries, vegetarian options

5. The Steakhouse - 654 Maple Dr
   Cuisine: American
   Notes: Premium cuts, wine selection"""

        self.note.create_note_with_time(
            folder="Personal",
            title="Restaurant Recommendations - Downtown",
            content=restaurant_note_content,
            pinned=False,
            created_at=datetime(2025, 11, 11, 14, 30, 0, tzinfo=UTC).strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=datetime(2025, 11, 11, 14, 30, 0, tzinfo=UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Populate Messaging app with contacts and group conversation
        # Add contacts to messaging app
        self.messaging.add_users(["Alex Chen", "Jordan Martinez"])

        # Create group conversation with Alex and Jordan
        alex_id = self.messaging.name_to_id["Alex Chen"]
        jordan_id = self.messaging.name_to_id["Jordan Martinez"]

        group_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, alex_id, jordan_id],
            title="Weekend Plans",
            messages=[],
        )
        self.messaging.add_conversation(group_conv)

        # Store conversation_id for use in build_events_flow()
        self.weekend_plans_conversation_id = group_conv.conversation_id

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        # Get conversation ID stored during init
        conversation_id = self.weekend_plans_conversation_id
        user_id = messaging_app.current_user_id

        with EventRegisterer.capture_mode():
            # Event 1: User sends message to group mentioning restaurant suggestions
            # This is the environment event that triggers agent awareness
            user_message_event = messaging_app.create_and_add_message(
                conversation_id=conversation_id,
                sender_id=user_id,
                content="Hey everyone! Let's meet up Saturday night. I wrote down some restaurant suggestions last week but need to find that note. Give me a minute to look it up!",
            ).delayed(10)

            # Event 2: Agent reads the group conversation to observe the context (thread + participants)
            # Motivated by: the user's message in the Weekend Plans chat indicates they are searching for a specific note to share.
            read_conversation_event = (
                messaging_app.read_conversation(conversation_id=conversation_id, offset=0, limit=10)
                .oracle()
                .depends_on(user_message_event, delay_seconds=1)
            )

            # Event 3: Agent searches Notes app for restaurant-related content
            # Motivated by: user's message explicitly mentioning "restaurant suggestions" and "that note"
            search_event = (
                note_app.search_notes(query="restaurant").oracle().depends_on(read_conversation_event, delay_seconds=2)
            )

            # Event 4: Agent retrieves the specific note by ID (discovered from search)
            # Motivated by: search_event should reveal note_id of "Restaurant Recommendations - Downtown"
            # Note: We need to get the note_id from the seeded note
            # Since we can't access it dynamically in event flow, we'll use search results as justification
            # and propose to user based on that

            # Event 5: Agent proposes to share restaurant list with the group
            # Motivated by: user's outgoing message requesting restaurant info + successful note search
            proposal_event = (
                aui.send_message_to_user(
                    content='I found your "Restaurant Recommendations - Downtown" note with 5 restaurants. Would you like me to share this list in the "Weekend Plans" group chat?'
                )
                .oracle()
                .depends_on([read_conversation_event, search_event], delay_seconds=2)
            )

            # Event 6: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please share the restaurant list with them!")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Event 7: Agent sends formatted restaurant information to the group
            # Motivated by: user acceptance in acceptance_event
            # Note: For group conversations, use send_message_to_group_conversation (sends as current user).
            share_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=conversation_id,
                    content="""Here are the restaurant recommendations:

1. Bella Italia - 123 Main St (Italian) - Excellent pasta, romantic atmosphere
2. Sakura Sushi - 456 Oak Ave (Japanese) - Fresh fish, great omakase
3. Le Petit Bistro - 789 Elm St (French) - Classic dishes, cozy setting
4. Spice Garden - 321 Pine Rd (Indian) - Authentic curries, vegetarian options
5. The Steakhouse - 654 Maple Dr (American) - Premium cuts, wine selection

What do you all think?""",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            user_message_event,
            read_conversation_event,
            search_event,
            proposal_event,
            acceptance_event,
            share_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning restaurant recommendations and the note
            # Equivalence class: proposal can come via send_message_to_user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["restaurant", "note"])
                for e in log_entries
            )

            # STRICT Check 2: Agent read the group conversation for context
            conversation_read_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                for e in log_entries
            )

            # STRICT Check 3: Agent searched Notes app for restaurant-related content
            # The agent must have queried the Notes app to retrieve relevant information
            notes_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "search_notes"
                and "restaurant" in e.action.args.get("query", "").lower()
                for e in log_entries
            )

            # STRICT Check 4: Agent sent restaurant information to the group conversation
            # Equivalence class: agent can use create_and_add_message OR send_message_to_group_conversation
            # We verify the correct conversation_id (sender_id may not exist for send_message_to_group_conversation)
            # Content flexibility: we don't check exact text, just that message was sent to the group
            message_sent_to_group = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["create_and_add_message", "send_message_to_group_conversation"]
                and e.action.args.get("conversation_id") == self.weekend_plans_conversation_id
                and (e.action.function_name != "create_and_add_message" or e.action.args.get("sender_id") is not None)
                for e in log_entries
            )

            # All strict checks must pass for success
            success = proposal_found and conversation_read_found and notes_search_found and message_sent_to_group

            if not success:
                rationale_parts = []
                if not proposal_found:
                    rationale_parts.append("no agent proposal mentioning restaurant/note found")
                if not conversation_read_found:
                    rationale_parts.append("no agent read of the group conversation found")
                if not notes_search_found:
                    rationale_parts.append("no Notes app search for 'restaurant' found")
                if not message_sent_to_group:
                    rationale_parts.append("no message sent to Weekend Plans group conversation")
                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
