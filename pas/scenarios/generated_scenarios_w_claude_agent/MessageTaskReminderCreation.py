"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("message_task_reminder_creation")
class MessageTaskReminderCreation(PASScenario):
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
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Register user names and their IDs in the messaging app
        self.messaging.add_users(["Sarah", "Mom", "Alex"])

        # Create three separate conversations (one with each contact)
        # Each conversation starts empty - messages will arrive during the event flow
        sarah_id = self.messaging.name_to_id["Sarah"]
        mom_id = self.messaging.name_to_id["Mom"]
        alex_id = self.messaging.name_to_id["Alex"]

        # Create conversations between user and each contact
        sarah_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, sarah_id],
            title="Sarah",
            messages=[],
        )
        self.messaging.add_conversation(sarah_conv)

        mom_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, mom_id],
            title="Mom",
            messages=[],
        )
        self.messaging.add_conversation(mom_conv)

        alex_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, alex_id],
            title="Alex",
            messages=[],
        )
        self.messaging.add_conversation(alex_conv)

        # Initialize reminder app (starts empty, reminders will be created by agent)
        self.reminder = StatefulReminderApp(name="Reminders")

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.reminder]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment events: Three task request messages arrive from different contacts
            # Get conversation IDs from the app state
            sarah_id = messaging_app.name_to_id["Sarah"]
            mom_id = messaging_app.name_to_id["Mom"]
            alex_id = messaging_app.name_to_id["Alex"]

            # Find conversation IDs for each contact
            sarah_conv_id = None
            mom_conv_id = None
            alex_conv_id = None

            for conv_id, conv in messaging_app.conversations.items():
                if sarah_id in conv.participant_ids and len(conv.participant_ids) == 2:
                    sarah_conv_id = conv_id
                elif mom_id in conv.participant_ids and len(conv.participant_ids) == 2:
                    mom_conv_id = conv_id
                elif alex_id in conv.participant_ids and len(conv.participant_ids) == 2:
                    alex_conv_id = conv_id

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
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events (oracle events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent a proposal to the user
            # The proposal should be sent via PASAgentUserInterface.send_message_to_user
            proposal_found = False
            for e in agent_events:
                if e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user":
                    proposal_found = True
                    break

            # STRICT Check 2: Agent created three reminders
            # Each reminder creation should use StatefulReminderApp.add_reminder
            reminder_creation_count = 0
            for e in agent_events:
                if e.action.class_name == "StatefulReminderApp" and e.action.function_name == "add_reminder":
                    # Verify the reminder has required fields (title and due_datetime are non-empty)
                    args = e.action.args if e.action.args else e.action.resolved_args
                    if args.get("title") and args.get("due_datetime"):
                        reminder_creation_count += 1

            reminders_created = reminder_creation_count == 3

            # All strict checks must pass
            success = proposal_found and reminders_created

            if not success:
                # Build a rationale explaining what failed
                failures = []
                if not proposal_found:
                    failures.append("no agent proposal (send_message_to_user) found in log")
                if not reminders_created:
                    failures.append(f"expected 3 reminders created, found {reminder_creation_count}")

                rationale = "; ".join(failures)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
