"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulMessagingApp,
)
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("reminder_context_recovery_from_messages")
class ReminderContextRecoveryFromMessages(PAREScenario):
    """Agent enriches an incomplete reminder by searching message history for context.

    The user has created a reminder titled "Follow up with Sarah Chen" due tomorrow, but the description is empty. Sarah
    sends a message asking for the follow-up, mentioning that the user planned to follow up tomorrow (i.e., a reminder).
    The agent must:
    1. Search all reminders to find the one mentioning "Sarah"
    2. List recent conversations with Sarah and read the recent thread to recover what the follow-up is about
    3. Extract the relevant context (e.g., Q4 budget proposal feedback)
    4. Send a message to the user summarizing the recovered context so they can respond (and optionally update the
       reminder description themselves)

    This scenario exercises reminder lookup, conversation history retrieval (`list_conversations_by_participant`,
    `read_conversation` with date filters), and using message history as a data source to restore context for an
    incomplete reminder.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")
        # current_user_id and current_user_name are already populated by StatefulMessagingApp
        user_id = self.messaging.current_user_id

        # Add Sarah Chen as a contact using add_users
        self.messaging.add_users(["Sarah Chen"])
        self.sarah_id = self.messaging.name_to_id["Sarah Chen"]

        # Seed message history: conversation with Sarah from last week about Q4 budget proposal
        # These messages occurred before the scenario start_time (Nov 18, 2025 09:00)
        # Conversations occurred around Nov 11-12, 2025 (one week before)
        self.conv_id = "conv_sarah_001"
        conversation_with_sarah = ConversationV2(
            conversation_id=self.conv_id,
            participant_ids=[user_id, self.sarah_id],
            title="Sarah Chen",
            messages=[
                MessageV2(
                    sender_id=self.sarah_id,
                    message_id="msg_001",
                    timestamp=datetime(2025, 11, 11, 14, 30, 0, tzinfo=UTC).timestamp(),
                    content="Hey! Did you get a chance to look at the Q4 budget proposal draft I sent over?",
                ),
                MessageV2(
                    sender_id=user_id,
                    message_id="msg_002",
                    timestamp=datetime(2025, 11, 11, 14, 45, 0, tzinfo=UTC).timestamp(),
                    content="Yes, I reviewed it. I have some thoughts on the resource allocation section.",
                ),
                MessageV2(
                    sender_id=self.sarah_id,
                    message_id="msg_003",
                    timestamp=datetime(2025, 11, 11, 15, 0, 0, tzinfo=UTC).timestamp(),
                    content="Great! Can we discuss it soon? I need to finalize this by the end of next week.",
                ),
                MessageV2(
                    sender_id=user_id,
                    message_id="msg_004",
                    timestamp=datetime(2025, 11, 12, 10, 15, 0, tzinfo=UTC).timestamp(),
                    content="Sure, let me follow up with you on this soon with my detailed feedback.",
                ),
            ],
            last_updated=datetime(2025, 11, 12, 10, 15, 0, tzinfo=UTC).timestamp(),
        )
        self.messaging.add_conversation(conversation_with_sarah)

        # Initialize reminder app
        self.reminder = StatefulReminderApp(name="Reminders")
        # Add a bare-bones reminder about following up with Sarah (created before scenario starts)
        # Due date is tomorrow (Nov 19, 2025 at 10:00)
        reminder_due_date = datetime(2025, 11, 19, 10, 0, 0, tzinfo=UTC).strftime("%Y-%m-%d %H:%M:%S")
        self.reminder.add_reminder(
            title="Follow up with Sarah Chen",
            due_datetime=reminder_due_date,
            description="",  # Empty description - agent needs to enrich this
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.reminder]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Sarah messages the user asking for a follow-up
            # This is the exogenous trigger: Sarah prompts the user, and the agent helps recover the reminder context.
            sarah_message_event = messaging_app.create_and_add_message(
                conversation_id=self.conv_id,
                sender_id=self.sarah_id,
                content="Hey — quick reminder: you mentioned you'd follow up with me tomorrow about the Q4 budget proposal draft. Can you send your detailed feedback?",
            ).delayed(2)

            # Oracle Event 1: Agent proposes checking reminders + message history to recover the follow-up context
            # Motivated by: Sarah explicitly references a "reminder" / planned follow-up tomorrow.
            proposal_event = (
                aui.send_message_to_user(
                    content="Sarah just pinged you and referenced that you planned to follow up tomorrow. Want me to check your reminders and your recent messages with her to recover the exact follow-up context?"
                )
                .oracle()
                .depends_on(sarah_message_event, delay_seconds=2)
            )

            # Oracle Event 2: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please check and remind me what I need to follow up on.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent searches for reminders
            # Motivated by: user accepted; agent starts by locating the relevant reminder that mentions Sarah.
            search_reminders_event = (
                reminder_app.get_all_reminders().oracle().depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent lists conversations to find the one with Sarah
            # Motivated by: Sarah asked for a follow-up; need recent message context to know what to follow up on.
            list_conversations_event = (
                messaging_app.list_conversations_by_participant(
                    user_id=self.sarah_id,
                    offset=0,
                    limit=5,
                    offset_recent_messages_per_conversation=0,
                    limit_recent_messages_per_conversation=5,
                )
                .oracle()
                .depends_on(search_reminders_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent reads the full conversation with Sarah to extract context
            # Motivated by: found conversations with Sarah; now need to read messages to understand what needs follow-up
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id=self.conv_id,
                    offset=0,
                    limit=10,
                    min_date="2025-11-11 00:00:00",
                    max_date="2025-11-18 23:59:59",
                )
                .oracle()
                .depends_on(list_conversations_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent sends enriched context directly to the user
            # Motivated by: found reminder and extracted context from Sarah's messages about Q4 budget proposal
            context_message_event = (
                aui.send_message_to_user(
                    content='I found your reminder "Follow up with Sarah Chen" (due tomorrow at 10:00 AM). Looking at your recent messages with Sarah from last week, you discussed the Q4 budget proposal and she\'s waiting for your detailed feedback on the resource allocation section. She mentioned needing to finalize this by end of next week.'
                )
                .oracle()
                .depends_on(read_conversation_event, delay_seconds=3)
            )

        self.events = [
            sarah_message_event,
            proposal_event,
            acceptance_event,
            search_reminders_event,
            list_conversations_event,
            read_conversation_event,
            context_message_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1 (STRICT): Agent searched for reminders containing Sarah
            # The agent must retrieve reminders to find the one about Sarah Chen
            search_reminders_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "get_all_reminders"
                for e in log_entries
            )

            # Check 2 (STRICT): Agent proposed help to check reminders/messages (motivated by Sarah's ping)
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 3 (STRICT): Agent listed conversations with Sarah Chen to find message history
            # The agent must access Sarah's conversations to recover context
            # Accept either list_conversations_by_participant or search_conversations as equivalent ways to find Sarah's messages
            list_conversations_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["list_conversations_by_participant", "search_conversations"]
                for e in log_entries
            )

            # Check 4 (STRICT): Agent read the conversation with Sarah to extract context
            # The agent must read message content to understand what needs follow-up
            read_conversation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                for e in log_entries
            )

            # Check 5 (STRICT on presence, FLEXIBLE on exact wording): Agent sent context message to user
            # The agent must communicate the recovered context, but the exact phrasing can vary
            # We only verify that a message was sent, without constraining the exact content
            context_message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            success = (
                search_reminders_found
                and proposal_found
                and list_conversations_found
                and read_conversation_found
                and context_message_found
            )

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not search_reminders_found:
                    missing_checks.append("agent did not search reminders")
                if not proposal_found:
                    missing_checks.append("agent did not propose checking reminders/messages")
                if not list_conversations_found:
                    missing_checks.append("agent did not list conversations with Sarah")
                if not read_conversation_found:
                    missing_checks.append("agent did not read conversation to extract context")
                if not context_message_found:
                    missing_checks.append("agent did not send context message to user")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
