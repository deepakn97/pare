"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.cab import StatefulCabApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("emergency_ride_for_stranded_friend")
class EmergencyRideForStrandedFriend(PASScenario):
    """Agent books emergency cab ride for stranded friend based on urgent message request.

    The user's friend Sarah sends an urgent message: "My car broke down on Highway 101 near the Cedar Street exit. Can you help? I need to get to the hospital for my shift in 30 minutes." The user replies "I'll get you a cab right away!" The agent must: 1. Parse Sarah's location (Highway 101 near Cedar Street exit) and destination (hospital) from the conversation. 2. Search for available rides matching the urgent timeline (within 30 minutes). 3. Identify the fastest service type that can arrive quickly enough. 4. Book the ride with Sarah as the passenger (if supported) or coordinate pickup details. 5. Send a confirmation message to Sarah with the ride details, driver info, and estimated arrival time. 6. Monitor the ride status and notify Sarah when the driver is approaching.

    This scenario exercises emergency context detection from messaging tone and content, location extraction from informal descriptions, time-sensitive ride booking with deadline constraints, cross-app coordination (messaging → cab service → messaging), and proactive status monitoring for third-party rides booked on behalf of others..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app with user and contacts
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.current_user_id = "user_001"
        self.messaging.current_user_name = "Me"

        # Add Sarah as a contact with phone number
        self.messaging.add_contacts([("Sarah Johnson", "+1-555-0101")])

        # Seed a baseline conversation with Sarah from earlier this morning
        # This shows prior friendly chat history before the emergency
        sarah_id = self.messaging.name_to_id["Sarah Johnson"]
        earlier_conversation = ConversationV2(
            participant_ids=[self.messaging.current_user_id, sarah_id],
            title="Sarah Johnson",
            messages=[
                MessageV2(
                    sender_id=sarah_id,
                    content="Good morning! How are you today?",
                    timestamp=self.start_time - 7200,  # 2 hours before scenario start
                ),
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Morning Sarah! Doing well, you?",
                    timestamp=self.start_time - 7100,
                ),
            ],
        )
        self.messaging.add_conversation(earlier_conversation)

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        # Get Sarah's ID for message events
        sarah_id = messaging_app.name_to_id["Sarah Johnson"]

        # Get the existing conversation ID with Sarah
        conv_ids = messaging_app.get_existing_conversation_ids([sarah_id])
        sarah_conversation_id = conv_ids[0]

        with EventRegisterer.capture_mode():
            # Environment Event 1: Sarah sends urgent message about car breakdown
            message1_event = messaging_app.create_and_add_message(
                conversation_id=sarah_conversation_id,
                sender_id=sarah_id,
                content="My car broke down on Highway 101 near the Cedar Street exit. Can you help? I need to get to the hospital for my shift in 30 minutes.",
            )

            # Environment Event 2: User replies agreeing to help
            message2_event = messaging_app.create_and_add_message(
                conversation_id=sarah_conversation_id,
                sender_id=messaging_app.current_user_id,
                content="I'll get you a cab right away!",
            ).delayed(3)

            # Oracle Event 1: Agent reads the conversation to understand the emergency
            # Motivation: The agent received environment notifications (messages 1 & 2) and needs to read the full context
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id=sarah_conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(message2_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent sends proposal to user about booking a cab for Sarah
            # Motivation: Based on reading Sarah's urgent message about being stranded and needing hospital transport
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw Sarah's urgent message about her car breaking down near Highway 101/Cedar Street exit. She needs to get to the hospital in 30 minutes. Should I book a cab for her pickup at that location?"
                )
                .oracle()
                .depends_on(read_conversation_event, delay_seconds=2)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please book the fastest ride for Sarah!")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent lists available rides from pickup to hospital
            # Motivation: User accepted the proposal; agent needs to find available rides for the route
            list_rides_event = (
                cab_app.list_rides(
                    start_location="Highway 101 near Cedar Street exit",
                    end_location="Hospital",
                    ride_time=None,
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent orders the fastest ride (Premium service with shortest delay)
            # Motivation: After listing rides, agent selects Premium service which has the fastest base_delay_min (3 mins)
            order_ride_event = (
                cab_app.order_ride(
                    start_location="Highway 101 near Cedar Street exit",
                    end_location="Hospital",
                    service_type="Premium",
                    ride_time=None,
                )
                .oracle()
                .depends_on(list_rides_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent sends confirmation message to Sarah with ride details
            # Motivation: After successfully booking the ride, agent informs Sarah about the incoming cab
            send_message_event = (
                messaging_app.send_message(
                    user_id=sarah_id,
                    content="I've booked a Premium cab for you! It should arrive at your location on Highway 101 near Cedar Street exit in a few minutes and will take you to the hospital.",
                )
                .oracle()
                .depends_on(order_ride_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            message1_event,
            message2_event,
            read_conversation_event,
            proposal_event,
            acceptance_event,
            list_rides_event,
            order_ride_event,
            send_message_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent events, as per validation requirements
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent read the conversation to understand Sarah's emergency
            # The agent must read the conversation to gather context about the emergency
            read_conversation_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                for e in agent_events
            )

            # STRICT Check 2: Agent proposed booking a cab for Sarah
            # The agent must offer to help with the emergency ride booking.
            # Content is flexible - we just verify the proposal was made.
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 3: Agent listed available rides
            # The agent must search for available rides to determine options
            list_rides_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "list_rides"
                for e in agent_events
            )

            # STRICT Check 4: Agent ordered a ride
            # The agent must complete the ride booking
            order_ride_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                for e in agent_events
            )

            # STRICT Check 5: Agent informed Sarah about the booked ride
            # The agent must notify Sarah with confirmation.
            # This can be achieved via send_message or potentially other message-sending methods.
            # We accept multiple valid methods for notifying Sarah.
            sarah_id = self.messaging.name_to_id["Sarah Johnson"]

            inform_sarah_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["send_message", "create_and_add_message"]
                and e.action.args.get("user_id") == sarah_id
                for e in agent_events
            )

            # All strict checks must pass
            success = (
                read_conversation_found
                and proposal_found
                and list_rides_found
                and order_ride_found
                and inform_sarah_found
            )

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not read_conversation_found:
                    missing_checks.append("agent did not read conversation")
                if not proposal_found:
                    missing_checks.append("agent did not propose help to user")
                if not list_rides_found:
                    missing_checks.append("agent did not list available rides")
                if not order_ride_found:
                    missing_checks.append("agent did not order ride")
                if not inform_sarah_found:
                    missing_checks.append("agent did not inform Sarah about the ride")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
