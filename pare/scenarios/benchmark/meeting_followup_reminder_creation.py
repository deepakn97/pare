from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.calendar import CalendarEvent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCalendarApp,
)
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("meeting_followup_reminder_creation")
class MeetingFollowupReminderCreation(PAREScenario):
    """Agent creates structured follow-up reminders based on action items mentioned in calendar event descriptions.

    The user has a calendar event titled "Product Strategy Meeting" scheduled for today at 2:00 PM with attendees
    "Sarah Thompson" and "David Chen". The event description contains: "Discuss Q1 roadmap priorities. Action items:
    Sarah to send competitive analysis by Nov 25, David to finalize budget by Nov 27, I need to prepare executive
    summary by Nov 28." Shortly after the scenario starts, a user-created reminder notification fires (time-driven)
    prompting the user to review the meeting notes and set a follow-up reminder for their action item. The agent must:
    1. Detect the reminder notification (time-driven; emitted automatically when the reminder is due)
    2. Read the calendar event details to extract action items
    3. Identify the user's personal action item (prepare executive summary by Nov 28)
    4. Propose creating a dedicated reminder for the user's task
    5. Create a new reminder titled "Prepare executive summary for Product Strategy follow-up" due November 27th at 5:00 PM
       (one day before deadline for buffer time)
    6. Set the reminder description to reference the original meeting context.

    This scenario exercises calendar-to-reminder synthesis (inverse of reminder-to-calendar conversion), natural language parsing of action items from event descriptions, temporal reasoning for appropriate reminder timing (buffer before deadline), and proactive task extraction to help users maintain accountability for meeting commitments..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize calendar and reminder apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.reminder = StatefulReminderApp(name="Reminders")

        # Populate calendar with the Product Strategy Meeting event
        # Event scheduled for today at 2:00 PM (14:00)
        meeting_event = CalendarEvent(
            title="Product Strategy Meeting",
            start_datetime=datetime(2025, 11, 18, 14, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 18, 15, 30, 0, tzinfo=UTC).timestamp(),
            description="Discuss Q1 roadmap priorities. Action items: Sarah to send competitive analysis by Nov 25, David to finalize budget by Nov 27, I need to prepare executive summary by Nov 28.",
            location="Conference Room B",
            attendees=["Sarah Thompson", "David Chen"],
            tag="work",
        )
        self.calendar.set_calendar_event(meeting_event)

        # Seed a time-driven reminder that will automatically notify the user+agent when due.
        # The scenario runner advances simulated time; we set this reminder shortly after start_time so it fires.
        self.reminder.add_reminder(
            title="Prep: follow up action items from Product Strategy Meeting",
            due_datetime="2025-11-18 09:01:00",
            description=(
                "Product Strategy Meeting today at 2:00 PM (Conference Room B) with Sarah Thompson and David Chen.\n\n"
                "Remember to set a reminder for the action item (prepare executive summary by Nov 28). "
                "Set it for Nov 27 at 5:00 PM (one day before the deadline, buffer time)."
            ),
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # NOTE: Reminder notifications are time-driven in the Reminders app.
            # The reminder seeded in init (`due_datetime="2025-11-18 09:01:00"`) will automatically notify user+agent.
            # The agent does NOT need to poll reminders; we model reaction time by delaying the first oracle action.

            # Oracle Event: Agent reads the calendar event details to extract action items
            # Motivated by: reminder notification prompted follow-up planning, so agent checks today's calendar details.
            get_event_details = calendar_app.read_today_calendar_events().oracle().delayed(70)

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
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_event, delay_seconds=3)
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

        self.events = [
            get_event_details,
            proposal_event,
            acceptance_event,
            create_reminder_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent proposed creating a reminder for the user's action item
            # Be flexible on exact wording, but check for key concepts
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent created a reminder with appropriate timing
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
            success = proposal_found and reminder_created

            if not success:
                rationale_parts = []
                if not proposal_found:
                    rationale_parts.append("agent did not propose creating a reminder")
                if not reminder_created:
                    rationale_parts.append("agent did not create reminder with Nov 27 due date")
                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
