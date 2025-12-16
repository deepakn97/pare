from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.city import CityApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("city_safety_apartment_suggestion")
class CitySafetyApartmentSuggestion(Scenario):
    """A proactive scenario where the agent proposes sharing a safety-rated apartment list.

    The agent searches for apartments, checks city crime rates using their zip codes,
    and then proposes to share the safest options with a user contact after getting confirmation.
    The scenario demonstrates use of all apps: system date/time, apartment listing search,
    city crime rate lookup, and proactive user interaction.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize environment applications and prepare dataset."""
        aui = AgentUserInterface()
        apartment_app = ApartmentListingApp()
        city_analyzer = CityApp()
        sys_app = SystemApp(name="system_clock")

        # Register all created apps in the environment
        self.apps = [aui, apartment_app, city_analyzer, sys_app]

    def build_events_flow(self) -> None:
        """Construct the sequence of scenario events."""
        aui = self.get_typed_app(AgentUserInterface)
        apt = self.get_typed_app(ApartmentListingApp)
        city = self.get_typed_app(CityApp)
        sys = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User initiates conversation: wants safe apartments for rent
            user_request = aui.send_message_to_agent(
                content="Hi, can you find safe and affordable apartments in the downtown area?"
            ).depends_on(None, delay_seconds=1)

            # Agent first checks the system time for context (maybe to timestamp data)
            time_check = sys.get_current_time().depends_on(user_request, delay_seconds=1)

            # Agent uses search to find apartments available in city center
            apt_search = apt.search_apartments(
                location="Downtown", min_price=900, max_price=1500, number_of_bedrooms=2
            ).depends_on(time_check, delay_seconds=2)

            # Agent retrieves details for two of them (mocked)
            apt_detail_1 = apt.get_apartment_details(apartment_id="APT101").depends_on(apt_search)
            apt_detail_2 = apt.get_apartment_details(apartment_id="APT204").depends_on(apt_search, delay_seconds=2)

            # Checks city crime data for the ZIP codes
            crime1 = city.get_crime_rate(zip_code="33001").depends_on(apt_detail_1, delay_seconds=1)
            crime2 = city.get_crime_rate(zip_code="33002").depends_on(apt_detail_2, delay_seconds=1)

            # The agent proposes sending a summary of safe apartments (proactive)
            propose_share = aui.send_message_to_user(
                content=(
                    "I've reviewed apartments and crime data for two downtown areas. "
                    "Would you like me to share the safest apartment list with your friend Morgan?"
                )
            ).depends_on(crime2, delay_seconds=2)

            # User approves the action contextually
            user_approves = aui.send_message_to_agent(
                content="Yes, please share the safest options with Morgan right away."
            ).depends_on(propose_share, delay_seconds=1)

            # Agent selects the safer apartment and saves it as favorite
            save_safe_apt = (
                apt.save_apartment(apartment_id="APT101").oracle().depends_on(user_approves, delay_seconds=1)
            )

            # Agent lists all saved to confirm sharing dataset
            verify_saved = apt.list_saved_apartments().depends_on(save_safe_apt, delay_seconds=1)

            # Optionally waits a bit before confirming completion
            final_wait = sys.wait_for_notification(timeout=2).depends_on(verify_saved)

        # Register oracle and expected sequence
        self.events = [
            user_request,
            time_check,
            apt_search,
            apt_detail_1,
            apt_detail_2,
            crime1,
            crime2,
            propose_share,
            user_approves,
            save_safe_apt,
            verify_saved,
            final_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent performed expected actions logically."""
        try:
            events = env.event_log.list_view()

            # Verify that the proposal message was sent to user
            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "safe" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Verify that an apartment was saved after the user approved
            saved_apt = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ApartmentListingApp"
                and e.action.function_name == "save_apartment"
                and e.action.args.get("apartment_id") == "APT101"
                for e in events
            )

            # Check that the system time was retrieved
            time_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "SystemApp"
                and e.action.function_name == "get_current_time"
                for e in events
            )

            # Confirm the city app was queried for crime data
            city_data_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CityApp"
                and e.action.function_name == "get_crime_rate"
                for e in events
            )

            success = all([proposal_sent, saved_apt, time_checked, city_data_checked])
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
