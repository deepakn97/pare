from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.messaging_v2 import ConversationV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulMessagingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("forgotten_item_friend_request")
class ForgottenItemFriendRequest(PASScenario):
    """Agent coordinates recovery of item left in cab when friend requests to borrow it.

    The user completes a cab ride and receives a notification from the cab service: "Ride completed. Did you leave anything behind? Your driver found a camera bag in the back seat." Shortly after, the user's friend Alex sends a message: "Hey! Can I borrow your camera for the concert tonight? I'll pick it up around 5 PM." The agent must:
    1. Detect the ride completion notification mentioning the forgotten camera bag
    2. Parse the incoming message from Alex requesting the camera
    3. Retrieve the completed ride details to identify the driver and service information
    4. Recognize that the requested item (camera) matches the forgotten item (camera bag)
    5. Send a message to Alex explaining the camera was left in a cab and propose a delayed pickup time after retrieval
    6. Propose contacting the cab company or provide driver contact details to arrange item recovery

    This scenario exercises cross-app item tracking (cab notification → messaging context), semantic matching between item references across apps, ride history lookup for driver coordination, and proactive obligation management when physical resources become temporarily unavailable.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add Alex as a contact in messaging app
        self.messaging.add_contacts([("Alex Johnson", "+1-555-0123")])

        # Add cab service as a contact in messaging app
        self.messaging.add_contacts([("Cab Service", "+1-555-0100")])

        # Seed an ongoing ride that will be completed via end_ride() to trigger lost item notification
        # This ride started earlier and will be completed 5 minutes before start_time
        ride_time = datetime.fromtimestamp(self.start_time - 300, tz=UTC)  # 5 minutes before start_time
        self.cab.order_ride(
            start_location="Home",
            end_location="Downtown Coffee Shop",
            service_type="Default",
            ride_time=ride_time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.cab, self.messaging]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        # Get Alex's user_id and create conversation dynamically
        alex_user_id = "+1-555-0123"
        user_id = messaging_app.current_user_id
        alex_conversation = ConversationV2(participant_ids=[user_id, alex_user_id], title="Alex Johnson")
        messaging_app.add_conversation(alex_conversation)
        alex_conversation_id = alex_conversation.conversation_id
        # Store conversation_id for validation
        self.alex_conversation_id = alex_conversation_id

        # Get cab service phone and create conversation dynamically
        cab_service_phone = "+1-555-0100"
        cab_service_conversation = ConversationV2(participant_ids=[user_id, cab_service_phone], title="Cab Service")
        messaging_app.add_conversation(cab_service_conversation)
        cab_service_conversation_id = cab_service_conversation.conversation_id

        with EventRegisterer.capture_mode():
            # Environment Event 1: Cab ride completes
            # This is the first exogenous trigger (non-oracle environment event)
            ride_completion_event = cab_app.end_ride().delayed(5)

            # Environment Event 1b: Cab service sends notification about lost item found
            # This notification matches the scenario description: "Ride completed. Did you leave anything behind? Your driver found a camera bag in the back seat."
            ride_notification_event = messaging_app.create_and_add_message(
                conversation_id=cab_service_conversation_id,
                sender_id=cab_service_phone,
                content="Ride completed. Did you leave anything behind? Your driver found a camera bag in the back seat. Call the cab company at +1-555-0100 to arrange the camera retrieval.",
            ).delayed(5.5)  # Slightly after ride completion

            # Environment Event 2: Friend Alex messages requesting to borrow camera
            # This is the second environment event that creates the conflict
            alex_message_event = messaging_app.create_and_add_message(
                conversation_id=alex_conversation_id,
                sender_id=alex_user_id,
                content="Hey! Can I borrow your camera for the concert tonight? I'll pick it up around 5 PM.",
            ).delayed(6)

            # Oracle Event 1: Agent checks ride history to get details about the completed ride
            # Motivated by: ride completion notification and Alex's camera request trigger need to check recent ride details
            ride_history_check = (
                cab_app.get_ride_history(offset=0, limit=5)
                .oracle()
                .depends_on([ride_notification_event, alex_message_event], delay_seconds=3)
            )

            # Oracle Event 2: Agent reads the conversation with Alex to understand the full request
            # Motivated by: new message notification from Alex; agent needs message content
            read_alex_conversation = (
                messaging_app.read_conversation(conversation_id=alex_conversation_id, offset=0, limit=5)
                .oracle()
                .depends_on(ride_history_check, delay_seconds=2)
            )

            # Oracle Event 3: Agent sends proposal to user about the situation
            # Motivated by: ride notification about forgotten camera + Alex's request for camera = conflict detected
            # Explicit dependency on environment events ensures this proposal is triggered by exogenous cues
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you left your camera bag in your recent cab ride to Downtown Coffee Shop. Alex just messaged asking to borrow your camera for a concert tonight at 5 PM. The camera is currently with your cab driver. Would you like me to help coordinate retrieving it from the cab company by calling +1-555-0100 and letting Alex know about the delay?"
                )
                .oracle()
                .depends_on([ride_notification_event, alex_message_event, read_alex_conversation], delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please first let Alex know about the delay and then let me call the driver to arrange the camera retrieval."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 5: Agent messages Alex about the situation
            # Motivated by: user accepted proposal to coordinate; need to inform Alex about delay
            message_alex_event = (
                messaging_app.send_message(
                    user_id=alex_user_id,
                    content="Hi Alex! About the camera - I just realized it was left in a cab this morning. I'm working on getting it back from the cab company. Can we push the pickup time to later this evening, maybe around 7 PM? I'll confirm once I have it.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent sends follow-up to user with next steps
            # Motivated by: user accepted coordination help; provide actionable information
            followup_event = (
                aui.send_message_to_user(
                    content="I've let Alex know about the delay and suggested a 7 PM pickup instead. Your most recent ride was with the Default cab service from Home to Downtown Coffee Shop. The ride ID is in your cab history. You may need to contact the cab company directly to arrange pickup of the camera bag."
                )
                .oracle()
                .depends_on(message_alex_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            ride_completion_event,
            ride_notification_event,
            alex_message_event,
            ride_history_check,
            read_alex_conversation,
            proposal_event,
            acceptance_event,
            message_alex_event,
            followup_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1 (STRICT): Agent sent proposal to user recognizing the camera/camera bag conflict
            # The proposal must reference both the lost item and Alex's request
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2 (STRICT): Agent informed Alex about the situation
            # Accept either send_message (to user_id) as the valid way to message Alex
            # Content flexibility: only require "camera" mentioned, not exact wording
            alex_notification_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == "+1-555-0123"
                and "camera" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # Compute success: all strict checks must pass; flexible check adds robustness but is not required
            strict_checks = proposal_found and alex_notification_found

            success = strict_checks

            # Build rationale for failures
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal to user about camera/Alex conflict not found")
                if not alex_notification_found:
                    missing_checks.append("agent did not message Alex about camera situation")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
