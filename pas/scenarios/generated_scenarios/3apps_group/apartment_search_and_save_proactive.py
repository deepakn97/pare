from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_search_and_save_proactive")
class ApartmentSearchAndSaveProactive(Scenario):
    """Scenario demonstrating an AI-assisted apartment search flow with a proactive confirmation step.

    The user asks the agent to look for apartments within a specific budget and city.
    The agent uses the ApartmentListingApp to search and retrieve detailed information.
    Then, the agent proactively suggests saving one to favorites — upon approval, it executes this action.

    This scenario uses all apps:
      - SystemApp: to get the current time and wait
      - AgentUserInterface: for proposal and confirmation messages
      - ApartmentListingApp: for search, detail lookup, and saving
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize environment applications."""
        # Initialize all required applications
        aui = AgentUserInterface()
        system = SystemApp(name="sys_app_primary")
        apartment_app = ApartmentListingApp()

        # Store initialized applications
        self.apps = [aui, system, apartment_app]

    def build_events_flow(self) -> None:
        """Build the core flow with proactive proposal and confirmation pattern."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        apartments = self.get_typed_app(ApartmentListingApp)

        with EventRegisterer.capture_mode():
            # Step 1: user asks for apartment search
            user_request = aui.send_message_to_agent(
                content="Hey Assistant, could you help me find a one-bedroom apartment in Seattle under $1800?"
            ).depends_on(None, delay_seconds=1)

            # Step 2: system gets current time before conducting search (to reference search timing)
            sys_time = system.get_current_time().depends_on(user_request, delay_seconds=1)

            # Step 3: agent searches apartments using given criteria
            search_results = apartments.search_apartments(
                location="Seattle", number_of_bedrooms=1, max_price=1800, property_type="Apartment"
            ).depends_on(sys_time, delay_seconds=1)

            # Step 4: agent fetches more info about a specific result (simulate with ID)
            details = apartments.get_apartment_details(apartment_id="apt_001").depends_on(
                search_results, delay_seconds=1
            )

            # Step 5 (proactive pattern): agent proposes saving the apartment
            proposal_msg = aui.send_message_to_user(
                content="I found a modern apartment in Seattle within your budget. Would you like me to save it for you?"
            ).depends_on(details, delay_seconds=1)

            # Step 6: user grants explicit approval (contextually meaningful)
            user_confirmation = aui.send_message_to_agent(
                content="Yes, please save that Seattle apartment for later review."
            ).depends_on(proposal_msg, delay_seconds=2)

            # Step 7: agent saves the apartment as user approved
            oracle_save = (
                apartments.save_apartment(apartment_id="apt_001")
                .oracle()
                .depends_on(user_confirmation, delay_seconds=1)
            )

            # Step 8: optional wait phase to simulate post-action idle state
            wait_complete = system.wait_for_notification(timeout=3).depends_on(oracle_save, delay_seconds=1)

        # Register the event timeline
        self.events = [
            user_request,
            sys_time,
            search_results,
            details,
            proposal_msg,
            user_confirmation,
            oracle_save,
            wait_complete,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the scenario behavior."""
        try:
            events = env.event_log.list_view()

            # Validate proactive message exists
            agent_proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "save" in e.action.args["content"].lower()
                for e in events
            )

            # Validate actual save operation occurred
            apartment_saved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ApartmentListingApp"
                and e.action.function_name == "save_apartment"
                and e.action.args.get("apartment_id") == "apt_001"
                for e in events
            )

            # Validate user responded meaningfully
            user_confirmation_given = any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.function_name == "send_message_to_agent"
                and "save" in e.action.args["content"].lower()
                for e in events
            )

            # Check that all three core elements of proactive workflow happened
            success = agent_proposal_sent and user_confirmation_given and apartment_saved
            return ScenarioValidationResult(success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
