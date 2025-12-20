"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2
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


@register_scenario("adjust_ride_for_late_friends")
class AdjustRideForLateFriends(PASScenario):
    """Agent cancels and rebooks a cab ride when friends message about running late to a shared destination. The user has ordered a cab to a concert venue scheduled to pick them up at 6:00 PM. Two friends (Alex and Jordan) in a group message thread inform the user they are running 30 minutes late due to traffic delays, and suggest the user arrive at 6:45 PM instead to avoid waiting alone at the venue. The agent must: 1. Parse the group messages to identify the delayed arrival time (6:45 PM). 2. Retrieve the user's current ride order and verify the originally scheduled pickup time (6:00 PM). 3. Recognize the mismatch between the user's cab and the group's adjusted arrival. 4. Cancel the existing 6:00 PM ride. 5. Book a new ride with a 6:30 PM pickup time that aligns with the friends' 6:45 PM arrival. 6. Send a confirmation message to the group chat confirming the adjusted arrival time.

    This scenario exercises cross-app coordination (messaging → cab ride management), temporal reasoning to calculate appropriate ride timing based on social context, transactional ride cancellation and rebooking workflows, and group messaging acknowledgment to close the coordination loop..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")
        # Set up current user
        self.messaging.current_user_id = "user_main_id"
        self.messaging.current_user_name = "Me"

        # Add friends as contacts in messaging
        self.messaging.add_users(["Alex Chen", "Jordan Smith"])

        # Create the group conversation with Alex and Jordan
        alex_id = self.messaging.name_to_id["Alex Chen"]
        jordan_id = self.messaging.name_to_id["Jordan Smith"]

        group_convo = ConversationV2(
            participant_ids=[self.messaging.current_user_id, alex_id, jordan_id],
            title="Alex Chen, Jordan Smith",
            messages=[],
        )
        self.messaging.add_conversation(group_convo)

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

        # Get user IDs for friends
        alex_id = messaging_app.name_to_id["Alex Chen"]
        jordan_id = messaging_app.name_to_id["Jordan Smith"]

        # Get the group conversation ID
        group_convo_id = next(iter(messaging_app.conversations.keys()))

        with EventRegisterer.capture_mode():
            # Environment Event 1: User books initial cab ride for 6:00 PM (pickup time: 2025-11-18 18:00:00)
            initial_ride_event = cab_app.order_ride(
                start_location="123 Main Street",
                end_location="Downtown Concert Hall",
                service_type="Default",
                ride_time="2025-11-18 18:00:00",
            ).delayed(10)

            # Environment Event 2: Alex messages the group about running late
            alex_message_event = messaging_app.create_and_add_message(
                conversation_id=group_convo_id,
                sender_id=alex_id,
                content="Hey everyone! Bad news - stuck in traffic on Highway 101. Looks like we're going to be about 30 minutes late. Probably won't get to the venue until around 6:45 PM.",
            ).delayed(15)

            # Environment Event 3: Jordan confirms they're also delayed
            jordan_message_event = messaging_app.create_and_add_message(
                conversation_id=group_convo_id,
                sender_id=jordan_id,
                content="Same here, traffic is crazy. Yeah, 6:45 sounds about right for us. Sorry for the delay!",
            ).delayed(5)

            # Oracle Event 1: Agent checks current ride status to understand existing booking
            check_ride_event = (
                cab_app.get_current_ride_status().oracle().depends_on(jordan_message_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent proposes to adjust the ride timing
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Alex and Jordan are running late and will arrive at the concert venue around 6:45 PM. Your cab is currently scheduled for 6:00 PM pickup. Would you like me to cancel the current ride and book a new one for 6:30 PM so you arrive closer to when they do?"
                )
                .oracle()
                .depends_on(check_ride_event, delay_seconds=2)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, that makes sense. Please reschedule the ride.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 4: Agent cancels the current ride
            cancel_ride_event = cab_app.user_cancel_ride().oracle().depends_on(acceptance_event, delay_seconds=1)

            # Oracle Event 5: Agent books new ride for 6:30 PM
            rebook_ride_event = (
                cab_app.order_ride(
                    start_location="123 Main Street",
                    end_location="Downtown Concert Hall",
                    service_type="Default",
                    ride_time="2025-11-18 18:30:00",
                )
                .oracle()
                .depends_on(cancel_ride_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent sends confirmation to the group chat
            confirmation_message_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=group_convo_id,
                    content="No worries! I've rescheduled my ride for 6:30 PM so I'll arrive around the same time as you both.",
                )
                .oracle()
                .depends_on(rebook_ride_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            initial_ride_event,
            alex_message_event,
            jordan_message_event,
            check_ride_event,
            proposal_event,
            acceptance_event,
            cancel_ride_event,
            rebook_ride_event,
            confirmation_message_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent checked the current ride status
            ride_status_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_current_ride_status"
                for e in log_entries
            )

            # Check Step 2: Agent sent proposal mentioning ride rescheduling and friends' delay
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and len(e.action.args.get("content", "")) > 0
                for e in log_entries
            )

            # Check Step 3: Agent cancelled the existing ride
            cancel_ride_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "user_cancel_ride"
                for e in log_entries
            )

            # Check Step 4: Agent booked a new ride with adjusted time (STRICT: must be 6:30 PM)
            rebook_ride_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and e.action.args.get("ride_time") == "2025-11-18 18:30:00"
                and e.action.args.get("start_location") == "123 Main Street"
                and e.action.args.get("end_location") == "Downtown Concert Hall"
                for e in log_entries
            )

            # Check Step 5: Agent sent confirmation message to group chat (FLEXIBLE on content)
            confirmation_message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and len(e.action.args.get("content", "")) > 0
                for e in log_entries
            )

            success = (
                ride_status_check_found
                and proposal_found
                and cancel_ride_found
                and rebook_ride_found
                and confirmation_message_found
            )

            if not success:
                missing_checks = []
                if not ride_status_check_found:
                    missing_checks.append("ride status check")
                if not proposal_found:
                    missing_checks.append("agent proposal")
                if not cancel_ride_found:
                    missing_checks.append("ride cancellation")
                if not rebook_ride_found:
                    missing_checks.append("ride rebooking with 6:30 PM time")
                if not confirmation_message_found:
                    missing_checks.append("group chat confirmation")

                rationale = f"Missing validation checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
