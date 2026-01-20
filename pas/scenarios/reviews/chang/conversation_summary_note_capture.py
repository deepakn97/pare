from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
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


@register_scenario("conversation_summary_note_capture")
class ConversationSummaryNoteCapture(PASScenario):
    """Agent creates structured notes from multi-party conversation decisions when explicitly requested.

    The user participates in a group conversation with Morgan Lee and Casey Park discussing "Mobile App Redesign Timeline". After extended back-and-forth about milestones, Morgan Lee sends a message: "This is getting long - can someone capture the key decisions in a note so we don't lose track?" The agent must:
    1. Detect the explicit request to document conversation content
    2. Read the current group conversation messages to extract decision points (who committed to what, deadlines mentioned, open questions)
    3. Create a new note in the Work folder with title derived from the conversation topic
    4. Structure the note content with sections: "Decisions Made", "Action Items", "Open Questions"
    5. Send a confirmation message to the group conversation: "I've created a summary note titled '[Title]' in your Work folder with the key decisions from this discussion"

    This scenario exercises conversation-to-note synthesis (reverse of note-to-conversation flows in prior scenarios), multi-message comprehension and extraction, structured note creation from unstructured discussion, and proactive documentation assistance that captures ephemeral conversation state into persistent storage.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Initialize notes app
        self.note = StatefulNotesApp(name="Notes")

        # Add contacts for the group conversation participants
        morgan_lee = Contact(first_name="Morgan", last_name="Lee", phone="+1-555-0101", email="morgan.lee@company.com")

        casey_park = Contact(first_name="Casey", last_name="Park", phone="+1-555-0102", email="casey.park@company.com")

        # Register users in messaging app
        self.messaging.add_users(["Morgan Lee", "Casey Park"])
        morgan_id = self.messaging.name_to_id["Morgan Lee"]
        casey_id = self.messaging.name_to_id["Casey Park"]

        # Create group conversation with existing discussion about Mobile App Redesign Timeline
        # This conversation already has several messages exchanged before the scenario starts
        conversation = ConversationV2(
            participant_ids=[morgan_id, casey_id, self.messaging.current_user_id],
            title="Mobile App Redesign Timeline",
            last_updated=self.start_time - 300,  # 5 minutes before scenario start
        )

        # Add baseline conversation messages (discussion already in progress)
        # These messages establish context that will need to be summarized
        base_time = self.start_time - 600  # 10 minutes before scenario start

        conversation.messages.append(
            MessageV2(
                sender_id=morgan_id,
                content="Hey team, we need to finalize the timeline for the mobile app redesign project. What are everyone's thoughts on the sprint schedule?",
                timestamp=base_time,
            )
        )

        conversation.messages.append(
            MessageV2(
                sender_id=casey_id,
                content="I think we should aim for a 6-week timeline. Sprint 1 could focus on UI mockups, Sprint 2 on core features, and Sprint 3 on testing and polish.",
                timestamp=base_time + 60,
            )
        )

        conversation.messages.append(
            MessageV2(
                sender_id=morgan_id,
                content="That sounds reasonable. I can commit to having the design system ready by end of Sprint 1 - so November 29th. Casey, can you handle the backend API setup during Sprint 1 as well?",
                timestamp=base_time + 120,
            )
        )

        conversation.messages.append(
            MessageV2(
                sender_id=casey_id,
                content="Yes, I'll have the API endpoints documented and ready for integration by November 29th. But we still need to decide on the authentication approach - OAuth or JWT?",
                timestamp=base_time + 180,
            )
        )

        conversation.messages.append(
            MessageV2(
                sender_id=morgan_id,
                content="Good question. Let's table that for now and revisit in our next technical review. For Sprint 2, I'll focus on implementing the main user flows - profile, dashboard, and settings.",
                timestamp=base_time + 240,
            )
        )

        conversation.messages.append(
            MessageV2(
                sender_id=casey_id,
                content="Sounds good. I'll work on the data sync and offline mode during Sprint 2. We should also schedule user testing sessions for early December.",
                timestamp=base_time + 300,
            )
        )

        conversation.messages.append(
            MessageV2(
                sender_id=morgan_id,
                content="Agreed on user testing. Sprint 3 will be December 9-20, so we can do testing the week of December 16th. Final release target is December 20th before the holiday break.",
                timestamp=base_time + 360,
            )
        )

        # Add the conversation to the messaging app
        self.messaging.add_conversation(conversation)

        # Store conversation_id for use in build_events_flow
        self.mobile_app_conversation_id = conversation.conversation_id

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.note]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        # Get the conversation ID and participant IDs for use in events
        morgan_id = messaging_app.name_to_id["Morgan Lee"]
        casey_id = messaging_app.name_to_id["Casey Park"]

        # Get conversation_id from stored instance variable
        conversation_id = self.mobile_app_conversation_id

        with EventRegisterer.capture_mode():
            # Environment event: Morgan Lee sends explicit request to capture conversation in a note
            # This is the trigger that should prompt the agent to offer help
            env1 = messaging_app.create_and_add_message(
                conversation_id=conversation_id,
                sender_id=morgan_id,
                content="This is getting long - can someone capture the key decisions in a note so we don't lose track?",
            ).delayed(5)

            # Agent observes the explicit request in the new message and reads the conversation to understand what needs to be documented
            oracle1 = (
                messaging_app.read_conversation(conversation_id=conversation_id, offset=0, limit=20)
                .oracle()
                .depends_on(env1, delay_seconds=3)
            )

            # Agent sends proposal to user offering to create a structured summary note
            proposal = (
                aui.send_message_to_user(
                    content="I noticed Morgan's request to capture the key decisions from your Mobile App Redesign Timeline conversation. I can create a structured summary note in your Work folder with sections for Decisions Made, Action Items, and Open Questions. Would you like me to do that?"
                )
                .oracle()
                .depends_on(oracle1, delay_seconds=2)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please create that summary note.")
                .oracle()
                .depends_on(proposal, delay_seconds=5)
            )

            # Agent reads the conversation again to extract all details for the note content
            oracle2 = (
                messaging_app.read_conversation(conversation_id=conversation_id, offset=0, limit=20)
                .oracle()
                .depends_on(acceptance, delay_seconds=2)
            )

            # Agent creates the structured summary note in the Work folder
            create_note = (
                note_app.create_note(
                    folder="Work",
                    title="Mobile App Redesign Timeline - Summary",
                    content="""Decisions Made:
