from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("personal_productivity_meeting")
class PersonalProductivityMeeting(Scenario):
    """Scenario where the agent acts as a productivity assistant.

    The agent coordinates a meeting setup across Contacts, Calendar, Reminders,
    Messaging, System, and UI apps, including a proactive confirmation.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all required applications with data."""
        self.aui = AgentUserInterface()
        self.system = SystemApp(name="system")
        self.contacts = ContactsApp()
        self.calendar = CalendarApp()
        self.reminder = ReminderApp()
        self.messaging = MessagingApp()

        # Populate contacts
        self.contacts.add_new_contact(
            first_name="Jordan",
            last_name="Patel",
            gender=Gender.MALE,
            age=32,
            city_living="Toronto",
            country="Canada",
            job="Project Manager",
            status=Status.EMPLOYED,
            phone="+1-416-888-2424",
            email="jordan.patel@example.com",
        )

        self.contacts.add_new_contact(
            first_name="Ava",
            last_name="Nguyen",
            gender=Gender.FEMALE,
            country="USA",
            job="Marketing Head",
            email="ava.nguyen@example.com",
            status=Status.EMPLOYED,
            age=29,
        )

        # List all initialized apps
        self.apps = [self.aui, self.system, self.contacts, self.calendar, self.reminder, self.messaging]

    def build_events_flow(self) -> None:
        """Build the event sequence for the meeting coordination workflow."""
        aui = self.get_typed_app(AgentUserInterface)
        contacts = self.get_typed_app(ContactsApp)
        calendar = self.get_typed_app(CalendarApp)
        reminder = self.get_typed_app(ReminderApp)
        messaging = self.get_typed_app(MessagingApp)
        system = self.get_typed_app(SystemApp)

        # Create a conversation with Jordan
        conv_id = messaging.create_conversation(participants=["Jordan Patel"], title="Project Timeline Discussion")

        with EventRegisterer.capture_mode():
            # User initiates the conversation with a request
            user_request = aui.send_message_to_agent(
                content="Assistant, I need to set up a quick status meeting with Jordan to discuss project updates."
            ).depends_on(None, delay_seconds=1)

            # System gets current time to decide event slot
            current_time = system.get_current_time().depends_on(user_request, delay_seconds=1)

            # Agent reads Jordan's contact info
            lookup = contacts.search_contacts(query="Jordan").depends_on(current_time, delay_seconds=1)

            # Proactive proposal: Agent offers to schedule meeting and send message confirmation
            proposal = aui.send_message_to_user(
                content="Would you like me to schedule a 30-minute project status meeting with Jordan Patel tomorrow at 10 AM and send him a confirmation message?"
            ).depends_on(lookup, delay_seconds=1)

            # User approval (important per proactive requirement)
            user_response = aui.send_message_to_agent(content="Yes, please schedule it and notify Jordan.").depends_on(
                proposal, delay_seconds=2
            )

            # Agent schedules the meeting in the calendar
            meeting_event = (
                calendar.add_calendar_event(
                    title="Project Status Meeting with Jordan Patel",
                    start_datetime="1970-01-02 10:00:00",
                    end_datetime="1970-01-02 10:30:00",
                    location="Zoom",
                    description="Discussion about current project deliverables and blockers.",
                    attendees=["Jordan Patel"],
                )
                .oracle()
                .depends_on(user_response, delay_seconds=1)
            )

            # Agent creates a reminder for the user about the meeting
            create_reminder = (
                reminder.add_reminder(
                    title="Prepare for Project Status Meeting",
                    due_datetime="1970-01-02 09:45:00",
                    description="Gather notes before meeting with Jordan Patel.",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(meeting_event, delay_seconds=1)
            )

            # Agent sends message to Jordan through messaging app to notify
            send_message = (
                messaging.send_message(
                    conversation_id=conv_id,
                    content="Hi Jordan, the project status meeting is scheduled for tomorrow at 10 AM. See you then!",
                )
                .oracle()
                .depends_on(create_reminder, delay_seconds=1)
            )

            # System waits for further notifications
            wait_end = system.wait_for_notification(timeout=3).depends_on(send_message, delay_seconds=1)

            # Agent informs the user all steps were completed
            notify_user_final = (
                aui.send_message_to_user(
                    content="The meeting with Jordan has been scheduled, a reminder is set, and Jordan has been notified."
                )
                .oracle()
                .depends_on(wait_end, delay_seconds=1)
            )

        self.events = [
            user_request,
            current_time,
            lookup,
            proposal,
            user_response,
            meeting_event,
            create_reminder,
            send_message,
            wait_end,
            notify_user_final,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the successful completion of the task."""
        try:
            events = env.event_log.list_view()

            # Check the agent prompted the user with a scheduling proposal
            prompted_user = any(
                isinstance(event.action, Action)
                and event.event_type == EventType.AGENT
                and event.action.class_name == "AgentUserInterface"
                and "schedule" in event.action.args.get("content", "").lower()
                and "jordan" in event.action.args.get("content", "").lower()
                for event in events
            )

            # Check if event creation in calendar happened
            created_event = any(
                isinstance(event.action, Action)
                and event.action.class_name == "CalendarApp"
                and event.action.function_name == "add_calendar_event"
                and "Project Status" in event.action.args.get("title", "")
                for event in events
            )

            # Verify reminder creation
            created_reminder = any(
                isinstance(event.action, Action)
                and event.action.class_name == "ReminderApp"
                and event.action.function_name == "add_reminder"
                and "Prepare" in event.action.args.get("title", "")
                for event in events
            )

            # Confirm message was sent to Jordan
            messaged_jordan = any(
                isinstance(event.action, Action)
                and event.action.class_name == "MessagingApp"
                and event.action.function_name == "send_message"
                and "Jordan" in event.action.args.get("content", "")
                for event in events
            )

            # Final user notification about successful completion
            closing_confirmation = any(
                isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and "meeting with jordan" in event.action.args.get("content", "").lower()
                and "scheduled" in event.action.args.get("content", "").lower()
                for event in events
            )

            success = prompted_user and created_event and created_reminder and messaged_jordan and closing_confirmation
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
