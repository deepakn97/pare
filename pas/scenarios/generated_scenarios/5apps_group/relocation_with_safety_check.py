from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import RentAFlat
from are.simulation.apps.city import CityApp
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("relocation_with_safety_check")
class RelocationWithSafetyCheck(Scenario):
    """A relocation decision scenario combining apartment search, safety data, and email communication.

    The user asks the agent to find an affordable furnished apartment in a given city and check the area's  # noqa: RUF002
    safety before contacting the landlord. The agent uses RentAFlat and CityApp for this purpose, proposes
    emailing the landlord after confirming with the user, and then performs the action upon user approval.
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate all applications."""
        # Core applications
        aui = AgentUserInterface()
        system = SystemApp(name="main_system")
        email_app = EmailClientApp()
        flats = RentAFlat()
        city = CityApp()

        # Add to self.apps to register with environment
        self.apps = [aui, system, email_app, flats, city]

    def build_events_flow(self) -> None:
        """Defines full event flow with proactive user interaction and all apps involved."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        email_app = self.get_typed_app(EmailClientApp)
        flats = self.get_typed_app(RentAFlat)
        city = self.get_typed_app(CityApp)

        with EventRegisterer.capture_mode():
            # User requests to find new apartments
            request_event = (
                aui.send_message_to_agent(
                    content="I'm moving to Seattle soon. Can you look for a furnished 2-bedroom apartment under $2500 and ensure the area is safe?"
                )
                .depends_on(None, delay_seconds=1)
                .with_id("user_request")
            )

            # Agent uses SystemApp to timestamp the search (for realism)
            time_event = system.get_current_time().depends_on(request_event, delay_seconds=1).with_id("timestamp_check")

            # Agent searches for apartments using RentAFlat
            apt_search = (
                flats.search_apartments(
                    location="Seattle", furnished_status="Furnished", number_of_bedrooms=2, max_price=2500
                )
                .depends_on(time_event, delay_seconds=1)
                .with_id("apartment_search")
            )

            # Agent gets the details of one of the results
            apt_detail = (
                flats.get_apartment_details(apartment_id="apt_sea_204")
                .depends_on(apt_search, delay_seconds=1)
                .with_id("apt_detail_retrieval")
            )

            # Check crime rate in the area using CityApp
            crime_check = (
                city.get_crime_rate(zip_code="98101")
                .depends_on(apt_detail, delay_seconds=1)
                .with_id("crime_rate_check")
            )

            # Agent proactively proposes to contact the landlord
            propose_email = (
                aui.send_message_to_user(
                    content=(
                        "I found a furnished 2-bedroom apartment in Seattle (ID apt_sea_204) under the budget. "
                        "The area (zip 98101) has a low crime rate. Would you like me to email the landlord to request a viewing?"
                    )
                )
                .depends_on(crime_check, delay_seconds=1)
                .with_id("propose_landlord_email")
            )

            # User approves the proactive suggestion
            user_approval = (
                aui.send_message_to_agent(content="Yes, go ahead and email the landlord to schedule a viewing please.")
                .depends_on(propose_email, delay_seconds=2)
                .with_id("user_approval_message")
            )

            # Agent executes sending email to landlord (oracle)
            send_email_to_landlord = (
                email_app.send_email(
                    recipients=["landlord@urbanestates.com"],
                    subject="Viewing Request for Seattle Apartment apt_sea_204",
                    content="Hello, I am interested in viewing the furnished 2-bedroom apartment (ID apt_sea_204). Could we arrange a convenient time?",
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
                .with_id("oracle_send_landlord_email")
            )

            # Agent may wait for confirmation signal or new notification after sending
            confirm_wait = (
                system.wait_for_notification(timeout=3)
                .depends_on(send_email_to_landlord, delay_seconds=1)
                .with_id("wait_after_email")
            )

            # To demonstrate RentAFlat favorites system
            mark_favorite = (
                flats.save_apartment(apartment_id="apt_sea_204")
                .depends_on(confirm_wait, delay_seconds=1)
                .with_id("mark_apartment_favorite")
            )

        self.events = [
            request_event,
            time_event,
            apt_search,
            apt_detail,
            crime_check,
            propose_email,
            user_approval,
            send_email_to_landlord,
            confirm_wait,
            mark_favorite,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validates agent success via multiple signals including email sent and proactive communication."""
        try:
            events = env.event_log.list_view()

            # Must include forward email to landlord
            email_action = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "EmailClientApp"
                and e.action.function_name == "send_email"
                and "Viewing Request" in e.action.args.get("subject", "")
                and "landlord@urbanestates.com" in e.action.args.get("recipients", [])
                for e in events
            )

            # Agent must have proposed the action and waited for confirmation
            proposal = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "Would you like" in e.action.args.get("content", "")
                and "email the landlord" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Verification that CityApp and RentAFlat usage occurred
            city_use = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CityApp"
                and e.action.function_name == "get_crime_rate"
                for e in events
            )

            flat_searched = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "RentAFlat"
                and e.action.function_name == "search_apartments"
                for e in events
            )

            all_conditions = email_action and proposal and city_use and flat_searched
            return ScenarioValidationResult(success=all_conditions)
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
