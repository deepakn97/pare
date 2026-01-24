"""Scenario: Agent assists message composition by retrieving and filtering relevant note content."""

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
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("composition_assist_notes_injection")
class CompositionAssistNotesInjection(PASScenario):
    """Agent assists message composition by retrieving and filtering relevant note content.

    The user has a note titled "Restaurant Recommendations - Downtown" in the Personal folder containing
    a list of 6 restaurants including 2 Indian restaurants (Spice Garden and Curry House). The user is
    in a group conversation with friends Alex Chen and Jordan Martinez planning a weekend dinner. Prior
    messages establish the context:
    - User: "Hey everyone! Let's meet up Saturday night for dinner."
    - Jordan: "Sounds great! I'm craving Indian food lately."
    - Alex: "Indian sounds perfect! Do you know any good Indian places?" (ENV trigger)

    When Alex asks for Indian restaurant suggestions, the agent must:
    1. Detect Alex's question asking specifically for Indian restaurants
    2. Search the Notes app for restaurant-related content
    3. Find the "Restaurant Recommendations - Downtown" note
    4. Filter the list to only include the 2 Indian restaurants (Spice Garden and Curry House)
    5. Proactively offer to share the filtered Indian restaurant options with the group
    6. Upon user acceptance, send only the Indian restaurant information to the group conversation

    This scenario exercises proactive composition assistance, cross-app content retrieval, intelligent
    filtering based on conversation context, and content sharing that bridges personal knowledge
    management with collaborative planning.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Initialize Messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Populate Notes app with restaurant recommendations (includes 2 Indian restaurants)
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

5. Curry House - 555 Spice Lane
   Cuisine: Indian
   Notes: Best biryani in town, great naan

6. The Steakhouse - 654 Maple Dr
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
        self.messaging.add_users(["Alex Chen", "Jordan Martinez"])

        alex_id = self.messaging.name_to_id["Alex Chen"]
        jordan_id = self.messaging.name_to_id["Jordan Martinez"]
        user_id = self.messaging.current_user_id

        # Create group conversation with prior messages establishing dinner planning context
        group_conv = ConversationV2(
            participant_ids=[user_id, alex_id, jordan_id],
            title="Weekend Plans",
            messages=[
                MessageV2(
                    sender_id=user_id,
                    content="Hey everyone! Let's meet up Saturday night for dinner.",
                ),
                MessageV2(
                    sender_id=jordan_id,
                    content="Sounds great! I'm craving Indian food lately.",
                ),
            ],
        )
        self.messaging.add_conversation(group_conv)

        # Store IDs for use in build_events_flow()
        self.weekend_plans_conversation_id = group_conv.conversation_id
        self.alex_id = alex_id

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.messaging]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        conversation_id = self.weekend_plans_conversation_id

        with EventRegisterer.capture_mode():
            # ENV: Alex asks for Indian restaurant suggestions in the group chat
            alex_message_event = messaging_app.create_and_add_message(
                conversation_id=conversation_id,
                sender_id=self.alex_id,
                content="Indian sounds perfect! Do you know any good Indian places?",
            ).delayed(5)

            # Oracle: Agent reads the conversation to understand context
            read_conversation_event = (
                messaging_app.read_conversation(conversation_id=conversation_id, offset=0, limit=10)
                .oracle()
                .depends_on(alex_message_event, delay_seconds=2)
            )

            # Oracle: Agent searches Notes app for restaurant-related content
            search_event = (
                note_app.search_notes(query="restaurant").oracle().depends_on(read_conversation_event, delay_seconds=2)
            )

            # Oracle: Agent proposes to share Indian restaurants from the note
            proposal_event = (
                aui.send_message_to_user(
                    content='I found 2 Indian restaurants in your "Restaurant Recommendations - Downtown" note: Spice Garden and Curry House. Would you like me to share these options with the group?'
                )
                .oracle()
                .depends_on(search_event, delay_seconds=2)
            )

            # Oracle: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, share those with the group!")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle: Agent sends only the Indian restaurant options to the group
            share_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=conversation_id,
                    content="""Here are my Indian restaurant recommendations:

1. Spice Garden - 321 Pine Rd
   Authentic curries, vegetarian options

2. Curry House - 555 Spice Lane
   Best biryani in town, great naan

Both are great choices! What do you think?""",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

        self.events = [
            alex_message_event,
            read_conversation_event,
            search_event,
            proposal_event,
            acceptance_event,
            share_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent achieved the essential outcomes for this scenario.

        Essential outcomes (what we check):
        - Agent sent proposal to user about sharing restaurants
        - Agent sent message to group conversation containing Indian restaurant names

        Not checked (intermediate steps the agent might do differently):
        - How agent read the conversation (read_conversation, etc.)
        - How agent searched notes (search_notes, list_notes, get_note_by_id, etc.)
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

            # CHECK 2: Agent sent message to group with Indian restaurant names
            # Must include at least one of the Indian restaurants (Spice Garden or Curry House)
            indian_restaurants_shared = False
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.class_name == "StatefulMessagingApp"
                    and e.action.function_name == "send_message_to_group_conversation"
                    and e.action.args.get("conversation_id") == self.weekend_plans_conversation_id
                ):
                    content = e.action.args.get("content", "").lower()
                    # Check that at least one Indian restaurant is mentioned
                    if "spice garden" in content or "curry house" in content:
                        indian_restaurants_shared = True
                        break

            success = proposal_found and indian_restaurants_shared

            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not send proposal to user")
                if not indian_restaurants_shared:
                    failed_checks.append(
                        "agent did not send message with Indian restaurants (Spice Garden/Curry House) to group"
                    )
                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
