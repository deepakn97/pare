from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp, RentAFlat
from are.simulation.apps.city import CityApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_safety_comparison")
class ApartmentSafetyComparison(Scenario):
    """A scenario where the agent helps the user compare apartment listings from two sources.

    The agent helps the user compare apartment listings from two sources and use city safety data to pick a good one.

    The scenario demonstrates:
    - Aggregating search results from ApartmentListingApp and RentAFlat apps
    - Using CityApp to check neighborhood crime rate
    - Using SystemApp for current time and waiting periods
    - Following a proactive interaction pattern: the agent proposes an action (sending a report),
      waits for user confirmation, and proceeds accordingly.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize the available apps for apartment searching and safety checking."""
        aui = AgentUserInterface()
        system = SystemApp(name="system_monitor")
        apt_catalog = ApartmentListingApp()
        rent_source = RentAFlat()
        city_stats = CityApp()

        # Assign instance attributes for access in build_events_flow
        self.apps = [aui, system, apt_catalog, rent_source, city_stats]

    def build_events_flow(self) -> None:
        """Define the sequence of oracle events (expected ground-truth behavior)."""
        aui = self.get_typed_app(AgentUserInterface)
        apt_catalog = self.get_typed_app(ApartmentListingApp)
        rent_source = self.get_typed_app(RentAFlat)
        city_stats = self.get_typed_app(CityApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User initiates a request for apartment comparison
            user_initial = aui.send_message_to_agent(
                content=(
                    "I'm searching for a 1-bedroom apartment around zip 94109 or 94110, "
                    "preferably safe and under $2500. Can you help?"
                )
            ).depends_on(None, delay_seconds=0)

            # Agent fetches current time for context
            time_check = system.get_current_time().depends_on(user_initial, delay_seconds=1)

            # Agent searches for apartments using both apps
            listing_search = apt_catalog.search_apartments(
                zip_code="94109", number_of_bedrooms=1, max_price=2500, property_type="Apartment"
            ).depends_on(time_check, delay_seconds=1)
            rent_search = rent_source.search_apartments(
                zip_code="94110", number_of_bedrooms=1, max_price=2500, property_type="Apartment"
            ).depends_on(time_check, delay_seconds=1)

            # Agent checks city safety for both areas
            count_quota = city_stats.get_api_call_count().depends_on(listing_search, delay_seconds=1)
            rate_94109 = city_stats.get_crime_rate(zip_code="94109").depends_on(count_quota, delay_seconds=1)
            rate_94110 = city_stats.get_crime_rate(zip_code="94110").depends_on(rate_94109, delay_seconds=1)
            limit_info = city_stats.get_api_call_limit().depends_on(rate_94110, delay_seconds=1)

            # Agent proposes sending a comparison summary to user
            proactive_propose = aui.send_message_to_user(
                content=(
                    "I've compared multiple listings and checked crime rates: "
                    "94109 has a lower crime rate than 94110. "
                    "Would you like me to save the best options and send you the comparison summary?"
                )
            ).depends_on(limit_info, delay_seconds=1)

            # User approves the proposed action
            user_approval = aui.send_message_to_agent(
                content=("Yes, please save the safest listings and send me the summary. I'll review them tonight.")
            ).depends_on(proactive_propose, delay_seconds=1)

            # Agent saves best apartments and completes report after approval
            save_from_apts = apt_catalog.save_apartment(apartment_id="APT94109_01").depends_on(
                user_approval, delay_seconds=1
            )
            save_from_rent = rent_source.save_apartment(apartment_id="RNT94109_A2").depends_on(
                user_approval, delay_seconds=1
            )
            wait_for_processing = system.wait_for_notification(timeout=5).depends_on(save_from_rent, delay_seconds=1)

            # Agent confirms sending the comparison report (oracle event)
            final_report = (
                aui.send_message_to_user(
                    content=(
                        "Safety summary and top apartments with zip 94109 have been saved "
                        "and sent to your favorites. You can now review the report anytime."
                    )
                )
                .depends_on(wait_for_processing, delay_seconds=1)
                .oracle()
            )

        self.events = [
            user_initial,
            time_check,
            listing_search,
            rent_search,
            count_quota,
            rate_94109,
            rate_94110,
            limit_info,
            proactive_propose,
            user_approval,
            save_from_apts,
            save_from_rent,
            wait_for_processing,
            final_report,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the scenario based on user confirmation and apartment saving events."""
        try:
            events = env.event_log.list_view()
            # Check if user approval message was received
            user_approved = any(
                event.event_type == EventType.USER
                and isinstance(event.action, Action)
                and event.action.function_name == "send_message_to_agent"
                and "yes" in event.action.args.get("content", "").lower()
                for event in events
            )
            # Check that both ApartmentListingApp and RentAFlat performed saves after approval
            apt_saved = any(
                event.event_type == EventType.AGENT
                and event.action.class_name == "ApartmentListingApp"
                and event.action.function_name == "save_apartment"
                and event.action.args.get("apartment_id") == "APT94109_01"
                for event in events
            )
            rent_saved = any(
                event.event_type == EventType.AGENT
                and event.action.class_name == "RentAFlat"
                and event.action.function_name == "save_apartment"
                and event.action.args.get("apartment_id") == "RNT94109_A2"
                for event in events
            )
            # Verify proactive report message was sent
            summary_delivered = any(
                event.event_type == EventType.AGENT
                and event.action.class_name == "AgentUserInterface"
                and event.action.function_name == "send_message_to_user"
                and "safety summary" in event.action.args.get("content", "").lower()
                for event in events
            )
            return ScenarioValidationResult(success=user_approved and apt_saved and rent_saved and summary_delivered)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
