from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.city import CityApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("city_trip_coordination")
class CityTripCoordination(Scenario):
    """Scenario: A collaborative travel coordination task using all available apps.

    The user wants to check safety conditions in a district before heading to a meeting.
    The agent checks the current time, evaluates the crime rate via CityApp,
    confirms user preferences, and upon approval, books a cab and sends arrival details
    through a messaging conversation with a colleague.

    This scenario demonstrates the integrated use of Contacts, Messaging, City,
    Cab, AgentUserInterface, and System apps with proactive confirmation patterns.
    """

    start_time: float | None = 0
    duration: float | None = 45

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate all applications with mock data."""
        aui = AgentUserInterface()
        contacts = ContactsApp()
        messaging = MessagingApp()
        cab = CabApp()
        system = SystemApp(name="SystemContext")
        city = CityApp()

        # Add current user and teammate contacts
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Lee",
            gender=Gender.FEMALE,
            age=31,
            nationality="USA",
            city_living="Brooklyn",
            country="USA",
            status=Status.EMPLOYED,
            job="Project Manager",
            email="jordan.lee@workmail.com",
            phone="+1 202 555 9034",
            description="Colleague scheduled for the meeting downtown.",
        )
        contacts.add_new_contact(
            first_name="Sam",
            last_name="Rivera",
            gender=Gender.MALE,
            age=29,
            nationality="USA",
            city_living="Manhattan",
            country="USA",
            status=Status.EMPLOYED,
            job="Agent user",
            email="sam.rivera@workmail.com",
            phone="+1 202 555 8812",
        )

        # Create a default conversation with Jordan
        messaging.create_conversation(participants=["Jordan Lee"], title="Team Downtown Meeting")

        self.apps = [aui, contacts, messaging, system, city, cab]

    def build_events_flow(self) -> None:
        """Define the sequence of user-agent and system interactions."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        city = self.get_typed_app(CityApp)
        cab = self.get_typed_app(CabApp)
        contacts = self.get_typed_app(ContactsApp)
        messaging = self.get_typed_app(MessagingApp)

        # Retrieve IDs for messaging
        conversations = messaging.list_recent_conversations(offset=0, limit=5)
        conv_id = (
            conversations[0].id
            if conversations
            else messaging.create_conversation(participants=["Jordan Lee"], title="Team Downtown Meeting")
        )

        with EventRegisterer.capture_mode():
            # USER event—user requests check for safe and fast travel downtown for meeting
            user_request = aui.send_message_to_agent(
                content="Assistant, can you check if the downtown district is safe and help me plan a ride to meet Jordan?"
            ).depends_on(None, delay_seconds=1)

            # AGENT uses SystemApp to check current time
            get_time = system.get_current_time().oracle().depends_on(user_request, delay_seconds=1)

            # AGENT checks recent crime rate information for target area (e.g., zip 10001)
            fetch_crime_rate = city.get_crime_rate(zip_code="10001").oracle().depends_on(get_time, delay_seconds=1)

            # AGENT notifies user with proactive message
            propose_action = aui.send_message_to_user(
                content=(
                    "The downtown (10001) area shows a moderate safety level. "
                    "Would you like me to go ahead and arrange a ride to your meeting location?"
                )
            ).depends_on(fetch_crime_rate, delay_seconds=1)

            # USER approves the proposed action
            user_confirmation = aui.send_message_to_agent(
                content="Yes, please book the cab now and let Jordan know my ETA."
            ).depends_on(propose_action, delay_seconds=1)

            # AGENT retrieves quote from CabApp and orders ride after user confirms
            quotation = (
                cab.get_quotation(start_location="Manhattan", end_location="Downtown", service_type="Premium")
                .oracle()
                .depends_on(user_confirmation, delay_seconds=1)
            )

            # AGENT books the cab
            book_ride = (
                cab.order_ride(start_location="Manhattan", end_location="Downtown", service_type="Premium")
                .oracle()
                .depends_on(quotation, delay_seconds=1)
            )

            # AGENT retrieves ride status
            ride_status = cab.get_current_ride_status().oracle().depends_on(book_ride, delay_seconds=2)

            # AGENT sends message to Jordan via messaging app with arrival details
            agent_message_to_colleague = (
                messaging.send_message(
                    conversation_id=conv_id,
                    content="Hi Jordan, Sam's ride is confirmed to Downtown. ETA approximately 20 minutes.",
                )
                .oracle()
                .depends_on(ride_status, delay_seconds=1)
            )

            # AGENT informs user ride is confirmed and notification sent
            notify_user_completion = (
                aui.send_message_to_user(
                    content="I have confirmed your premium ride to Downtown and notified Jordan about your arrival."
                )
                .oracle()
                .depends_on(agent_message_to_colleague, delay_seconds=1)
            )

            # SYSTEM waits for any final notification before ending scenario
            wait_and_done = system.wait_for_notification(timeout=5).oracle().depends_on(notify_user_completion)

        self.events = [
            user_request,
            get_time,
            fetch_crime_rate,
            propose_action,
            user_confirmation,
            quotation,
            book_ride,
            ride_status,
            agent_message_to_colleague,
            notify_user_completion,
            wait_and_done,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that all apps were involved and the workflow was complete."""
        try:
            event_log = env.event_log.list_view()

            # Check that a cab order was made
            ordered_ride = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
                for e in event_log
            )

            # Check that city safety check happened
            city_checked = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "CityApp"
                and e.action.function_name == "get_crime_rate"
                for e in event_log
            )

            # Check proactive proposal + user confirmation pattern
            user_prompt_sent = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "AgentUserInterface"
                and "Would you like me to go ahead and arrange a ride" in e.action.args.get("content", "")
                for e in event_log
            )
            user_approval_received = any(
                e.event_type == EventType.USER and "Yes, please book the cab" in e.action.args.get("content", "")
                for e in event_log
            )

            # Check message sent to colleague via messaging app
            messaged_colleague = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "MessagingApp"
                and e.action.function_name == "send_message"
                and "Jordan" in e.action.args.get("content", "")
                for e in event_log
            )

            # Check system actions exist
            time_checked = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "SystemApp"
                and e.action.function_name == "get_current_time"
                for e in event_log
            )

            # All apps must have been used
            all_apps_used = all([ordered_ride, city_checked, messaged_colleague, user_prompt_sent, time_checked])

            return ScenarioValidationResult(success=(all_apps_used and user_approval_received))
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
