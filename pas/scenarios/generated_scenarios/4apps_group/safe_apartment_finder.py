from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.city import CityApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("safe_apartment_finder")
class SafeApartmentFinder(Scenario):
    """Scenario where the agent helps the user find safe and affordable apartments.

    The workflow demonstrates:
    - Apartment search and filtering (ApartmentListingApp)
    - Checking neighborhood safety (CityApp)
    - Time tracking and waiting (SystemApp)
    - User-agent conversation and confirmation pattern (AgentUserInterface)

    The proactive interaction pattern includes:
      1. The agent proposes sharing filtered results with the user
      2. The user consents in detail
      3. The agent executes the proposal by sharing specific apartments
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate application states."""
        self.agent_ui = AgentUserInterface()
        self.system = SystemApp(name="system_safe_finder")
        self.apartments = ApartmentListingApp()
        self.city = CityApp()

        # Add all apps to the scenario
        self.apps = [self.agent_ui, self.system, self.apartments, self.city]

    def build_events_flow(self) -> None:
        """Define the key interaction and expected oracle actions."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        apt_app = self.get_typed_app(ApartmentListingApp)
        city_app = self.get_typed_app(CityApp)

        with EventRegisterer.capture_mode():
            # 1. User starts the conversation asking for apartment options
            e0 = aui.send_message_to_agent(
                content="Hi Assistant, I want safe 2-bedroom apartments around 94016 under $2500."
            ).depends_on(None, delay_seconds=1)

            # 2. Agent gets the current system time
            e1 = system.get_current_time().depends_on(e0, delay_seconds=1)

            # 3. Agent searches for apartments matching filters
            e2 = apt_app.search_apartments(
                location="San Francisco",
                zip_code="94016",
                number_of_bedrooms=2,
                max_price=2500,
                furnished_status="Unfurnished",
            ).depends_on(e1, delay_seconds=1)

            # 4. Agent checks the API limit before requesting crime rates
            e3 = city_app.get_api_call_limit().depends_on(e2, delay_seconds=1)
            e4 = city_app.get_api_call_count().depends_on(e3, delay_seconds=1)

            # 5. Agent gets crime rate for the area to evaluate safety
            e5 = city_app.get_crime_rate(zip_code="94016").depends_on(e4, delay_seconds=1)

            # 6. Agent informs user of preliminary results and proposes to share filtered list
            proposal = aui.send_message_to_user(
                content="I found several apartments around 94016. The area's crime rate is moderate. "
                "Would you like me to save and share the top 2 safest options for browsing later?"
            ).depends_on(e5, delay_seconds=1)

            # 7. User response with detailed approval
            user_response = aui.send_message_to_agent(
                content="Yes, please go ahead and save the top two safest options for me to review later."
            ).depends_on(proposal, delay_seconds=1)

            # 8. Agent saves a couple of apartments to favorites after user approval
            save_apt1 = (
                apt_app.save_apartment(apartment_id="apt_safe_1").oracle().depends_on(user_response, delay_seconds=1)
            )
            save_apt2 = (
                apt_app.save_apartment(apartment_id="apt_safe_2").oracle().depends_on(save_apt1, delay_seconds=1)
            )

            # 9. System waits briefly after action completion
            e9 = system.wait_for_notification(timeout=3).depends_on(save_apt2, delay_seconds=1)

            # 10. Agent lists and shares saved apartments back to user (oracle ground truth)
            list_saved = apt_app.list_saved_apartments().depends_on(e9, delay_seconds=1)
            share_result = (
                aui.send_message_to_user(
                    content="I've saved two of the safest apartments in your favorites list for 94016. You can check them anytime!"
                )
                .oracle()
                .depends_on(list_saved, delay_seconds=1)
            )

        # Register all events for scenario
        self.events = [
            e0,
            e1,
            e2,
            e3,
            e4,
            e5,
            proposal,
            user_response,
            save_apt1,
            save_apt2,
            e9,
            list_saved,
            share_result,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation checks if agent correctly saved apartments and notified the user."""
        try:
            events = env.event_log.list_view()

            saved_actions = [
                e
                for e in events
                if e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ApartmentListingApp"
                and e.action.function_name == "save_apartment"
            ]

            shared_message = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "favorites" in e.action.args.get("content", "").lower()
                for e in events
            )

            api_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CityApp"
                and e.action.function_name == "get_crime_rate"
                for e in events
            )

            # Validate all required conditions: crime check, apartment saved, user informed
            success = len(saved_actions) >= 2 and shared_message and api_checked
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
