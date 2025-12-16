from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType


@register_scenario("morning_meeting_and_ride_coordination")
class MorningMeetingAndRideCoordination(Scenario):
    """A scenario demonstrating coordination between contact lookup, reminders, and cab booking.

    The agent helps the user schedule a morning event and proactively proposes a cab ride
    to reach a meeting location, sets a reminder upon confirmation, and confirms contact info check.
    """

    start_time: float | None = 0
    duration: float | None = 32

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize applications and populate them with contextual data."""
        aui = AgentUserInterface()
        cab = CabApp()
        contacts = ContactsApp()
        reminder = ReminderApp()
        system = SystemApp(name="system")

        # Get current user details for context
        contacts.get_current_user_details()

        # Populate contact list with a team meeting participant
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Smith",
            gender=Gender.OTHER,
            age=31,
            nationality="US",
            city_living="New York",
            country="United States",
            status=Status.EMPLOYED,
            job="Business Analyst",
            description="Colleague for early meeting project",
            phone="+1 212 555 7812",
            email="jordan.smith@company.com",
            address="105 Madison Ave, New York, NY",
        )

        # List of initialized apps
        self.apps = [aui, cab, contacts, reminder, system]

    def build_events_flow(self) -> None:
        """Define the expected event flow for the morning meeting coordination use case."""
        aui = self.get_typed_app(AgentUserInterface)
        cab = self.get_typed_app(CabApp)
        contacts = self.get_typed_app(ContactsApp)
        reminder = self.get_typed_app(ReminderApp)
        system = self.get_typed_app(SystemApp)

        current_time_info = system.get_current_time()
        current_datetime = current_time_info.get("datetime", "1970-01-01 00:00:00")

        with EventRegisterer.capture_mode():
            # Step 1: User starts the conversation
            user_initiate = aui.send_message_to_agent(
                content="Good morning Assistant, I have a meeting with Jordan at 9 AM at the downtown office. Can you help me prepare and get there on time?"
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent searches Jordan's contact details for confirmation
            contact_search = contacts.search_contacts(query="Jordan").depends_on(user_initiate, delay_seconds=1)

            # Step 3: Agent checks current time
            time_info = system.get_current_time().depends_on(contact_search, delay_seconds=1)

            # Step 4: Agent proactively proposes a cab ride and reminder
            proposal_message = aui.send_message_to_user(
                content="I found Jordan's contact and the meeting is scheduled for 9 AM. Would you like me to book a cab from your home to the downtown office and set a reminder for 30 minutes before the trip?"
            ).depends_on(time_info, delay_seconds=1)

            # Step 5: User responds with permission
            user_confirmation = aui.send_message_to_agent(
                content="Yes, please go ahead and arrange the cab and reminder."
            ).depends_on(proposal_message, delay_seconds=2)

            # Step 6: Agent requests a cab quotation
            quote = cab.get_quotation(
                start_location="Home, 50 West 23rd Street, New York",
                end_location="Downtown Office, 200 Broadway, New York",
                service_type="Default",
                ride_time="1970-01-01 08:30:00",
            ).depends_on(user_confirmation, delay_seconds=1)

            # Step 7: Agent places the cab order (oracle)
            order = (
                cab.order_ride(
                    start_location="Home, 50 West 23rd Street, New York",
                    end_location="Downtown Office, 200 Broadway, New York",
                    service_type="Default",
                    ride_time="1970-01-01 08:30:00",
                )
                .oracle()
                .depends_on(quote, delay_seconds=1)
            )

            # Step 8: Agent sets up a reminder (oracle)
            reminder_create = (
                reminder.add_reminder(
                    title="Prepare for meeting with Jordan",
                    due_datetime="1970-01-01 08:00:00",
                    description="Get ready for the 9 AM meeting and confirm cab pickup.",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(order, delay_seconds=1)
            )

            # Step 9: Agent notifies user that everything is set
            completion_message = aui.send_message_to_user(
                content="Cab booked for 8:30 AM to the downtown office and reminder set for 8 AM. You'll be all set for your meeting with Jordan."
            ).depends_on(reminder_create, delay_seconds=1)

            # Step 10: Agent waits for a confirmation notification from system
            sys_wait = system.wait_for_notification(timeout=5).depends_on(completion_message, delay_seconds=1)

        self.events = [
            user_initiate,
            contact_search,
            time_info,
            proposal_message,
            user_confirmation,
            quote,
            order,
            reminder_create,
            completion_message,
            sys_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the proactive proposal, user confirmation, and subsequent actions occurred."""
        try:
            events = env.event_log.list_view()

            proposed = any(
                event.event_type == EventType.AGENT
                and event.action.function_name == "send_message_to_user"
                and "book a cab" in event.action.args.get("content", "").lower()
                for event in events
            )

            approved = any(
                event.event_type == EventType.USER and "arrange the cab" in event.action.args.get("content", "").lower()
                for event in events
            )

            cab_ordered = any(
                event.event_type == EventType.AGENT
                and event.action.class_name == "CabApp"
                and event.action.function_name == "order_ride"
                for event in events
            )

            reminder_set = any(
                event.event_type == EventType.AGENT
                and event.action.class_name == "ReminderApp"
                and event.action.function_name == "add_reminder"
                for event in events
            )

            success = proposed and approved and cab_ordered and reminder_set
            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
