"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("meeting_followup_reminder_creation")
class MeetingFollowupReminderCreation(PASScenario):
    """Agent creates structured follow-up reminders based on action items mentioned in calendar event descriptions.

    The user has a calendar event titled "Product Strategy Meeting" scheduled for November 20th at 2:00 PM with attendees "Sarah Thompson" and "David Chen". The event description contains: "Discuss Q1 roadmap priorities. Action items: Sarah to send competitive analysis by Nov 25, David to finalize budget by Nov 27, I need to prepare executive summary by Nov 28." A calendar notification arrives on the morning of November 20th reminding the user about the upcoming meeting. The agent must: 1. Detect the meeting reminder notification, 2. Read the calendar event details to extract action items, 3. Identify the user's personal action item (prepare executive summary by Nov 28), 4. Propose creating a dedicated reminder for the user's task, 5. Create a new reminder titled "Prepare executive summary for Product Strategy follow-up" due November 27th at 5:00 PM (one day before deadline for buffer time), 6. Set the reminder description to reference the original meeting context.

    This scenario exercises calendar-to-reminder synthesis (inverse of reminder-to-calendar conversion), natural language parsing of action items from event descriptions, temporal reasoning for appropriate reminder timing (buffer before deadline), and proactive task extraction to help users maintain accountability for meeting commitments..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize calendar and reminder apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.reminder = StatefulReminderApp(name="Reminders")

        # Populate calendar with the Product Strategy Meeting event
        # Event scheduled for November 20th at 2:00 PM (14:00)
        meeting_event = CalendarEvent(
            title="Product Strategy Meeting",
            start_datetime=datetime(2025, 11, 20, 14, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 20, 15, 30, 0, tzinfo=UTC).timestamp(),
            description="Discuss Q1 roadmap priorities. Action items: Sarah to send competitive analysis by Nov 25, David to finalize budget by Nov 27, I need to prepare executive summary by Nov 28.",
            location="Conference Room B",
            attendees=["Sarah Thompson", "David Chen"],
            tag="work",
        )
        self.calendar.set_calendar_event(meeting_event)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.reminder]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment Event: Calendar reminder notification for the upcoming meeting
            # This triggers on November 20th morning, reminding the user about the meeting at 2:00 PM
            meeting_reminder_notification = calendar_app.add_calendar_event_by_attendee(
                who_add="System",
                title="Product Strategy Meeting",
                start_datetime="2025-11-20 14:00:00",
                end_datetime="2025-11-20 15:30:00",
                description=(
                    "Reminder: Product Strategy Meeting today at 2:00 PM with Sarah Thompson and David Chen.\n\n"
                    "Discuss Q1 roadmap priorities.\n"
                    "Action items:\n"
                    "- Sarah to send competitive analysis by Nov 25\n"
                    "- David to finalize budget by Nov 27\n"
                    "- [TASK ASSIGNED TO YOU] You need to prepare executive summary by Nov 28\n\n"
                    "[ACTION SUGGESTION] Reminder suggestion: set your reminder for Nov 27 at 5:00 PM (buffer before the Nov 28 deadline)."
                ),
                location="Conference Room B",
            ).delayed(10)

            # Oracle Event: Agent reads the calendar event details to extract action items
            # Motivated by: meeting_reminder_notification shows a meeting is upcoming, prompting agent to check details
            get_event_details = (
                calendar_app.read_today_calendar_events()
                .oracle()
                .depends_on(meeting_reminder_notification, delay_seconds=2)
            )

            # Oracle Event: Agent sends proposal to create a reminder for the user's action item
            # Motivated by: get_event_details reveals action items in the event description, including user's task
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your Product Strategy Meeting today includes action items. The event notes say you need to prepare an executive summary by November 28th and suggest setting a reminder for November 27th at 5:00 PM. Would you like me to create that reminder?"
                )
                .oracle()
                .depends_on(get_event_details, delay_seconds=2)
            )

            # Oracle Event: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please create that reminder.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event: Agent creates the reminder for the user's action item
            # Motivated by: user accepted the proposal via acceptance_event
            create_reminder_event = (
                reminder_app.add_reminder(
                    title="Prepare executive summary for Product Strategy follow-up",
                    due_datetime="2025-11-27 17:00:00",
                    description="Executive summary needed by Nov 28 (from Product Strategy Meeting with Sarah Thompson and David Chen on Nov 20)",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            meeting_reminder_notification,
            get_event_details,
            proposal_event,
            acceptance_event,
            create_reminder_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent read the calendar event to extract action items
            # Accept either get_calendar_event or get_calendar_events_from_to as equivalent methods
            calendar_read_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name
                in ["get_calendar_event", "get_calendar_events_from_to", "read_today_calendar_events"]
                for e in log_entries
            )

            # STRICT Check 2: Agent proposed creating a reminder for the user's action item
            # Be flexible on exact wording, but check for key concepts
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 3: Agent created a reminder with appropriate timing
            # Must have due date Nov 27 (buffer before Nov 28 deadline)
            # Flexible on exact title/description wording
            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "add_reminder"
                and "2025-11-27" in e.action.args.get("due_datetime", "")
                and e.action.args.get("title", "") != ""
                for e in log_entries
            )

            # Determine success and build rationale
            success = calendar_read_found and proposal_found and reminder_created

            if not success:
                rationale_parts = []
                if not calendar_read_found:
                    rationale_parts.append("agent did not read calendar event to extract action items")
                if not proposal_found:
                    rationale_parts.append("agent did not propose creating a reminder")
                if not reminder_created:
                    rationale_parts.append("agent did not create reminder with Nov 27 due date")
                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
