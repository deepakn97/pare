from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("project_planning_proactive")
class ProjectPlanningProactive(Scenario):
    """Scenario: The agent helps the user plan a product release meeting with reminders.

    This scenario demonstrates proactive planning assistance:
    - The agent checks the current date and user's schedule.
    - It then proposes scheduling a team review meeting.
    - Upon the user's approval, it creates the event and sets a reminder.
    - All four core applications are used meaningfully.
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize system time, calendar, reminder, and communication apps."""
        agui = AgentUserInterface()
        calendar = CalendarApp()
        reminders = ReminderApp()
        system = SystemApp(name="primary_system")

        # For demonstration, start with an empty calendar and reminder set.
        self.apps = [agui, calendar, reminders, system]

    def build_events_flow(self) -> None:
        """Define the sequence of interactions with proactive agent behavior."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        reminders = self.get_typed_app(ReminderApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 1: User triggers the scenario by asking about current plan
            user_request = aui.send_message_to_agent(
                content="Can you help me plan the kickoff meeting for the new product release?"
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent gets current time to determine a potential date
            get_time = system.get_current_time().depends_on(user_request, delay_seconds=1)

            # Step 3: Agent checks if today's calendar is free
            get_today_events = calendar.read_today_calendar_events().depends_on(get_time, delay_seconds=1)

            # Step 4: Agent proactively proposes a meeting plan to the user
            propose_to_user = aui.send_message_to_user(
                content=(
                    "I see your schedule is open today. "
                    "Would you like me to schedule a 'Product Launch Kickoff' meeting tomorrow at 10:00 AM "
                    "and set a reminder an hour before it?"
                )
            ).depends_on(get_today_events, delay_seconds=1)

            # Step 5: User confirms the proposal
            user_confirms = aui.send_message_to_agent(
                content="Yes, that sounds good. Please go ahead and set the meeting and reminder."
            ).depends_on(propose_to_user, delay_seconds=2)

            # Step 6: Agent adds the meeting to the calendar (oracle)
            add_meeting = (
                calendar.add_calendar_event(
                    title="Product Launch Kickoff",
                    start_datetime="1970-01-02 10:00:00",
                    end_datetime="1970-01-02 11:00:00",
                    tag="Product_Release",
                    description="Kickoff meeting to coordinate the release plan with the dev team.",
                    location="Conference Room 3",
                    attendees=["Alice Johnson", "Marcus Lin"],
                )
                .oracle()
                .depends_on(user_confirms, delay_seconds=1)
            )

            # Step 7: Agent adds a reminder for the event (oracle)
            add_reminder = (
                reminders.add_reminder(
                    title="Kickoff Reminder",
                    due_datetime="1970-01-02 09:00:00",
                    description="Reminder: The Product Launch Kickoff meeting starts in one hour.",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(add_meeting, delay_seconds=1)
            )

            # Step 8: System waits for any notification (for completion simulation)
            system_wait = system.wait_for_notification(timeout=2).depends_on(add_reminder, delay_seconds=1)

        self.events = [
            user_request,
            get_time,
            get_today_events,
            propose_to_user,
            user_confirms,
            add_meeting,
            add_reminder,
            system_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that both a calendar event and reminder were created."""
        try:
            all_events = env.event_log.list_view()

            # Verify the meeting creation
            meeting_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "add_calendar_event"
                and e.action.class_name == "CalendarApp"
                and "Kickoff" in e.action.args["title"]
                and "1970-01-02 10:00:00" in e.action.args["start_datetime"]
                for e in all_events
            )

            # Verify the reminder creation
            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "add_reminder"
                and e.action.class_name == "ReminderApp"
                and "Reminder" in e.action.args["title"]
                and "09:00:00" in e.action.args["due_datetime"]
                for e in all_events
            )

            # Verify that the agent proposed the action proactively
            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "send_message_to_user"
                and "schedule" in e.action.args["content"].lower()
                and "reminder" in e.action.args["content"].lower()
                for e in all_events
            )

            return ScenarioValidationResult(success=(meeting_created and reminder_created and proposal_sent))
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
