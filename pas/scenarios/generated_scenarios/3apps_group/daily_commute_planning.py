from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("daily_commute_planning")
class DailyCommutePlanning(Scenario):
    """Scenario: The agent helps the user plan a morning commute with proactive confirmation and full app ecosystem use."""

    start_time: float | None = 0
    duration: float | None = 22

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate the available apps with contextual data."""
        # Initialize apps
        self.aui = AgentUserInterface()
        self.cab_app = CabApp()
        self.system = SystemApp(name="clock_system")

        # Collect all apps in scenario
        self.apps = [self.aui, self.cab_app, self.system]

    def build_events_flow(self) -> None:
        """Define the sequence of events: user asks for help, agent proposes ride, user approves, agent acts."""
        aui = self.get_typed_app(AgentUserInterface)
        cab = self.get_typed_app(CabApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # 0. User starts conversation asking about daily commute
            event0 = aui.send_message_to_agent(
                content="Good morning, can you help me plan my commute to work from 14 Pine Street to 88 Oak Avenue?"
            ).depends_on(None, delay_seconds=1)

            # 1. The agent checks current system time to base decisions on it
            time_info = system.get_current_time().depends_on(event0, delay_seconds=1)

            # 2. The agent checks available ride options and quotations
            list_options = cab.list_rides(start_location="14 Pine Street", end_location="88 Oak Avenue").depends_on(
                time_info, delay_seconds=1
            )
            quote = cab.get_quotation(
                start_location="14 Pine Street", end_location="88 Oak Avenue", service_type="Default", ride_time=None
            ).depends_on(list_options, delay_seconds=1)

            # 3. The agent proactively proposes ordering the best ride for the user
            agent_propose = aui.send_message_to_user(
                content=(
                    "I found a couple of ride options for your commute. The default service looks best — "
                    "Would you like me to book the Default ride from 14 Pine Street to 88 Oak Avenue now?"
                )
            ).depends_on(quote, delay_seconds=1)

            # 4. The user replies, approving the booking
            user_confirms = aui.send_message_to_agent(
                content="Yes, please go ahead and order that Default service now."
            ).depends_on(agent_propose, delay_seconds=2)

            # 5. Since user approved, the agent proceeds to order the ride
            oracle_order = (
                cab.order_ride(
                    start_location="14 Pine Street",
                    end_location="88 Oak Avenue",
                    service_type="Default",
                    ride_time=None,
                )
                .oracle()
                .depends_on(user_confirms, delay_seconds=1)
            )

            # 6. The agent can later check current ride status (if needed)
            ride_status = cab.get_current_ride_status().depends_on(oracle_order, delay_seconds=2)

            # 7. Agent notifies the user that the cab is on its way
            notify_user = aui.send_message_to_user(
                content="Your ride has been successfully booked and is on its way! I'll keep you updated if anything changes."
            ).depends_on(ride_status, delay_seconds=1)

            # 8. Wait for a system notification for the ride completion simulation
            wait_event = system.wait_for_notification(timeout=5).depends_on(notify_user, delay_seconds=1)

            # 9. Agent checks history length as a closing step
            check_history_len = cab.get_ride_history_length().depends_on(wait_event, delay_seconds=1)

            # 10. And optionally retrieves recent history entry for validation
            retrieve_history = cab.get_ride_history(offset=0, limit=3).depends_on(check_history_len, delay_seconds=1)

        self.events = [
            event0,
            time_info,
            list_options,
            quote,
            agent_propose,
            user_confirms,
            oracle_order,
            ride_status,
            notify_user,
            wait_event,
            check_history_len,
            retrieve_history,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate agent successfully proposed, received approval, and ordered the Correct ride."""
        try:
            events = env.event_log.list_view()

            # Was the agent proactive with a meaningful proposal message?
            proposed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "send_message_to_user"
                and e.action.class_name == "AgentUserInterface"
                and "ride" in e.action.args["content"].lower()
                and "book" in e.action.args["content"].lower()
                for e in events
            )

            # Did the user approve properly?
            approved = any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.function_name == "send_message_to_agent"
                and e.action.class_name == "AgentUserInterface"
                and ("yes" in e.action.args["content"].lower() and "order" in e.action.args["content"].lower())
                for e in events
            )

            # Was the ride ordered by the agent after user approval?
            ride_ordered = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "order_ride"
                and e.action.class_name == "CabApp"
                for e in events
            )

            # Agent fetched ride status or history as final checks
            status_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name in ["get_current_ride_status", "get_ride_history_length"]
                and e.action.class_name == "CabApp"
                for e in events
            )

            success = proposed and approved and ride_ordered and status_checked
            return ScenarioValidationResult(success=success)
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
