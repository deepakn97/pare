from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import RentAFlat
from are.simulation.apps.city import CityApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_safety_check")
class ApartmentSafetyCheck(Scenario):
    """Scenario demonstrating a workflow where the agent helps the user find an apartment.

    The agent finds an apartment that fits their preferences and cross-checks local safety metrics from CityApp before
    proposing to save it. Includes a proactive interaction pattern: the agent proposes
    saving the apartment after checking safety, waits for user approval, and then saves it.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all available applications for this scenario."""
        # Create all apps according to environment requirements
        aui = AgentUserInterface()
        rent_app = RentAFlat()
        city_app = CityApp()
        system_app = SystemApp(name="system_util")

        # Register all apps
        self.apps = [aui, rent_app, city_app, system_app]

    def build_events_flow(self) -> None:
        """Define the event sequence for the apartment safety checking and saving workflow."""
        aui = self.get_typed_app(AgentUserInterface)
        rent_app = self.get_typed_app(RentAFlat)
        city_app = self.get_typed_app(CityApp)
        system_app = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 0: Get current system time at start
            event0 = system_app.get_current_time().depends_on(None, delay_seconds=0).with_id("check_time")

            # Step 1: User initiates a request for apartments in a specific area
            event1 = (
                aui.send_message_to_agent(
                    content="Hey assistant, could you find 2-bedroom apartments in the 94016 zip code?"
                )
                .depends_on(event0, delay_seconds=1)
                .with_id("user_request")
            )

            # Step 2: Agent searches apartments using RentAFlat
            event2 = (
                rent_app.search_apartments(
                    location="San Francisco",
                    zip_code="94016",
                    number_of_bedrooms=2,
                    min_price=1200,
                    max_price=2500,
                    saved_only=False,
                )
                .oracle()
                .depends_on(event1, delay_seconds=1)
                .with_id("search_apartments")
            )

            # Step 3: System waits briefly to simulate asynchronous info gathering
            event3 = (
                system_app.wait_for_notification(timeout=3).depends_on(event2, delay_seconds=0).with_id("wait_briefly")
            )

            # Step 4: Agent gets the first apartment's details
            event4 = (
                rent_app.get_apartment_details(apartment_id="apt_94016_1")
                .oracle()
                .depends_on(event3, delay_seconds=1)
                .with_id("fetch_details_first")
            )

            # Step 5: Agent checks CityApp for local crime rate for this apartment's zip
            event5 = (
                city_app.get_crime_rate(zip_code="94016")
                .oracle()
                .depends_on(event4, delay_seconds=1)
                .with_id("query_crime_rate")
            )

            # Step 6: Agent proposes saving this apartment to the user based on safety info
            event6 = (
                aui.send_message_to_user(
                    content=(
                        "I found a 2-bedroom apartment in zip 94016 with an acceptable crime rate. "
                        "Would you like me to add it to your favorites for further review?"
                    )
                )
                .depends_on(event5, delay_seconds=1)
                .with_id("agent_proposal")
            )

            # Step 7: User gives informed approval to proceed
            event7 = (
                aui.send_message_to_agent(
                    content="Yes, please save that apartment to my favorites so I can review it later."
                )
                .depends_on(event6, delay_seconds=1)
                .with_id("user_approval")
            )

            # Step 8: Agent saves the apartment after approval
            event8 = (
                rent_app.save_apartment(apartment_id="apt_94016_1")
                .oracle()
                .depends_on(event7, delay_seconds=1)
                .with_id("save_confirmed_apt")
            )

            # Step 9: Agent provides confirmation to the user that action was completed
            event9 = (
                aui.send_message_to_user(content="The apartment has been successfully added to your favorites list.")
                .depends_on(event8, delay_seconds=1)
                .with_id("confirmation_message")
            )

        self.events = [event0, event1, event2, event3, event4, event5, event6, event7, event8, event9]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the scenario achieved the intended flow.

        Agent proposed saving an apartment after checking safety and saved it only after user's approval.
        """
        try:
            events = env.event_log.list_view()

            # Confirm agent proposed to the user
            proposal_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "apartment" in e.action.args["content"].lower()
                and "favorites" in e.action.args["content"].lower()
                for e in events
            )

            # Confirm user approved saving
            approval_received = any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_agent"
                and "save" in e.action.args["content"].lower()
                for e in events
            )

            # Confirm the agent saved the apartment only after that approval
            save_executed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "RentAFlat"
                and e.action.function_name == "save_apartment"
                for e in events
            )

            # Additionally check that the city crime rate retrieval occurred
            city_call = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CityApp"
                and e.action.function_name == "get_crime_rate"
                for e in events
            )

            success = proposal_done and approval_received and save_executed and city_call
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
