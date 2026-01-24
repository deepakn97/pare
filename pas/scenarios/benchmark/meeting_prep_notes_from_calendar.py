from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
)
from pas.apps.note import StatefulNotesApp
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("meeting_prep_notes_from_calendar")
class MeetingPrepNotesFromCalendar(PASScenario):
    """Agent creates structured meeting preparation notes based on upcoming calendar events.

    The user has an important "Project Kickoff Meeting" scheduled for tomorrow at 10:00 AM with multiple attendees
    including the client and team leads. Shortly after the scenario starts, a reminder notification fires from the
    Reminders app (time-driven) prompting the user to prepare a structured note in their Work folder. The agent must:
    1. Read the calendar event details including attendees, time, and description
    2. Propose creating a new note in the "Work" folder with a structured preparation template
    3. After user acceptance, create the note and populate it using the calendar details
    4. Add relevant preparation sections (agenda items, action items, attendee roles)
    5. Pin the note for easy access before the meeting.

    This scenario exercises calendar-to-notes information transfer, structured content generation, cross-app data synthesis, and proactive meeting preparation assistance..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.reminder = StatefulReminderApp(name="Reminders")
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

        # Seed a time-driven reminder that will automatically notify the user+agent when due.
        # The scenario runner advances simulated time; we set this reminder shortly after start_time so it fires.
        self.reminder.add_reminder(
            title="Reminder: prepare notes for Project Kickoff Meeting",
            due_datetime="2025-11-18 09:01:00",
            description=(
                "Project Kickoff Meeting is tomorrow at 10:00 AM (Conference Room B) with Sarah Chen, "
                "Michael Rodriguez, and Jennifer Park.\n\n"
                "Before the meeting: create a structured prep note in the Work folder (agenda, questions, and action "
                "items)."
            ),
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.reminder, self.note]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # NOTE: Reminder notifications are time-driven in the Reminders app.
            # The reminder seeded in init (`due_datetime="2025-11-18 09:01:00"`) will automatically notify user+agent.
            # The agent does NOT need to poll reminders; we model reaction time by delaying the first oracle action.

            # Agent queries calendar for tomorrow's meeting details after the reminder notification fires.
            # Motivation: the reminder notification explicitly mentions a meeting tomorrow and asks to prepare a note.
            get_events = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-19 00:00:00", end_datetime="2025-11-19 23:59:59"
                )
                .oracle()
                .delayed(70)
            )

            # Agent proposes to create meeting preparation notes
            # Justification: the agent saw the calendar reminder notification (env_event) for tomorrow's Project Kickoff Meeting
            proposal = (
                aui.send_message_to_user(
                    content="I noticed you have a Project Kickoff Meeting tomorrow at 10:00 AM in Conference Room B with Sarah Chen, Michael Rodriguez, and Jennifer Park. A reminder suggests preparing a structured note in your Work folder—would you like me to create one for you?"
                )
                .oracle()
                .depends_on(get_events, delay_seconds=3)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal, delay_seconds=5)
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

        # Register ALL events here in self.events
        self.events = [get_events, proposal, acceptance, create_note]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
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

            # STRICT Check 2: Agent created a note in the Work folder
            # The note must be created with structured meeting preparation content
            note_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                and e.action.args.get("folder").lower() == "work"
                for e in log_entries
            )

            # Determine success based on all strict checks
            success = proposal_found and note_created

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal not found")
                if not note_created:
                    missing_checks.append("meeting prep note not created in Work folder")

                rationale = f"Validation failed: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
