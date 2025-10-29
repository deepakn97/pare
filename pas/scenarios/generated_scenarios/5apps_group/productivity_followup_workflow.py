from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("productivity_followup_workflow")
class ProductivityFollowUpWorkflow(Scenario):
    """Scenario demonstrating cross-app productivity interactions: email follow-up with calendar and reminders.

    Flow:
        1. User receives a client email requesting a project update call.
        2. Agent proposes scheduling a meeting for the next morning.
        3. User approves, and the agent schedules the meeting + adds a reminder.
        4. Agent later sends a follow-up email confirmation to the client.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all required apps with starting state."""
        self.apps = [
            AgentUserInterface(),
            CalendarApp(),
            EmailClientApp(),
            ReminderApp(),
            SystemApp(name="system_runner"),
        ]

    def build_events_flow(self) -> None:
        """Define the chronological sequence of simulation events."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        email_client = self.get_typed_app(EmailClientApp)
        reminder = self.get_typed_app(ReminderApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # 1. Get current time
            event_0 = system.get_current_time().depends_on(None, delay_seconds=1)

            # 2. Simulate receiving a client email
            event_1 = email_client.list_emails(folder_name="INBOX", offset=0, limit=5).depends_on(
                event_0, delay_seconds=1
            )
            event_2 = email_client.get_email_by_index(idx=0, folder_name="INBOX").depends_on(event_1, delay_seconds=1)

            # 3. Agent proactively proposes scheduling a meeting
            event_3 = aui.send_message_to_user(
                content="I received an email from your client asking for a project update call. Shall I schedule a 30-minute meeting for tomorrow at 10 AM?"
            ).depends_on(event_2, delay_seconds=1)

            # 4. User responds with contextual approval
            event_4 = aui.send_message_to_agent(
                content="Yes, go ahead and set up the meeting tomorrow morning with them."
            ).depends_on(event_3, delay_seconds=2)

            # 5. Agent schedules a calendar event after approval
            event_5 = (
                calendar.add_calendar_event(
                    title="Project Update Call with Client A",
                    start_datetime="2023-09-22 10:00:00",
                    end_datetime="2023-09-22 10:30:00",
                    tag="client_meetings",
                    description="Discuss project progress and next steps",
                    location="Video Call Link",
                    attendees=["Client A", "You"],
                )
                .oracle()
                .depends_on(event_4, delay_seconds=1)
            )

            # 6. Agent also adds a reminder for follow-up shortly before the meeting
            event_6 = (
                reminder.add_reminder(
                    title="Prepare project notes for client call",
                    due_datetime="2023-09-22 09:30:00",
                    description="Gather progress details and pending tasks before the call",
                    repetition_unit=None,
                    repetition_value=1,
                )
                .oracle()
                .depends_on(event_5, delay_seconds=1)
            )

            # 7. Agent then sends confirmation email to client
            event_7 = (
                email_client.send_email(
                    recipients=["clientA@example.com"],
                    subject="Scheduled: Project Update Call Tomorrow",
                    content="Hello Client A, I've scheduled our update call for 10 AM tomorrow. Looking forward to speaking with you.",
                )
                .oracle()
                .depends_on(event_6, delay_seconds=1)
            )

            # 8. Finally, agent syncs new reminders and events and waits for updates
            event_8 = reminder.get_all_reminders().depends_on(event_7, delay_seconds=1)
            event_9 = calendar.search_events(query="client").depends_on(event_8, delay_seconds=1)
            event_10 = system.wait_for_notification(timeout=5).depends_on(event_9, delay_seconds=1)

        self.events = [
            event_0,
            event_1,
            event_2,
            event_3,
            event_4,
            event_5,
            event_6,
            event_7,
            event_8,
            event_9,
            event_10,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate success by confirming a meeting creation, reminder addition, and confirmation email sent."""
        try:
            events = env.event_log.list_view()

            has_calendar_event = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "CalendarApp"
                and event.action.function_name == "add_calendar_event"
                and "Project Update" in event.action.args["title"]
                for event in events
            )

            has_followup_email = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "EmailClientApp"
                and event.action.function_name == "send_email"
                and "Scheduled" in event.action.args["subject"]
                for event in events
            )

            has_reminder = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "ReminderApp"
                and event.action.function_name == "add_reminder"
                and "project notes" in event.action.args["title"].lower()
                for event in events
            )

            has_proposal_and_user_confirmation = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action.args.get("content", ""), str)
                and "schedule a 30-minute meeting" in event.action.args["content"]
                for event in events
            ) and any(
                (
                    event.event_type == EventType.USER
                    and "go ahead and set up the meeting" in getattr(event.action.args, "content", "")
                )
                or "set up the meeting" in str(event.action.args)
                for event in events
            )

            success = all([has_calendar_event, has_followup_email, has_reminder, has_proposal_and_user_confirmation])
            return ScenarioValidationResult(success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
