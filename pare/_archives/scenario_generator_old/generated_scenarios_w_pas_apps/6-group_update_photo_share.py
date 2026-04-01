from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("group_update_photo_share")
class GroupUpdatePhotoShare(Scenario):
    """Agent observes project update message with attachment and proposes sharing it to a group chat.

    The user receives a photo update in a private conversation from teammate "Nina Green" related
    to the "Project Aurora". The agent proactively suggests forwarding this photo to the existing
    "Aurora Team" group conversation so the rest of the team can stay informed.

    The user approves, and the agent identifies the correct group, shares the message,
    updates the conversation title to include today's date, and confirms completion.

    This scenario uses environment-driven context from incoming messages, a proactive
    agent proposal, contextual acceptance, and then multiple meaningful oracle operations.
    """

    start_time = datetime(2025, 5, 12, 14, 30, 0, tzinfo=UTC).timestamp()
    status = "Draft"
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all apps and prepare base state."""
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")

        self.messaging.current_user_id = "user-001"
        self.messaging.current_user_name = "Alex Rivera"

        nina_lookup = self.messaging.lookup_user_id(user_name="Nina Green").oracle()
        self.nina_id = next(iter(nina_lookup.values()))

        tom_lookup = self.messaging.lookup_user_id(user_name="Tom Walker").oracle()
        self.tom_id = next(iter(tom_lookup.values()))

        self.aurora_team_id = self.messaging.create_group_conversation(
            user_ids=[self.nina_id, self.tom_id], title="Aurora Team"
        ).oracle()

        self.private_conv_id = self.messaging.create_group_conversation(
            user_ids=[self.nina_id], title="Chat with Nina"
        ).oracle()

        self.apps = [self.messaging, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow for sharing a photo update to a group chat."""
        messaging = self.get_typed_app(StatefulMessagingApp)
        aui = self.get_typed_app(PASAgentUserInterface)
        system = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            incoming_message_event = messaging.create_and_add_message(
                conversation_id=self.private_conv_id,
                sender_id=self.nina_id,
                content="Hey Alex, here's the prototype photo update for Project Aurora.",
            ).delayed(2)

            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "You just received a new photo from Nina Green about Project Aurora. "
                        "Would you like to share this update with your Aurora Team group chat?"
                    )
                )
                .oracle()
                .depends_on(incoming_message_event, delay_seconds=2)
            )

            approval_event = (
                aui.accept_proposal(content="Yes, please share Nina's photo update to the Aurora Team.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            open_app_event = system.open_app(app_name="Messaging").oracle().depends_on(approval_event, delay_seconds=1)

            # Agent verifies the Aurora Team group exists by search
            search_results = messaging.search(query="Aurora Team").oracle().depends_on(open_app_event, delay_seconds=1)

            # Use the search results to pick the right group conversation ID
            verify_group_event = (
                messaging.read_conversation(conversation_id=self.aurora_team_id, limit=3)
                .oracle()
                .depends_on(search_results, delay_seconds=1)
            )

            # Agent retrieves Nina's name from her ID to confirm sharing attribution
            nina_name_info = (
                messaging.get_user_name_from_id(user_id=self.nina_id)
                .oracle()
                .depends_on(verify_group_event, delay_seconds=1)
            )

            # Use Nina's name in the message content
            send_share_event = (
                messaging.send_message_to_group_conversation(
                    conversation_id=self.aurora_team_id,
                    content="Forwarded from Nina Green: here's the new prototype photo update for Project Aurora.",
                )
                .oracle()
                .depends_on(nina_name_info, delay_seconds=1)
            )

            # Get current time to update the conversation title
            current_time_info = system.get_current_time().oracle().depends_on(send_share_event, delay_seconds=1)

            rename_event = (
                messaging.change_conversation_title(
                    conversation_id=self.aurora_team_id,
                    title=f"Aurora Team Updates - {datetime.fromtimestamp(current_time_info['timestamp']).strftime('%b %d, %Y')}",
                )
                .oracle()
                .depends_on(current_time_info, delay_seconds=1)
            )

            confirmation_event = (
                aui.send_message_to_user(
                    content=("I've shared Nina's photo with the Aurora Team and updated the conversation title.")
                )
                .oracle()
                .depends_on(rename_event, delay_seconds=1)
            )

        self.events = [
            incoming_message_event,
            proposal_event,
            approval_event,
            open_app_event,
            search_results,
            verify_group_event,
            nina_name_info,
            send_share_event,
            current_time_info,
            rename_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the share, title change, and confirmation occurred."""
        try:
            logs = env.event_log.list_view()

            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Aurora" in e.action.args.get("content", "")
                and "Nina" in e.action.args.get("content", "")
                for e in logs
            )

            approval_found = any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "accept_proposal"
                and "Aurora Team" in e.action.args.get("content", "")
                for e in logs
            )

            group_share_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "Nina" in e.action.args.get("content", "")
                and "Aurora" in e.action.args.get("content", "")
                for e in logs
            )

            title_change_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "change_conversation_title"
                and "Aurora" in e.action.args.get("title", "")
                for e in logs
            )

            success = proposal_found and approval_found and group_share_found and title_change_found
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
