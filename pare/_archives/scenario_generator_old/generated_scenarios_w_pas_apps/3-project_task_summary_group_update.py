from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("project_task_summary_group_update")
class ProjectTaskSummaryGroupUpdate(Scenario):
    """Agent builds context from incoming group discussion and offers to create a new 'Project Tasks' group chat.

    Scenario Overview:
    - Context: The user is part of a busy team chat discussing project tasks.
    - Participants mention needing a 'dedicated tasks-only group' for better organization.
    - The agent detects this from environment messages, proactively proposes to create a new chat.
    - Upon user approval, the agent creates the new group, adds participants,
      renames it, and sends a starting message summarizing the group's intent.
    """

    start_time = datetime(2025, 11, 13, 14, 0, 0, tzinfo=UTC).timestamp()
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the messaging and system apps."""
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.messaging.current_user_name = "Alex Johnson"
        self.messaging.current_user_id = self.messaging.get_user_id(user_name=self.messaging.current_user_name)

        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")
        self.agent_ui = PASAgentUserInterface()

        # Resolve teammate IDs via lookup instead of hardcoding
        sam_lookup = self.messaging.lookup_user_id(user_name="Sam Parker")
        tina_lookup = self.messaging.lookup_user_id(user_name="Tina Ray")

        self.sam_id = next(iter(sam_lookup.values())) if sam_lookup else None
        self.tina_id = next(iter(tina_lookup.values())) if tina_lookup else None

        # If IDs could not be resolved, attempt fallback by ensuring they exist in the system first
        # (no literal fallback string IDs introduced)
        if not self.sam_id or not self.tina_id:
            raise RuntimeError("Failed to retrieve valid user IDs for Sam Parker or Tina Ray.")

        # Create an existing team chat with Sam and Tina
        self.team_conversation_id = self.messaging.create_group_conversation(
            user_ids=[self.sam_id, self.tina_id], title="Alpha Team Discussion"
        )

        self.apps = [self.messaging, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow demonstrating proactive assistant behavior."""
        messaging = self.get_typed_app(StatefulMessagingApp)
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            # Context events: teammates chatting about tasks
            msg1 = messaging.create_and_add_message(
                conversation_id=self.team_conversation_id,
                sender_id=self.sam_id,
                content="Our chat is getting cluttered. We should make a new group just for tracking tasks.",
            ).delayed(1)

            msg2 = messaging.create_and_add_message(
                conversation_id=self.team_conversation_id,
                sender_id=self.tina_id,
                content="Yes, maybe something like 'Project Tasks' — only for work-related updates.",
            ).delayed(2)

            # Agent detects conversation pattern, proposes new group
            proposal = (
                aui.send_message_to_user(
                    content=(
                        "It seems Sam and Tina want a dedicated group for project tasks. "
                        "Would you like me to create a new 'Project Tasks' group with them and send a starter message?"
                    )
                )
                .oracle()
                .depends_on(msg2, delay_seconds=2)
            )

            approval = (
                aui.accept_proposal(content="Yes, please create the group and send a welcome message.")
                .oracle()
                .depends_on(proposal, delay_seconds=2)
            )

            # Agent opens the Messaging app
            open_messaging = system_app.open_app(app_name="Messaging").oracle().depends_on(approval, delay_seconds=1)

            # Agent creates the new group conversation
            create_group = (
                messaging.create_group_conversation(user_ids=[self.sam_id, self.tina_id], title="Project Tasks")
                .oracle()
                .depends_on(open_messaging, delay_seconds=1)
            )

            # The created group conversation ID is used for all further actions
            new_group_id = create_group

            # Agent sends a starter message to the new tasks group
            send_intro = (
                messaging.send_message_to_group_conversation(
                    conversation_id=new_group_id,
                    content="Hi all! The 'Project Tasks' group is ready for tracking our work updates.",
                )
                .oracle()
                .depends_on(create_group, delay_seconds=2)
            )

            # Return to home after setup confirmed
            go_home = system_app.go_home().oracle().depends_on(send_intro, delay_seconds=1)

        self.events = [
            msg1,
            msg2,
            proposal,
            approval,
            open_messaging,
            create_group,
            send_intro,
            go_home,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation ensuring the proactive flow occurred logically."""
        try:
            entries = env.event_log.list_view()

            proposal_ok = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "dedicated group" in e.action.args.get("content", "")
                for e in entries
            )

            approval_ok = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "accept_proposal"
                for e in entries
            )

            create_ok = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "create_group_conversation"
                and "Project Tasks" in (e.action.args.get("title") or "")
                for e in entries
            )

            send_intro_ok = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "Project Tasks" in e.action.args.get("content", "")
                for e in entries
            )

            return ScenarioValidationResult(success=(proposal_ok and approval_ok and create_ok and send_intro_ok))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
