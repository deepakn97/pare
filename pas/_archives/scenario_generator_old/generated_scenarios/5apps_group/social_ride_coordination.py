from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("social_ride_coordination")
class SocialRideCoordination(Scenario):
    """A scenario where the agent coordinates a social meetup by confirming ride details.

    This scenario includes proactive interaction:
    The agent proposes a ride booking for a user meetup. The user approves, and the agent executes it.

    All apps are utilized:
    - ContactsApp: Manage guest details
    - MessagingApp: Coordinate meetups via chat
    - SystemApp: Time reference
    - CabApp: Request ride quotations and book a cab
    - AgentUserInterface: Communicate with the user
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all required apps and populate them with mock data."""
        aui = AgentUserInterface()
        system = SystemApp(name="System")
        messaging = MessagingApp()
        contacts = ContactsApp()
        cab = CabApp()

        # Add known contacts
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Smith",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            age=28,
            phone="+1 555 319 4455",
            email="jordan.smith@example.com",
            city_living="San Francisco",
            country="USA",
        )
        contacts.add_new_contact(
            first_name="Ava",
            last_name="Williams",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            age=26,
            phone="+1 555 883 1042",
            email="ava.williams@example.com",
            city_living="San Francisco",
            country="USA",
        )

        self.apps = [aui, system, messaging, contacts, cab]

    def build_events_flow(self) -> None:
        """Define the oracle event flow for the social ride coordination scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        messaging = self.get_typed_app(MessagingApp)
        contacts = self.get_typed_app(ContactsApp)
        cab = self.get_typed_app(CabApp)

        # Current time reference
        current_time_info = system.get_current_time()
        current_datetime = current_time_info["datetime"]

        # Create a chat with Jordan to discuss meetup
        conv_id = messaging.create_conversation(["Jordan Smith"], title="Brunch plans with Jordan")

        with EventRegisterer.capture_mode():
            # 1. User requests help planning a brunch meetup
            user_intro = aui.send_message_to_agent(
                content="Hey Assistant, can you help me confirm a brunch meetup with Jordan this weekend and arrange a cab?"
            ).depends_on(None, delay_seconds=0)

            # 2. Jordan texts the user to finalize time and place
            jordan_msg = messaging.send_message(
                conversation_id=conv_id, content="How about meeting at Cafe Aroma at 10 AM on Saturday?"
            ).depends_on(user_intro, delay_seconds=1)

            # 3. Agent fetches user's details for context
            current_user_info = contacts.get_current_user_details()

            # 4. Agent proposes to confirm the meetup and arrange a cab ride proactively
            agent_propose = aui.send_message_to_user(
                content=(
                    "I see Jordan wants to meet at Cafe Aroma at 10 AM on Saturday. "
                    "Would you like me to confirm the plan in chat and order a cab from your location?"
                )
            ).depends_on(jordan_msg, delay_seconds=1)

            # 5. User approves the proposal
            user_approval = aui.send_message_to_agent(
                content="Yes, go ahead and confirm with Jordan, then book the cab to Cafe Aroma."
            ).depends_on(agent_propose, delay_seconds=1)

            # 6. Agent confirms the meetup in conversation
            confirm_msg = (
                messaging.send_message(
                    conversation_id=conv_id, content="Sounds great, Jordan! See you at Cafe Aroma at 10 AM on Saturday."
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # 7. Agent retrieves a quotation for the cab booking
            quotation = (
                cab.get_quotation(
                    start_location="123 Oak Street",
                    end_location="Cafe Aroma, San Francisco",
                    service_type="Default",
                    ride_time=current_datetime,
                )
                .oracle()
                .depends_on(confirm_msg, delay_seconds=1)
            )

            # 8. Agent then books the ride after getting the quotation
            order_ride = (
                cab.order_ride(
                    start_location="123 Oak Street",
                    end_location="Cafe Aroma, San Francisco",
                    service_type="Default",
                    ride_time=current_datetime,
                )
                .oracle()
                .depends_on(quotation, delay_seconds=1)
            )

            # 9. Agent sends confirmation message to user about successful cab scheduling
            completion_notify = (
                aui.send_message_to_user(
                    content="The brunch with Jordan is confirmed, and your cab to Cafe Aroma at 9:45 AM is booked."
                )
                .oracle()
                .depends_on(order_ride, delay_seconds=1)
            )

        self.events = [
            user_intro,
            jordan_msg,
            agent_propose,
            user_approval,
            confirm_msg,
            quotation,
            order_ride,
            completion_notify,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent executed the proposal and action correctly."""
        try:
            events = env.event_log.list_view()

            # Check that a cab order occurred
            ordered = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
                and "Cafe Aroma" in e.action.args["end_location"]
                for e in events
            )

            # Check that the agent sent a proposing message
            proposed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Cafe Aroma" in e.action.args["content"]
                and "Would you like me" in e.action.args["content"]
                for e in events
            )

            # Check that the agent confirmed the meetup in a message
            confirmed_conversation = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "MessagingApp"
                and e.action.function_name == "send_message"
                and "See you at Cafe Aroma" in e.action.args["content"]
                for e in events
            )

            success = ordered and proposed and confirmed_conversation
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
