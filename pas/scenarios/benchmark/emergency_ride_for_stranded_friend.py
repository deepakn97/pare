"""Scenario for booking emergency cab ride for stranded friend."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
    """Agent books emergency cab ride for stranded friend whose phone is dying.

    Story:
    1. User has an existing conversation with friend Sarah Johnson
    2. Sarah sends urgent message: car broke down, phone at 3%, no cab app, needs ride to hospital
    3. User replies agreeing to help
    4. Agent detects the emergency, proposes booking a cab for Sarah
    5. User accepts
    6. Agent books the fastest available cab and sends Sarah the ride details quickly
       (before her phone dies)

    This scenario exercises emergency context detection, location extraction from messages,
    time-sensitive ride booking, and cross-app coordination (messaging -> cab -> messaging).
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """Your friend Sarah is stranded and needs a cab urgently. Her phone is dying.

ACCEPT proposals that:
- Show you quotation details (price, estimated arrival time, service type) for at least one cab option
- Give you enough information to make an informed decision about which service to book

REJECT proposals that:
- Simply ask "should I book a cab?" without showing quotation/pricing details
- Don't provide specific ride options with costs and timing

If the agent asks without showing quotation details, reject and ask them to get a quotation first so you can see the price and timing options."""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add Sarah as a contact
        self.messaging.add_contacts([("Sarah Johnson", "+1-555-0101")])
        self.sarah_id = self.messaging.name_to_id["Sarah Johnson"]

        # Create baseline conversation with Sarah from earlier this morning
        # User sends first message to create the conversation
        self.sarah_conv_id = self.messaging.send_message(
            user_id=self.sarah_id,
            content="Hey Sarah! Are we still on for lunch this week?",
        )

        # Add Sarah's reply with earlier timestamp so conversation flows naturally
        self.messaging.add_message(
            conversation_id=self.sarah_conv_id,
            sender_id=self.sarah_id,
            content="Yes! Let's do Thursday. I'll text you the place.",
            timestamp=self.start_time - 7000,
        )

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow for emergency ride booking scenario."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # ENV: Sarah sends urgent message - car broke down, phone dying, needs cab
            message1_event = messaging_app.create_and_add_message(
                conversation_id=self.sarah_conv_id,
                sender_id=self.sarah_id,
                content=(
                    "HELP! My car broke down on Highway 101 near Cedar Street exit. "
                    "Phone at 3% and I don't have the cab app! Can you order me a ride to "
                    "the hospital? I have a shift in 30 minutes. Send details quick before my phone dies!"
                ),
            )

            # Oracle: Agent reads the conversation to understand the emergency
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id=self.sarah_conv_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(message1_event, delay_seconds=2)
            )

            # Oracle: Agent gets quotation for available rides
            get_quotation_event = (
                cab_app.list_rides(
                    start_location="Highway 101 near Cedar Street exit",
                    end_location="Hospital",
                    ride_time=None,
                )
                .oracle()
                .depends_on(read_conversation_event, delay_seconds=2)
            )

            # Oracle: Agent proposes booking with quotation details
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "Sarah's phone is dying and she's stranded on Highway 101 near Cedar Street exit. "
                        "She needs to get to the hospital for her shift. I found these cab options:\n\n"
                        "- Premium: $25, arrives in ~3 min (fastest)\n"
                        "- Standard: $18, arrives in ~8 min\n"
                        "- Economy: $12, arrives in ~12 min\n\n"
                        "Given the urgency (her phone is dying), I recommend Premium. Should I book it?"
                    )
                )
                .oracle()
                .depends_on(get_quotation_event, delay_seconds=2)
            )

            # Oracle: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, book the Premium cab!")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle: Agent orders Premium cab (fastest service)
            order_ride_event = (
                cab_app.order_ride(
                    start_location="Highway 101 near Cedar Street exit",
                    end_location="Hospital",
                    service_type="Premium",
                    ride_time=None,
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle: Agent sends Sarah the ride details quickly before her phone dies
            send_message_event = (
                messaging_app.send_message(
                    user_id=self.sarah_id,
                    content=(
                        "BOOKED! Premium cab arriving at Highway 101/Cedar Street exit in ~5 min. "
                        "Look for a black sedan. It will take you straight to the hospital. Good luck!"
                    ),
                )
                .oracle()
                .depends_on(order_ride_event, delay_seconds=2)
            )

        self.events = [
            message1_event,
            read_conversation_event,
            get_quotation_event,
            proposal_event,
            acceptance_event,
            order_ride_event,
            send_message_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent booked cab and informed Sarah.

        Essential outcomes checked:
        1. Agent sent proposal to user before taking action
        2. Agent ordered a ride for Sarah
        3. Agent sent Sarah the ride details
        """
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Agent proposed booking a cab for Sarah
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check 2: Agent ordered a ride
            order_ride_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                for e in agent_events
            )

            # Check 3: Agent informed Sarah about the booked ride
            inform_sarah_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.sarah_id
                for e in agent_events
            )

            success = proposal_found and order_ride_found and inform_sarah_found

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user about booking cab")
                if not order_ride_found:
                    missing.append("cab ride order")
                if not inform_sarah_found:
                    missing.append("ride details sent to Sarah")
                return ScenarioValidationResult(
                    success=False,
                    rationale=f"Missing required actions: {', '.join(missing)}",
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
