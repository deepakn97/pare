from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_hunt_assistant")
class ApartmentHuntAssistant(Scenario):
    """Scenario: Agent helps the user plan apartment viewings, propose scheduling, and set reminders.

    Demonstrates full integration of all available apps:
    - Apartment search and saving (ApartmentListingApp)
    - Contacts management (ContactsApp)
    - Calendar scheduling (CalendarApp)
    - Reminder creation (ReminderApp)
    - System time awareness (SystemApp)
    - Agent-User communication (AgentUserInterface)
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate apps for the apartment hunting scenario."""
        aui = AgentUserInterface()
        system = SystemApp(name="system")
        calendar = CalendarApp()
        contacts = ContactsApp()
        reminders = ReminderApp()
        apartments = ApartmentListingApp()

        # Add contact for a landlord to contacts
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Hall",
            gender=Gender.MALE,
            age=34,
            nationality="American",
            city_living="New York",
            country="USA",
            status=Status.EMPLOYED,
            job="Property Manager",
            phone="+1 333 444 5555",
            email="jordan.hall@homeestate.com",
            description="Manages multiple apartments across Manhattan",
        )

        # The system now has: time, contact, apartment listings available.
        self.apps = [aui, system, calendar, contacts, reminders, apartments]

    def build_events_flow(self) -> None:
        """Define the flow of events for the apartment hunting scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(CalendarApp)
        contacts = self.get_typed_app(ContactsApp)
        reminder = self.get_typed_app(ReminderApp)
        apartments = self.get_typed_app(ApartmentListingApp)

        with EventRegisterer.capture_mode():
            # User starts the conversation: needs help finding an apartment
            user_request = aui.send_message_to_agent(
                content="Hey Assistant, I need help finding a 2-bedroom apartment in Brooklyn under $2500."
            ).depends_on(None, delay_seconds=1)

            # Agent searches for apartments
            search_action = apartments.search_apartments(
                location="Brooklyn", max_price=2500, number_of_bedrooms=2
            ).depends_on(user_request, delay_seconds=1)

            # Agent fetches current time to propose an appointment
            current_time = system.get_current_time().depends_on(search_action, delay_seconds=1)

            # Agent proactively proposes scheduling an apartment viewing with landlord Jordan
            agent_propose = aui.send_message_to_user(
                content="I found a few options in Brooklyn under $2500. Would you like me to schedule a viewing with landlord Jordan Hall for tomorrow at 10 AM?"
            ).depends_on(current_time, delay_seconds=1)

            # User confirms the proposal
            user_confirms = aui.send_message_to_agent(
                content="Yes, go ahead and schedule that viewing with Jordan."
            ).depends_on(agent_propose, delay_seconds=1)

            # Agent adds calendar event for the viewing meeting
            meet_event = (
                calendar.add_calendar_event(
                    title="Apartment Viewing - Brooklyn",
                    start_datetime="1970-01-02 10:00:00",
                    end_datetime="1970-01-02 11:00:00",
                    location="Brooklyn, NY",
                    description="Viewing organized with landlord Jordan Hall",
                    attendees=["Jordan Hall"],
                    tag="Apartment Viewing",
                )
                .oracle()
                .depends_on(user_confirms, delay_seconds=1)
            )

            # Agent adds a reminder before the event
            reminder_add = (
                reminder.add_reminder(
                    title="Leave for Apartment Viewing",
                    due_datetime="1970-01-02 09:30:00",
                    description="Prepare documents and leave for the meeting in Brooklyn with Jordan Hall.",
                )
                .oracle()
                .depends_on(meet_event, delay_seconds=1)
            )

            # Agent saves apartment as favorite for user
            save_apartment = (
                apartments.save_apartment(apartment_id="apt_001").oracle().depends_on(reminder_add, delay_seconds=1)
            )

            # Agent notifies the user everything is arranged
            final_notify = (
                aui.send_message_to_user(
                    content="The apartment viewing with Jordan Hall is scheduled and a reminder has been set. I've also saved the apartment to your favorites."
                )
                .oracle()
                .depends_on(save_apartment, delay_seconds=1)
            )

        self.events = [
            user_request,
            search_action,
            current_time,
            agent_propose,
            user_confirms,
            meet_event,
            reminder_add,
            save_apartment,
            final_notify,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate if the schedule, reminder, and communication were properly executed."""
        try:
            events = env.event_log.list_view()

            # Check if calendar event was added
            calendar_action = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Jordan Hall" in str(e.action.args.get("attendees", []))
                for e in events
            )

            # Check if a reminder was added
            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                and "Leave for Apartment Viewing" in e.action.args.get("title", "")
                for e in events
            )

            # Check if a saved apartment operation occurred
            apartment_saved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ApartmentListingApp"
                and e.action.function_name == "save_apartment"
                for e in events
            )

            # Ensure the proactive proposal and final confirmation messages occurred
            proactive_proposed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "schedule" in e.action.args.get("content", "").lower()
                for e in events
            )
            user_confirms = any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "schedule" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = all([calendar_action, reminder_created, apartment_saved, proactive_proposed, user_confirms])
            return ScenarioValidationResult(success=success)
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
