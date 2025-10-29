from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.sandbox_file_system import Files
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("travel_assistant_with_calendar_and_ride")
class TravelAssistantWithCalendarAndRide(Scenario):
    """Scenario: The user wants to organize a business trip including saving the itinerary.

    The user wants to organize a business trip including saving the itinerary, scheduling it
    in the calendar, and ordering a cab to the airport.

    This scenario tests:
    - Files: creating and organizing documents
    - CalendarApp: scheduling and reading events
    - CabApp: getting a ride quotation and confirming the ride
    - SystemApp: retrieving system time
    - AgentUserInterface: proactive proposal by the Agent and confirmation by the user
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate all app data."""
        aui = AgentUserInterface()
        system = SystemApp(name="sys_travel")
        calendar = CalendarApp()
        fs = Files(name="travel_files", sandbox_dir=kwargs.get("sandbox_dir"))
        cab = CabApp()

        # create folder and a dummy itinerary file
        fs.makedirs("/docs/trips", exist_ok=True)
        fs.open(path="/docs/trips/itinerary.txt", mode="wb")
        fs.cat(path="/docs/trips/itinerary.txt")

        self.apps = [aui, system, calendar, fs, cab]

    def build_events_flow(self) -> None:
        """Construct sequence of events for this business trip assistant scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(CalendarApp)
        fs = self.get_typed_app(Files)
        cab = self.get_typed_app(CabApp)

        with EventRegisterer.capture_mode():
            # 1. user starts a chat describing the business trip they want to organize
            event0 = aui.send_message_to_agent(
                content="Hey, could you help me arrange my business trip to Paris tomorrow morning?"
            ).depends_on(None, delay_seconds=1)

            # 2. agent checks the current time to prepare schedule
            get_time = system.get_current_time().depends_on(event0, delay_seconds=1)

            # 3. agent writes a summary itinerary into a file in the sandbox
            create_itinerary = fs.cat(path="/docs/trips/itinerary.txt", recursive=False).depends_on(
                get_time, delay_seconds=1
            )

            # 4. agent schedules a calendar event for the business meeting
            calendar_event = calendar.add_calendar_event(
                title="Paris Business Meeting",
                start_datetime="1970-01-02 09:00:00",
                end_datetime="1970-01-02 11:00:00",
                tag="BusinessTravel",
                description="Meeting with the Paris branch team",
                location="Paris Office",
                attendees=["You"],
            ).depends_on(create_itinerary, delay_seconds=1)

            # 5. agent gets quotation for cab ride to airport next morning
            quote_action = cab.get_quotation(
                start_location="Home address",
                end_location="International Airport",
                service_type="Premium",
                ride_time="1970-01-02 07:15:00",
            ).depends_on(calendar_event, delay_seconds=1)

            # 6. proactive step: agent proposes ordering the cab after checking quotation
            proactive_proposal = aui.send_message_to_user(
                content="I've prepared your Paris meeting and got a cab quote for tomorrow at 7:15 AM to the airport. Should I confirm the ride booking now?"
            ).depends_on(quote_action, delay_seconds=1)

            # 7. user responds with contextual approval
            user_approval = aui.send_message_to_agent(
                content="Yes, please confirm the ride to the airport."
            ).depends_on(proactive_proposal, delay_seconds=1)

            # 8. agent orders the ride as per user approval
            order_cab = (
                cab.order_ride(
                    start_location="Home address",
                    end_location="International Airport",
                    service_type="Premium",
                    ride_time="1970-01-02 07:15:00",
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # 9. agent adds the ride trip into calendar as part of travel schedule
            airport_event = (
                calendar.add_calendar_event(
                    title="Cab ride to airport",
                    start_datetime="1970-01-02 07:15:00",
                    end_datetime="1970-01-02 07:45:00",
                    tag="Transport",
                    description="Booked Premium cab ride to the airport",
                    location="Home address",
                    attendees=["You"],
                )
                .oracle()
                .depends_on(order_cab, delay_seconds=1)
            )

        self.events = [
            event0,
            get_time,
            create_itinerary,
            calendar_event,
            quote_action,
            proactive_proposal,
            user_approval,
            order_cab,
            airport_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Scenario validation: Verify that cab was ordered after user approval and calendar updated."""
        try:
            events = env.event_log.list_view()

            proactive_ok = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "send_message_to_user"
                and "airport" in e.action.args["content"].lower()
                for e in events
            )

            approval_ok = any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.function_name == "send_message_to_agent"
                and "confirm" in e.action.args["content"].lower()
                for e in events
            )

            ride_ordered = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
                for e in events
            )

            calendar_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "airport" in (e.action.args.get("title", "").lower())
                for e in events
            )

            all_apps_used = proactive_ok and approval_ok and ride_ordered and calendar_added
            return ScenarioValidationResult(success=all_apps_used)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
