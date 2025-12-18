from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("team_project_file_forward")
class TeamProjectFileForward(Scenario):
    """Agent notices a teammate requesting a project file in chat, then proactively offers to forward it."""

    start_time = datetime(2025, 4, 14, 8, 30, 0, tzinfo=UTC).timestamp()
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize messaging scenario apps."""
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")
        self.agent_ui = PASAgentUserInterface()

        # Initialize current user
        self.messaging.current_user_id = "user_current"
        self.messaging.current_user_name = "Chris Jordan"

        # Lookup user IDs for participants
        self.daniel_lookup = self.messaging.lookup_user_id("Daniel Roberts")
        self.priya_lookup = self.messaging.lookup_user_id("Priya Nair")

        self.daniel_id = (
            next(iter(self.daniel_lookup.values()))
            if self.daniel_lookup
            else self.messaging.get_user_id(user_name="Daniel Roberts")
        )
        self.priya_id = (
            next(iter(self.priya_lookup.values()))
            if self.priya_lookup
            else self.messaging.get_user_id(user_name="Priya Nair")
        )

        # Create a group conversation
        self.project_chat_id = self.messaging.create_group_conversation(
            user_ids=[self.daniel_id, self.priya_id],
            title="Project Falcon Team Chat",
        )

        # Instead of a hard-coded download path, store a variable placeholder for later use
        self.download_folder_var = "user_download_dir"
        # Path to attachment will be derived from download event output
        self.apps = [self.messaging, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow: Daniel requests forwarding, user approves, and agent forwards."""
        messaging = self.get_typed_app(StatefulMessagingApp)
        aui = self.get_typed_app(PASAgentUserInterface)

        with EventRegisterer.capture_mode():
            # Step 1: Daniel shares the project file
            file_message_event = messaging.create_and_add_message(
                conversation_id=self.project_chat_id,
                sender_id=self.daniel_id,
                content="Here's the Falcon_Project_Deck.pdf for review.",
            ).delayed(2)

            # Step 2: Daniel asks for forwarding
            forward_request_event = messaging.create_and_add_message(
                conversation_id=self.project_chat_id,
                sender_id=self.daniel_id,
                content="Can you send the latest deck to Priya as well?",
            ).delayed(3)

            # Step 3: Agent proposes forwarding
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "Daniel asked to forward the latest 'Falcon_Project_Deck.pdf' "
                        "to Priya. Would you like me to send it to her now?"
                    )
                )
                .oracle()
                .depends_on(forward_request_event, delay_seconds=2)
            )

            # Step 4: User approves the proposal
            approval_event = (
                aui.accept_proposal(content="Yes, please forward the presentation deck to Priya and confirm once done.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Step 5: Check if a conversation with Priya already exists
            check_existing_priya_chat_event = (
                messaging.get_existing_conversation_ids(user_ids=[self.priya_id])
                .oracle()
                .depends_on(approval_event, delay_seconds=1)
            )

            # Step 6: Download local copy before forwarding; use message_id from file_message_event output
            download_file_event = (
                messaging.download_attachment(
                    conversation_id=self.project_chat_id,
                    message_id=file_message_event.returned_message_id,
                    download_path=self.download_folder_var,
                )
                .oracle()
                .depends_on(check_existing_priya_chat_event, delay_seconds=1)
            )

            # Step 7: Forward the file to Priya, using the downloaded attachment path returned
            send_message_event = (
                messaging.send_message(
                    user_id=self.priya_id,
                    content="Hi Priya, forwarding the latest Falcon project deck from Daniel.",
                    attachment_path=download_file_event.return_value,
                )
                .oracle()
                .depends_on(download_file_event, delay_seconds=2)
            )

            # Step 8: Agent notifies user
            confirmation_event = (
                aui.send_message_to_user(
                    content=(
                        "I've forwarded 'Falcon_Project_Deck.pdf' "
                        "to Priya as requested. Daniel's request is taken care of."
                    )
                )
                .oracle()
                .depends_on(send_message_event, delay_seconds=1)
            )

        self.events = [
            file_message_event,
            forward_request_event,
            proposal_event,
            approval_event,
            check_existing_priya_chat_event,
            download_file_event,
            send_message_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent proposed, user approved, and file was sent."""
        try:
            logs = env.event_log.list_view()

            proposal_logged = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and all(kw in e.action.args.get("content", "") for kw in ["Priya", "Falcon_Project_Deck"])
                for e in logs
            )

            acceptance_logged = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "accept_proposal"
                and "forward" in e.action.args.get("content", "").lower()
                for e in logs
            )

            message_forwarded = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.priya_id
                and "Falcon" in e.action.args.get("attachment_path", "")
                and "deck" in e.action.args.get("content", "").lower()
                for e in logs
            )

            confirmation_logged = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "forwarded" in e.action.args.get("content", "").lower()
                and "Priya" in e.action.args.get("content", "")
                for e in logs
            )

            success = proposal_logged and acceptance_logged and message_forwarded and confirmation_logged
            return ScenarioValidationResult(success=success)

        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
