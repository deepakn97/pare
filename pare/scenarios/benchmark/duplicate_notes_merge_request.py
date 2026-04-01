from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulMessagingApp,
)
from pare.apps.note import StatefulNotesApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("duplicate_notes_merge_request")
class DuplicateNotesMergeRequest(PAREScenario):
    """Agent consolidates duplicate note drafts when a collaborator requests progress updates.

    The user has been drafting notes about "Project Roadmap" in the Notes app. Over several days, they created multiple scattered notes: "Roadmap Ideas" in the Personal folder, "Project Roadmap Draft" in the Work folder, and "Q1 Roadmap Notes" also in Work. The user receives a message from their colleague Sarah Kim saying "Hey, can you share your roadmap notes? I need them for tomorrow's presentation." The agent must:
    1. Detect the request for roadmap notes in the incoming message
    2. Search across all Notes folders for notes containing "roadmap" in title or content
    3. Identify the three related notes as duplicate/scattered drafts
    4. Create a consolidated note titled "Project Roadmap - Consolidated" in the Work folder combining the content from all three drafts
    5. Send a reply to Sarah confirming the consolidated note is ready and offering to share it

    This scenario exercises cross-app coordination (messaging → notes), multi-folder note search and content analysis, duplicate detection through semantic similarity, note consolidation with content merging, and proactive workspace organization triggered by external collaboration pressure rather than internal housekeeping..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add contact for Sarah Kim
        self.messaging.add_contacts([("Sarah Kim", "+1234567890")])

        # Create conversation with Sarah (baseline history from past week)
        sarah_id = self.messaging.name_to_id["Sarah Kim"]
        conversation = ConversationV2(participant_ids=[self.messaging.current_user_id, sarah_id], title="Sarah Kim")

        # Add past message history (older messages from last week)
        conversation.messages.append(
            MessageV2(
                sender_id=sarah_id,
                content="Thanks for the meeting notes from last week!",
                timestamp=self.start_time - 86400 * 5,  # 5 days ago
            )
        )
        conversation.messages.append(
            MessageV2(
                sender_id=self.messaging.current_user_id,
                content="No problem! Let me know if you need anything else.",
                timestamp=self.start_time - 86400 * 5 + 3600,  # 5 days ago, 1hr later
            )
        )
        conversation.update_last_updated(self.start_time - 86400 * 5 + 3600)

        self.messaging.add_conversation(conversation)

        # Initialize notes app
        self.note = StatefulNotesApp(name="Notes")

        # Seed three scattered roadmap notes created over several days
        # Note 1: "Roadmap Ideas" in Personal folder (oldest, 7 days ago)
        self.note.create_note_with_time(
            folder="Personal",
            title="Roadmap Ideas",
            content="Initial thoughts on project roadmap:\n- User authentication module\n- Database migration planning\n- API endpoint design\n- Testing framework setup",
            created_at=datetime.fromtimestamp(self.start_time - 86400 * 7, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=datetime.fromtimestamp(self.start_time - 86400 * 7, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Note 2: "Project Roadmap Draft" in Work folder (4 days ago)
        self.note.create_note_with_time(
            folder="Work",
            title="Project Roadmap Draft",
            content="Q1 Project Roadmap:\n- Phase 1: Core infrastructure (Weeks 1-3)\n- Phase 2: Feature development (Weeks 4-8)\n- Phase 3: Testing and optimization (Weeks 9-12)\n- Milestone reviews at end of each phase",
            created_at=datetime.fromtimestamp(self.start_time - 86400 * 4, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=datetime.fromtimestamp(self.start_time - 86400 * 4, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Note 3: "Q1 Roadmap Notes" in Work folder (2 days ago, most recent)
        self.note.create_note_with_time(
            folder="Work",
            title="Q1 Roadmap Notes",
            content="Additional roadmap considerations:\n- Team resource allocation\n- External dependencies and vendor coordination\n- Risk mitigation strategies\n- Key deliverables and success metrics",
            created_at=datetime.fromtimestamp(self.start_time - 86400 * 2, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=datetime.fromtimestamp(self.start_time - 86400 * 2, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.note]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        # Get the conversation ID with Sarah
        sarah_id = messaging_app.name_to_id["Sarah Kim"]
        conv_ids = messaging_app.get_existing_conversation_ids([sarah_id])
        sarah_conversation_id = conv_ids[0]

        with EventRegisterer.capture_mode():
            # Event 1: Environment event - Sarah sends message requesting roadmap notes
            message_event = messaging_app.create_and_add_message(
                conversation_id=sarah_conversation_id,
                sender_id=sarah_id,
                content="Hey, can you double check your roadmap notes? Our team needs them for tomorrow's presentation. If you can, please consolidate them into a single organized note.",
            ).delayed(10)

            # Event 2: Agent searches notes for "roadmap" (motivated by Sarah's request)
            search_event = note_app.search_notes(query="roadmap").oracle().depends_on(message_event, delay_seconds=3)

            # Event 3: Agent proposes to consolidate the scattered notes
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Sarah Kim requested you to check your roadmap notes for tomorrow's presentation. I found three related notes scattered across Personal and Work folders. Would you like me to consolidate them into a single organized note?"
                )
                .oracle()
                .depends_on(search_event, delay_seconds=2)
            )

            # Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please consolidate them. And send the confirmation notice to Sarah Kim."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 5: Agent creates consolidated note in Work folder (motivated by user acceptance)
            consolidate_event = (
                note_app.create_note(
                    folder="Work",
                    title="Project Roadmap - Consolidated",
                    content="""Project Roadmap - Consolidated

Initial Thoughts:
- User authentication module
- Database migration planning
- API endpoint design
- Testing framework setup

Q1 Project Timeline:
- Phase 1: Core infrastructure (Weeks 1-3)
- Phase 2: Feature development (Weeks 4-8)
- Phase 3: Testing and optimization (Weeks 9-12)
- Milestone reviews at end of each phase

Additional Considerations:
- Team resource allocation
- External dependencies and vendor coordination
- Risk mitigation strategies
- Key deliverables and success metrics""",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Event 6: Agent sends reply to Sarah (motivated by completing the consolidation)
            reply_event = (
                messaging_app.send_message(
                    user_id=sarah_id,
                    content="Hi Sarah! I've double checked and consolidated the roadmap notes into one document. Ready for our team's presentation tomorrow!",
                )
                .oracle()
                .depends_on(consolidate_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            message_event,
            search_event,
            proposal_event,
            acceptance_event,
            consolidate_event,
            reply_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check: Agent created consolidated note
            consolidated_note_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                for e in log_entries
            )

            # Check: Agent sent reply confirming notes are ready
            reply_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                for e in log_entries
            )

            # Determine success - essential checks must pass
            success = consolidated_note_created and reply_found

            if not success:
                rationale_parts = []
                if not consolidated_note_created:
                    rationale_parts.append("no consolidated note created")
                if not reply_found:
                    rationale_parts.append("no reply message sent")
                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
