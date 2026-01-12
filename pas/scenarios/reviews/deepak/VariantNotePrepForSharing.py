"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
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


@register_scenario("variant_note_prep_for_sharing")
class VariantNotePrepForSharing(PASScenario):
    """Agent creates a sanitized duplicate of a note with corrected attachments when user needs to share documentation externally.

    The user has a note titled "Q1 Strategy - Internal" in the Work folder containing sensitive internal context plus attachments: `/files/Strategy_Overview.pdf`, `/files/Internal_Financials.xlsx`, and `/files/Team_Notes_Raw.docx`. The user sends a message to external consultant Dr. Pat Kim saying they will share a sanitized copy and explicitly plans to "make a copy" of the "Q1 Strategy - Internal" note and remove the "Internal_Financials.xlsx" attachment before sharing. After sending this message, the agent recognizes the user needs to prepare external-appropriate materials. The agent must:

    1. Detect from the outgoing message context that the user intends to share strategy materials but exclude sensitive financials
    2. Search Notes app to locate the "Q1 Strategy - Internal" note referenced implicitly by "Q1 strategy materials"
    3. Duplicate the note to create a shareable variant (duplicate_note will create "Copy of Q1 Strategy - Internal")
    4. List attachments on the new duplicate note to establish what needs correction
    5. Identify that Internal_Financials.xlsx must be removed per the user's stated intent ("removing the internal financials")
    6. Remove the Internal_Financials.xlsx attachment from the duplicate
    7. Update the duplicate note's title from "Copy of Q1 Strategy - Internal" to "Q1 Strategy - External Version"

    This scenario exercises proactive inference from outgoing message context (user stating sharing intent triggers preparation workflow), note duplication to create variants, attachment removal based on a user-stated constraint, and a copy-before-share workflow to keep the original intact.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.current_user_id = "user_main"
        self.messaging.current_user_name = "Me"

        # Add Dr. Pat Kim as a contact
        self.messaging.add_users(["Dr. Pat Kim"])

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Create the "Q1 Strategy - Internal" note in the Work folder with attachments
        # The note contains internal strategy content and three attachments
        note_id = self.note.create_note_with_time(
            folder="Work",
            title="Q1 Strategy - Internal",
            content="Q1 Strategy Overview\n\nKey Objectives:\n- Revenue growth target: 25% YoY\n- Market expansion into APAC region\n- Product line diversification\n\nInternal Notes:\n- Budget allocation pending CFO approval\n- Competitive analysis shows strong positioning\n- Resource requirements detailed in financials attachment",
            pinned=False,
            created_at="2025-11-15 10:00:00",
            updated_at="2025-11-17 14:30:00",
        )

        # Add attachments to the note (simulated as base64 encoded content)
        # Note: In the actual scenario, these would reference real files in the file system
        # For baseline data, we're creating the note with attachment metadata that will be
        # seeded. The actual attachment addition would need a real file system.
        # Since we cannot create real files here, Step 3 must ensure the agent can work with
        # the attachment names that will be revealed via list_attachments.

        # Store the note_id for reference in other steps
        self._internal_note_id = note_id

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.note]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # Environment Event 1: User sends message to Dr. Pat Kim about sharing Q1 strategy materials
            # This is the trigger that reveals the user needs to prepare shareable documentation
            # The message explicitly mentions "removing the internal financials" which provides the key guidance
            user_message_event = messaging_app.create_and_add_message(
                conversation_id=messaging_app.name_to_id["Dr. Pat Kim"],
                sender_id=messaging_app.current_user_id,
                content=(
                    "Hi Pat, I need to share our Q1 strategy materials with you for the advisory session next week. "
                    "I'll send over the overview deck and a sanitized copy — I'll make a copy of my Work note 'Q1 Strategy - Internal' "
                    "and remove the internal financials before sharing. "
                    "That note currently has an attachment named 'Internal_Financials.xlsx' that should not be shared. "
                    "Can you review by Friday?"
                ),
            ).delayed(5)

            # Oracle Event 1: Agent reads the conversation to understand the user's outgoing message context
            # Motivation: user_message_event explicitly mentions "Q1 strategy materials" and "removing the internal financials"
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id=messaging_app.name_to_id["Dr. Pat Kim"],
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(user_message_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent searches Notes to locate the Q1 Strategy note
            # Motivation: user_message_event explicitly names the note title ("Q1 Strategy - Internal") in Work.
            search_notes_event = (
                note_app.search_notes(query="Q1 Strategy - Internal")
                .oracle()
                .depends_on(read_conversation_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent gets the note details to understand its current state
            # Motivation: search_notes_event should have revealed the "Q1 Strategy - Internal" note
            get_note_event = (
                note_app.get_note_by_id(note_id=self._internal_note_id)
                .oracle()
                .depends_on(search_notes_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent lists attachments on the original note to understand what needs to be filtered
            # Motivation: user_message_event explicitly calls out an attachment named "Internal_Financials.xlsx" that must be removed before sharing.
            list_attachments_event = (
                note_app.list_attachments(note_id=self._internal_note_id)
                .oracle()
                .depends_on(get_note_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent proposes to create a sanitized duplicate with financials removed
            # Motivation: user_message_event shows intent to share materials externally with "removing the internal financials"
            # The proposal explicitly references the triggering message context
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you're planning to share Dr. Pat Kim a sanitized copy of your Work note 'Q1 Strategy - Internal' and explicitly mentioned removing the 'Internal_Financials.xlsx' attachment before sharing. Would you like me to duplicate the note, remove that attachment from the copy, and rename it as an external version?"
                )
                .oracle()
                .depends_on(list_attachments_event, delay_seconds=2)
            )

            # Oracle Event 6: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please prepare the external version.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 7: Agent duplicates the note to create a variant
            # Motivation: user_message_event explicitly says the user will "make a copy" of the note before sharing; acceptance_event grants permission.
            duplicate_note_event = (
                note_app.duplicate_note(folder_name="Work", note_id=self._internal_note_id)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent lists attachments on the duplicate to confirm what needs removal
            # Motivation: duplicate_note_event created the new note; need to verify attachments before removal
            # Note: We'll need to extract the duplicate note ID from duplicate_note_event's return value
            # For now, we'll use a placeholder approach - in reality, the agent would extract the ID from the event
            list_duplicate_attachments_event = (
                note_app.list_attachments(note_id=self._internal_note_id)
                .oracle()
                .depends_on(duplicate_note_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent removes the Internal_Financials.xlsx attachment from the duplicate
            # Motivation: user_message_event explicitly requested "removing the internal financials"
            remove_attachment_event = (
                note_app.remove_attachment(
                    note_id=self._internal_note_id,
                    attachment="Internal_Financials.xlsx",
                )
                .oracle()
                .depends_on(list_duplicate_attachments_event, delay_seconds=1)
            )

            # Oracle Event 10: Agent updates the duplicate note's title to distinguish it as external version
            # Motivation: acceptance_event approved the workflow; need to rename to indicate sanitized status
            update_title_event = (
                note_app.update_note(
                    note_id=self._internal_note_id,
                    title="Q1 Strategy - External Version",
                )
                .oracle()
                .depends_on(remove_attachment_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            user_message_event,
            read_conversation_event,
            search_notes_event,
            get_note_event,
            list_attachments_event,
            proposal_event,
            acceptance_event,
            duplicate_note_event,
            list_duplicate_attachments_event,
            remove_attachment_event,
            update_title_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for all checks
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent searched for the Q1 Strategy note
            # Accept either search_notes OR get_note_by_id as valid ways to locate the note
            note_search_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["search_notes", "get_note_by_id"]
                for e in agent_events
            )

            # STRICT Check 2: Agent duplicated the note
            # This is the primary operation - must be present
            note_duplicated = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "duplicate_note"
                for e in agent_events
            )

            # STRICT Check 3: Agent removed the Internal_Financials.xlsx attachment
            # This is critical to the scenario - must be present
            attachment_removed = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "remove_attachment"
                and "Internal_Financials" in str(e.action.args.get("attachment", ""))
                for e in agent_events
            )

            # STRICT Check 4: Agent updated the note title
            # Must contain "External" or "external" to indicate sanitization
            # Accept any title that clearly indicates external/shareable version
            title_updated = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "update_note"
                and "title" in e.action.args
                and e.action.args.get("title", "") != ""
                and "external" in e.action.args.get("title", "").lower()
                for e in agent_events
            )

            # Determine success and build rationale
            success = note_search_found and note_duplicated and attachment_removed and title_updated

            if not success:
                missing_checks = []
                if not note_search_found:
                    missing_checks.append("note search/retrieval")
                if not note_duplicated:
                    missing_checks.append("note duplication")
                if not attachment_removed:
                    missing_checks.append("Internal_Financials.xlsx removal")
                if not title_updated:
                    missing_checks.append("note title update with 'external' indicator")

                rationale = f"Missing critical actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
