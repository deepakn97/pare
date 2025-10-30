from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import RentAFlat
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_viewing_schedule")
class ApartmentViewingSchedule(Scenario):
    """A scenario where the agent helps the user find an apartment and coordinate a viewing appointment.

    It integrates all available apps:
    - SystemApp to get the current date/time and wait for a break
    - RentAFlat to search, inspect, and save apartments
    - CalendarApp to create and review viewing appointments
    - AgentUserInterface to coordinate the proactive conversation with the user

    Core focus:
    Demonstrates a proactive proposal workflow where the agent proposes to schedule a viewing,
    waits for user approval, then proceeds with calendar booking.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate all apps with sample test data."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        rent = RentAFlat()
        system = SystemApp(name="SysApp")

        # Prepopulate the calendar with some unrelated personal event
        calendar.add_calendar_event(
            title="Morning Workout",
            start_datetime="2024-07-10 07:00:00",
            end_datetime="2024-07-10 08:00:00",
            tag="personal",
            description="Daily exercise session.",
            location="Gym Center",
            attendees=["User"],
        )

        # Prepopulate RentAFlat with possible rentals
        rent.list_all_apartments()
        rent.search_apartments(
            location="Sunnyvale", min_price=1200, max_price=2500, number_of_bedrooms=2, amenities=["Balcony", "Garage"]
        )

        self.apps = [aui, calendar, rent, system]

    def build_events_flow(self) -> None:
        """Defines the event flow, including proactive interaction pattern."""
        aui = self.get_typed_app(AgentUserInterface)
        rent = self.get_typed_app(RentAFlat)
        calendar = self.get_typed_app(CalendarApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Event 0: user initiates request to find a rental apartment
            user_request = aui.send_message_to_agent(
                content="Hi Assistant, can you help me find a 2-bedroom apartment in Sunnyvale under $2500?"
            ).depends_on(None, delay_seconds=1)

            # Event 1: agent queries the apartment listings database
            search_apts = rent.search_apartments(location="Sunnyvale", max_price=2500, number_of_bedrooms=2).depends_on(
                user_request, delay_seconds=1
            )

            # Event 2: agent gets details of the first search result
            get_details = rent.get_apartment_details(apartment_id="APT101").depends_on(search_apts, delay_seconds=1)

            # Event 3: agent saves the apartment to favorites
            save_listing = rent.save_apartment(apartment_id="APT101").depends_on(get_details, delay_seconds=1)

            # Event 4: agent notifies the user about a suitable apartment
            agent_message = aui.send_message_to_user(
                content=(
                    "I've found a 2-bedroom apartment in Sunnyvale within your budget, located at 45 Creek Drive. "
                    "Would you like me to schedule a viewing with the agent for tomorrow at 5 PM?"
                )
            ).depends_on(save_listing, delay_seconds=1)

            # Event 5: user provides approval to schedule the viewing
            user_approval = aui.send_message_to_agent(
                content="Yes, please book the viewing appointment for tomorrow at 5 PM."
            ).depends_on(agent_message, delay_seconds=1)

            # Event 6: system checks current time to determine date offset
            current_time = system.get_current_time().depends_on(user_approval, delay_seconds=1)

            # Event 7: agent creates the calendar event for the viewing
            create_event = (
                calendar.add_calendar_event(
                    title="Apartment Viewing - 45 Creek Drive",
                    start_datetime="2024-07-11 17:00:00",
                    end_datetime="2024-07-11 18:00:00",
                    tag="apartment_viewing",
                    description="Meeting with agent at 45 Creek Drive to view the apartment.",
                    location="45 Creek Drive, Sunnyvale",
                    attendees=["User", "Agent from RentAFlat"],
                )
                .oracle()
                .depends_on(current_time, delay_seconds=1)
            )

            # Event 8: after booking, system idles to simulate waiting for updates
            wait_idle = system.wait_for_notification(timeout=5).depends_on(create_event, delay_seconds=1)

            # Event 9: agent confirms the viewing has been scheduled successfully
            confirmation_msg = (
                aui.send_message_to_user(
                    content="The apartment viewing has been successfully scheduled for tomorrow at 5 PM at 45 Creek Drive."
                )
                .oracle()
                .depends_on(wait_idle, delay_seconds=1)
            )

        self.events = [
            user_request,
            search_apts,
            get_details,
            save_listing,
            agent_message,
            user_approval,
            current_time,
            create_event,
            wait_idle,
            confirmation_msg,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure an apartment viewing was scheduled after user confirmation."""
        try:
            events = env.event_log.list_view()

            # Validation: check if the agent created a calendar event after user approval
            event_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Viewing" in e.action.args.get("title", "")
                for e in events
            )

            # Validation: check if the proactive message proposal happened
            proactive_present = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Would you like me to schedule" in e.action.args.get("content", "")
                for e in events
            )

            # Validation: ensure system tools were used (current time or wait)
            time_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "SystemApp"
                and e.action.function_name in ["get_current_time", "wait_for_notification"]
                for e in events
            )

            success = event_created and proactive_present and time_checked
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
