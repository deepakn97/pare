"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.cab import StatefulCabApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("group_ride_coordination_split_payment")
class GroupRideCoordinationSplitPayment(PASScenario):
    """Agent coordinates shared ride booking and payment splitting based on group messaging discussion.

    The user is in a group conversation with friends Alice and Bob planning to attend a concert together. Alice sends a message proposing they share a ride from downtown to the venue at 6:30 PM, and Bob agrees. The user confirms participation. Later, Bob sends another message asking how they'll split the ride cost. The agent must:
    1. Detect the group conversation establishing shared ride intent with specific pickup location and time
    2. Identify all participants who agreed to share the ride (3 people total)
    3. Search for available rides matching the discussed route and time
    4. Calculate per-person cost for the selected ride option
    5. Propose booking the ride with cost breakdown showing the split amount
    6. After user acceptance, order the ride

    This scenario exercises multi-participant coordination inference from messaging, ride service integration with pricing calculations, cost-splitting logic for group expenses, and group communication about shared logistics..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Set current user details
        self.messaging.current_user_id = "user_001"
        self.messaging.current_user_name = "Me"

        # Add friends Alice and Bob
        self.messaging.add_users(["Alice", "Bob"])

        # Get user IDs for Alice and Bob
        alice_id = self.messaging.name_to_id["Alice"]
        bob_id = self.messaging.name_to_id["Bob"]

        # Create a group conversation about the concert
        concert_conversation = ConversationV2(
            participant_ids=[self.messaging.current_user_id, alice_id, bob_id],
            title="Alice, Bob",
            messages=[
                MessageV2(
                    sender_id=alice_id,
                    content="Hey guys! Are we still on for the concert tonight?",
                    timestamp=self.start_time - 3600,  # 1 hour before start_time
                ),
                MessageV2(
                    sender_id=bob_id,
                    content="Yes! Can't wait!",
                    timestamp=self.start_time - 3500,
                ),
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Absolutely! See you there!",
                    timestamp=self.start_time - 3400,
                ),
            ],
        )

        # Add the conversation to the messaging app
        self.messaging.add_conversation(concert_conversation)

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        # Get user IDs for Alice and Bob
        alice_id = messaging_app.name_to_id["Alice"]
        bob_id = messaging_app.name_to_id["Bob"]

        # Get the conversation ID
        conv_ids = messaging_app.get_existing_conversation_ids([alice_id, bob_id])
        concert_conversation_id = conv_ids[0]

        with EventRegisterer.capture_mode():
            # Environment event 1: Alice proposes shared ride with specific pickup location and time
            e1 = messaging_app.create_and_add_message(
                conversation_id=concert_conversation_id,
                sender_id=alice_id,
                content="I was thinking we could all share a ride to the venue! How about we meet downtown at 6:30 PM?",
            ).delayed(10)

            # Environment event 2: Bob agrees to the ride plan
            e2 = messaging_app.create_and_add_message(
                conversation_id=concert_conversation_id,
                sender_id=bob_id,
                content="Great idea! Downtown at 6:30 works for me.",
            ).delayed(15)

            # Environment event 3: User confirms participation
            e3 = messaging_app.create_and_add_message(
                conversation_id=concert_conversation_id,
                sender_id=messaging_app.current_user_id,
                content="Count me in! Downtown at 6:30.",
            ).delayed(20)

            # Environment event 4: Bob asks about cost splitting
            e4 = messaging_app.create_and_add_message(
                conversation_id=concert_conversation_id,
                sender_id=bob_id,
                content="By the way, how should we split the ride cost?",
            ).delayed(30)

            # Environment event 5: Bob explicitly asks the user to check ride options + per-person cost and book if OK
            # This grounds the agent's decision to fetch ride pricing and compute a split (not just assumed helpfulness).
            e5 = messaging_app.create_and_add_message(
                conversation_id=concert_conversation_id,
                sender_id=bob_id,
                content=(
                    "Can you check a couple ride options and tell us the total + per-person split for the three of us? "
                    "If it's reasonable, go ahead and book it."
                ),
            ).depends_on(e4, delay_seconds=2)

            # Agent action 1: Agent reads the conversation to understand the ride plan
            # Evidence: the conversation contains messages establishing shared ride intent
            e6 = (
                messaging_app.read_conversation(
                    conversation_id=concert_conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on([e5], delay_seconds=5)
            )

            # Agent action 2: Agent lists available rides matching the discussed route and time
            # Evidence: conversation mentions "downtown" as pickup and "venue" as destination at "6:30 PM";
            # Bob explicitly asked to check ride options and compute a per-person split.
            e7 = (
                cab_app.list_rides(
                    start_location="Downtown",
                    end_location="Concert Venue",
                    ride_time="2025-11-18 18:30:00",
                )
                .oracle()
                .depends_on([e6], delay_seconds=3)
            )

            # Agent action 3: Agent sends proposal with ride option and per-person cost breakdown
            # Evidence: Bob explicitly asked for total + split and whether to book; list_rides revealed pricing.
            e8 = (
                aui.send_message_to_user(
                    content="In the group chat, Bob asked you to check ride options and compute the per-person split (and book if it's reasonable). I found a Default ride from Downtown to the Concert Venue at 6:30 PM for $15.00 total — that's $5.00 per person for the three of you. Would you like me to book it?",
                )
                .oracle()
                .depends_on([e7], delay_seconds=5)
            )

            # User action: User accepts the proposal
            e9 = (
                aui.accept_proposal(
                    content="Yes, please book it!",
                )
                .oracle()
                .depends_on([e8], delay_seconds=10)
            )

            # Agent action 4: Agent orders the ride
            # Evidence: user accepted the proposal to book the ride
            e10 = (
                cab_app.order_ride(
                    start_location="Downtown",
                    end_location="Concert Venue",
                    service_type="Default",
                    ride_time="2025-11-18 18:30:00",
                )
                .oracle()
                .depends_on([e9], delay_seconds=3)
            )

        # Register ALL events here in self.events
        self.events = [e1, e2, e3, e4, e5, e6, e7, e8, e9, e10]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent events
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1 (STRICT): Agent read the conversation
            read_conversation_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulMessagingApp" and e.action.function_name == "read_conversation":
                    read_conversation_found = True
                    break

            # Check 2 (STRICT): Agent listed rides with correct parameters
            list_rides_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulCabApp" and e.action.function_name in [
                    "list_rides",
                    "get_quotation",
                ]:
                    args = e.action.args
                    # Verify key arguments are present (flexible on exact values)
                    if (
                        "start_location" in args
                        and args["start_location"]
                        and "end_location" in args
                        and args["end_location"]
                        and "ride_time" in args
                        and args["ride_time"]
                    ):
                        list_rides_found = True
                        break

            # Check 3 (STRICT on structure, FLEXIBLE on content): Agent sent proposal to user
            proposal_found = False
            for e in agent_events:
                if e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user":
                    # Just check that the proposal was sent, don't validate exact content
                    proposal_found = True
                    break

            # Check 4 (STRICT): Agent ordered the ride with correct parameters
            order_ride_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulCabApp" and e.action.function_name == "order_ride":
                    args = e.action.args
                    # Verify key arguments are present
                    if (
                        "start_location" in args
                        and args["start_location"]
                        and "end_location" in args
                        and args["end_location"]
                        and "ride_time" in args
                        and args["ride_time"]
                    ):
                        order_ride_found = True
                        break

            # Determine success and build rationale
            success = read_conversation_found and list_rides_found and proposal_found and order_ride_found

            rationale = None
            if not success:
                missing = []
                if not read_conversation_found:
                    missing.append("agent did not read the conversation")
                if not list_rides_found:
                    missing.append("agent did not list rides with required parameters")
                if not proposal_found:
                    missing.append("agent did not send proposal to user")
                if not order_ride_found:
                    missing.append("agent did not order ride with required parameters")
                rationale = "; ".join(missing)

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
