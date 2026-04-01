"""Scenario for synchronizing meeting notes when calendar events are rescheduled."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCalendarApp,
)
from pare.apps.note import StatefulNotesApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("note_update_reflects_meeting_changes")
class NoteUpdateReflectsMeetingChanges(PAREScenario):
    """Agent synchronizes meeting notes when calendar events are rescheduled.

    Story:
    1. User has a note "Client Demo Preparation - Nov 20" with meeting details
       (original time: Nov 20 at 2:00 PM)
    2. User has a calendar event "Client Demo" for Nov 20 at 2:00 PM
    3. Sarah Chen (organizer) reschedules the meeting to Nov 22 at 3:00 PM
    4. Agent notices the reschedule and proposes updating the preparation note
    5. User accepts
    6. Agent updates both the note title and content to reflect the new date/time

    This scenario exercises calendar-to-notes synchronization, temporal reference
    update, and cross-app data consistency.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You have a preparation note for the Client Demo meeting scheduled for Nov 20.

ACCEPT proposals that:
- Offer to update your note when the meeting is rescheduled
- Clearly explain what changes will be made (old date/time to new date/time)

REJECT proposals that:
- Make changes without explaining what will be updated
- Don't mention the specific date/time changes"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Create note and capture the note_id
        self.prep_note_id = self.note.create_note_with_time(
            folder="Work",
            title="Client Demo Preparation - Nov 20",
            content=(
                "Meeting scheduled for Nov 20 at 2:00 PM.\n\n"
                "Agenda:\n"
                "- Product feature walkthrough\n"
                "- Q&A session\n"
                "- Pricing discussion\n\n"
                "Attendees: Sarah Chen, Mike Rodriguez\n\n"
                "Preparation checklist:\n"
                "- Prepare demo environment\n"
                "- Load sample data\n"
                "- Test all key features\n"
                "- Prepare backup slides"
            ),
            pinned=False,
            created_at="2025-11-15 14:30:00",
            updated_at="2025-11-15 14:30:00",
        )

        # Initialize Calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Create original calendar event
        self.original_event_id = self.calendar.add_calendar_event(
            title="Client Demo",
            start_datetime="2025-11-20 14:00:00",
            end_datetime="2025-11-20 15:30:00",
            description="Product demonstration for potential client",
            location="Conference Room B",
            attendees=["Sarah Chen", "Mike Rodriguez"],
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.calendar]

    def build_events_flow(self) -> None:
        """Build event flow for calendar-note synchronization."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # ENV: Calendar reschedule notification from organizer Sarah Chen
            reschedule_event = calendar_app.add_calendar_event_by_attendee(
                who_add="Sarah Chen",
                title="Client Demo",
                start_datetime="2025-11-22 15:00:00",  # New time: Nov 22 at 3:00 PM
                end_datetime="2025-11-22 16:30:00",
                description="Client Demo - rescheduled from Nov 20",
                location="Conference Room B",
                attendees=["Sarah Chen", "Mike Rodriguez"],
            ).delayed(10)

            # Oracle: Agent searches notes for related content
            search_notes_event = (
                note_app.search_notes(query="Client Demo").oracle().depends_on(reschedule_event, delay_seconds=2)
            )

            # Oracle: Agent retrieves the note to read full content
            get_note_event = (
                note_app.get_note_by_id(note_id=self.prep_note_id)
                .oracle()
                .depends_on(search_notes_event, delay_seconds=1)
            )

            # Oracle: Agent proposes updating the note
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I noticed the Client Demo meeting was rescheduled by Sarah Chen "
                        "from Nov 20 at 2:00 PM to Nov 22 at 3:00 PM. Your preparation note "
                        "still references the old date and time. Would you like me to update "
                        "the note title and content to reflect the new meeting time?"
                    )
                )
                .oracle()
                .depends_on([reschedule_event, get_note_event], delay_seconds=2)
            )

            # Oracle: User accepts
            acceptance_event = (
                aui.accept_proposal(content="Yes, please update the note with the new meeting time.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle: Agent updates the note title
            update_title_event = (
                note_app.update_note(
                    note_id=self.prep_note_id,
                    title="Client Demo Preparation - Nov 22",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle: Agent updates the note content with new date/time
            update_content_event = (
                note_app.update_note(
                    note_id=self.prep_note_id,
                    content=(
                        "Meeting scheduled for Nov 22 at 3:00 PM.\n\n"
                        "Agenda:\n"
                        "- Product feature walkthrough\n"
                        "- Q&A session\n"
                        "- Pricing discussion\n\n"
                        "Attendees: Sarah Chen, Mike Rodriguez\n\n"
                        "Preparation checklist:\n"
                        "- Prepare demo environment\n"
                        "- Load sample data\n"
                        "- Test all key features\n"
                        "- Prepare backup slides"
                    ),
                )
                .oracle()
                .depends_on(update_title_event, delay_seconds=1)
            )

        self.events = [
            reschedule_event,
            search_notes_event,
            get_note_event,
            proposal_event,
            acceptance_event,
            update_title_event,
            update_content_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate essential outcomes.

        Checks:
        1. Agent sent proposal to user
        2. Agent updated the note with new date/time (Nov 22 or 3:00 PM)
        """
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Proposal sent to user
            proposal_found = any(
                e.action.class_name == "PAREAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check 2: Note updated with new date/time
            note_update_found = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "update_note"
                and (
                    "22" in str(e.action.args.get("title", ""))
                    or "22" in str(e.action.args.get("content", ""))
                    or "3:00" in str(e.action.args.get("content", ""))
                )
                for e in agent_events
            )

            success = proposal_found and note_update_found

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user")
                if not note_update_found:
                    missing.append("note update with new date/time (Nov 22 or 3:00 PM)")
                return ScenarioValidationResult(
                    success=False,
                    rationale=f"Missing: {', '.join(missing)}",
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
