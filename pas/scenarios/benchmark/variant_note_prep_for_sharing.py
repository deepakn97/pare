"""Scenario: Agent creates external version of note by removing internal details."""

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
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("variant_note_prep_for_sharing")
class VariantNotePrepForSharing(PASScenario):
    """Agent creates an external version of a note by removing internal details.

    The user has a note titled "Q1 Strategy - Internal" in the Work folder containing
    strategy details. Some bullet points are marked with [internal] to indicate sensitive
    information. The user's boss messages asking them to prepare an external version of
    the strategy document to share with a client. The agent proposes to duplicate the note
    and remove all [internal] content to create a shareable version.

    This scenario tests:
    - Message-triggered document preparation
    - Note duplication for creating variants
    - Content sanitization based on markers
    - Proactive assistance for document sharing workflows
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You have a note called "Q1 Strategy - Internal" in your Work folder.
Some points in the note are marked with [internal] to indicate sensitive information.

BEFORE your boss's message arrives:
- Browse your notes or messages app

AFTER your boss asks for an external version:

ACCEPT proposals that:
- Offer to create a copy/duplicate of the strategy note
- Offer to remove the internal details from the copy
- Offer to rename the copy to indicate it's an external version

REJECT proposals that:
- Modify the original note directly (should create a copy first)
- Don't mention removing internal content"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Internal content markers for validation
        self.internal_markers = ["[internal]", "pending CFO approval", "competitor analysis", "resource allocation"]

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.add_users(["Rachel Torres"])
        self.boss_id = self.messaging.get_user_id("Rachel Torres")

        # Initialize Notes app with the internal strategy note
        self.note = StatefulNotesApp(name="Notes")
        self.note.create_note_with_time(
            folder="Work",
            title="Q1 Strategy - Internal",
            content="""Q1 Strategy Overview

Key Objectives:
- Revenue growth target: 25% YoY
- Market expansion into APAC region
- Product line diversification with 3 new SKUs
- Budget allocation pending CFO approval [internal]

Market Analysis:
- Strong positioning in North American market
- Competitor analysis shows we're ahead on features [internal]
- Customer satisfaction scores above industry average

Resource Planning:
- Engineering team expanding by 15%
- Resource allocation still being finalized [internal]
- New hires starting in February

Timeline:
- Phase 1: January-February (planning)
- Phase 2: March-April (execution)
- Phase 3: May-June (review)""",
            pinned=False,
            created_at="2025-11-15 10:00:00",
            updated_at="2025-11-17 14:30:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.note]

    def build_events_flow(self) -> None:
        """Build event flow - boss message triggers external version preparation."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # ENV Event: Boss messages asking for external version of strategy doc
            boss_message_event = messaging_app.create_and_add_message(
                conversation_id=self.boss_id,
                sender_id=self.boss_id,
                content=(
                    "Hey, I need to share our Q1 strategy with the Acme Corp team next week. "
                    "Can you prepare an external version of that strategy note you have? "
                    "Make sure to remove any internal details before sharing."
                ),
            ).delayed(5)

            # Oracle: Agent proposes to create sanitized copy
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "Your boss Rachel is asking for an external version of your Q1 Strategy note "
                        "to share with Acme Corp. I can duplicate the note, remove the internal details "
                        "(marked with [internal]), and rename it as an external version. Would you like me to do that?"
                    )
                )
                .oracle()
                .depends_on(boss_message_event, delay_seconds=3)
            )

            # Oracle: User accepts
            acceptance_event = (
                aui.accept_proposal(content="Yes, please prepare the external version.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle: Agent duplicates the note
            duplicate_event = (
                note_app.duplicate_note(folder_name="Work", note_id="note_1")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle: Agent updates the duplicate to remove internal content and rename
            update_event = (
                note_app.update_note(
                    note_id="note_2",
                    title="Q1 Strategy - External Version",
                    content="""Q1 Strategy Overview

Key Objectives:
- Revenue growth target: 25% YoY
- Market expansion into APAC region
- Product line diversification with 3 new SKUs

Market Analysis:
- Strong positioning in North American market
- Customer satisfaction scores above industry average

Resource Planning:
- Engineering team expanding by 15%
- New hires starting in February

Timeline:
- Phase 1: January-February (planning)
- Phase 2: March-April (execution)
- Phase 3: May-June (review)""",
                )
                .oracle()
                .depends_on(duplicate_event, delay_seconds=2)
            )

        self.events = [
            boss_message_event,
            proposal_event,
            acceptance_event,
            duplicate_event,
            update_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent creates external version without internal markers."""
        try:
            log_entries = env.event_log.list_view()

            # Essential outcome 1: Agent sent proposal to user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Essential outcome 2: Agent created external note without internal markers
            # Accept either: (a) duplicate_note + update_note, or (b) create_note directly
            external_note_created = False
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.class_name == "StatefulNotesApp"
                    and e.action.function_name in ["update_note", "create_note"]
                ):
                    content = e.action.args.get("content", "")
                    title = e.action.args.get("title", "")
                    # Check that content doesn't have internal markers
                    has_internal = any(marker.lower() in content.lower() for marker in self.internal_markers)
                    has_external_title = "external" in title.lower()
                    if not has_internal and has_external_title:
                        external_note_created = True
                        break

            success = proposal_found and external_note_created

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user")
                if not external_note_created:
                    missing.append("external note without internal markers")
                rationale = f"Missing: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
