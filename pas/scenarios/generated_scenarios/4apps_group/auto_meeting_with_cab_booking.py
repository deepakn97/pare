from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("auto_meeting_with_cab_booking")
class AutoMeetingWithCabBooking(Scenario):
    """Scenario for automated meeting scheduling with cab booking.

    The user wants to attend a meeting at an external site, and the agent helps by checking the time,
    adding the meeting event to the calendar, and proposing to arrange a cab to the location.
    This scenario demonstrates integration between time management, scheduling, and mobility apps,
    including proactive proposal from the agent and conditional execution based on user approval.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate all required apps."""
        aui = AgentUserInterface()
        system = SystemApp(name="system_agent")
        calendar = CalendarApp()
        cab = CabApp()

        # Populate the calendar with an existing dummy event
        calendar.add_calendar_event(
            title="Project Standup",
            start_datetime="1970-01-01 09:00:00",
            end_datetime="1970-01-01 09:30:00",
            tag="work",
            description="Daily standup meeting with team",
            location="Office",
            attendees=["Alex Johnson", "Team"],
        )

        self.apps = [aui, system, calendar, cab]

    def build_events_flow(self) -> None:
        """Define full event sequence, including proactive interaction and follow-up actions."""
        aui = self.get_typed_app(AgentUserInterface)
        cab = self.get_typed_app(CabApp)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(CalendarApp)

        with EventRegisterer.capture_mode():
            # User starts the interaction
            user_request = aui.send_message_to_agent(
                content="I have a client meeting tomorrow morning at GreenHub Center. Please help me organize it."
            ).depends_on(None, delay_seconds=1)

            # Agent checks current time
            check_time = system.get_current_time().depends_on(user_request, delay_seconds=1)

            # Agent proposes scheduling a meeting in the calendar
            agent_propose_schedule = aui.send_message_to_user(
                content="Would you like me to schedule the GreenHub Center meeting for tomorrow at 10 AM in your calendar?"
            ).depends_on(check_time, delay_seconds=1)

            # User approves proactive action
            user_approval_schedule = aui.send_message_to_agent(
                content="Yes, please schedule it and plan transport as well."
            ).depends_on(agent_propose_schedule, delay_seconds=1)

            # Agent adds event to calendar
            add_meeting_event = (
                calendar.add_calendar_event(
                    title="Client Meeting at GreenHub Center",
                    start_datetime="1970-01-02 10:00:00",
                    end_datetime="1970-01-02 11:30:00",
                    tag="client",
                    description="Discussion with client regarding partnership opportunities.",
                    location="GreenHub Center",
                    attendees=["Self", "Client Representative"],
                )
                .depends_on(user_approval_schedule, delay_seconds=1)
                .oracle()
            )

            # Agent retrieves the meeting event to confirm details (read-back)
            verify_added_event = calendar.get_calendar_event(event_id=add_meeting_event.output_ref).depends_on(
                add_meeting_event, delay_seconds=1
            )

            # Agent checks calendar tags after adding event
            check_tags = calendar.get_all_tags().depends_on(verify_added_event, delay_seconds=1)

            # Agent proactively offers to book a cab (core proactive move)
            propose_cab = aui.send_message_to_user(
                content="Shall I book a Premium cab to GreenHub Center 30 minutes before your 10 AM meeting?"
            ).depends_on(check_tags, delay_seconds=1)

            # User agrees to the cab booking
            user_approves_cab = aui.send_message_to_agent(
                content="Yes, go ahead and book the Premium cab for that time."
            ).depends_on(propose_cab, delay_seconds=1)

            # Agent gets quotation before ordering
            quote_ride = cab.get_quotation(
                start_location="Home Address",
                end_location="GreenHub Center",
                service_type="Premium",
                ride_time="1970-01-02 09:30:00",
            ).depends_on(user_approves_cab, delay_seconds=1)

            # Agent places the actual ride order
            order_trip = (
                cab.order_ride(
                    start_location="Home Address",
                    end_location="GreenHub Center",
                    service_type="Premium",
                    ride_time="1970-01-02 09:30:00",
                )
                .depends_on(quote_ride, delay_seconds=1)
                .oracle()
            )

            # Agent waits for confirmation signal / cooldown
            pause_for_system = system.wait_for_notification(timeout=3).depends_on(order_trip, delay_seconds=1)

            # Agent follows up by listing rides (to confirm booking success)
            list_recent_rides = cab.get_ride_history(offset=0, limit=5).depends_on(pause_for_system, delay_seconds=1)

            # Agent searches for calendar event by keyword to confirm placement
            confirm_event_added = calendar.search_events(query="GreenHub Center").depends_on(
                list_recent_rides, delay_seconds=1
            )

        self.events = [
            user_request,
            check_time,
            agent_propose_schedule,
            user_approval_schedule,
            add_meeting_event,
            verify_added_event,
            check_tags,
            propose_cab,
            user_approves_cab,
            quote_ride,
            order_trip,
            pause_for_system,
            list_recent_rides,
            confirm_event_added,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation based on evidence of both calendar scheduling and cab booking."""
        try:
            events = env.event_log.list_view()
            # Success conditions
            calendar_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "CalendarApp"
                and event.action.function_name == "add_calendar_event"
                and "GreenHub Center" in event.action.args.get("location", "")
                for event in events
            )
            cab_ordered = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "CabApp"
                and event.action.function_name == "order_ride"
                and event.action.args["end_location"] == "GreenHub Center"
                for event in events
            )
            proactive_msg_exists = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and event.action.function_name == "send_message_to_user"
                and "book" in event.action.args.get("content", "").lower()
                and "cab" in event.action.args.get("content", "").lower()
                for event in events
            )
            return ScenarioValidationResult(success=(calendar_created and cab_ordered and proactive_msg_exists))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
