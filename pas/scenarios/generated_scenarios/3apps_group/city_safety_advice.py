from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.city import CityApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("city_safety_advice")
class CitySafetyAdvice(Scenario):
    """Agent assists the user by checking city safety levels using crime rate data.

    The agent proposes to share insights with a friend, and proceeds upon confirmation.

    This scenario demonstrates:
    - Integration of CityApp to fetch crime rates
    - Time awareness and waiting mechanics using SystemApp
    - Proactive conversation with the user interface
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate apps."""
        aui = AgentUserInterface()
        city = CityApp()
        system = SystemApp(name="system")

        # Combine all apps into a list for the environment
        self.apps = [aui, city, system]

    def build_events_flow(self) -> None:
        """Build the event flow for this scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        city = self.get_typed_app(CityApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 1: User initiates request to compare city safety
            user_msg = aui.send_message_to_agent(
                content=(
                    "Hi, I'm considering moving either to zipcode 94103 or 95014. "
                    "Can you tell me which one seems safer?"
                )
            ).depends_on(None, delay_seconds=1)

            # Step 2: System records current time before requests
            time_snapshot = system.get_current_time().depends_on(user_msg, delay_seconds=1)

            # Step 3: Agent retrieves API usage details (limit and count)
            api_limit = city.get_api_call_limit().depends_on(time_snapshot, delay_seconds=1)
            api_count = city.get_api_call_count().depends_on(api_limit, delay_seconds=1)

            # Step 4: Agent queries crime rates for both zip codes
            crime_rate_1 = city.get_crime_rate(zip_code="94103").depends_on(api_count, delay_seconds=1)
            crime_rate_2 = city.get_crime_rate(zip_code="95014").depends_on(crime_rate_1, delay_seconds=1)

            # Step 5: Agent proactively proposes sharing insight with a friend
            propose_share = aui.send_message_to_user(
                content=(
                    "I found that 95014 appears to have a lower crime rate than 94103. "
                    "Would you like me to send this summary to your friend Jordan so they can review it too?"
                )
            ).depends_on(crime_rate_2, delay_seconds=1)

            # Step 6: User provides contextual approval to share
            user_approval = aui.send_message_to_agent(
                content="Yes, please send the summary and mention we should consider 95014."
            ).depends_on(propose_share, delay_seconds=1)

            # Step 7: Agent waits for a bit before performing the sharing (simulate idle period)
            wait_for_event = system.wait_for_notification(timeout=3).depends_on(user_approval, delay_seconds=1)

            # Step 8: Agent executes the approved action (simulated as sending message to user again for validation)
            confirm_share = (
                aui.send_message_to_user(
                    content="I've sent Jordan the safety summary and recommended 95014 as a safer area."
                )
                .depends_on(wait_for_event, delay_seconds=1)
                .oracle()
            )

        self.events = [
            user_msg,
            time_snapshot,
            api_limit,
            api_count,
            crime_rate_1,
            crime_rate_2,
            propose_share,
            user_approval,
            wait_for_event,
            confirm_share,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent correctly gathered data and executed the sharing action."""
        try:
            events = env.event_log.list_view()

            # Check that the agent used CityApp APIs to get both rates
            used_city_api = sum(
                1
                for e in events
                if e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CityApp"
                and e.action.function_name == "get_crime_rate"
            )

            # Check for proactive messaging involving user proposal
            proposed_message = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "would you like me to send this summary" in e.action.args["content"].lower()
                for e in events
            )

            # Check for confirmation message actually being sent
            confirmation_executed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "i've sent jordan" in e.action.args["content"].lower()
                for e in events
            )

            success = used_city_api >= 2 and proposed_message and confirmation_executed
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
