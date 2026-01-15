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


@register_scenario("cancelled_meeting_note_cleanup")
class CancelledMeetingNoteCleanup(PASScenario):
    """Agent cleans up preparation notes when calendar events are cancelled by organizers.

    The user has a note in their "Work" folder titled "Client Onboarding Meeting Prep - Nov 28" containing detailed
    preparation materials, agenda items, and attendee information for an upcoming client meeting scheduled for November
    28th at 3:00 PM. The meeting organizer sends a calendar cancellation notification due to the client's scheduling
    conflict. A follow-up calendar note/reminder explicitly references the prep note title so the agent can locate it
    without guessing. The agent must:
    1. Recognize the calendar event cancellation notification
    2. Read the follow-up cancellation note/reminder to get the exact prep note title
    3. Search notes for that prep note title to identify the now-obsolete note
    4. Propose deleting the note to avoid clutter
    5. Delete the note after user acceptance
    6. Confirm with the user that the workspace has been cleaned up.

    This scenario exercises calendar-to-notes reverse synchronization, cleanup automation when external events invalidate prepared materials, cross-app coordination for workspace maintenance, and proactive information lifecycle management..
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

        # Initialize Calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Populate baseline data: calendar event scheduled for Nov 28 at 3:00 PM
        # The event exists before start_time and will be cancelled during the scenario
        self.calendar_event_id = self.calendar.add_calendar_event(
            title="Client Onboarding Meeting",
            start_datetime="2025-11-28 15:00:00",
            end_datetime="2025-11-28 16:30:00",
            location="Conference Room B",
            description="Onboarding meeting with new client - reviewing contract terms, project scope, and timeline",
            attendees=["Sarah Chen", "User"],
            tag="work",
        )

        # Populate baseline data: preparation note in Work folder
        # Created a few days before the meeting
        self.prep_note_id = self.note.create_note_with_time(
            folder="Work",
            title="Client Onboarding Meeting Prep - Nov 28",
            content="""Meeting preparation for Client Onboarding on November 28th at 3:00 PM

Agenda Items:
1. Contract review - key terms and conditions
2. Project scope discussion - deliverables and milestones
3. Timeline and resource allocation
4. Communication protocols and points of contact
5. Next steps and action items

Attendees:
- Sarah Chen (Project Manager)
- User

Location: Conference Room B

Materials to prepare:
- Contract documents
- Project proposal slides
- Resource allocation chart
- Communication plan template

Key Points to Cover:
- Establish clear expectations
- Define success metrics
- Set up regular check-in schedule""",
            created_at="2025-11-15 10:30:00",
            updated_at="2025-11-17 14:20:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.calendar]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Event 1: Calendar event cancelled by organizer (environment event - concrete exogenous trigger)
            # Sarah Chen cancels the meeting due to scheduling conflict
            cancellation_event = calendar_app.delete_calendar_event_by_attendee(
                event_id=self.calendar_event_id, who_delete="Sarah Chen"
            ).delayed(20)

            # Event 2: Organizer adds a follow-up calendar reminder with explicit prep-note title
            # Rationale: delete_calendar_event_by_attendee only includes event_id, so the agent needs an explicit cue
            # for which Notes entry to clean up.
            followup_event = calendar_app.add_calendar_event_by_attendee(
                who_add="Sarah Chen",
                title="Client onboarding update: clean up prep note",
                start_datetime="2025-11-18 09:30:00",
                end_datetime="2025-11-18 09:40:00",
                location="",
                description=(
                    "Update: The Client Onboarding Meeting on Nov 28 at 3:00 PM has been cancelled (client scheduling conflict). "
                    "You can delete any related notes for the previous Client Onboarding Meeting since they are not needed anymore.\n\n"
                ),
            ).delayed(25)

            # Oracle Event 1: Agent reads calendar context to observe the explicit cleanup instruction + note title
            # Motivation: followup_event contains the exact prep note title to look up in Notes.
            read_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 00:00:00",
                    end_datetime="2025-11-19 00:00:00",
                )
                .oracle()
                .depends_on(followup_event, delay_seconds=2)
            )

            # The agent observes the cancellation + follow-up instruction and searches for the specific prep note
            search_notes_event = (
                note_app.search_notes(query="Client Onboarding Meeting")
                .oracle()
                .depends_on(read_calendar_event, delay_seconds=3)
            )

            # Agent proposes cleanup action based on the cancellation notification
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw that Sarah Chen cancelled the Client Onboarding Meeting (Nov 28) and left a follow-up note to clean up the prep note for the previous Client Onboarding Meeting. Would you like me to delete that prep note since the meeting is no longer happening?"
                )
                .oracle()
                .depends_on(search_notes_event, delay_seconds=2)
            )

            # User accepts the cleanup proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please delete the prep note.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Agent deletes the obsolete preparation note
            delete_note_event = (
                note_app.delete_note(note_id=self.prep_note_id).oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # Agent confirms cleanup completion
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've deleted the Client Onboarding Meeting prep note. Your workspace is now cleaned up."
                )
                .oracle()
                .depends_on(delete_note_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            cancellation_event,
            followup_event,
            read_calendar_event,
            search_notes_event,
            proposal_event,
            acceptance_event,
            delete_note_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent searched for notes related to the cancelled meeting
            # Accepting list_notes or search_notes as equivalent methods to detect related notes
            notes_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["search_notes", "list_notes"]
                for e in log_entries
            )

            # STRICT Check 2: Agent proposed cleanup action to the user
            # Content-flexible: we verify the message was sent but don't constrain exact wording
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 3: Agent deleted the preparation note after user acceptance
            # Verifies the correct note_id was deleted
            note_deleted = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "delete_note"
                and e.action.args.get("note_id") == self.prep_note_id
                for e in log_entries
            )

            # Collect missing checks for rationale
            missing_checks = []
            if not notes_search_found:
                missing_checks.append("agent did not search notes for cancelled meeting")
            if not proposal_found:
                missing_checks.append("agent did not propose cleanup to user")
            if not note_deleted:
                missing_checks.append("agent did not delete the obsolete preparation note")

            success = notes_search_found and proposal_found and note_deleted
            rationale = "; ".join(missing_checks) if missing_checks else "all checks passed"

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