- 6-week timeline with 3 sprints (Sprint 1: UI mockups, Sprint 2: core features, Sprint 3: testing/polish)
- Sprint 1 ends November 29th with design system (Morgan) and API endpoints (Casey) ready
- Sprint 2 focus: Morgan on user flows (profile/dashboard/settings), Casey on data sync/offline mode
- Sprint 3 runs December 9-20 with user testing week of December 16th
- Final release target: December 20th before holiday break

Action Items:
- Morgan: Design system ready by November 29th
- Casey: API endpoints documented and ready by November 29th
- Morgan: Implement main user flows during Sprint 2
- Casey: Work on data sync and offline mode during Sprint 2
- Team: Schedule user testing sessions for early December (week of December 16th)

Open Questions:
- Authentication approach: OAuth vs JWT (to be decided in next technical review)""",
                )
                .oracle()
                .depends_on(oracle2, delay_seconds=3)
            )

            # Agent sends confirmation message to the group conversation
            oracle3 = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=conversation_id,
                    content="I've created a summary note titled 'Mobile App Redesign Timeline - Summary' in the Work folder with the key decisions from this discussion.",
                )
                .oracle()
                .depends_on(create_note, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [env1, oracle1, proposal, acceptance, oracle2, create_note, oracle3]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user
            # STRICT: Agent must explicitly reference Morgan's request and offer to create a summary note
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 2: Agent read the conversation to extract content
            # STRICT: Agent must read the conversation (using read_conversation or equivalent methods)
            # Allow multiple equivalent read methods from the messaging API
            conversation_read_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["read_conversation", "get_messages"]
                for e in log_entries
            )

            # Check Step 3: Agent created the structured note
            # STRICT: Agent must create a note with correct folder ("Work") and structured content
            # FLEXIBLE: Title may vary as long as it relates to the conversation topic
            note_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                for e in log_entries
            )

            # Check Step 4: Agent sent confirmation to the group conversation
            # STRICT: Agent must send a message back to the conversation mentioning the note creation
            # FLEXIBLE: Exact wording can vary, but must mention note and confirmation
            # Allow both send_message_to_group_conversation and send_message as equivalent methods
            confirmation_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name
                in ["send_message_to_group_conversation", "send_message", "create_and_add_message"]
                for e in log_entries
            )

            success = proposal_found and conversation_read_found and note_created and confirmation_sent

            if not success:
                # Build rationale for failure
                missing = []
                if not proposal_found:
                    missing.append("agent proposal referencing Morgan's request")
                if not conversation_read_found:
                    missing.append("conversation read to extract decisions")
                if not note_created:
                    missing.append("structured note creation in Work folder")
                if not confirmation_sent:
                    missing.append("confirmation message to group conversation")

                rationale = f"Missing critical checks: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
