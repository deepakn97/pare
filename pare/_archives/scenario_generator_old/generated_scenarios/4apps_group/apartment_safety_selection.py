from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.city import CityApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_safety_selection")
class ApartmentSafetySelection(Scenario):
    """Scenario: Agent helps the user find safe apartments in a preferred neighborhood.

    This scenario demonstrates:
    1. Using the ApartmentListingApp to search and save apartments.
    2. Using CityApp to check crime rates of apartments' zip codes.
    3. Using SystemApp to timestamp the process and handle idle waiting.
    4. Proactive agent interaction: agent proposes to share a shortlist after user confirmation.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all apps and prepare the mock environment."""
        aui = AgentUserInterface()
        listings = ApartmentListingApp()
        city_info = CityApp()
        system = SystemApp(name="system_monitor")

        # Store all apps for scenario
        self.apps = [aui, listings, city_info, system]

    def build_events_flow(self) -> None:
        """Define the sequential interaction events."""
        aui = self.get_typed_app(AgentUserInterface)
        listings = self.get_typed_app(ApartmentListingApp)
        city_info = self.get_typed_app(CityApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # 1. User initiates the apartment search task
            evt_user_request = aui.send_message_to_agent(
                content="Hi Assistant, could you help me find a 2-bedroom apartment in Lakeside area under $2500?"
            ).depends_on(None, delay_seconds=1)

            # 2. Agent checks system time for contextual timestamp
            evt_time_check = system.get_current_time().depends_on(evt_user_request, delay_seconds=1)

            # 3. Agent searches for apartments matching user's request
            evt_search = listings.search_apartments(
                location="Lakeside", number_of_bedrooms=2, max_price=2500
            ).depends_on(evt_time_check, delay_seconds=2)

            # 4. Agent retrieves details of the first apartment to analyze
            evt_details = listings.get_apartment_details(apartment_id="apt_lakeside_001").depends_on(
                evt_search, delay_seconds=1
            )

            # 5. Agent checks local crime rate of this apartment's zip code
            evt_crime_check = city_info.get_crime_rate(zip_code="90210").depends_on(evt_details, delay_seconds=1)

            # 6. Agent informs the user proactively about the crime rate and proposes shortlisting
            evt_propose = aui.send_message_to_user(
                content="I found a promising listing at Lakeside (apt_lakeside_001). The crime rate in this area is below average. Should I add this to your saved apartments list and compile a shortlist?"
            ).depends_on(evt_crime_check, delay_seconds=1)

            # 7. User agrees with a detailed confirmation
            evt_user_confirm = aui.send_message_to_agent(
                content="Yes, please save the Lakeside apartment and create a shortlist."
            ).depends_on(evt_propose, delay_seconds=2)

            # 8. Agent saves the apartment after user approval
            evt_save = (
                listings.save_apartment(apartment_id="apt_lakeside_001")
                .oracle()
                .depends_on(evt_user_confirm, delay_seconds=1)
            )

            # 9. Agent lists saved apartments for the summary
            evt_saved_list = listings.list_saved_apartments().depends_on(evt_save, delay_seconds=1)

            # 10. Agent waits for user notification after sharing info (simulate idle)
            evt_idle = system.wait_for_notification(timeout=2).depends_on(evt_saved_list, delay_seconds=1)

            # 11. Agent sends a final message with summarized results
            evt_final = (
                aui.send_message_to_user(
                    content="I've added the Lakeside apartment to your saved list. Your shortlist currently includes 1 safe property under $2500."
                )
                .oracle()
                .depends_on(evt_idle, delay_seconds=1)
            )

        self.events = [
            evt_user_request,
            evt_time_check,
            evt_search,
            evt_details,
            evt_crime_check,
            evt_propose,
            evt_user_confirm,
            evt_save,
            evt_saved_list,
            evt_idle,
            evt_final,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent helped the user select and save a safe apartment."""
        try:
            log = env.event_log.list_view()

            # 1. Verify that the save_apartment action occurred
            apt_saved = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "ApartmentListingApp"
                and ev.action.function_name == "save_apartment"
                and ev.action.args.get("apartment_id") == "apt_lakeside_001"
                for ev in log
            )

            # 2. Verify proactive proposal to user occurred
            proposed_saving = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.function_name == "send_message_to_user"
                and "shortlist" in ev.action.args.get("content", "").lower()
                for ev in log
            )

            # 3. Verify final confirmation message sent to user
            final_summary_sent = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.function_name == "send_message_to_user"
                and "added the lakeside apartment" in ev.action.args.get("content", "").lower()
                for ev in log
            )

            result = apt_saved and proposed_saving and final_summary_sent
            return ScenarioValidationResult(success=result)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
