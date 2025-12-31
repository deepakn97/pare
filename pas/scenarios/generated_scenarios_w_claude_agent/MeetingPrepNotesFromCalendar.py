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


@register_scenario("meeting_prep_notes_from_calendar")
class MeetingPrepNotesFromCalendar(PASScenario):
    """Agent creates structured meeting preparation notes based on upcoming calendar events. The user has an important "Project Kickoff Meeting" scheduled for tomorrow at 10:00 AM with multiple attendees including the client and team leads. The agent receives a calendar notification reminding the user about this meeting. The agent must: 1. Read the calendar event details including attendees, time, and description 2. Create a new note in the "Work" folder with a structured preparation template 3. Extract key information from the calendar (meeting title, attendees, time, location) and populate the note 4. Add relevant preparation sections (agenda items, action items, attendee roles) 5. Pin the note for easy access before the meeting.

    This scenario exercises calendar-to-notes information transfer, structured content generation, cross-app data synthesis, and proactive meeting preparation assistance..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
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

        # Populate calendar with baseline data
        # The Project Kickoff Meeting is scheduled for tomorrow (Nov 19, 2025) at 10:00 AM
        # This is pre-existing state that the agent will discover after a notification trigger
        self.calendar.add_calendar_event(
            title="Project Kickoff Meeting",
            start_datetime="2025-11-19 10:00:00",
            end_datetime="2025-11-19 11:30:00",
            location="Conference Room B",
            description="Initial meeting to discuss project goals, timeline, and deliverables with the client team.",
            attendees=["Sarah Chen", "Michael Rodriguez", "Jennifer Park"],
            tag="work",
        )

        # Add a few other existing calendar events for context
        self.calendar.add_calendar_event(
            title="Team Standup",
            start_datetime="2025-11-18 09:30:00",
            end_datetime="2025-11-18 09:45:00",
            location="Virtual",
            description="Daily team sync",
            attendees=["Michael Rodriguez", "Jennifer Park"],
            tag="work",
        )

        # Populate notes app with existing notes to show the Work folder is in use
        self.note.create_note_with_time(
            folder="Work",
            title="Q4 Planning Notes",
            content="Key objectives for Q4:\n- Complete client onboarding\n- Launch new feature set\n- Team capacity planning",
            pinned=False,
            created_at="2025-11-15 14:30:00",
            updated_at="2025-11-15 14:30:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.note]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # Environment event: calendar reminder notification about tomorrow's meeting
            # This is the triggering cue that motivates all subsequent agent actions
            env_event = calendar_app.add_calendar_event_by_attendee(
                who_add="Sarah Chen",
                title="Project Kickoff Meeting Reminder",
                start_datetime="2025-11-19 10:00:00",
                end_datetime="2025-11-19 10:00:00",
                description="Reminder: Project Kickoff Meeting tomorrow at 10:00 AM in Conference Room B with Sarah Chen, Michael Rodriguez, and Jennifer Park. Please prepare for the meeting by creating a structured preparation note in your Work folder.",
            )

            # Agent detects the calendar reminder and queries calendar for event details
            # Motivation: the reminder notification explicitly mentions a meeting tomorrow, so the agent needs to retrieve full event details
            get_events = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-19 00:00:00", end_datetime="2025-11-19 23:59:59"
                )
                .oracle()
                .depends_on(env_event, delay_seconds=2)
            )

            # Agent proposes to create meeting preparation notes
            # Justification: the agent saw the calendar reminder notification (env_event) for tomorrow's Project Kickoff Meeting
            proposal = (
                aui.send_message_to_user(
                    content="I noticed you have a Project Kickoff Meeting tomorrow at 10:00 AM in Conference Room B with Sarah Chen, Michael Rodriguez, and Jennifer Park. According to Sarah Chen's reminder, would you like me to create a structured preparation note for this meeting in your Work folder?"
                )
                .oracle()
                .depends_on(get_events, delay_seconds=3)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please create a preparation note for the meeting.")
                .oracle()
                .depends_on(proposal, delay_seconds=5)
            )

            # Agent creates the meeting preparation note with structured content
            # Using information retrieved from the calendar event query
            create_note = (
                note_app.create_note(
                    folder="Work",
                    title="Meeting Prep: Project Kickoff Meeting",
                    content="""Meeting: Project Kickoff Meeting
Time: November 19, 2025, 10:00 AM - 11:30 AM
Location: Conference Room B
Attendees: Sarah Chen, Michael Rodriguez, Jennifer Park

Agenda Items:
- Project goals and objectives
- Timeline and milestones
- Deliverables overview
- Resource allocation
- Next steps

Preparation Notes:
- Review project scope documentation
- Prepare questions about timeline
- Identify potential roadblocks

Action Items:
- (To be filled during meeting)

Attendee Roles:
- Sarah Chen: Client lead
- Michael Rodriguez: Team member
- Jennifer Park: Team member""",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=4)
            )

            # Agent confirms completion
            completion = (
                aui.send_message_to_user(
                    content="I've created a meeting preparation note titled 'Meeting Prep: Project Kickoff Meeting' in your Work folder with structured sections for agenda, preparation notes, action items, and attendee information."
                )
                .oracle()
                .depends_on(create_note, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [env_event, get_events, proposal, acceptance, create_note, completion]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal to user mentioning the meeting
            # The proposal must reference the Project Kickoff Meeting and show awareness of the calendar reminder trigger
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent queried the calendar to retrieve event details
            # Using get_calendar_events_from_to to fetch events for tomorrow (Nov 19)
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                and "2025-11-19" in e.action.args.get("start_datetime", "")
                for e in log_entries
            )

            # STRICT Check 3: Agent created a note in the Work folder
            # The note must be created with structured meeting preparation content
            note_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                and e.action.args.get("folder").lower() == "work"
                and any(
                    keyword in e.action.args.get("content", "").lower() for keyword in ["meeting", "prep", "kickoff"]
                )
                for e in log_entries
            )

            # Determine success based on all strict checks
            success = proposal_found and calendar_check_found and note_created

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal not found")
                if not calendar_check_found:
                    missing_checks.append("calendar query not performed")
                if not note_created:
                    missing_checks.append("meeting prep note not created in Work folder")

                rationale = f"Validation failed: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
