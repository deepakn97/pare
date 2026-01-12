"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.reminder import Reminder
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import HomeScreenSystemApp, PASAgentUserInterface, StatefulCalendarApp
from pas.apps.note import StatefulNotesApp
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("reminder_driven_meeting_review")
class ReminderDrivenMeetingReview(PASScenario):
    """Agent consolidates client meeting outcomes by reviewing calendar events triggered by a follow-up reminder.

    The user has a reminder titled "Follow up on client meetings from last week" due on Monday, January 20th, 2025 at 9:00 AM. Since reminders are not
    delivered as environment notifications in PAS, the run is triggered by an external calendar notification that says the follow-up reminder is due and
    explicitly instructs the user/agent to check the Reminders app for the client list. The reminder description contains three client names: Sarah Thompson,
    Marcus Rodriguez, and Jennifer Lee. The calendar already contains three separate meeting events from the previous week (January 13-17) with each of these
    clients, and each event has a brief description field with discussion topics but no documented outcomes. When the trigger arrives, the agent must:
    1. Read the due reminder and extract the list of three client names
    2. Search/read the calendar for the matching meetings
    3. Propose a documentation plan to the user and collect outcomes
    4. Edit each calendar event to append outcome notes
    5. Create a consolidated note in the "Work" folder summarizing outcomes
    6. Delete the follow-up reminder since the review task is complete
    7. Send a confirmation summarizing what was updated

    This scenario exercises reminder-triggered workflows, calendar filtering by attendee, calendar event modification (edit_calendar_event), multi-event data synthesis, and cross-app coordination where reminders drive calendar updates and note creation rather than the reverse pattern..
    """

    start_time = datetime(2025, 1, 20, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Reminder app
        self.reminder = StatefulReminderApp(name="Reminders")

        # Seed the follow-up reminder that will trigger at start_time
        # The reminder contains three client names in the description
        self.reminder.reminders["reminder_001"] = Reminder(
            reminder_id="reminder_001",
            title="Follow up on client meetings from last week",
            description="Review and document outcomes for meetings with Sarah Thompson, Marcus Rodriguez, and Jennifer Lee",
            due_datetime=datetime(2025, 1, 20, 9, 0, 0, tzinfo=UTC),
            repetition_unit=None,
            repetition_value=None,
            time_notified=None,
        )

        # Initialize Calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Seed three client meetings from last week (Jan 13-17)
        # Meeting 1: Sarah Thompson on Monday, Jan 13, 2025 at 10:00 AM
        self.calendar.events["event_001"] = CalendarEvent(
            event_id="event_001",
            title="Client Meeting - Sarah Thompson",
            start_datetime=datetime(2025, 1, 13, 10, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 1, 13, 11, 0, 0, tzinfo=UTC).timestamp(),
            tag="Client Meeting",
            description="Discussion topics: Q1 budget proposal, new project timeline, resource allocation",
            location="Conference Room A",
            attendees=["Sarah Thompson", "User"],
        )

        # Meeting 2: Marcus Rodriguez on Wednesday, Jan 15, 2025 at 2:00 PM
        self.calendar.events["event_002"] = CalendarEvent(
            event_id="event_002",
            title="Client Meeting - Marcus Rodriguez",
            start_datetime=datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 1, 15, 15, 0, 0, tzinfo=UTC).timestamp(),
            tag="Client Meeting",
            description="Discussion topics: Phase 2 implementation plan, technical requirements, deployment schedule",
            location="Zoom Meeting",
            attendees=["Marcus Rodriguez", "User"],
        )

        # Meeting 3: Jennifer Lee on Friday, Jan 17, 2025 at 3:00 PM
        self.calendar.events["event_003"] = CalendarEvent(
            event_id="event_003",
            title="Client Meeting - Jennifer Lee",
            start_datetime=datetime(2025, 1, 17, 15, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 1, 17, 16, 30, 0, tzinfo=UTC).timestamp(),
            tag="Client Meeting",
            description="Discussion topics: Contract renewal terms, pricing structure, support package options",
            location="Conference Room B",
            attendees=["Jennifer Lee", "User"],
        )

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")
        # No baseline notes needed; the consolidated note will be created during the event flow

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.reminder, self.calendar, self.note]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Calendar notification prompts the user/agent to check Reminders for a due follow-up task
            # Note: Reminders do not have notification templates, so we ground the trigger via a calendar notification.
            env_calendar_trigger_event = calendar_app.add_calendar_event_by_attendee(
                who_add="Calendar Assistant",
                title="Reminder: Follow up on client meetings from last week",
                start_datetime="2025-01-20 09:00:00",
                end_datetime="2025-01-20 09:05:00",
                attendees=["User"],
                location="",
                description=(
                    'Your reminder "Follow up on client meetings from last week" is due now. '
                    "Please check the Reminders app for the client list and document outcomes in the meeting events."
                ),
            ).delayed(1)

            # Agent Event 1: Agent checks for due reminders
            # Motivation: env_calendar_trigger_event explicitly says the follow-up reminder is due now and to check Reminders for details.
            check_reminders_event = (
                reminder_app.get_due_reminders().oracle().depends_on(env_calendar_trigger_event, delay_seconds=1)
            )

            # Agent Event 2: Agent reads the specific reminder details to extract client names
            # Motivation: The get_due_reminders call revealed reminder_001 is due
            get_reminder_event = (
                reminder_app.get_all_reminders().oracle().depends_on(check_reminders_event, delay_seconds=1)
            )

            # Agent Event 3: Agent searches calendar for Sarah Thompson's meetings
            # Motivation: Reminder description mentions "Sarah Thompson" - search for her meetings
            search_sarah_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-01-13 00:00:00", end_datetime="2025-01-17 23:59:59"
                )
                .oracle()
                .depends_on(get_reminder_event, delay_seconds=2)
            )

            # Agent Event 4: Agent gets details of Sarah Thompson's meeting
            # Motivation: search_sarah_event returned event_001, now retrieve full details
            get_sarah_event = (
                calendar_app.get_calendar_event(event_id="event_001")
                .oracle()
                .depends_on(search_sarah_event, delay_seconds=1)
            )

            # Agent Event 5: Agent gets details of Marcus Rodriguez's meeting
            # Motivation: Reminder mentions "Marcus Rodriguez" - retrieve his meeting details
            get_marcus_event = (
                calendar_app.get_calendar_event(event_id="event_002")
                .oracle()
                .depends_on(get_sarah_event, delay_seconds=1)
            )

            # Agent Event 6: Agent gets details of Jennifer Lee's meeting
            # Motivation: Reminder mentions "Jennifer Lee" - retrieve her meeting details
            get_jennifer_event = (
                calendar_app.get_calendar_event(event_id="event_003")
                .oracle()
                .depends_on(get_marcus_event, delay_seconds=1)
            )

            # Agent Event 7: Agent proposes to document meeting outcomes
            # Motivation: Agent has gathered all three client meeting details and can now propose the documentation workflow
            proposal_event = (
                aui.send_message_to_user(
                    content="I found your due reminder about following up on client meetings from last week. I've identified three client meetings: Sarah Thompson (Jan 13), Marcus Rodriguez (Jan 15), and Jennifer Lee (Jan 17). Would you like me to document the outcomes for these meetings and create a consolidated summary note?"
                )
                .oracle()
                .depends_on(get_jennifer_event, delay_seconds=2)
            )

            # User Event: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please document the outcomes and create a summary note. For Sarah's meeting, we approved the Q1 budget. For Marcus, the client approved Phase 2. For Jennifer, we agreed on a 2-year renewal."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Agent Event 8: Agent edits Sarah Thompson's calendar event to add outcome
            # Motivation: User provided outcome for Sarah's meeting in acceptance; now append it to event description
            edit_sarah_event = (
                calendar_app.edit_calendar_event(
                    event_id="event_001",
                    description="Discussion topics: Q1 budget proposal, new project timeline, resource allocation\n\nOutcome: Client approved Q1 budget proposal.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Agent Event 9: Agent edits Marcus Rodriguez's calendar event to add outcome
            # Motivation: User provided outcome for Marcus's meeting; append it to event description
            edit_marcus_event = (
                calendar_app.edit_calendar_event(
                    event_id="event_002",
                    description="Discussion topics: Phase 2 implementation plan, technical requirements, deployment schedule\n\nOutcome: Client approved Phase 2 implementation plan.",
                )
                .oracle()
                .depends_on(edit_sarah_event, delay_seconds=1)
            )

            # Agent Event 10: Agent edits Jennifer Lee's calendar event to add outcome
            # Motivation: User provided outcome for Jennifer's meeting; append it to event description
            edit_jennifer_event = (
                calendar_app.edit_calendar_event(
                    event_id="event_003",
                    description="Discussion topics: Contract renewal terms, pricing structure, support package options\n\nOutcome: Agreed on 2-year contract renewal.",
                )
                .oracle()
                .depends_on(edit_marcus_event, delay_seconds=1)
            )

            # Agent Event 11: Agent creates consolidated summary note
            # Motivation: All calendar events have been updated with outcomes; now synthesize into a single note
            create_note_event = (
                note_app.create_note(
                    folder="Work",
                    title="Client Meeting Summary - Week of Jan 13",
                    content="""Summary of client meetings from the week of January 13, 2025:

1. Sarah Thompson (Jan 13, 10:00 AM - Conference Room A)
   - Topics: Q1 budget proposal, new project timeline, resource allocation
   - Outcome: Client approved Q1 budget proposal

2. Marcus Rodriguez (Jan 15, 2:00 PM - Zoom Meeting)
   - Topics: Phase 2 implementation plan, technical requirements, deployment schedule
   - Outcome: Client approved Phase 2 implementation plan

3. Jennifer Lee (Jan 17, 3:00 PM - Conference Room B)
   - Topics: Contract renewal terms, pricing structure, support package options
   - Outcome: Agreed on 2-year contract renewal

All meeting outcomes have been documented in the respective calendar events.""",
                )
                .oracle()
                .depends_on(edit_jennifer_event, delay_seconds=2)
            )

            # Agent Event 12: Agent deletes the completed follow-up reminder
            # Motivation: The review task is complete; the reminder is no longer needed
            delete_reminder_event = (
                reminder_app.delete_reminder(reminder_id="reminder_001")
                .oracle()
                .depends_on(create_note_event, delay_seconds=1)
            )

            # Agent Event 13: Agent sends confirmation message
            # Motivation: All actions complete; inform user of completion
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've completed the client meeting follow-up. Updated all three calendar events with outcomes and created a consolidated summary note titled 'Client Meeting Summary - Week of Jan 13' in your Work folder. The follow-up reminder has been marked as complete."
                )
                .oracle()
                .depends_on(delete_reminder_event, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            env_calendar_trigger_event,
            check_reminders_event,
            get_reminder_event,
            search_sarah_event,
            get_sarah_event,
            get_marcus_event,
            get_jennifer_event,
            proposal_event,
            acceptance_event,
            edit_sarah_event,
            edit_marcus_event,
            edit_jennifer_event,
            create_note_event,
            delete_reminder_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT event types (oracle events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent checked for due reminders
            # Equivalence: get_due_reminders OR get_all_reminders
            reminder_check_found = any(
                e.action.class_name == "StatefulReminderApp"
                and e.action.function_name in ["get_due_reminders", "get_all_reminders"]
                for e in agent_events
            )

            # STRICT Check 2: Agent queried calendar for meeting events
            # Equivalence: get_calendar_events_from_to OR get_calendar_event (at least once)
            calendar_query_found = any(
                e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name in ["get_calendar_events_from_to", "get_calendar_event"]
                for e in agent_events
            )

            # STRICT Check 3: Agent sent a proposal to user
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent edited at least one calendar event with updated description
            # This verifies the agent modified calendar events (core action)
            calendar_edit_found = any(
                e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "edit_calendar_event"
                and "description" in e.action.args
                for e in agent_events
            )

            # FLEXIBLE Check: Count how many calendar events were edited
            # Ideally 3 (one for each client), but we'll be flexible if at least 1 exists
            calendar_edits_count = sum(
                1
                for e in agent_events
                if e.action.class_name == "StatefulCalendarApp" and e.action.function_name == "edit_calendar_event"
            )

            # STRICT Check 5: Agent created a note in the Work folder
            # Verify note creation with folder="Work" (structural check)
            note_created = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                and e.action.args.get("folder") == "Work"
                for e in agent_events
            )

            # STRICT Check 6: Agent deleted the reminder
            reminder_deleted = any(
                e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "delete_reminder"
                and "reminder_id" in e.action.args
                and e.action.args["reminder_id"] == "reminder_001"
                for e in agent_events
            )

            # Assemble success criteria: all strict checks must pass
            success = (
                reminder_check_found
                and calendar_query_found
                and proposal_found
                and calendar_edit_found
                and note_created
                and reminder_deleted
            )

            # Build rationale if validation fails
            if not success:
                missing_checks = []
                if not reminder_check_found:
                    missing_checks.append("agent did not check for due reminders")
                if not calendar_query_found:
                    missing_checks.append("agent did not query calendar for meeting events")
                if not proposal_found:
                    missing_checks.append("agent did not send proposal to user")
                if not calendar_edit_found:
                    missing_checks.append("agent did not edit any calendar events")
                if not note_created:
                    missing_checks.append("agent did not create consolidated note in Work folder")
                if not reminder_deleted:
                    missing_checks.append("agent did not delete the follow-up reminder")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
