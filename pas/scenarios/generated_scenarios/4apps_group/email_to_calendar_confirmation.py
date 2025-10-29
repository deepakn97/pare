from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("email_to_calendar_confirmation")
class EmailToCalendarConfirmation(Scenario):
    """Scenario where the agent reads a meeting invitation from email.

    Proposes to add it to the calendar, and upon user's approval, schedules the event.
    Demonstrates system time usage, email parsing, proactive agent interaction,
    and confirmed calendar editing.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate the environment with all applications."""
        aui = AgentUserInterface()
        system = SystemApp(name="system")
        email_client = EmailClientApp()
        calendar = CalendarApp()

        # Create a sample incoming meeting email (already in user's inbox)
        email_client.send_email_to_user(
            email=Email(
                sender="nina.hart@startuphub.com",
                recipients=["user@domain.com"],
                subject="Team Strategy Session invite",
                content=(
                    "Hi, I'd like to arrange a 45-min strategy alignment session "
                    "tomorrow at 10:00 AM in Meeting Room B. Let me know if this time works."
                ),
                email_id="meeting_invite_001",
            )
        )

        # Store initialized apps
        self.apps = [aui, system, email_client, calendar]

    def build_events_flow(self) -> None:
        """Build sequence of events with proactive action & user approval."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        email_client = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)

        with EventRegisterer.capture_mode():
            # User starts the conversation asking for unread meeting invites
            user_request = aui.send_message_to_agent(
                content="Assistant, please check if I have any pending meeting invites in my inbox."
            ).depends_on(None, delay_seconds=1)

            # Agent fetches current time context before suggesting scheduling
            get_now = system.get_current_time().depends_on(user_request, delay_seconds=1)

            # Agent reads the first email in inbox that is meeting-related
            read_email = email_client.get_email_by_index(idx=0, folder_name="INBOX").depends_on(
                get_now, delay_seconds=1
            )

            # Agent proposes to the user to convert the meeting email into a calendar event
            propose_action = aui.send_message_to_user(
                content=(
                    "I found an email from Nina Hart about a strategy session tomorrow at 10:00 AM. "
                    "Would you like me to add it to your calendar as 'Team Strategy Session'?"
                )
            ).depends_on(read_email, delay_seconds=1)

            # User approves with detailed context (proactive interaction confirmation)
            user_approval = aui.send_message_to_agent(
                content="Yes, please add it to my calendar and include Nina as an attendee."
            ).depends_on(propose_action, delay_seconds=1)

            # Agent adds the meeting to calendar after confirmation (oracle action)
            event_creation = (
                calendar.add_calendar_event(
                    title="Team Strategy Session",
                    start_datetime="2024-08-22 10:00:00",
                    end_datetime="2024-08-22 10:45:00",
                    tag="Strategy",
                    description="Team alignment with Nina Hart",
                    location="Meeting Room B",
                    attendees=["Nina Hart"],
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Agent confirms completion by summarizing the created event
            final_confirm = aui.send_message_to_user(
                content="The 'Team Strategy Session' was added to your calendar tomorrow at 10 AM with Nina Hart."
            ).depends_on(event_creation, delay_seconds=1)

            # Then system waits for the next user or system notification passively
            idle_wait = system.wait_for_notification(timeout=5).depends_on(final_confirm, delay_seconds=2)

        # Register the full event flow
        self.events = [
            user_request,
            get_now,
            read_email,
            propose_action,
            user_approval,
            event_creation,
            final_confirm,
            idle_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the scenario outcome after execution."""
        try:
            logs = env.event_log.list_view()

            # Verify calendar event was added with correct details
            new_event_created = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "CalendarApp"
                and ev.action.function_name == "add_calendar_event"
                and "Strategy" in (ev.action.args.get("tag", "") or "")
                and "Nina Hart" in (str(ev.action.args.get("attendees", "")))
                for ev in logs
            )

            # Verify the agent proactively proposed the addition
            proactive_proposal = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "AgentUserInterface"
                and ev.action.function_name == "send_message_to_user"
                and "Would you like me to add" in ev.action.args.get("content", "")
                for ev in logs
            )

            # Check if user approved (shows user accepted action)
            user_reply_present = any(
                ev.event_type == EventType.USER and "Yes, please add" in ev.action.args.get("content", "")
                for ev in logs
            )

            success = new_event_created and proactive_proposal and user_reply_present
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
