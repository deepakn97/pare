from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import RentAFlat
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("rental_search_assistant")
class RentalSearchAssistant(Scenario):
    """Scenario: agent assists the user in searching and saving an apartment rental.

    The agent demonstrates its workflow across all available apps by:
    - Using SystemApp to get the current time (for context)
    - Using RentAFlat to search, retrieve, and save apartment listings
    - Using AgentUserInterface for proactive messaging interactions
    - Including a proactive agent proposal followed by user confirmation and subsequent action
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and register all required apps."""
        # Initialize all apps
        aui = AgentUserInterface()
        rent_app = RentAFlat()
        system = SystemApp(name="sys")

        # Register apps
        self.apps = [aui, rent_app, system]

    def build_events_flow(self) -> None:
        """Build the flow of proactive apartment search assistance."""
        aui = self.get_typed_app(AgentUserInterface)
        rent_app = self.get_typed_app(RentAFlat)
        sys_app = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Event 0: User initiates the conversation
            init_request = (
                aui.send_message_to_agent(
                    content=(
                        "Hi, can you help me find an apartment in Paris under 2000€ per month with at least 2 bedrooms?"
                    )
                )
                .depends_on(None, delay_seconds=1)
                .with_id("user_init_request")
            )

            # Event 1: Agent checks system time for contextual response
            get_time = (
                sys_app.get_current_time()
                .oracle()
                .depends_on(init_request, delay_seconds=1)
                .with_id("system_time_check")
            )

            # Event 2: Agent searches apartments meeting criteria
            search_flats = (
                rent_app.search_apartments(location="Paris", max_price=2000, number_of_bedrooms=2)
                .oracle()
                .depends_on(get_time, delay_seconds=1)
                .with_id("search_apartments")
            )

            # Event 3: Agent gets details for one of the found apartments
            get_details = (
                rent_app.get_apartment_details(apartment_id="apt_102")
                .oracle()
                .depends_on(search_flats, delay_seconds=1)
                .with_id("get_apartment_details")
            )

            # Event 4: Agent sends proactive proposal to the user
            propose_action = (
                aui.send_message_to_user(
                    content=(
                        "I found a nice 2-bedroom apartment in Paris (ID apt_102) within your budget. "
                        "Would you like me to save this listing to your favorites for easier access?"
                    )
                )
                .depends_on(get_details, delay_seconds=1)
                .with_id("agent_propose_save")
            )

            # Event 5: User confirms the proactive proposal
            user_confirms = (
                aui.send_message_to_agent(content="Yes, please save that apartment so I can review it later.")
                .depends_on(propose_action, delay_seconds=1)
                .with_id("user_confirms_save")
            )

            # Event 6: Agent saves the apartment based on user approval (proactive follow-up)
            agent_saves = (
                rent_app.save_apartment(apartment_id="apt_102")
                .oracle()
                .depends_on(user_confirms, delay_seconds=1)
                .with_id("save_favorite_apt")
            )

            # Event 7: Agent lists saved apartments to verify the change
            list_saved = (
                rent_app.list_saved_apartments()
                .oracle()
                .depends_on(agent_saves, delay_seconds=1)
                .with_id("list_saved_flats")
            )

            # Event 8: Optional wait for user feedback or notification
            wait_response = (
                sys_app.wait_for_notification(timeout=5)
                .depends_on(list_saved, delay_seconds=1)
                .with_id("wait_feedback")
            )

        self.events = [
            init_request,
            get_time,
            search_flats,
            get_details,
            propose_action,
            user_confirms,
            agent_saves,
            list_saved,
            wait_response,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the proactive rental search scenario was completed successfully."""
        try:
            events = env.event_log.list_view()

            # Check if the agent proposed the saving action
            proposed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "save this listing" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Check that user approved the action
            user_approved = any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "please save" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Check that apartment saving action was executed
            saved_correctly = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "RentAFlat"
                and e.action.function_name == "save_apartment"
                and e.action.args.get("apartment_id") == "apt_102"
                for e in events
            )

            # Check the system time usage
            time_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "SystemApp"
                and e.action.function_name == "get_current_time"
                for e in events
            )

            # Overall success depends on all key validations passing
            success = proposed and user_approved and saved_correctly and time_checked
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
