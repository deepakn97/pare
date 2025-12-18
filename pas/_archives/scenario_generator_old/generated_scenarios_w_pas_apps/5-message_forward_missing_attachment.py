from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("message_forward_missing_attachment")
class MessageForwardMissingAttachment(Scenario):
    """Agent helps user forward a missing file after a teammate requests it via chat.

    The user is chatting in a team group conversation about a product demo.
    A teammate, Maria Lopez, sends a message asking for a copy of the 'DemoPlan.pdf' file
    that was attached earlier by James. The proactive agent detects this mention,
    proposes forwarding the file to Maria, waits for user approval, and upon approval,
    downloads and then sends the file.

    This scenario tests multi-step message context reading, proactive proposal confirmation,
    file handling (download and send), and multiple messaging tool interactions.
    """

    start_time = datetime(2025, 11, 15, 14, 0, 0, tzinfo=UTC).timestamp()
    status = "Draft"
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize HomeScreenSystemApp, PASAgentUserInterface, and MessagingApp."""
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")
        self.aui = PASAgentUserInterface()
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")

        # Current user setup
        self.messaging.current_user_id = "user-001"
        self.messaging.current_user_name = "Jordan Parker"

        # Define teammates (Maria, James)
        self.maria_id = self.messaging.get_user_id(user_name="Maria Lopez")
        self.james_id = self.messaging.get_user_id(user_name="James Reed")

        # Create a group conversation for demo discussion
        self.team_conversation_id = self.messaging.create_group_conversation(
            user_ids=[self.maria_id, self.james_id],
            title="Product Demo Planning",
        )

        # define base download directory variable
        self.download_dir = "DemoFiles"  # variable-based constant for reuse
        # define file path variable constructed from download_dir
        self.demo_plan_file_path = f"{self.download_dir}/DemoPlan.pdf"

        self.apps = [self.system_app, self.aui, self.messaging]

    def build_events_flow(self) -> None:
        """Define event flow: message from Maria → agent proposes → user approves → agent forwards file."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging = self.get_typed_app(StatefulMessagingApp)
        system_app = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            # Context 1: James shared the file earlier (environment event)
            initial_file_share = messaging.create_and_add_message(
                conversation_id=self.team_conversation_id,
                sender_id=self.james_id,
                content="Here's the DemoPlan.pdf we discussed earlier.",
            ).delayed(1)

            # Context 2: Maria asks about the file (environment event)
            maria_request = messaging.create_and_add_message(
                conversation_id=self.team_conversation_id,
                sender_id=self.maria_id,
                content="Could you please forward me the DemoPlan.pdf file from James? I can't find it in the thread.",
            ).delayed(2)

            # Agent action 1: Propose to user (oracle)
            proposal = (
                aui.send_message_to_user(
                    content="Maria Lopez requested the 'DemoPlan.pdf' file that James shared earlier. "
                    "Would you like me to forward the file to her directly in this chat?"
                )
                .oracle()
                .depends_on(maria_request, delay_seconds=1)
            )

            # User action: Accepts proposal (oracle)
            approval = (
                aui.accept_proposal(content="Yes, please forward the DemoPlan.pdf file to Maria so she gets it.")
                .oracle()
                .depends_on(proposal, delay_seconds=2)
            )

            # Agent action 2: Search for the file reference message (oracle)
            search_conversation = (
                messaging.regex_search(query="DemoPlan\\.pdf").oracle().depends_on(approval, delay_seconds=1)
            )

            # Use the message_id from the earlier file share explicitly
            download_attachment = (
                messaging.download_attachment(
                    conversation_id=self.team_conversation_id,
                    message_id=initial_file_share.output.get("message_id"),
                    download_path=self.download_dir,
                )
                .oracle()
                .depends_on(search_conversation, delay_seconds=1)
            )

            # Agent action 3: Forward/send attachment to the same group (oracle)
            forward_file = (
                messaging.send_message_to_group_conversation(
                    conversation_id=self.team_conversation_id,
                    content="Forwarding DemoPlan.pdf to Maria as requested.",
                    attachment_path=self.demo_plan_file_path,
                )
                .oracle()
                .depends_on(download_attachment, delay_seconds=2)
            )

            # Agent action 4: Confirm completion to user (oracle)
            confirm_to_user = (
                aui.send_message_to_user(
                    content="I've forwarded DemoPlan.pdf to Maria Lopez in your 'Product Demo Planning' conversation."
                )
                .oracle()
                .depends_on(forward_file, delay_seconds=2)
            )

        # Register sequence of events
        self.events = [
            initial_file_share,
            maria_request,
            proposal,
            approval,
            search_conversation,
            download_attachment,
            forward_file,
            confirm_to_user,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation: Ensure that the agent proposed, user approved, and the file forward occurred."""
        try:
            log_entries = env.event_log.list_view()

            proposal_detected = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and all(keyword in e.action.args.get("content", "") for keyword in ["Maria Lopez", "DemoPlan.pdf"])
                for e in log_entries
            )

            accepted = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "accept_proposal"
                and "forward" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            download_done = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "download_attachment"
                for e in log_entries
            )

            forward_done = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "DemoPlan.pdf" in e.action.args.get("attachment_path", "")
                for e in log_entries
            )

            confirmation_sent = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "forwarded" in e.action.args.get("content", "").lower()
                and "DemoPlan.pdf" in e.action.args.get("content", "")
                for e in log_entries
            )

            success = proposal_detected and accepted and download_done and forward_done and confirmation_sent
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
