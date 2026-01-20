from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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


@register_scenario("ride_status_sharing_with_friend")
class RideStatusSharingWithFriend(PASScenario):
    """Agent monitors delayed ride status and proactively notifies waiting friend with updated arrival time.

    The user has ordered a ride to meet their friend Sarah at a restaurant. The user previously sent Sarah a message saying "I'll be there around 7:00 PM." After the ride is confirmed, the cab company sends a notification that the driver is running 15 minutes late due to traffic. The agent must:
    1. Detect the ride delay notification from the cab app
    2. Retrieve the current ride status to confirm the new estimated arrival time
    3. Identify the relevant prior conversation where the user committed to meeting Sarah
    4. Calculate the updated arrival time based on the delay
    5. Propose sending an update message to Sarah with the revised ETA
    6. Send the update message to Sarah after user acceptance

    This scenario exercises ride-tracking awareness, cross-app coordination (cab → messaging), time-sensitive communication inference, and social obligation management when plans are affected by external delays.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add Sarah as a contact in messaging
        sarah_name = "Sarah"
        self.messaging.add_users([sarah_name])
        sarah_id = self.messaging.name_to_id[sarah_name]

        # Create baseline conversation with Sarah containing user's commitment to meet at 7 PM
        # This conversation happened earlier in the day
        baseline_timestamp = self.start_time - 3600  # 1 hour before start_time
        sarah_conversation = ConversationV2(
            participant_ids=[self.messaging.current_user_id, sarah_id],
            title=sarah_name,
        )

        # Add earlier messages establishing the dinner plan
        sarah_conversation.messages.append(
            MessageV2(
                sender_id=sarah_id,
                content="Hey! Still on for dinner tonight at Bella's Restaurant?",
                timestamp=baseline_timestamp - 1800,  # 30 min before baseline
            )
        )
        sarah_conversation.messages.append(
            MessageV2(
                sender_id=self.messaging.current_user_id,
                content="Yes! I'll be there around 7:00 PM.",
                timestamp=baseline_timestamp - 900,  # 15 min before baseline
            )
        )
        sarah_conversation.messages.append(
            MessageV2(
                sender_id=sarah_id,
                content="Great! See you then.",
                timestamp=baseline_timestamp,
            )
        )

        sarah_conversation.update_last_updated(baseline_timestamp)
        self.messaging.add_conversation(sarah_conversation)

        # Store conversation_id for use in build_events_flow
        self.sarah_conversation_id = sarah_conversation.conversation_id

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        # Get Sarah's participant ID and conversation ID from stored instance variables
        sarah_id = messaging_app.name_to_id["Sarah"]
        sarah_conversation_id = self.sarah_conversation_id

        with EventRegisterer.capture_mode():
            # Environment Event 1: User orders a ride to restaurant
            # This creates the ride that will later be delayed
            order_event = cab_app.order_ride(
                start_location="User Home",
                end_location="Bella's Restaurant",
                service_type="Default",
                ride_time=None,
            ).delayed(1)

            # Environment Event 2: Cab company sends delay notification - driver running 15 minutes late
            # This is the trigger that should prompt the agent to notify Sarah
            delay_event = cab_app.update_ride_status(
                status="DELAYED",
                message="Your driver is running 15 minutes late due to heavy traffic. Updated arrival time: 7:15 PM.",
            ).delayed(10)

            # Agent retrieves current ride status to confirm delay details
            # Motivated by: the delay notification above prompted agent to check ride details
            status_check_event = cab_app.get_current_ride_status().oracle().depends_on([delay_event], delay_seconds=2)

            # Agent reads recent conversations to identify who was expecting the user
            # Motivated by: agent needs to find the relevant conversation where user committed to meeting someone
            conversation_search_event = (
                messaging_app.list_recent_conversations(offset=0, limit=5)
                .oracle()
                .depends_on([status_check_event], delay_seconds=1)
            )

            # Agent opens the conversation with Sarah to confirm the commitment
            # Motivated by: conversation list revealed Sarah conversation; agent needs to read the actual commitment message
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id=sarah_conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on([conversation_search_event], delay_seconds=1)
            )

            # Agent proposes sending update to Sarah about the delay
            # Motivated by: agent confirmed ride delay (15 min) and user's commitment to Sarah ("I'll be there around 7:00 PM")
            proposal_event = (
                aui.send_message_to_user(
                    content="Your ride to Bella's Restaurant is delayed by 15 minutes due to traffic. You told Sarah you'd arrive around 7:00 PM, but you'll now arrive closer to 7:15 PM. Would you like me to send her an update?"
                )
                .oracle()
                .depends_on([read_conversation_event], delay_seconds=2)
            )

            # User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please let her know.")
                .oracle()
                .depends_on([proposal_event], delay_seconds=2)
            )

            # Agent sends update message to Sarah
            # Motivated by: user accepted the proposal to notify Sarah of the delay
            notification_event = (
                messaging_app.send_message(
                    user_id=sarah_id,
                    content="Hi Sarah, just a heads up - my ride is running a bit late due to traffic. I'll be there around 7:15 PM instead of 7:00 PM. See you soon!",
                )
                .oracle()
                .depends_on([acceptance_event], delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            order_event,
            delay_event,
            status_check_event,
            conversation_search_event,
            read_conversation_event,
            proposal_event,
            acceptance_event,
            notification_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent checked ride status to confirm delay details (STRICT)
            status_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_current_ride_status"
                for e in log_entries
            )

            # Check 2: Agent searched for relevant conversations (STRICT)
            conversation_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "list_recent_conversations"
                for e in log_entries
            )

            # Check 3: Agent read Sarah's conversation to confirm commitment (STRICT)
            sarah_id = self.messaging.name_to_id.get("Sarah")

            read_conversation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["open_conversation", "read_conversation"]
                for e in log_entries
            )

            # Check 4: Agent sent proposal to user (FLEXIBLE on content, STRICT on presence)
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 5: Agent sent update message to Sarah (STRICT on app/function, FLEXIBLE on content)
            notification_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["send_message_to_group_conversation", "send_message"]
                for e in log_entries
            )

            success = (
                status_check_found
                and conversation_search_found
                and read_conversation_found
                and proposal_found
                and notification_sent
            )

            if not success:
                rationale_parts = []
                if not status_check_found:
                    rationale_parts.append("ride status check not found")
                if not conversation_search_found:
                    rationale_parts.append("conversation search not found")
                if not read_conversation_found:
                    rationale_parts.append("Sarah's conversation not read")
                if not proposal_found:
                    rationale_parts.append("proposal to user not found")
                if not notification_sent:
                    rationale_parts.append("notification to Sarah not sent")
                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
