from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("message_summary_share_request")
class MessageSummaryShareRequest(Scenario):
    """Agent detects multiple unread messages from a team chat, proposes to summarize and share with another teammate.

    Demonstrates proactive assistance through the agent UI and use of HomeScreenSystemApp for navigation context.
    """

    start_time = datetime(2025, 11, 20, 10, 0, 0, tzinfo=UTC).timestamp()
    status = "Draft"
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize messaging and system apps with a baseline conversation."""
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")

        # Set current user
        self.messaging.current_user_id = "user_self"
        self.messaging.current_user_name = "Jordan Lee"

        # Retrieve user IDs using oracles (they are needed for later messaging actions)
        self.riley_id = self.messaging.get_user_id(user_name="Riley Park").oracle()
        self.sam_id = self.messaging.get_user_id(user_name="Sam Patel").oracle()
        self.logan_id = self.messaging.get_user_id(user_name="Logan White").oracle()

        # Create internal chat group with Riley and Sam
        self.team_chat_id = self.messaging.create_group_conversation(
            user_ids=[self.riley_id, self.sam_id],
            title="Project Alpha Discussion",
        ).oracle()

        self.apps = [self.messaging, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow demonstrating proactive summarization and share proposal."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging = self.get_typed_app(StatefulMessagingApp)
        system_app = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            # Incoming messages while user is away
            msg_evt1 = messaging.create_and_add_message(
                conversation_id=self.team_chat_id,
                sender_id=self.riley_id,
                content="I've uploaded the final design draft to the drive. Please review the layout by EOD.",
            ).delayed(1)

            msg_evt2 = messaging.create_and_add_message(
                conversation_id=self.team_chat_id,
                sender_id=self.sam_id,
                content="Also, we need to confirm the client presentation slides for next Monday's review.",
            ).delayed(2)

            msg_evt3 = messaging.create_and_add_message(
                conversation_id=self.team_chat_id,
                sender_id=self.sam_id,
                content="Do we have the latest KPIs for the marketing report? I can compile them if someone sends them.",
            ).delayed(3)

            # Agent observes unread accumulation
            unread_check = aui.get_last_unread_messages().oracle().depends_on(msg_evt3, delay_seconds=2)

            # Agent proposes proactive summarization
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "You have several unread messages in the 'Project Alpha Discussion' chat from Riley and Sam. "
                        "Would you like me to summarize the key points and share the summary with Logan White?"
                    )
                )
                .oracle()
                .depends_on(unread_check, delay_seconds=2)
            )

            # User accepts proposal
            approval_event = (
                aui.accept_proposal(content="Yes, please prepare the summary and share it with Logan.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Agent verifies existing conversations including Logan
            existing_convs = (
                messaging.get_existing_conversation_ids(user_ids=[self.riley_id, self.sam_id, self.logan_id])
                .oracle()
                .depends_on(approval_event, delay_seconds=1)
            )

            # Read conversation for summary preparation
            read_conv_event = (
                messaging.read_conversation(conversation_id=self.team_chat_id, limit=5)
                .oracle()
                .depends_on(existing_convs, delay_seconds=1)
            )

            # Create a new conversation for sharing summary with Logan
            create_share_conv = (
                messaging.create_group_conversation(
                    user_ids=[self.logan_id],
                    title="Alpha Chat Summary with Logan",
                )
                .oracle()
                .depends_on(read_conv_event, delay_seconds=1)
            )

            # Add Riley for visibility
            add_riley_event = (
                messaging.add_participant_to_conversation(conversation_id=create_share_conv, user_id=self.riley_id)
                .oracle()
                .depends_on(create_share_conv, delay_seconds=1)
            )

            # Rename the conversation to reflect all members
            rename_conv_event = (
                messaging.change_conversation_title(
                    conversation_id=create_share_conv,
                    title="Alpha Summary (Logan, Riley, Jordan)",
                )
                .oracle()
                .depends_on(add_riley_event, delay_seconds=1)
            )

            # Send summary message
            send_summary = (
                messaging.send_message_to_group_conversation(
                    conversation_id=create_share_conv,
                    content=(
                        "Summary of Project Alpha Discussion:\n"
                        "- Riley uploaded the design draft and requested review by EOD.\n"
                        "- Sam mentioned finalizing client presentation slides for Monday.\n"
                        "- Marketing KPIs are pending; team to compile once data is received."
                    ),
                )
                .oracle()
                .depends_on(rename_conv_event, delay_seconds=2)
            )

            # Agent confirms completion to user
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've shared a concise summary of the chat with Logan White in a new group conversation that includes Riley as well."
                )
                .oracle()
                .depends_on(send_summary, delay_seconds=1)
            )

        self.events = [
            msg_evt1,
            msg_evt2,
            msg_evt3,
            unread_check,
            proposal_event,
            approval_event,
            existing_convs,
            read_conv_event,
            create_share_conv,
            add_riley_event,
            rename_conv_event,
            send_summary,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent summarized and shared the conversation with Logan."""
        try:
            log = env.event_log.list_view()

            proposal_ok = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and ("Logan" in e.action.args.get("content", ""))
                and ("summarize" in e.action.args.get("content", "") or "summary" in e.action.args.get("content", ""))
                for e in log
            )

            conv_created = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "create_group_conversation"
                and "Logan" in e.action.args.get("title", "")
                for e in log
            )

            summary_sent = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "Summary" in e.action.args.get("content", "")
                and "Riley" in e.action.args.get("content", "")
                and "Sam" in e.action.args.get("content", "")
                for e in log
            )

            added_riley = any(
                e.event_type == EventType.AGENT and e.action.function_name == "add_participant_to_conversation"
                for e in log
            )

            renamed = any(
                e.event_type == EventType.AGENT
                and e.action.function_name == "change_conversation_title"
                and "Alpha Summary" in e.action.args.get("title", "")
                for e in log
            )

            success = proposal_ok and conv_created and summary_sent and added_riley and renamed
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
