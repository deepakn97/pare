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


@register_scenario("conflicting_reminder_negotiation")
class ConflictingReminderNegotiation(PAREScenario):
    """Agent negotiates consensus timing for a shared task when receiving conflicting reminder requests from multiple participants via messages.

    The user receives three messages about scheduling a "Team Video Recording" task. Jordan sends "Hey, can you set a reminder for our team video recording? We need to do it by Friday 3 PM." Then Casey messages "About the video recording—let's aim for Thursday evening around 7 PM so everyone's free." Finally, Alex writes "For the team video, I think Wednesday afternoon is better, maybe 2 PM? I'm traveling Thursday-Friday." The agent must:
    1. Detect three incoming messages requesting reminders for the same task ("Team Video Recording") but with different proposed times
    2. Parse and extract the conflicting time preferences: Friday 3 PM (Jordan), Thursday 7 PM (Casey), Wednesday 2 PM (Alex)
    3. Search existing reminders to check if "Team Video Recording" already exists
    4. Identify the scheduling conflict and determine that Wednesday 2 PM is earliest and accommodates Alex's travel constraint
    5. Create a single reminder for "Team Video Recording" set for Wednesday at 2 PM with a description listing all three participants
    6. Send individual reply messages to Jordan, Casey, and Alex explaining the consensus time choice and asking for confirmation

    This scenario exercises multi-message temporal parsing, conflict detection across incoming requests, reminder deduplication via search, single-reminder creation with compromise timing, and individualized reply generation to reconcile conflicting stakeholder preferences.
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

        # Add three contacts who will send conflicting reminder requests
        self.messaging.add_users(["Jordan", "Casey", "Alex"])

        # Create individual conversations for each contact (empty for now; messages arrive in Step 3)
        jordan_id = self.messaging.name_to_id["Jordan"]
        casey_id = self.messaging.name_to_id["Casey"]
        alex_id = self.messaging.name_to_id["Alex"]

        # Create empty conversations that will be populated by environment events in Step 3
        # Use current_user_id from app (automatically generated)
        jordan_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, jordan_id],
            title="Jordan",
        )
        casey_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, casey_id],
            title="Casey",
        )
        alex_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, alex_id],
            title="Alex",
        )

        self.messaging.add_conversation(jordan_conv)
        self.messaging.add_conversation(casey_conv)
        self.messaging.add_conversation(alex_conv)

        # Initialize reminder app (no baseline reminders; agent will create one in Step 3)
        self.reminder = StatefulReminderApp(name="Reminders")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        # Get conversation IDs and sender IDs from initialization
        jordan_id = messaging_app.name_to_id["Jordan"]
        casey_id = messaging_app.name_to_id["Casey"]
        alex_id = messaging_app.name_to_id["Alex"]

        jordan_conv_id = messaging_app.get_existing_conversation_ids([jordan_id])[0]
        casey_conv_id = messaging_app.get_existing_conversation_ids([casey_id])[0]
        alex_conv_id = messaging_app.get_existing_conversation_ids([alex_id])[0]

        with EventRegisterer.capture_mode():
            # Environment Event 1: Jordan requests reminder for Friday 3 PM
            jordan_message = messaging_app.create_and_add_message(
                conversation_id=jordan_conv_id,
                sender_id=jordan_id,
                content="Hey, can you set a reminder for our team video recording? We need to do it by Friday 3 PM.",
            ).delayed(5)

            # Environment Event 2: Casey requests reminder for Thursday 7 PM
            casey_message = messaging_app.create_and_add_message(
                conversation_id=casey_conv_id,
                sender_id=casey_id,
                content="About the video recording—let's aim for Thursday evening around 7 PM so everyone's free.",
            ).delayed(8)

            # Environment Event 3: Alex requests reminder for Wednesday 2 PM with travel constraint
            alex_message = messaging_app.create_and_add_message(
                conversation_id=alex_conv_id,
                sender_id=alex_id,
                content="For the team video, I think Wednesday afternoon is better, maybe 2 PM? I'm traveling Thursday-Friday.",
            ).delayed(10)

            # Agent reads Jordan's conversation to see the first request
            # Motivated by: Jordan's message arrived requesting a reminder
            read_jordan = (
                messaging_app.read_conversation(conversation_id=jordan_conv_id, offset=0, limit=10)
                .oracle()
                .depends_on(jordan_message, delay_seconds=2)
            )

            # Agent reads Casey's conversation to see the second request
            # Motivated by: Casey's message arrived with a conflicting time for the same task
            read_casey = (
                messaging_app.read_conversation(conversation_id=casey_conv_id, offset=0, limit=10)
                .oracle()
                .depends_on(casey_message, delay_seconds=2)
            )

            # Agent reads Alex's conversation to see the third request
            # Motivated by: Alex's message arrived with another conflicting time and a travel constraint
            read_alex = (
                messaging_app.read_conversation(conversation_id=alex_conv_id, offset=0, limit=10)
                .oracle()
                .depends_on(alex_message, delay_seconds=2)
            )

            # Agent searches for existing reminders to check for duplicates
            # Motivated by: agent needs to verify if "Team Video Recording" reminder already exists before creating a new one
            search_reminders = (
                reminder_app.get_all_reminders()
                .oracle()
                .depends_on([read_jordan, read_casey, read_alex], delay_seconds=3)
            )

            # Agent sends proposal to user explaining the conflict and suggesting Wednesday 2 PM consensus
            # Motivated by: three messages from Jordan/Casey/Alex requesting conflicting times for team video recording
            proposal = (
                aui.send_message_to_user(
                    content="I received messages from Jordan, Casey, and Alex about scheduling a team video recording. They suggested Friday 3 PM, Thursday 7 PM, and Wednesday 2 PM respectively. Since Alex mentioned traveling Thursday-Friday, I recommend Wednesday at 2 PM to accommodate everyone. Should I create a reminder for 'Team Video Recording' on Wednesday, November 20th at 2:00 PM and reply to Jordan, Casey, and Alex explaining the consensus time choice and asking for confirmation?"
                )
                .oracle()
                .depends_on(search_reminders, delay_seconds=2)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please create the reminder.")
                .oracle()
                .depends_on(proposal, delay_seconds=3)
            )

            # Agent creates the reminder for Wednesday 2 PM
            # Motivated by: user accepted the proposal to create the reminder
            create_reminder = (
                reminder_app.add_reminder(
                    title="Team Video Recording",
                    due_datetime="2025-11-20 14:00:00",
                    description="Team video recording task. Participants: Jordan, Casey, Alex. Scheduled for Wednesday to accommodate Alex's travel.",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=2)
            )

            # Agent sends reply to Jordan explaining the consensus
            # Motivated by: Jordan's original message requested the reminder; agent should confirm the chosen time
            reply_jordan = (
                messaging_app.send_message(
                    user_id=jordan_id,
                    content="I've set up the team video recording reminder for Wednesday at 2 PM to accommodate everyone's schedules. Alex will be traveling Thursday-Friday. Does this work for you?",
                )
                .oracle()
                .depends_on(create_reminder, delay_seconds=2)
            )

            # Agent sends reply to Casey explaining the consensus
            # Motivated by: Casey's original message requested the reminder; agent should confirm the chosen time
            reply_casey = (
                messaging_app.send_message(
                    user_id=casey_id,
                    content="I've scheduled the team video recording for Wednesday at 2 PM instead of Thursday evening, since Alex will be traveling Thursday-Friday. Please let me know if this works.",
                )
                .oracle()
                .depends_on(create_reminder, delay_seconds=2)
            )

            # Agent sends reply to Alex confirming his preferred time
            # Motivated by: Alex's original message requested the reminder; agent should confirm the chosen time
            reply_alex = (
                messaging_app.send_message(
                    user_id=alex_id,
                    content="I've created a reminder for the team video recording on Wednesday at 2 PM as you suggested. This should work before your travel. Thanks for flagging the conflict!",
                )
                .oracle()
                .depends_on(create_reminder, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            jordan_message,
            casey_message,
            alex_message,
            read_jordan,
            read_casey,
            read_alex,
            search_reminders,
            proposal,
            acceptance,
            create_reminder,
            reply_jordan,
            reply_casey,
            reply_alex,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1 (STRICT): Agent created the reminder
            create_reminder_found = any(
                e.action.class_name == "StatefulReminderApp" and e.action.function_name == "add_reminder"
                for e in agent_events
            )

            # Check 2 (STRICT): Agent sent reply messages to all three participants
            # Count the number of send_message calls (should be at least 3)
            send_message_count = sum(
                1
                for e in agent_events
                if e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["send_message", "send_message_to_group_conversation"]
            )
            all_replies_sent = send_message_count >= 3

            # Determine success based on core checks
            success = create_reminder_found and all_replies_sent

            # Build rationale for failures
            if not success:
                failures = []
                if not create_reminder_found:
                    failures.append("reminder for 'Team Video Recording' not created")
                if not all_replies_sent:
                    failures.append(f"not all three reply messages sent (found {send_message_count}, expected 3)")

                rationale = "; ".join(failures)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
