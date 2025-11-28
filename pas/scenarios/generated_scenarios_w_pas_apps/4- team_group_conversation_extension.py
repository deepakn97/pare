from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("team_group_conversation_extension")
class TeamGroupConversationExtension(Scenario):
    """Scenario: The user participates in an active group chat discussing a report.

    A teammate (Jordan) joins late and requests to be added to the group.
    The proactive agent notices this in the chat log and offers to add Jordan automatically.

    Workflow:
    1. Environment creates incoming messages in a group chat indicating Jordan missed the discussion.
    2. Agent checks the recent conversations to confirm the correct chat context.
    3. Agent proactively proposes adding Jordan.
    4. User approves the proposal.
    5. Agent discovers Jordan's user ID via lookup_user_id and adds Jordan to the group.
    6. Agent renames the conversation to reflect the updated participant list.
    7. Agent sends a welcome message in the group conversation announcing Jordan's addition.

    Apps initialized: StatefulMessagingApp, PASAgentUserInterface, HomeScreenSystemApp
    """

    start_time = datetime(2025, 7, 10, 14, 0, 0, tzinfo=UTC).timestamp()
    status = "Draft"
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all selected apps and prepare baseline chat with known participants."""
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.aui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")

        # Define current user and participants
        self.messaging.current_user_id = "user-001"
        self.messaging.current_user_name = "Casey Morgan"
        self.alex_id = "user-002"
        self.taylor_id = "user-003"

        # Create initial group conversation for the project report discussion
        self.report_conversation_id = self.messaging.create_group_conversation(
            user_ids=[self.alex_id, self.taylor_id], title="Q3 Report Discussion"
        )

        self.apps = [self.messaging, self.aui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow — detect teammate request and extend group conversation."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging = self.get_typed_app(StatefulMessagingApp)
        system_app = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            # Context: Ongoing group chat messages
            message1_event = messaging.create_and_add_message(
                conversation_id=self.report_conversation_id,
                sender_id=self.alex_id,
                content="Hey everyone, let's finalize the Q3 report updates by tomorrow.",
            ).delayed(1)

            message2_event = messaging.create_and_add_message(
                conversation_id=self.report_conversation_id,
                sender_id=self.taylor_id,
                content="Jordan said he missed this thread — maybe we should add him here.",
            ).delayed(3)

            # Agent checks recent conversations to confirm which one is active
            list_recent_event = (
                messaging.list_recent_conversations(offset=0, limit=3)
                .oracle()
                .depends_on(message2_event, delay_seconds=2)
            )

            # Agent now uses recent conversation info to target proposal correctly
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I noticed Taylor mentioned that Jordan missed the Q3 Report Discussion "
                        "in your recent chats. Would you like me to add Jordan to that group and "
                        "update the chat title accordingly?"
                    )
                )
                .oracle()
                .depends_on(list_recent_event, delay_seconds=2)
            )

            # User approves proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please add Jordan to the group and adjust the title.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Agent looks up Jordan's user ID
            lookup_event = (
                messaging.lookup_user_id(user_name="Jordan").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # Extract Jordan's user_id variable from lookup result
            self.jordan_id = lookup_event["Jordan"]

            # Agent adds Jordan to the conversation using the looked-up ID
            add_event = (
                messaging.add_participant_to_conversation(
                    conversation_id=self.report_conversation_id, user_id=self.jordan_id
                )
                .oracle()
                .depends_on(lookup_event, delay_seconds=1)
            )

            # Agent changes conversation title
            rename_event = (
                messaging.change_conversation_title(
                    conversation_id=self.report_conversation_id, title="Q3 Report Discussion + Jordan"
                )
                .oracle()
                .depends_on(add_event, delay_seconds=1)
            )

            # Agent posts a welcome message in the group
            welcome_message_event = (
                messaging.send_message_to_group_conversation(
                    conversation_id=self.report_conversation_id,
                    content="Welcome to the group, Jordan! We've been discussing Q3 report updates.",
                )
                .oracle()
                .depends_on(rename_event, delay_seconds=2)
            )

            # Agent goes back to home
            go_home_event = system_app.go_home().oracle().depends_on(welcome_message_event, delay_seconds=1)

        self.events = [
            message1_event,
            message2_event,
            list_recent_event,
            proposal_event,
            acceptance_event,
            lookup_event,
            add_event,
            rename_event,
            welcome_message_event,
            go_home_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that Jordan was added and title changed after user approval."""
        try:
            logs = env.event_log.list_view()

            proposal_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Jordan" in e.action.args["content"]
                and "Q3 Report" in e.action.args["content"]
                for e in logs
            )

            participant_add_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "add_participant_to_conversation"
                and e.action.args["conversation_id"] == self.report_conversation_id
                and e.action.args["user_id"] == self.jordan_id
                for e in logs
            )

            title_changed = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "change_conversation_title"
                and "Jordan" in e.action.args["title"]
                and e.action.args["conversation_id"] == self.report_conversation_id
                for e in logs
            )

            welcome_message_sent = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "Welcome" in e.action.args["content"]
                and "Jordan" in e.action.args["content"]
                for e in logs
            )

            success = proposal_found and participant_add_found and title_changed and welcome_message_sent
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
