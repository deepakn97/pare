from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("proactive_project_brainstorm_forward")
class ProactiveProjectBrainstormForward(Scenario):
    """Agent identifies brainstorming ideas from team chat and offers to share them with project partner.

    Context:
    - A group conversation with teammates Alex and Taylor named "UI Brainstorm" is ongoing.
    - The conversation happens on 2025-11-21 morning.
    - Earlier, Taylor shares a summary message with design brainstorming notes.

    Agent workflow:
    1. Detects Taylor's detailed brainstorming message arrival.
    2. Proactively proposes to the user to forward or summarize these notes to partner Jordan.
    3. User approves the proactive suggestion.
    4. Agent looks up Jordan's user ID, checks existing conversations with Jordan, creates or reuses one, and forwards the message.
    5. Agent optionally renames the group chat to reflect updated topic and confirms to user.

    Demonstrates: multi-step proactive messaging, use of lookup_user_id, create_group_conversation,
    send_message_to_group_conversation, and conversation title manipulation.
    """

    start_time = datetime(2025, 11, 21, 9, 0, 0, tzinfo=UTC).timestamp()
    status = "Draft"
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize messaging and related system apps."""
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.agent_ui = PASAgentUserInterface(name="PASAgentUserInterface")
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")

        # Initialize current user
        self.messaging.current_user_id = "user-self-001"
        self.messaging.current_user_name = "You"

        # Simulate known teammates in the system
        self.alex_id = self.messaging.get_user_id(user_name="Alex Morgan").oracle()
        self.taylor_id = self.messaging.get_user_id(user_name="Taylor Reed").oracle()
        # Directly get Jordan ID; no redundant lookup later
        self.jordan_id = self.messaging.get_user_id(user_name="Jordan").oracle()

        # Create a group conversation for "UI Brainstorm"
        self.brainstorm_conv_id = self.messaging.create_group_conversation(
            user_ids=[self.alex_id, self.taylor_id],
            title="UI Brainstorm",
        ).oracle()

        self.apps = [self.messaging, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Simulate message-based proactive flow and corresponding actions."""
        messaging = self.get_typed_app(StatefulMessagingApp)
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            # Environmental context: Taylor posts brainstorming summary
            new_msg_event = messaging.create_and_add_message(
                conversation_id=self.brainstorm_conv_id,
                sender_id=self.taylor_id,
                content=(
                    "I've compiled several ideas for the new dashboard layout—"
                    "User flow simplification, color balance improvement, "
                    "and adaptive component responsiveness for mobile. "
                    "Can you share these with Jordan for external feedback?"
                ),
            ).delayed(2)

            # Agent proactively proposes to forward to Jordan after message arrival
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "Taylor just shared some UI brainstorming ideas. "
                        "Would you like me to forward these notes to Jordan for external review?"
                    )
                )
                .oracle()
                .depends_on(new_msg_event, delay_seconds=2)
            )

            # User approves the proposal
            approval_event = (
                aui.accept_proposal(content="Yes, please share Taylor's brainstorming summary with Jordan.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # After approval, check Jordan's info and ensure there's a conversation or create one
            ensure_jordan_contact = (
                messaging.get_user_name_from_id(user_id=self.jordan_id).oracle().depends_on(approval_event)
            )

            # Create or reuse a conversation for sharing with Jordan
            jordan_conv_oracle = (
                messaging.create_group_conversation(
                    user_ids=[self.jordan_id],
                    title="Feedback with Jordan",
                )
                .oracle()
                .depends_on(ensure_jordan_contact, delay_seconds=1)
            )

            # Add Alex for transparency
            add_participant_event = (
                messaging.add_participant_to_conversation(
                    conversation_id=jordan_conv_oracle,
                    user_id=self.alex_id,
                )
                .oracle()
                .depends_on(jordan_conv_oracle, delay_seconds=1)
            )

            # Forward Taylor's message to Jordan's chat
            forward_event = (
                messaging.send_message_to_group_conversation(
                    conversation_id=jordan_conv_oracle,
                    content=(
                        "Taylor shared the following brainstorming ideas:\n"
                        "— User flow simplification, color balance improvement, and adaptive responsiveness"
                    ),
                )
                .oracle()
                .depends_on(add_participant_event, delay_seconds=1)
            )

            # Rename original brainstorm conversation after forward completes
            rename_event = (
                messaging.change_conversation_title(
                    conversation_id=self.brainstorm_conv_id,
                    title="UI Brainstorm - Shared with Jordan",
                )
                .oracle()
                .depends_on(forward_event, delay_seconds=1)
            )

            # Retrieve user's own name from ID for confirmation
            self_name_oracle = (
                messaging.get_user_name_from_id(user_id=self.messaging.current_user_id)
                .oracle()
                .depends_on(rename_event)
            )

            # Confirm success to user
            confirm_content = (
                "I've shared the brainstorming ideas with Jordan and updated the chat title to reflect the share. "
                f"Message sent by {self_name_oracle}."
            )
            confirm_event = (
                aui.send_message_to_user(content=confirm_content).oracle().depends_on(self_name_oracle, delay_seconds=1)
            )

        self.events = [
            new_msg_event,
            proposal_event,
            approval_event,
            ensure_jordan_contact,
            jordan_conv_oracle,
            add_participant_event,
            forward_event,
            rename_event,
            self_name_oracle,
            confirm_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check that the proactive proposal was made, approved, and executed."""
        try:
            logs = env.event_log.list_view()

            proposal_ok = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and "Taylor" in e.action.args.get("content", "")
                and "Jordan" in e.action.args.get("content", "")
                for e in logs
            )

            approved_ok = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "accept_proposal"
                and "share Taylor" in e.action.args.get("content", "")
                for e in logs
            )

            forward_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "Taylor" in e.action.args.get("content", "")
                for e in logs
            )

            rename_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "change_conversation_title"
                and "Shared with Jordan" in e.action.args.get("title", "")
                for e in logs
            )

            return ScenarioValidationResult(success=(proposal_ok and approved_ok and forward_done and rename_done))
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
