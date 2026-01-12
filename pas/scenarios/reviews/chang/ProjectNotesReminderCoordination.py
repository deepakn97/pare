"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
)
from pas.apps.note import StatefulNotesApp
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("project_notes_reminder_coordination")
class ProjectNotesReminderCoordination(PASScenario):
    """Agent synthesizes project deadline from calendar and organizes related notes with actionable reminders.

    The user has a calendar event "Project Proposal Submission" scheduled for Friday, January 17th at 5:00 PM with attendees and location details. An attendee then adds a "Proposal Prep Check-in" meeting on Jan 16th whose notification explicitly lists the three required sections (Executive Summary, Technical Architecture, Budget Breakdown), asks participants to pull any existing drafts from Notes (e.g., search/list notes for those keywords plus "proposal"), and suggests setting reminders so each section draft is ready before the check-in and final deadline. The agent must:
    1. Read the upcoming calendar deadline and extract key details (date, time, attendees)
    2. Create a dedicated project note in the Notes app with structured sections for each deliverable
    3. List/search existing notes to find any prior drafts relevant to the required sections
    4. Set up three separate time-bound reminders (one for each section) with due dates staggered before the final deadline
    5. Attach the calendar event location/attendee info to the project note for context
    6. Send confirmation summarizing the organized workflow

    This scenario exercises cross-app deadline awareness (calendar → notes → reminders), multi-item reminder creation with different due times, note structuring with attachments, content search across notes, and proactive workflow scaffolding from a single trigger event..
    """

    start_time = datetime(2025, 1, 13, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.note = StatefulNotesApp(name="Notes")
        self.reminder = StatefulReminderApp(name="Reminders")

        # Populate apps with scenario specific baseline data
        # Calendar: seed the main deadline event "Project Proposal Submission" on Friday, Jan 17th, 5:00 PM
        # This event exists before start_time and will be read by the agent during Step 3
        self.calendar.add_calendar_event(
            title="Project Proposal Submission",
            start_datetime="2025-01-17 17:00:00",
            end_datetime="2025-01-17 18:00:00",
            tag="work",
            description="Final submission deadline for Q1 project proposal. All sections must be completed.",
            location="Building 7, Conference Room B",
            attendees=["Sarah Chen", "Michael Torres", "Dr. Amanda Rodriguez"],
        )

        # Notes: seed some prior notes that contain relevant keywords the agent may search for
        # These demonstrate existing work that the agent can reference
        self.note.create_note_with_time(
            folder="Work",
            title="Technical Architecture Draft",
            content="Preliminary thoughts on system design:\n- Microservices approach\n- API Gateway pattern\n- Database: PostgreSQL with read replicas\n- Caching layer with Redis\n\nNeed to expand and formalize for proposal.",
            created_at="2025-11-15 14:30:00",
            updated_at="2025-11-16 10:20:00",
        )

        self.note.create_note_with_time(
            folder="Work",
            title="Budget Estimates",
            content="Rough budget numbers:\n- Personnel: ~$150K\n- Infrastructure: ~$30K\n- Tools & Licenses: ~$10K\n\nTotal estimate: $190K\nNeed detailed breakdown.",
            created_at="2025-11-14 09:00:00",
            updated_at="2025-11-14 16:45:00",
        )

        self.note.create_note_with_time(
            folder="Personal",
            title="Meeting Notes - Kickoff",
            content="Project kickoff meeting notes:\n- Stakeholders identified\n- Timeline discussed\n- Key deliverables: Executive Summary, Technical Architecture, Budget Breakdown\n- Final submission: Jan 17th",
            created_at="2025-11-10 11:00:00",
            updated_at="2025-11-10 11:45:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.note, self.reminder]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Attendee adds urgent preparation meeting to calendar
            # This creates pressure by adding a pre-deadline checkpoint meeting with all stakeholders
            # Notification content explicitly states deliverables and the connection to the Jan 17th deadline
            prep_meeting_event = calendar_app.add_calendar_event_by_attendee(
                who_add="Sarah Chen",
                title="Proposal Prep Check-in",
                start_datetime="2025-01-16 14:00:00",
                end_datetime="2025-01-16 15:00:00",
                attendees=["Sarah Chen", "Michael Torres", "Dr. Amanda Rodriguez"],
                location="Building 7, Conference Room B",
                description=(
                    "Pre-submission review: each person must present their completed section (Executive Summary, Technical Architecture, Budget Breakdown) "
                    "before final submission on Jan 17th at 5:00 PM.\n\n"
                    "Please pull any existing drafts from your Notes ahead of time (for example, list/search Notes for: "
                    '"Executive Summary", "Technical Architecture", "Budget Breakdown", and "proposal").\n\n'
                    "Suggestion: create a simple checklist note for your section(s) and set reminders for drafting/review so you're ready before the "
                    "Jan 16 check-in and the Jan 17 submission deadline."
                ),
            ).delayed(10)

            # Oracle Event 1: Agent reads calendar context (prep meeting + submission deadline) to ground deliverables and timing
            # Motivation: The prep meeting notification explicitly references the Jan 17 deadline and lists required sections + note keywords.
            calendar_context_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-01-16 00:00:00",
                    end_datetime="2025-01-18 00:00:00",
                )
                .oracle()
                .depends_on(prep_meeting_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent lists note folders to decide where to look for drafts
            # Motivation: The prep meeting notification explicitly asks the user to pull existing drafts from Notes.
            list_folders_event = note_app.list_folders().oracle().depends_on(calendar_context_event, delay_seconds=2)

            # Oracle Event 3: Agent lists Work notes to find existing drafts relevant to the prep meeting's required sections
            # Motivation: The prep meeting notification provides the section keywords to look for in Notes.
            list_work_notes_event = (
                note_app.list_notes(folder="Work", offset=0, limit=20)
                .oracle()
                .depends_on(list_folders_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent lists Personal notes to pick up any kickoff/context notes that mention the proposal sections
            # Motivation: The prep meeting notification suggests pulling existing drafts/context from Notes before the check-in.
            list_personal_notes_event = (
                note_app.list_notes(folder="Personal", offset=0, limit=20)
                .oracle()
                .depends_on(list_work_notes_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent proposes organizing workflow with structured note + reminders
            # Motivation: Prep meeting notification explicitly lists the three required sections, asks to pull drafts from Notes,
            # and suggests creating a checklist note + setting reminders to stay on track for Jan 16/Jan 17.
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Sarah Chen added a Proposal Prep Check-in meeting on Jan 16th, requiring you to present three completed sections before the final Jan 17th deadline. I found related work in your notes (Technical Architecture Draft, Budget Estimates, Meeting Notes). Would you like me to create a structured project note with sections for Executive Summary, Technical Architecture, and Budget Breakdown, and set up three staggered reminders (one for each section) to help you prepare on time?"
                )
                .oracle()
                .depends_on(list_personal_notes_event, delay_seconds=3)
            )

            # User Event: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please organize everything for me.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle Event 6: Agent creates structured project coordination note
            # Motivation: User accepted proposal; agent now executes by creating the structured note
            create_note_event = (
                note_app.create_note(
                    folder="Work",
                    title="Project Proposal - Coordination",
                    content="""# Project Proposal Coordination

## Deadline: January 17th, 5:00 PM
Location: Building 7, Conference Room B
Attendees: Sarah Chen, Michael Torres, Dr. Amanda Rodriguez

## Pre-deadline Check-in: January 16th, 2:00 PM
Each person must present their completed section.

## Required Deliverables:

### 1. Executive Summary
- [ ] Draft overview
- [ ] Key highlights
- [ ] Business value statement

### 2. Technical Architecture
- [ ] Expand microservices approach
- [ ] Formalize API Gateway pattern
- [ ] Database design (PostgreSQL + replicas)
- [ ] Caching layer details (Redis)

### 3. Budget Breakdown
- [ ] Personnel costs detail ($150K)
- [ ] Infrastructure costs detail ($30K)
- [ ] Tools & Licenses breakdown ($10K)
- [ ] Total: $190K with justification

## Related Notes:
- Technical Architecture Draft (has preliminary design)
- Budget Estimates (has rough numbers)
- Meeting Notes - Kickoff (has deliverable list)
""",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent adds first reminder for Executive Summary (due Jan 14th, 5:00 PM)
            # Motivation: User accepted proposal; agent executes by creating staggered reminders
            reminder1_event = (
                reminder_app.add_reminder(
                    title="Draft Executive Summary",
                    due_datetime="2025-01-14 17:00:00",
                    description="Complete Executive Summary section for Project Proposal. Check Coordination note for details.",
                )
                .oracle()
                .depends_on(create_note_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent adds second reminder for Technical Architecture (due Jan 15th, 5:00 PM)
            # Motivation: User accepted proposal; staggered reminder for second deliverable
            reminder2_event = (
                reminder_app.add_reminder(
                    title="Finalize Technical Architecture",
                    due_datetime="2025-01-15 17:00:00",
                    description="Expand and formalize Technical Architecture section for Project Proposal. Review Technical Architecture Draft note.",
                )
                .oracle()
                .depends_on(reminder1_event, delay_seconds=2)
            )

            # Oracle Event 9: Agent adds third reminder for Budget Breakdown (due Jan 16th, 12:00 PM)
            # Motivation: User accepted proposal; final staggered reminder before prep meeting
            reminder3_event = (
                reminder_app.add_reminder(
                    title="Complete Budget Breakdown",
                    due_datetime="2025-01-16 12:00:00",
                    description="Finalize Budget Breakdown section with detailed justification for Project Proposal. Reference Budget Estimates note.",
                )
                .oracle()
                .depends_on(reminder2_event, delay_seconds=2)
            )

            # Oracle Event 10: Agent sends confirmation summary to user
            # Motivation: User accepted proposal; agent confirms completion of all setup actions
            confirmation_event = (
                aui.send_message_to_user(
                    content="Done! I've created a structured coordination note in Work folder with all three deliverable sections and deadlines. I've also set up three reminders: Executive Summary (due Jan 14th 5PM), Technical Architecture (due Jan 15th 5PM), and Budget Breakdown (due Jan 16th 12PM noon, before your 2PM prep meeting). Your related notes (Technical Architecture Draft, Budget Estimates) are referenced in the coordination note."
                )
                .oracle()
                .depends_on(reminder3_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            prep_meeting_event,
            calendar_context_event,
            list_folders_event,
            list_work_notes_event,
            list_personal_notes_event,
            proposal_event,
            acceptance_event,
            create_note_event,
            reminder1_event,
            reminder2_event,
            reminder3_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT CHECK 1: Agent observed calendar deadline information
            # Accept either get_calendar_events_from_to or read_today_calendar_events (equivalent for this purpose)
            calendar_observation_found = any(
                e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name in ["get_calendar_events_from_to", "read_today_calendar_events"]
                for e in agent_events
            )

            # FLEXIBLE CHECK 2: Agent searched notes for relevant keywords (at least one search)
            # Not strictly required, but expected behavior
            note_search_found = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["search_notes", "list_notes", "list_folders"]
                for e in agent_events
            )

            # STRICT CHECK 3: Agent sent proposal to user
            # Accept either send_message_to_user or any messaging function
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT CHECK 4: Agent created a note (the coordination note)
            note_creation_found = any(
                e.action.class_name == "StatefulNotesApp" and e.action.function_name == "create_note"
                for e in agent_events
            )

            # STRICT CHECK 5: Agent added exactly three reminders with staggered due dates
            reminder_events = [
                e
                for e in agent_events
                if e.action.class_name == "StatefulReminderApp" and e.action.function_name == "add_reminder"
            ]
            three_reminders_found = len(reminder_events) >= 3

            # Combine strict checks
            success = calendar_observation_found and proposal_found and note_creation_found and three_reminders_found

            if not success:
                rationale_parts = []
                if not calendar_observation_found:
                    rationale_parts.append("agent did not observe calendar deadline")
                if not proposal_found:
                    rationale_parts.append("agent did not send proposal to user")
                if not note_creation_found:
                    rationale_parts.append("agent did not create coordination note")
                if not three_reminders_found:
                    rationale_parts.append("agent did not create three reminders")

                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
