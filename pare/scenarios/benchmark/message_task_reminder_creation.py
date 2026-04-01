from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.messaging_v2 import ConversationV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulMessagingApp,
)
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("message_task_reminder_creation")
class MessageTaskReminderCreation(PAREScenario):
    """Agent creates individual reminders from multiple incoming task requests via messages and confirms completion back to requesters.

    The user receives three separate messages asking them to handle errands: Sarah writes "Can you pick up my prescription from Walgreens tomorrow afternoon?", Mom sends "Don't forget to grab milk and eggs from the grocery store before dinner tonight", and Alex messages "Hey, need you to drop off that package at the post office by 5 PM today." The agent must:
    1. Detect incoming task requests across three different message conversations
    2. Extract task details (item/action, location, timing) from each message
    3. Create three separate reminders with appropriate due times: prescription pickup (tomorrow afternoon), grocery shopping (today evening), package drop-off (today 5 PM)
    4. Set reminder titles and descriptions that capture the task and location
    5. Send confirmation messages back to each person acknowledging their request and confirming the reminder was set

    This scenario exercises message-to-reminder task extraction, temporal parsing ("tomorrow afternoon", "tonight", "by 5 PM"), multi-reminder creation workflow, and closed-loop confirmation messaging to multiple participants.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Register user names and their IDs in the messaging app
        self.messaging.add_users(["Sarah", "Mom", "Alex"])

        # Create three separate conversations (one with each contact)
        # Each conversation starts empty - messages will arrive during the event flow
        # Store user IDs for use in build_events_flow
        self.sarah_id = self.messaging.name_to_id["Sarah"]
        self.mom_id = self.messaging.name_to_id["Mom"]
        self.alex_id = self.messaging.name_to_id["Alex"]

        # Create conversations between user and each contact
        sarah_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, self.sarah_id],
            title="Sarah",
            messages=[],
        )
        self.messaging.add_conversation(sarah_conv)
        # Store conversation_id for use in build_events_flow and validate
        self.sarah_conversation_id = sarah_conv.conversation_id

        mom_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, self.mom_id],
            title="Mom",
            messages=[],
        )
        self.messaging.add_conversation(mom_conv)
        # Store conversation_id for use in build_events_flow and validate
        self.mom_conversation_id = mom_conv.conversation_id

        alex_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, self.alex_id],
            title="Alex",
            messages=[],
        )
        self.messaging.add_conversation(alex_conv)
        # Store conversation_id for use in build_events_flow and validate
        self.alex_conversation_id = alex_conv.conversation_id

        # Initialize reminder app (starts empty, reminders will be created by agent)
        self.reminder = StatefulReminderApp(name="Reminders")

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment events: Three task request messages arrive from different contacts
            # Use stored user IDs and conversation IDs from init_and_populate_apps
            sarah_id = self.sarah_id
            mom_id = self.mom_id
            alex_id = self.alex_id
            sarah_conv_id = self.sarah_conversation_id
            mom_conv_id = self.mom_conversation_id
            alex_conv_id = self.alex_conversation_id

            # Environment event 1: Sarah requests prescription pickup tomorrow afternoon
            msg_sarah = messaging_app.create_and_add_message(
                conversation_id=sarah_conv_id,
                sender_id=sarah_id,
                content="Can you pick up my prescription from Walgreens tomorrow afternoon?",
            )

            # Environment event 2: Mom requests grocery shopping tonight (delayed by 5 seconds)
            msg_mom = messaging_app.create_and_add_message(
                conversation_id=mom_conv_id,
                sender_id=mom_id,
                content="Don't forget to grab milk and eggs from the grocery store before dinner tonight",
            ).delayed(2)

            # Environment event 3: Alex requests package drop-off by 5 PM today (delayed by 10 seconds)
            msg_alex = messaging_app.create_and_add_message(
                conversation_id=alex_conv_id,
                sender_id=alex_id,
                content="Hey, need you to drop off that package at the post office by 5 PM today.",
            ).delayed(3)

            # Oracle events: Agent detects messages and processes them
            # Agent reads the first conversation (Sarah) to understand the task request
            # Motivated by: incoming message notification from Sarah
            read_sarah = (
                messaging_app.read_conversation(conversation_id=sarah_conv_id, offset=0, limit=10)
                .oracle()
                .depends_on(msg_sarah, delay_seconds=2)
            )

            # Agent reads the second conversation (Mom) to understand the task request
            # Motivated by: incoming message notification from Mom
            read_mom = (
                messaging_app.read_conversation(conversation_id=mom_conv_id, offset=0, limit=10)
                .oracle()
                .depends_on(msg_mom, delay_seconds=2)
            )

            # Agent reads the third conversation (Alex) to understand the task request
            # Motivated by: incoming message notification from Alex
            read_alex = (
                messaging_app.read_conversation(conversation_id=alex_conv_id, offset=0, limit=10)
                .oracle()
                .depends_on(msg_alex, delay_seconds=2)
            )

            # Agent sends proposal to user after analyzing all three task requests
            # Proposal explicitly cites the triggering cues (the three messages)
            proposal = (
                aui.send_message_to_user(
                    content="I noticed you received three task requests: Sarah asked you to pick up her prescription from Walgreens tomorrow afternoon, Mom reminded you to grab milk and eggs from the grocery store before dinner tonight, and Alex needs you to drop off a package at the post office by 5 PM today. Would you like me to create reminders for these three tasks?"
                )
                .oracle()
                .depends_on([read_sarah, read_mom, read_alex], delay_seconds=3)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please create reminders for all three tasks.")
                .oracle()
                .depends_on(proposal, delay_seconds=2)
            )

            # Agent creates reminder 1: Prescription pickup tomorrow afternoon
            # This write action depends on user acceptance
            add_reminder_1 = (
                reminder_app.add_reminder(
                    title="Pick up Sarah's prescription",
                    due_datetime="2025-11-19 14:00:00",
                    description="Pick up prescription from Walgreens for Sarah",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=2)
            )

            # Agent creates reminder 2: Grocery shopping tonight
            # This write action depends on user acceptance
            add_reminder_2 = (
                reminder_app.add_reminder(
                    title="Grocery shopping for Mom",
                    due_datetime="2025-11-18 18:00:00",
                    description="Grab milk and eggs from the grocery store before dinner",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

            # Agent creates reminder 3: Package drop-off by 5 PM today
            # This write action depends on user acceptance
            add_reminder_3 = (
                reminder_app.add_reminder(
                    title="Drop off package for Alex",
                    due_datetime="2025-11-18 17:00:00",
                    description="Drop off package at the post office by 5 PM",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

            # Agent sends confirmation message to Sarah
            # Motivated by: User accepted proposal, reminders created, now confirm back to requester
            confirm_sarah = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=sarah_conv_id,
                    content="Got it! I've set a reminder to pick up your prescription from Walgreens tomorrow afternoon.",
                )
                .oracle()
                .depends_on(add_reminder_1, delay_seconds=1)
            )

            # Agent sends confirmation message to Mom
            # Motivated by: User accepted proposal, reminders created, now confirm back to requester
            confirm_mom = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=mom_conv_id,
                    content="No problem! I've set a reminder to grab milk and eggs from the grocery store before dinner tonight.",
                )
                .oracle()
                .depends_on(add_reminder_2, delay_seconds=1)
            )

            # Agent sends confirmation message to Alex
            # Motivated by: User accepted proposal, reminders created, now confirm back to requester
            confirm_alex = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=alex_conv_id,
                    content="Sure thing! I've set a reminder to drop off the package at the post office by 5 PM today.",
                )
                .oracle()
                .depends_on(add_reminder_3, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            msg_sarah,
            msg_mom,
            msg_alex,
            read_sarah,
            read_mom,
            read_alex,
            proposal,
            acceptance,
            add_reminder_1,
            add_reminder_2,
            add_reminder_3,
            confirm_sarah,
            confirm_mom,
            confirm_alex,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate final outcomes: reminders created and confirmations sent."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Three reminders created with valid title and due_datetime
            reminder_count = sum(
                1
                for e in agent_events
                if e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "add_reminder"
                and (e.action.resolved_args or e.action.args or {}).get("title")
                and (e.action.resolved_args or e.action.args or {}).get("due_datetime")
            )

            # Check 2: Confirmation messages sent to all three requesters
            target_conv_ids = {self.sarah_conversation_id, self.mom_conversation_id, self.alex_conversation_id}
            confirmation_count = sum(
                1
                for e in agent_events
                if e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and (e.action.resolved_args or e.action.args or {}).get("conversation_id") in target_conv_ids
            )

            success = reminder_count == 3 and confirmation_count == 3

            if not success:
                missing = []
                if reminder_count != 3:
                    missing.append(f"expected 3 reminders, found {reminder_count}")
                if confirmation_count != 3:
                    missing.append(f"expected 3 confirmations, found {confirmation_count}")
                return ScenarioValidationResult(success=False, rationale="; ".join(missing))

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
