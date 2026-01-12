"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
)
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("note_update_reflects_meeting_changes")
class NoteUpdateReflectsMeetingChanges(PASScenario):
    """Agent synchronizes meeting notes when calendar events are rescheduled. The user has a note in their "Work" folder titled "Client Demo Preparation - Nov 20" containing detailed preparation items, attendee names, and the original meeting time (Nov 20 at 2:00 PM). The user receives a calendar notification that the "Client Demo" event has been rescheduled to Nov 22 at 3:00 PM by the organizer. The agent must: 1. Read the calendar reschedule notification and extract the new date/time 2. Search notes for content matching the original meeting title and date 3. Open the relevant note and identify outdated temporal references 4. Update the note title to reflect the new date ("Client Demo Preparation - Nov 22") 5. Update the note content to replace "Nov 20 at 2:00 PM" with "Nov 22 at 3:00 PM" 6. Confirm with the user that the preparation note was synchronized with the calendar change.

    This scenario exercises calendar-to-notes synchronization, temporal reference update, cross-app data consistency, and proactive information maintenance when external events trigger stale note content..
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

        # Seed baseline note in Work folder created before start_time
        # This note contains the original meeting time (Nov 20 at 2:00 PM)
        self.note.create_note_with_time(
            folder="Work",
            title="Client Demo Preparation - Nov 20",
            content="Meeting scheduled for Nov 20 at 2:00 PM.\n\nAgenda:\n- Product feature walkthrough\n- Q&A session\n- Pricing discussion\n\nAttendees: Sarah Chen, Mike Rodriguez\n\nPreparation checklist:\n- Prepare demo environment\n- Load sample data\n- Test all key features\n- Prepare backup slides",
            pinned=False,
            created_at="2025-11-15 14:30:00",
            updated_at="2025-11-15 14:30:00",
        )

        # Initialize Calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Seed baseline calendar event (original event before reschedule)
        # This will be updated/deleted in Step 3 when the reschedule notification arrives
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
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Calendar reschedule notification from organizer Sarah Chen
            # This is the concrete exogenous trigger that starts the flow
            reschedule_notification = calendar_app.add_calendar_event_by_attendee(
                who_add="Sarah Chen",
                title="Client Demo",
                start_datetime="2025-11-22 15:00:00",  # Nov 22 at 3:00 PM (new time)
                end_datetime="2025-11-22 16:30:00",
                description="Client Demo Preparation - rescheduled",
                location="Conference Room B",
                attendees=["Sarah Chen", "Mike Rodriguez"],
            ).delayed(10)

            # Oracle Event 1: Agent searches notes for content matching the meeting
            # Evidence: the reschedule notification above mentions "Client Demo", motivating the search
            search_notes = (
                note_app.search_notes(query="Client Demo").oracle().depends_on(reschedule_notification, delay_seconds=2)
            )

            # Oracle Event 2: Agent retrieves the specific note by ID to read full content
            # Evidence: search_notes above will reveal the note ID, allowing the agent to fetch it
            get_note = (
                note_app.get_note_by_id(note_id=next(iter(note_app.folders["Work"].notes.keys())))
                .oracle()
                .depends_on(search_notes, delay_seconds=1)
            )

            # Oracle Event 3: Agent proposes updating the note to reflect the reschedule
            # Evidence: the reschedule_notification env event shows the new date/time (Nov 22 at 3:00 PM)
            proposal = (
                aui.send_message_to_user(
                    content="I noticed the Client Demo meeting was rescheduled by Sarah Chen from Nov 20 at 2:00 PM to Nov 22 at 3:00 PM. Your preparation note still references the old date and time. Would you like me to update the note to reflect the new meeting time?"
                )
                .oracle()
                .depends_on([reschedule_notification, get_note], delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please update the note with the new meeting time.")
                .oracle()
                .depends_on(proposal, delay_seconds=2)
            )

            # Oracle Event 5: Agent updates the note title to reflect the new date
            # Evidence: acceptance event above confirms user approval
            update_title = (
                note_app.update_note(
                    note_id=next(iter(note_app.folders["Work"].notes.keys())),
                    title="Client Demo Preparation - Nov 22",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

            # Oracle Event 6: Agent updates the note content to replace the old time with the new time
            # Evidence: acceptance event confirms the action; new time comes from reschedule_notification
            update_content = (
                note_app.update_note(
                    note_id=next(iter(note_app.folders["Work"].notes.keys())),
                    content="Meeting scheduled for Nov 22 at 3:00 PM.\n\nAgenda:\n- Product feature walkthrough\n- Q&A session\n- Pricing discussion\n\nAttendees: Sarah Chen, Mike Rodriguez\n\nPreparation checklist:\n- Prepare demo environment\n- Load sample data\n- Test all key features\n- Prepare backup slides",
                )
                .oracle()
                .depends_on(update_title, delay_seconds=1)
            )

            # Oracle Event 7: Agent confirms completion with the user
            confirmation = (
                aui.send_message_to_user(
                    content="I've updated your Client Demo preparation note to reflect the new meeting time (Nov 22 at 3:00 PM). The note title and content have been synchronized with the calendar change."
                )
                .oracle()
                .depends_on(update_content, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            reschedule_notification,
            search_notes,
            get_note,
            proposal,
            acceptance,
            update_title,
            update_content,
            confirmation,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent searched for notes related to the meeting
            # Evidence: The reschedule notification mentioned "Client Demo", so agent should search notes
            search_notes_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "search_notes"
                for e in agent_events
            )

            # STRICT Check 2: Agent retrieved the note to read its content
            # Evidence: Agent needs to read the note to identify outdated temporal references
            # Accept either get_note_by_id OR list_notes as equivalent ways to access note content
            get_note_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["get_note_by_id", "list_notes"]
                for e in agent_events
            )

            # STRICT Check 3: Agent sent proposal to the user
            # Evidence: Agent must offer to update the note before taking action
            # FLEXIBLE: Do not check exact content wording, just that the proposal happened
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent updated the note (title and/or content with new date/time)
            # Evidence: User acceptance requires the agent to update the note with Nov 22 at 3:00 PM
            # Look for update_note calls that reference the new date/time
            note_update_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "update_note"
                and (
                    ("22" in str(e.action.args.get("title", "")) or "22" in str(e.action.args.get("content", "")))
                    or ("3" in str(e.action.args.get("content", "")))
                )
                for e in agent_events
            )

            # All strict checks must pass
            success = search_notes_found and get_note_found and proposal_found and note_update_found

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not search_notes_found:
                    missing_checks.append("note search for 'Client Demo'")
                if not get_note_found:
                    missing_checks.append("note retrieval by ID or list")
                if not proposal_found:
                    missing_checks.append("proposal message to user")
                if not note_update_found:
                    missing_checks.append("note update with new date/time (Nov 22 or 3:00 PM)")

                rationale = f"Missing required agent actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
