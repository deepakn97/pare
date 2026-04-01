from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("group_chat_file_followup")
class GroupChatFileFollowUp(Scenario):
    """Agent proposes to forward a received document in a group chat to another colleague.

    The user participates in a group chat called 'Project Nova' with Anna and Lucas.
    Anna sends a message with an attachment named 'Summary_Q2.pdf'. The agent observes
    that a teammate, Jordan, is often mentioned in previous discussions but not in
    this chat. It proactively proposes to share the file with Jordan.

    After the user approves, the agent looks up Jordan's user ID, adds Jordan to the
    conversation, and forwards the file. The workflow integrates proactive suggestions,
    participant management, and contextual messaging.

    This scenario demonstrates messaging context awareness and proactive assistance
    that facilitates knowledge sharing within a chat group.
    """

    start_time = datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp()
    status = "Draft"
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all apps."""
        # Initialize applications
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")
        self.agent_ui = PASAgentUserInterface()

        # Set current user configuration
        self.messaging.current_user_id = "user_001"
        self.messaging.current_user_name = "Taylor Reed"

        anna_id = self.messaging.get_user_id(user_name="Anna Rivera").oracle()
        lucas_id = self.messaging.get_user_id(user_name="Lucas Zhao").oracle()

        self.project_nova_conv_id = self.messaging.create_group_conversation(
            user_ids=[anna_id, lucas_id], title="Project Nova Team"
        ).oracle()

        self.anna_id = anna_id
        self.lucas_id = lucas_id

        # Prepare a variable for download path
        self.download_dir = "tmp_download_dir"

        self.apps = [self.messaging, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Core event flow demonstrating proactive file sharing proposal."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging = self.get_typed_app(StatefulMessagingApp)
        system_app = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            # 1. Anna sends message with a file and mentions Jordan
            incoming_msg_event = messaging.create_and_add_message(
                conversation_id=self.project_nova_conv_id,
                sender_id=self.anna_id,
                content="Here is the summary document for Q2 findings. Jordan asked for it earlier.",
            ).delayed(1)

            # Use returned message ID rather than a fabricated one
            anna_message_id = incoming_msg_event.transform("lambda v: v if v else None").oracle()

            # 2. Agent proactive suggestion
            proactive_proposal = (
                aui.send_message_to_user(
                    content="Anna shared a Q2 Summary document in 'Project Nova'. Jordan was mentioned—shall I share it with him as well?"
                )
                .oracle()
                .depends_on(incoming_msg_event, delay_seconds=2)
            )

            # 3. User approves
            user_approval = (
                aui.accept_proposal(content="Yes, please forward it to Jordan.")
                .oracle()
                .depends_on(proactive_proposal, delay_seconds=2)
            )

            # 4. Agent looks up Jordan's ID
            lookup_event = messaging.lookup_user_id(user_name="Jordan Lee").oracle().depends_on(user_approval, 1)

            # Use Jordan's resolved ID for the next actions
            get_jordan_id = lookup_event.transform("lambda v: next(iter(v.values())) if v else None").oracle()

            # 5. Agent adds Jordan to the conversation
            add_participant_event = (
                messaging.add_participant_to_conversation(
                    conversation_id=self.project_nova_conv_id, user_id=get_jordan_id
                )
                .oracle()
                .depends_on(lookup_event, 1)
            )

            # 6. Change conversation title to include Jordan
            rename_event = (
                messaging.change_conversation_title(
                    conversation_id=self.project_nova_conv_id, title="Project Nova Team + Jordan"
                )
                .oracle()
                .depends_on(add_participant_event, delay_seconds=1)
            )

            # 7. Download Anna's shared attachment using output IDs and stored download dir
            download_event = (
                messaging.download_attachment(
                    conversation_id=self.project_nova_conv_id,
                    message_id=anna_message_id,
                    download_path=self.download_dir,
                )
                .oracle()
                .depends_on(rename_event, delay_seconds=1)
            )

            # Extract downloaded path for re-use
            downloaded_file_path = download_event.transform("lambda v: v").oracle()

            # 8. Forward file message using downloaded_file_path
            followup_send_event = (
                messaging.send_message_to_group_conversation(
                    conversation_id=self.project_nova_conv_id,
                    content="Forwarding the Summary_Q2.pdf file for Jordan's review.",
                    attachment_path=downloaded_file_path,
                )
                .oracle()
                .depends_on(download_event, delay_seconds=1)
            )

            # 9. Check Jordan's participation in this conversation now (motivated use)
            confirm_participant_event = (
                messaging.list_conversations_by_participant(user_id=get_jordan_id, limit=2)
                .oracle()
                .depends_on(followup_send_event, delay_seconds=1)
            )

            # 10. Confirm that the conversation Jordan just got added to is among these conversations
            confirm_event = (
                confirm_participant_event.transform(
                    f"lambda v: '{self.project_nova_conv_id}' in [c.id for c in v] if v else False"
                )
                .oracle()
                .depends_on(confirm_participant_event, delay_seconds=1)
            )

            # 11. Conclude with a message confirming completion (non-superficial end)
            conclude_event = (
                aui.send_message_to_user(
                    content="The Summary_Q2.pdf has been successfully shared with Jordan in the updated group chat."
                )
                .oracle()
                .depends_on(confirm_event, delay_seconds=1)
            )

        self.events = [
            incoming_msg_event,
            anna_message_id,
            proactive_proposal,
            user_approval,
            lookup_event,
            get_jordan_id,
            add_participant_event,
            rename_event,
            download_event,
            downloaded_file_path,
            followup_send_event,
            confirm_participant_event,
            confirm_event,
            conclude_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation checks that the agent proposed, user approved, and file was sent to Jordan."""
        try:
            logs = env.event_log.list_view()

            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Jordan" in e.action.args.get("content", "")
                and "document" in e.action.args.get("content", "")
                for e in logs
            )

            user_confirmed = any(
                e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "accept_proposal"
                and "forward" in e.action.args.get("content", "").lower()
                for e in logs
            )

            participant_added = any(
                e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "add_participant_to_conversation"
                for e in logs
            )

            file_downloaded = any(
                e.action.class_name == "StatefulMessagingApp" and e.action.function_name == "download_attachment"
                for e in logs
            )

            message_forwarded = any(
                e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "Summary_Q2.pdf" in str(e.action.args.get("attachment_path", ""))
                for e in logs
            )

            return ScenarioValidationResult(
                success=(
                    proposal_sent and user_confirmed and participant_added and file_downloaded and message_forwarded
                )
            )

        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
