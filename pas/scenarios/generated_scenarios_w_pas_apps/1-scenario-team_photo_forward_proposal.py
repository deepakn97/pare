from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("team_photo_forward_proposal")
class TeamPhotoForwardProposal(Scenario):
    """Agent proposes to forward received team photo to another colleague based on user approval.

    A recent group conversation among teammates includes a new photo just shared by "Lena".
    The assistant detects that the photo may also be relevant for "Jordan" (mentioned earlier in the chat),
    who is not yet part of this conversation. It then proactively proposes to the user to forward the image
    to Jordan. Upon user's approval, the assistant looks up Jordan's user ID, creates a direct chat, and
    forwards the image.

    This scenario exercises messaging context handling, participant lookup, group messaging,
    proactive proposals, and motivated oracle usage across MessagingApp, AUI, and SystemApp.
    """

    start_time = datetime(2025, 11, 14, 15, 30, 0, tzinfo=UTC).timestamp()
    status = "Draft"
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps and prepare conversation data."""
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")

        self.messaging.current_user_id = "user-main"
        self.messaging.current_user_name = "Sam"

        self.lena_id = self.messaging.get_user_id(user_name="Lena") or "lena-001"
        self.jordan_name = "Jordan"

        self.team_conv_id = self.messaging.create_group_conversation(user_ids=[self.lena_id], title="Team Catchup")

        self.messaging.get_existing_conversation_ids()
        self.apps = [self.messaging, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow demonstrating proactive file-forwarding proposal."""
        aui = self.get_typed_app(PASAgentUserInterface)
        sys_app = self.get_typed_app(HomeScreenSystemApp)
        messaging = self.get_typed_app(StatefulMessagingApp)

        with EventRegisterer.capture_mode():
            # Env Event 1: Lena sends a message mentioning Jordan in Team Catchup group
            mention_event = messaging.create_and_add_message(
                conversation_id=self.team_conv_id,
                sender_id=self.lena_id,
                content="Hey team! The presentation slides look great. Jordan would love this photo from yesterday!",
            ).delayed(2)

            # Env Event 2: Lena sends the actual photo message
            photo_event = messaging.create_and_add_message(
                conversation_id=self.team_conv_id,
                sender_id=self.lena_id,
                content="(Attachment: office_team_photo.jpg)",
            ).delayed(4)

            # Oracle 1 (revised): Read conversation to extract context (motivated by photo mention)
            read_event = (
                messaging.read_conversation(conversation_id=self.team_conv_id, limit=5)
                .oracle()
                .depends_on(photo_event, delay_seconds=1)
            )

            # Oracle 2 (revised): Agent uses system time for timestamp (motivated by contextual summary)
            time_info_event = sys_app.get_current_time().oracle().depends_on(read_event, delay_seconds=1)

            # Oracle 3: Agent proposes to user, referencing time and conversation content
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        f"At {{}}, Lena shared a new team photo and mentioned {self.jordan_name}. "
                        "Would you like me to forward this image to them since they're not in the 'Team Catchup' group?"
                    ).format(time_info_event.output["datetime"])
                )
                .oracle()
                .depends_on(time_info_event, delay_seconds=2)
            )

            # Oracle 4: User accepts
            accept_event = (
                aui.accept_proposal(content="Yes, please share that team photo with Jordan directly.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle 5: Agent looks up Jordan's user ID
            lookup_event = (
                messaging.lookup_user_id(user_name=self.jordan_name).oracle().depends_on(accept_event, delay_seconds=1)
            )

            # Oracle 6: Agent downloads the shared attachment
            download_event = (
                messaging.download_attachment(
                    conversation_id=self.team_conv_id, message_id="last-photo-message", download_path="Downloads/"
                )
                .oracle()
                .depends_on(lookup_event, delay_seconds=1)
            )

            # Oracle 7: Agent switches to Messaging
            switch_event = sys_app.switch_app(app_name="Messaging").oracle().depends_on(download_event, delay_seconds=1)

            # Oracle 8: Agent creates direct chat with Jordan
            create_chat_event = (
                messaging.create_group_conversation(
                    user_ids=[next(iter(lookup_event.output.values())) if lookup_event.output else "jordan-unknown"],
                    title="Chat with Jordan",
                )
                .oracle()
                .depends_on(switch_event, delay_seconds=1)
            )

            # Oracle 9: Agent adds the current user explicitly to the chat
            add_participant_event = (
                messaging.add_participant_to_conversation(
                    conversation_id=create_chat_event.output.get("conversation_id", "new-chat-jordan"),
                    user_id=self.messaging.current_user_id,
                )
                .oracle()
                .depends_on(create_chat_event, delay_seconds=1)
            )

            # Oracle 10: Agent sends message with photo to Jordan
            send_photo_event = (
                messaging.send_message(
                    user_id=(next(iter(lookup_event.output.values())) if lookup_event.output else "jordan-unknown"),
                    content="Hi Jordan! Lena shared this photo in 'Team Catchup' — thought you'd like to see it!",
                    attachment_path="Downloads/office_team_photo.jpg",
                )
                .oracle()
                .depends_on(add_participant_event, delay_seconds=1)
            )

            # Oracle 11: Agent changes the group conversation title afterward
            retitle_event = (
                messaging.change_conversation_title(
                    conversation_id=self.team_conv_id,
                    title="Team Catchup (Photo shared)",
                )
                .oracle()
                .depends_on(send_photo_event, delay_seconds=1)
            )

            # Oracle 12: Agent confirms completion to user
            confirm_event = (
                aui.send_message_to_user(
                    content="I've forwarded the team photo to Jordan and updated your group chat title."
                )
                .oracle()
                .depends_on(retitle_event, delay_seconds=1)
            )

        self.events = [
            mention_event,
            photo_event,
            read_event,
            time_info_event,
            proposal_event,
            accept_event,
            lookup_event,
            download_event,
            switch_event,
            create_chat_event,
            add_participant_event,
            send_photo_event,
            retitle_event,
            confirm_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check successful proactive proposal, approval, and photo forwarding process."""
        try:
            log_entries = env.event_log.list_view()

            proposal_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "forward" in e.action.args.get("content", "")
                and "Jordan" in e.action.args.get("content", "")
                for e in log_entries
            )

            acceptance_logged = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "accept_proposal"
                and "share" in e.action.args.get("content", "")
                for e in log_entries
            )

            message_forwarded = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and "photo" in e.action.args.get("content", "").lower()
                and "Jordan" in e.action.args.get("content", "")
                for e in log_entries
            )

            title_changed = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "change_conversation_title"
                and e.action.args.get("conversation_id") == self.team_conv_id
                and "Photo shared" in e.action.args.get("title", "")
                for e in log_entries
            )

            success = proposal_found and acceptance_logged and message_forwarded and title_changed
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
