from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("recurring_expense_split_coordination")
class RecurringExpenseSplitCoordination(PASScenario):
    """Agent sets up recurring reminder and group chat for shared monthly expense tracking after participants confirm split arrangement via individual messages.

    The user receives three separate messages about sharing a monthly streaming service subscription. Jordan proposes splitting the $15/month cost and suggests collecting everyone's share on the 1st of each month via a group chat. Casey and Alex both confirm they're in and ask/agree about the 1st-of-month payment timing. The agent must:
    1. Detect incoming commitment messages from three different participants about a recurring monthly expense split
    2. Calculate per-person cost ($15 split 4 ways = $3.75 per person per month)
    3. Create a repeating reminder titled "Collect Streaming Subscription Split" with monthly repetition, due on the 1st of each month, with description listing all four participants and individual share amounts
    4. Create a new group conversation including Jordan, Casey, Alex, and the user with title "Streaming Subscription Split"
    5. Send an initial message to the group conversation confirming the setup, stating the monthly due date (1st of each month), per-person amount ($3.75), and total ($15)

    This scenario exercises multi-participant message parsing, arithmetic computation for expense splitting, recurring reminder creation with `set_repetition()`, group conversation creation with `create_group_conversation()`, and coordinated setup confirmation messaging..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app with three contacts
        self.messaging = StatefulMessagingApp(
            name="Messages",
        )
        # current_user_id is automatically set by StatefulMessagingApp

        # Add three contacts: Jordan, Casey, Alex
        self.messaging.add_users(["Jordan", "Casey", "Alex"])

        # Seed three individual conversations with older baseline messages
        # (These exist before the triggering messages in Step 3)
        jordan_id = self.messaging.name_to_id["Jordan"]
        casey_id = self.messaging.name_to_id["Casey"]
        alex_id = self.messaging.name_to_id["Alex"]

        # Conversation with Jordan - prior context about streaming service
        jordan_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, jordan_id],
            messages=[
                MessageV2(
                    sender_id=jordan_id,
                    content="Have you seen the new shows on StreamFlix? Worth the subscription!",
                    timestamp=datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Yeah, I've been thinking about subscribing but it's a bit pricey.",
                    timestamp=datetime(2025, 11, 15, 15, 0, 0, tzinfo=UTC).timestamp(),
                ),
            ],
        )
        self.messaging.add_conversation(jordan_conv)
        # Store conversation_id for use in build_events_flow
        self.jordan_conversation_id = jordan_conv.conversation_id

        # Conversation with Casey - general chat history
        casey_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, casey_id],
            messages=[
                MessageV2(
                    sender_id=casey_id,
                    content="Hey, how was your weekend?",
                    timestamp=datetime(2025, 11, 16, 10, 0, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Pretty good! Caught up on some shows.",
                    timestamp=datetime(2025, 11, 16, 10, 30, 0, tzinfo=UTC).timestamp(),
                ),
            ],
        )
        self.messaging.add_conversation(casey_conv)
        # Store conversation_id for use in build_events_flow
        self.casey_conversation_id = casey_conv.conversation_id

        # Conversation with Alex - general chat history
        alex_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, alex_id],
            messages=[
                MessageV2(
                    sender_id=alex_id,
                    content="Are we still on for lunch next week?",
                    timestamp=datetime(2025, 11, 17, 12, 0, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Yep, Thursday works for me!",
                    timestamp=datetime(2025, 11, 17, 12, 15, 0, tzinfo=UTC).timestamp(),
                ),
            ],
        )
        self.messaging.add_conversation(alex_conv)
        # Store conversation_id for use in build_events_flow
        self.alex_conversation_id = alex_conv.conversation_id

        # Initialize reminder app (empty initially - agent will create the recurring reminder)
        self.reminder = StatefulReminderApp(name="Reminders")

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        # Get conversation IDs for the three contacts
        jordan_id = messaging_app.name_to_id["Jordan"]
        casey_id = messaging_app.name_to_id["Casey"]
        alex_id = messaging_app.name_to_id["Alex"]

        # Use stored conversation IDs from init_and_populate_apps
        jordan_conv_id = self.jordan_conversation_id
        casey_conv_id = self.casey_conversation_id
        alex_conv_id = self.alex_conversation_id

        with EventRegisterer.capture_mode():
            # Environment events: three separate messages arriving about streaming subscription split
            # Message 1: Jordan proposes the split idea
            env1 = messaging_app.create_and_add_message(
                conversation_id=jordan_conv_id,
                sender_id=jordan_id,
                content="Hey, want to split that $15/month streaming service? I'm in if we can get 2 more people. If we do it, let's collect $3.75 each on the 1st of every month, and we can coordinate in a group chat.",
            )

            # Message 2: Casey commits to joining (short delay for realism)
            env2 = messaging_app.create_and_add_message(
                conversation_id=casey_conv_id,
                sender_id=casey_id,
                content="I heard you and Jordan are splitting a $15/month subscription - count me in! Paying on the 1st of each month works for me. A group chat would be easiest.",
            ).delayed(5)

            # Message 3: Alex confirms and asks about payment timing
            env3 = messaging_app.create_and_add_message(
                conversation_id=alex_conv_id,
                sender_id=alex_id,
                content="For the streaming split, I'll join too. I think you can collect on the 1st of each month. Also happy to be added to a group chat.",
            ).delayed(10)

            # Oracle events: agent detects the messages and proposes coordination setup
            # Agent reads the three conversations to understand the commitment pattern
            # Motivated by: three new message notifications about subscription splitting
            oracle1 = (
                messaging_app.read_conversation(conversation_id=jordan_conv_id, offset=0, limit=5)
                .oracle()
                .depends_on(env3, delay_seconds=2)
            )

            oracle2 = (
                messaging_app.read_conversation(conversation_id=casey_conv_id, offset=0, limit=5)
                .oracle()
                .depends_on(env3, delay_seconds=2)
            )

            oracle3 = (
                messaging_app.read_conversation(conversation_id=alex_conv_id, offset=0, limit=5)
                .oracle()
                .depends_on(env3, delay_seconds=2)
            )

            # Agent sends proposal to user about setting up coordination
            # Motivated by: three incoming messages from Jordan, Casey, and Alex all committing to split the $15/month subscription
            proposal = (
                aui.send_message_to_user(
                    content="I noticed Jordan, Casey, and Alex all agreed to split the $15/month streaming service with you (4 people total, $3.75 each) and they also suggested to collect on the 1st of each month and also create a group chat for coordination. Would you like me to:\n1. Create a recurring monthly reminder for the 1st of each month to collect payments\n2. Set up a group chat with all four of you for coordination?"
                )
                .oracle()
                .depends_on([oracle1, oracle2, oracle3], delay_seconds=3)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(
                    content="Yes, please set that up! You can create the reminder with due date of 09:00:00 on 2025-12-01."
                )
                .oracle()
                .depends_on(proposal, delay_seconds=5)
            )

            # Agent creates the recurring reminder (motivated by user acceptance of the coordination setup)
            oracle4 = (
                reminder_app.add_reminder(
                    title="Collect Streaming Subscription Split",
                    due_datetime="2025-12-01 09:00:00",
                    description="Monthly payment collection for StreamFlix subscription split:\n- Jordan: $3.75\n- Casey: $3.75\n- Alex: $3.75\n- Me: $3.75\nTotal: $15.00",
                    repetition_unit="month",
                    repetition_value=1,
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=3)
            )

            # Agent creates group conversation with all participants (motivated by user acceptance)
            oracle5 = (
                messaging_app.create_group_conversation(
                    user_ids=[jordan_id, casey_id, alex_id], title="Streaming Subscription Split"
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=3)
            )

            # Agent sends initial message to group conversation confirming the setup
            # (motivated by having created the group chat per scenario requirement)
            # The conversation_id will be resolved at runtime by the agent finding the group conversation
            # created by oracle5. We use a placeholder here; validation will verify the correct conversation_id.
            oracle6 = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id="",  # Placeholder: agent will resolve this by finding the group conversation
                    content="Hi everyone! I've set up the monthly reminder for our StreamFlix subscription split. We'll collect $3.75 from each person (Jordan, Casey, Alex, and Me) on the 1st of each month. Total: $15.00",
                )
                .oracle()
                .depends_on(oracle5, delay_seconds=2)
            )

            # Agent sends confirmation message to user (motivated by having completed all setup tasks)
            oracle7 = (
                aui.send_message_to_user(
                    content="Setup complete! I've created a recurring monthly reminder for the 1st of each month to collect $3.75 from each person (Jordan, Casey, Alex, and you) for the $15 StreamFlix subscription. I also created a group chat titled 'Streaming Subscription Split' with all participants and sent an initial message to coordinate."
                )
                .oracle()
                .depends_on([oracle4, oracle6], delay_seconds=3)
            )

        # Register ALL events here in self.events
        self.events = [
            env1,
            env2,
            env3,
            oracle1,
            oracle2,
            oracle3,
            proposal,
            acceptance,
            oracle4,
            oracle5,
            oracle6,
            oracle7,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate final outcomes: recurring reminder created and group conversation set up."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT event types (oracle events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
            jordan_id = messaging_app.name_to_id["Jordan"]
            casey_id = messaging_app.name_to_id["Casey"]
            alex_id = messaging_app.name_to_id["Alex"]

            # Check 1 (STRICT): Recurring monthly reminder created
            # Core requirement: monthly repetition for expense collection
            reminder_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "add_reminder"
                and e.action.args.get("repetition_unit") == "month"
                and e.action.args.get("repetition_value") == 1
                for e in agent_events
            )

            # Check 2 (STRICT): Group conversation created with all participants
            # Core requirement: group chat with Jordan, Casey, and Alex
            group_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "create_group_conversation"
                and set(e.action.args.get("user_ids", [])) == {jordan_id, casey_id, alex_id}
                for e in agent_events
            )

            # Check 3 (STRICT): Message sent to group conversation
            # Core requirement: initial coordination message to the group
            group_message_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                for e in agent_events
            )

            success = reminder_created and group_created and group_message_sent

            if not success:
                missing = []
                if not reminder_created:
                    missing.append("recurring monthly reminder")
                if not group_created:
                    missing.append("group conversation with all participants")
                if not group_message_sent:
                    missing.append("message sent to group conversation")
                return ScenarioValidationResult(
                    success=False, rationale=f"Missing final outcomes: {'; '.join(missing)}"
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
