from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.city import CityApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("trip_to_safe_conference")
class TripToSafeConference(Scenario):
    """A comprehensive scenario combining all available apps.

    The user is attending a conference in another city and the agent assists by:
      1. Checking crime rate to recommend a safe area near the destination
      2. Adding a calendar event for the conference
      3. Suggesting and booking a cab ride to the venue after user approval
      4. Adding a new contact for a colleague met at the conference
      5. Waiting for a notification from SystemApp to simulate real-time updates.

    Demonstrates coordination between:
      - AgentUserInterface: for proactive communication with the user
      - CalendarApp: for setting up the event
      - ContactsApp: for managing contact of a colleague
      - CabApp: for scheduling safe transportation
      - CityApp: for analyzing the safety of the location
      - SystemApp: for getting time and timing the workflow
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all applications and populate minimal data."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        contacts = ContactsApp()
        cab = CabApp()
        city = CityApp()
        system = SystemApp(name="system")

        # Populate ContactsApp with a few existing contacts
        contacts.add_new_contact(
            first_name="Alice",
            last_name="Nguyen",
            gender=Gender.FEMALE,
            age=29,
            nationality="French",
            city_living="Paris",
            country="France",
            status=Status.EMPLOYED,
            job="Research Scientist",
            email="alice.nguyen@example.com",
        )

        contacts.add_new_contact(
            first_name="Mark",
            last_name="Evans",
            gender=Gender.MALE,
            age=35,
            nationality="UK",
            city_living="London",
            country="UK",
            status=Status.EMPLOYED,
            job="Event Coordinator",
            email="mark.evans@conferencehub.org",
        )

        # Store initialized apps
        self.apps = [aui, cab, calendar, city, contacts, system]

    def build_events_flow(self) -> None:
        """Build the event flow demonstrating the entire system ecosystem."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        cab = self.get_typed_app(CabApp)
        city = self.get_typed_app(CityApp)
        contacts = self.get_typed_app(ContactsApp)
        sys_app = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User starts the conversation asking for help with the conference
            user_message = aui.send_message_to_agent(
                content="I have to attend a tech conference in Lyon next Thursday. Can you help me plan everything safely?"
            ).depends_on(None, delay_seconds=1)

            # SystemApp provides the current time, used for planning timeline
            get_time = sys_app.get_current_time().depends_on(user_message, delay_seconds=1)

            # CityApp checks the crime rate for Lyon (dummy postal code used)
            safety_check = city.get_crime_rate(zip_code="69001").depends_on(get_time, delay_seconds=1)

            # Agent notifies the user about the safety information and proposes next actions
            propose_action = aui.send_message_to_user(
                content=(
                    "Lyon's city center (zip 69001) shows low crime risk this week. "
                    "Would you like me to create a conference event in your calendar "
                    "and prepare a cab ride from your hotel to the venue?"
                )
            ).depends_on(safety_check, delay_seconds=1)

            # User approves the proposal with contextual agreement
            user_confirms = aui.send_message_to_agent(
                content=("Yes, please schedule the conference and also arrange a cab from my hotel to the venue.")
            ).depends_on(propose_action, delay_seconds=2)

            # Calendar event creation for the conference
            add_event = (
                calendar.add_calendar_event(
                    title="AI & Robotics Conference - Lyon",
                    start_datetime="1970-01-08 09:00:00",
                    end_datetime="1970-01-08 17:00:00",
                    tag="Conference",
                    description="Day 1: AI talks and robotics demos",
                    location="Lyon Convention Center",
                    attendees=["Alice Nguyen", "Mark Evans"],
                )
                .oracle()
                .depends_on(user_confirms, delay_seconds=1)
            )

            # Cab quote retrieval based on hotel (dummy location)
            cab_quote = cab.get_quotation(
                start_location="Hotel du Rhône, Lyon",
                end_location="Lyon Convention Center",
                service_type="Premium",
                ride_time="1970-01-08 08:15:00",
            ).depends_on(add_event, delay_seconds=1)

            # Agent informs user about estimated cab cost and asks to confirm booking
            propose_cab_booking = aui.send_message_to_user(
                content="The premium ride from Hotel du Rhône to the convention center is €25. Should I book it now?"
            ).depends_on(cab_quote, delay_seconds=1)

            # User responds with contextual approval
            user_confirms_cab = aui.send_message_to_agent(
                content="Yes, go ahead and book the premium ride."
            ).depends_on(propose_cab_booking, delay_seconds=1)

            # The agent books the cab ride after user approval
            cab_order = (
                cab.order_ride(
                    start_location="Hotel du Rhône, Lyon",
                    end_location="Lyon Convention Center",
                    service_type="Premium",
                    ride_time="1970-01-08 08:15:00",
                )
                .oracle()
                .depends_on(user_confirms_cab, delay_seconds=1)
            )

            # Add new contact for a colleague met at the conference
            add_contact = contacts.add_new_contact(
                first_name="Elena",
                last_name="Rossi",
                gender=Gender.FEMALE,
                age=31,
                nationality="Italian",
                city_living="Milan",
                country="Italy",
                status=Status.EMPLOYED,
                job="Product Manager",
                email="elena.rossi@aiworld.org",
                description="Met at AI Conference in Lyon.",
            ).depends_on(cab_order, delay_seconds=1)

            # System waits for a notification to simulate follow-up (like ride status change)
            wait_event = sys_app.wait_for_notification(timeout=3).depends_on(add_contact, delay_seconds=1)

            # Final confirmation message summarizing completed plans
            finalize_plan = (
                aui.send_message_to_user(
                    content="Everything is set! The calendar event is created, cab booked, and new contact 'Elena Rossi' added."
                )
                .oracle()
                .depends_on(wait_event, delay_seconds=1)
            )

        self.events = [
            user_message,
            get_time,
            safety_check,
            propose_action,
            user_confirms,
            add_event,
            cab_quote,
            propose_cab_booking,
            user_confirms_cab,
            cab_order,
            add_contact,
            wait_event,
            finalize_plan,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure the agent scheduled event, booked ride, and communicated properly."""
        try:
            events = env.event_log.list_view()

            # Check that event creation, ride order, and user messages occurred
            calendar_event_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "add_calendar_event"
                and "AI & Robotics Conference" in (e.action.args.get("title") or "")
                for e in events
            )

            ride_ordered = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "order_ride"
                and "Lyon Convention Center" in e.action.args.get("end_location")
                for e in events
            )

            contact_added = any(
                e.event_type == EventType.SYSTEM
                or (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.function_name == "add_new_contact"
                    and "Elena" in (e.action.args.get("first_name") or "")
                )
                for e in events
            )

            user_notified = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "send_message_to_user"
                and "Everything is set" in (e.action.args.get("content") or "")
                for e in events
            )

            success = calendar_event_created and ride_ordered and contact_added and user_notified
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
