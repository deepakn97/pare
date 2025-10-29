from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.cab import CabApp
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_hunt_transport_and_schedule")
class ApartmentHuntTransportAndSchedule(Scenario):
    """Scenario where the user asks the agent to find apartments, propose a visit, get a ride quote, and schedule a calendar event.

    The agent searches apartments, proposes a specific one to the user, gets confirmation, orders a cab, and schedules a viewing
    in the calendar, demonstrating all applications in coordinated workflow.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all applications required for the scenario."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        system = SystemApp(name="core_system")
        apartment_app = ApartmentListingApp()
        cab = CabApp()

        # All apps are registered for environment
        self.apps = [aui, calendar, system, apartment_app, cab]

    def build_events_flow(self) -> None:
        """Define the oracle and user interaction events for the scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(CalendarApp)
        apartment_app = self.get_typed_app(ApartmentListingApp)
        cab = self.get_typed_app(CabApp)

        with EventRegisterer.capture_mode():
            # Step 1: User asks the agent to help find apartments
            user_request = (
                aui.send_message_to_agent(
                    content="Can you find a two-bedroom apartment to visit this week near Downtown?"
                )
                .depends_on(None, delay_seconds=1)
                .with_id("user_request")
            )

            # Step 2: Agent searches apartments and finds results
            search_apts = (
                apartment_app.search_apartments(location="Downtown", number_of_bedrooms=2, max_price=3000)
                .depends_on(user_request, delay_seconds=1)
                .oracle()
            )

            # Step 3: Agent proposes to the user which apartment to visit
            proactive_proposal = aui.send_message_to_user(
                content="I found a nice two-bedroom apartment on Main Street listed at $2800. "
                "Would you like me to schedule a tour and arrange a cab to take you there?"
            ).depends_on(search_apts, delay_seconds=1)

            # Step 4: User responds with contextual approval
            user_approval = aui.send_message_to_agent(
                content="Yes, please schedule it for Thursday afternoon and arrange the cab ride there."
            ).depends_on(proactive_proposal, delay_seconds=2)

            # Step 5: Get current time and compute planned event time
            get_time = system.get_current_time().depends_on(user_approval, delay_seconds=1).oracle()

            # Step 6: Agent adds the tour to the calendar
            calendar_event = (
                calendar.add_calendar_event(
                    title="Apartment Viewing - Main Street",
                    start_datetime="1970-01-01 14:00:00",
                    end_datetime="1970-01-01 15:00:00",
                    location="123 Main Street, Downtown",
                    description="Guided viewing for 2-bedroom apartment (Downtown)",
                    attendees=["User", "Realtor"],
                    tag="ApartmentTour",
                )
                .depends_on(get_time, delay_seconds=1)
                .oracle()
            )

            # Step 7: Agent requests ride quotation for the trip
            quotation = (
                cab.get_quotation(
                    start_location="Home",
                    end_location="123 Main Street, Downtown",
                    service_type="Default",
                    ride_time="1970-01-01 13:30:00",
                )
                .depends_on(calendar_event, delay_seconds=1)
                .oracle()
            )

            # Step 8: Agent orders a ride after getting quote
            ride_order = (
                cab.order_ride(
                    start_location="Home",
                    end_location="123 Main Street, Downtown",
                    service_type="Default",
                    ride_time="1970-01-01 13:30:00",
                )
                .depends_on(quotation, delay_seconds=1)
                .oracle()
            )

            # Step 9: Agent confirms success back to the user
            final_confirmation = (
                aui.send_message_to_user(
                    content="Your apartment tour on Thursday at 2 PM is scheduled, "
                    "and a cab will pick you up at 1:30 PM. All set!"
                )
                .depends_on(ride_order, delay_seconds=1)
                .oracle()
            )

        self.events = [
            user_request,
            search_apts,
            proactive_proposal,
            user_approval,
            get_time,
            calendar_event,
            quotation,
            ride_order,
            final_confirmation,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent successfully scheduled and arranged the transport."""
        try:
            events = env.event_log.list_view()

            # Verify if a calendar event was created
            created_event = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Apartment Viewing" in e.action.args.get("title", "")
                for e in events
            )

            # Verify if a ride was ordered
            ride_booked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
                for e in events
            )

            # Verify if user received a confirmation message
            confirmation_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "apartment tour" in e.action.args.get("content", "").lower()
                for e in events
            )

            return ScenarioValidationResult(success=(created_event and ride_booked and confirmation_sent))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
