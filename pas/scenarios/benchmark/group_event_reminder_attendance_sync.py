from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
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


@register_scenario("group_event_reminder_attendance_sync")
class GroupEventReminderAttendanceSync(PASScenario):
    """Agent synchronizes group event attendance changes from messaging conversations back into reminder system to maintain accurate headcount.

    The user has a reminder set for "Team Potluck Dinner" scheduled for tomorrow at 6 PM with a note listing five confirmed attendees. Three separate message conversations bring updates: Jordan writes "Sorry, can't make the potluck tomorrow—family emergency," Taylor messages "Hey, bringing my partner to the dinner, hope that's ok!", and Casey sends "I'll be 30 minutes late, start without me." The agent must:
    1. Detect incoming attendance changes across three different messaging threads
    2. Read the existing "Team Potluck Dinner" reminder and parse the current attendee list
    3. Compute the updated attendance: remove Jordan, add Taylor's partner (net +1 guest), note Casey's delayed arrival
    4. Propose editing the reminder to reflect the new headcount and timing notes
    5. After user acceptance, update the reminder description with revised attendee list and Casey's late arrival note
    6. Send confirmation messages back to each person acknowledging their update

    This scenario exercises cross-app state reconciliation between messaging and reminders, attendance delta computation, reminder editing workflow, and closed-loop confirmation messaging to multiple participants.

    ---.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Initialize Reminder app
        self.reminder = StatefulReminderApp(name="Reminders")

        # Add users to messaging app - this will automatically set up id_to_name and name_to_id
        self.messaging.add_users(["Jordan", "Taylor", "Casey"])
        # Save user IDs as instance variables for use in build_events_flow and validate
        self.jordan_id = self.messaging.name_to_id["Jordan"]
        self.taylor_id = self.messaging.name_to_id["Taylor"]
        self.casey_id = self.messaging.name_to_id["Casey"]
        # current_user_id is automatically set by StatefulMessagingApp

        # Create individual conversations with each person (seeding baseline history)
        # Jordan conversation - older messages from planning
        jordan_conv_id = "jordan_conv_id"
        jordan_conv = ConversationV2(
            conversation_id=jordan_conv_id,
            participant_ids=["user_id", self.jordan_id],
            title="Jordan",
            messages=[
                MessageV2(
                    sender_id="user_id",
                    content="Hey Jordan, are you coming to the team potluck tomorrow?",
                    timestamp=datetime(2025, 11, 17, 14, 0, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=self.jordan_id,
                    content="Yes, I'll be there! Looking forward to it.",
                    timestamp=datetime(2025, 11, 17, 14, 15, 0, tzinfo=UTC).timestamp(),
                ),
            ],
            last_updated=datetime(2025, 11, 17, 14, 15, 0, tzinfo=UTC).timestamp(),
        )
        self.messaging.add_conversation(jordan_conv)

        # Taylor conversation - older messages from planning
        taylor_conv_id = "taylor_conv_id"
        taylor_conv = ConversationV2(
            conversation_id=taylor_conv_id,
            participant_ids=["user_id", self.taylor_id],
            title="Taylor",
            messages=[
                MessageV2(
                    sender_id="user_id",
                    content="Taylor, see you at the potluck tomorrow at 6!",
                    timestamp=datetime(2025, 11, 17, 15, 0, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=self.taylor_id,
                    content="Absolutely! Can't wait.",
                    timestamp=datetime(2025, 11, 17, 15, 10, 0, tzinfo=UTC).timestamp(),
                ),
            ],
            last_updated=datetime(2025, 11, 17, 15, 10, 0, tzinfo=UTC).timestamp(),
        )
        self.messaging.add_conversation(taylor_conv)

        # Casey conversation - older messages from planning
        casey_conv_id = "casey_conv_id"
        casey_conv = ConversationV2(
            conversation_id=casey_conv_id,
            participant_ids=["user_id", self.casey_id],
            title="Casey",
            messages=[
                MessageV2(
                    sender_id="user_id",
                    content="Casey, reminder about the potluck tomorrow evening!",
                    timestamp=datetime(2025, 11, 17, 16, 0, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=self.casey_id,
                    content="Got it, thanks! See you there.",
                    timestamp=datetime(2025, 11, 17, 16, 5, 0, tzinfo=UTC).timestamp(),
                ),
            ],
            last_updated=datetime(2025, 11, 17, 16, 5, 0, tzinfo=UTC).timestamp(),
        )
        self.messaging.add_conversation(casey_conv)

        # Create the Team Potluck Dinner reminder with attendee list
        # Tomorrow at 6 PM = Nov 19, 2025 18:00:00 UTC
        self.reminder.add_reminder(
            title="Team Potluck Dinner",
            due_datetime="2025-11-19 18:00:00",
            description="Team potluck at the office. Confirmed attendees: Jordan, Taylor, Casey, Alex, Morgan (5 people total)",
            repetition_unit=None,
            repetition_value=None,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Jordan sends cancellation message (family emergency)
            jordan_message_event = messaging_app.create_and_add_message(
                conversation_id="jordan_conv_id",
                sender_id=self.jordan_id,
                content="Sorry, can't make the potluck tomorrow—family emergency",
            ).delayed(30)

            # Environment Event 2: Taylor sends message about bringing partner
            taylor_message_event = messaging_app.create_and_add_message(
                conversation_id="taylor_conv_id",
                sender_id=self.taylor_id,
                content="Hey, bringing my partner to the dinner, hope that's ok!",
            ).delayed(45)

            # Environment Event 3: Casey sends message about being late
            casey_message_event = messaging_app.create_and_add_message(
                conversation_id="casey_conv_id",
                sender_id=self.casey_id,
                content="I'll be 30 minutes late, start without me",
            ).delayed(60)

            # Oracle Event 1: Agent reads all reminders to locate the potluck reminder
            # Motivated by: the agent needs to verify the current attendee list before proposing changes
            get_reminders_event = (
                reminder_app.get_all_reminders().oracle().depends_on(casey_message_event, delay_seconds=5)
            )

            # Oracle Event 2: Agent proposes updating the reminder with attendance changes
            # Motivated by: three attendance-related messages (Jordan canceling, Taylor +1, Casey late) have arrived
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed attendance updates for tomorrow's Team Potluck Dinner:\n- Jordan can't attend (family emergency)\n- Taylor is bringing a partner (+1 guest)\n- Casey will be 30 minutes late\n\nShould I update the reminder to reflect the revised headcount and timing note?"
                )
                .oracle()
                .depends_on(get_reminders_event, delay_seconds=2)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please update the reminder.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 4: Agent deletes the old reminder
            # Motivated by: user accepted the proposal; need to remove old reminder before creating updated one
            delete_reminder_event = (
                reminder_app.delete_reminder(reminder_id="potluck_reminder_id")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent adds updated reminder with new attendance info
            # Motivated by: old reminder deleted; now create new one with revised attendee list
            add_reminder_event = (
                reminder_app.add_reminder(
                    title="Team Potluck Dinner",
                    due_datetime="2025-11-19 18:00:00",
                    description="Team potluck at the office. Confirmed attendees: Taylor, Taylor's partner, Casey (arriving 30 min late), Alex, Morgan (5 people total). Jordan unable to attend.",
                    repetition_unit=None,
                    repetition_value=None,
                )
                .oracle()
                .depends_on(delete_reminder_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent sends confirmation to Jordan
            # Motivated by: reminder updated; agent should acknowledge Jordan's cancellation
            jordan_confirmation_event = (
                messaging_app.send_message(
                    user_id=self.jordan_id,
                    content="Thanks for letting me know, Jordan. I've updated the potluck attendance. Hope everything's okay with your family.",
                )
                .oracle()
                .depends_on(add_reminder_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent sends confirmation to Taylor
            # Motivated by: reminder updated; agent should confirm Taylor's +1 is noted
            taylor_confirmation_event = (
                messaging_app.send_message(
                    user_id=self.taylor_id,
                    content="Great! I've updated the reminder to include your partner for the potluck.",
                )
                .oracle()
                .depends_on(add_reminder_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent sends confirmation to Casey
            # Motivated by: reminder updated; agent should acknowledge Casey's late arrival
            casey_confirmation_event = (
                messaging_app.send_message(
                    user_id=self.casey_id,
                    content="No problem, Casey! I've noted you'll be arriving 30 minutes late to the potluck.",
                )
                .oracle()
                .depends_on(add_reminder_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            jordan_message_event,
            taylor_message_event,
            casey_message_event,
            get_reminders_event,
            proposal_event,
            acceptance_event,
            delete_reminder_event,
            add_reminder_event,
            jordan_confirmation_event,
            taylor_confirmation_event,
            casey_confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Agent proposes updating the reminder
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check 2: Agent deletes old reminder and adds updated one
            delete_found = any(
                e.action.class_name == "StatefulReminderApp" and e.action.function_name == "delete_reminder"
                for e in agent_events
            )
            add_found = any(
                e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "add_reminder"
                and (e.action.args or e.action.resolved_args or {}).get("title") == "Team Potluck Dinner"
                for e in agent_events
            )

            # Check 3: Agent sends confirmations to all three participants
            message_recipients = {
                (e.action.args or e.action.resolved_args or {}).get("user_id")
                for e in agent_events
                if e.action.class_name == "StatefulMessagingApp" and e.action.function_name == "send_message"
            }
            expected_recipients = {self.jordan_id, self.taylor_id, self.casey_id}
            confirmations_sent = expected_recipients.issubset(message_recipients)

            success = proposal_found and delete_found and add_found and confirmations_sent

            if not success:
                failed = []
                if not proposal_found:
                    failed.append("no proposal sent")
                if not delete_found:
                    failed.append("old reminder not deleted")
                if not add_found:
                    failed.append("updated reminder not added")
                if not confirmations_sent:
                    missing = expected_recipients - message_recipients
                    failed.append(f"missing confirmations to: {missing}")
                return ScenarioValidationResult(success=False, rationale="; ".join(failed))

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
