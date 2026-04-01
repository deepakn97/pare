"""Scenario: Agent coordinates study group scheduling from separate conversations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCalendarApp,
    StatefulMessagingApp,
)
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("study_group_availability_synthesis")
class StudyGroupAvailabilitySynthesis(PAREScenario):
    """Agent coordinates study group scheduling by synthesizing availability constraints from separate one-on-one message conversations. The user is organizing a study session for an upcoming exam and receives individual messages from three classmates (Jordan Lee, Casey Morgan, and Alex Rivera) in three separate conversations, each stating their available time windows over the next few days. Jordan can meet "Tuesday afternoon or Wednesday morning," Casey says "I'm free Tuesday after 2 PM or Thursday anytime," and Alex mentions "Tuesday works best for me, anytime after 3 PM." The agent must: 1. Parse availability statements from three independent conversations. 2. Identify the overlapping time window that accommodates all four participants (Tuesday afternoon starting at 3 PM). 3. Create a calendar event titled "Study Group - Exam Prep" for Tuesday at 3:00 PM with all three classmates as attendees. 4. Send individual confirmation messages to each participant in their respective conversations stating the finalized time.

    This scenario exercises multi-conversation information aggregation without group chat, temporal constraint satisfaction across disconnected messaging threads, availability inference from natural language expressions, calendar event creation with synthesized participant list, and individualized follow-up communication to close the coordination loop with each stakeholder separately..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You are coordinating a study group with three classmates: Jordan, Casey, and Alex.
Wait for all three to respond with their availability before accepting any scheduling proposal.
Only accept if the proposed time works for everyone based on their stated availability."""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add users and get their IDs using proper app methods
        self.messaging.add_users(["Jordan Lee", "Casey Morgan", "Alex Rivera"])
        self.jordan_id = self.messaging.get_user_id("Jordan Lee")
        self.casey_id = self.messaging.get_user_id("Casey Morgan")
        self.alex_id = self.messaging.get_user_id("Alex Rivera")

        if self.jordan_id is None or self.casey_id is None or self.alex_id is None:
            raise RuntimeError("Failed to get user IDs for classmates")

        # Create three separate 1:1 conversations with prior history (user asked about availability)
        jordan_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, self.jordan_id],
            title="Jordan Lee",
            messages=[
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Hey Jordan, we should organize a study group for the exam next week. When are you free?",
                    timestamp=datetime(2025, 11, 17, 14, 0, 0, tzinfo=UTC).timestamp(),
                )
            ],
        )

        casey_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, self.casey_id],
            title="Casey Morgan",
            messages=[
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Hi Casey! Trying to set up a study session for the exam. What times work for you?",
                    timestamp=datetime(2025, 11, 17, 15, 0, 0, tzinfo=UTC).timestamp(),
                )
            ],
        )

        alex_conv = ConversationV2(
            participant_ids=[self.messaging.current_user_id, self.alex_id],
            title="Alex Rivera",
            messages=[
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Alex, want to join the study group for next week's exam? Let me know when you're available.",
                    timestamp=datetime(2025, 11, 17, 16, 0, 0, tzinfo=UTC).timestamp(),
                )
            ],
        )

        self.messaging.add_conversation(jordan_conv)
        self.messaging.add_conversation(casey_conv)
        self.messaging.add_conversation(alex_conv)

        # Store conversation IDs for use in build_events_flow
        self.jordan_conv_id = jordan_conv.conversation_id
        self.casey_conv_id = casey_conv.conversation_id
        self.alex_conv_id = alex_conv.conversation_id

        # Initialize calendar app with baseline event
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.calendar.add_calendar_event(
            title="Class Lecture",
            start_datetime="2025-11-18 10:00:00",
            end_datetime="2025-11-18 11:30:00",
            location="Room 301",
            description="Regular class session",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.calendar]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Jordan responds with availability
            jordan_msg_event = messaging_app.create_and_add_message(
                conversation_id=self.jordan_conv_id,
                sender_id=self.jordan_id,
                content="Sure! I can do Tuesday afternoon or Wednesday morning. Let me know what works!",
            ).delayed(15)

            # Environment Event 2: Casey responds with availability
            casey_msg_event = messaging_app.create_and_add_message(
                conversation_id=self.casey_conv_id,
                sender_id=self.casey_id,
                content="I'm free Tuesday after 2 PM or Thursday anytime. Whatever works for everyone!",
            ).delayed(18)

            # Environment Event 3: Alex responds with availability
            alex_msg_event = messaging_app.create_and_add_message(
                conversation_id=self.alex_conv_id,
                sender_id=self.alex_id,
                content="Tuesday works best for me, anytime after 3 PM. Looking forward to studying together!",
            ).delayed(22)

            # Oracle Event 1: Agent reads Jordan's conversation to extract availability
            jordan_read_event = (
                messaging_app.read_conversation(conversation_id=self.jordan_conv_id, offset=0, limit=10)
                .oracle()
                .depends_on(alex_msg_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent reads Casey's conversation to extract availability
            casey_read_event = (
                messaging_app.read_conversation(conversation_id=self.casey_conv_id, offset=0, limit=10)
                .oracle()
                .depends_on(jordan_read_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent reads Alex's conversation to extract availability
            alex_read_event = (
                messaging_app.read_conversation(conversation_id=self.alex_conv_id, offset=0, limit=10)
                .oracle()
                .depends_on(casey_read_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent proposes scheduling the study session
            proposal_event = (
                aui.send_message_to_user(
                    content="I've received availability updates from Jordan, Casey, and Alex for the study group. The overlapping time that works for all three is Tuesday at 3:00 PM. Would you like me to create a calendar event titled 'Study Group - Exam Prep' for Tuesday, November 19, 2025 at 3:00 PM and send confirmations to everyone?"
                )
                .oracle()
                .depends_on(alex_read_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please schedule it and let everyone know.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent creates calendar event
            calendar_event = (
                calendar_app.add_calendar_event(
                    title="Study Group - Exam Prep",
                    start_datetime="2025-11-19 15:00:00",
                    end_datetime="2025-11-19 17:00:00",
                    description="Study session for upcoming exam",
                    attendees=["Jordan Lee", "Casey Morgan", "Alex Rivera"],
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent sends confirmation to Jordan
            jordan_confirm_event = (
                messaging_app.send_message(
                    user_id=self.jordan_id,
                    content="Study group scheduled! Tuesday, November 19 at 3:00 PM. See you there!",
                )
                .oracle()
                .depends_on(calendar_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent sends confirmation to Casey
            casey_confirm_event = (
                messaging_app.send_message(
                    user_id=self.casey_id,
                    content="Study group scheduled! Tuesday, November 19 at 3:00 PM. See you there!",
                )
                .oracle()
                .depends_on(jordan_confirm_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent sends confirmation to Alex
            alex_confirm_event = (
                messaging_app.send_message(
                    user_id=self.alex_id,
                    content="Study group scheduled! Tuesday, November 19 at 3:00 PM. See you there!",
                )
                .oracle()
                .depends_on(casey_confirm_event, delay_seconds=1)
            )

        self.events = [
            jordan_msg_event,
            casey_msg_event,
            alex_msg_event,
            jordan_read_event,
            casey_read_event,
            alex_read_event,
            proposal_event,
            acceptance_event,
            calendar_event,
            jordan_confirm_event,
            casey_confirm_event,
            alex_confirm_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent achieved the essential outcomes for this scenario.

        Essential outcomes (what we check):
        - Agent sent proposal to user before taking action
        - Agent created calendar event for study group
        - Agent sent confirmation messages to all three participants

        Not checked (intermediate steps the agent might do differently):
        - How agent read/discovered the availability information
        - Exact conversation IDs used for reading
        """
        try:
            log_entries = env.event_log.list_view()

            # CHECK 1: Agent sent proposal to user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # CHECK 2: Agent created calendar event
            calendar_event_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                for e in log_entries
            )

            # CHECK 3: Agent sent confirmation messages to all three participants
            jordan_confirmation = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.jordan_id
                for e in log_entries
            )

            casey_confirmation = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.casey_id
                for e in log_entries
            )

            alex_confirmation = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.alex_id
                for e in log_entries
            )

            all_confirmations_sent = jordan_confirmation and casey_confirmation and alex_confirmation
            success = proposal_found and calendar_event_found and all_confirmations_sent

            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not send proposal to user")
                if not calendar_event_found:
                    failed_checks.append("agent did not create calendar event")
                if not all_confirmations_sent:
                    missing = []
                    if not jordan_confirmation:
                        missing.append("Jordan")
                    if not casey_confirmation:
                        missing.append("Casey")
                    if not alex_confirmation:
                        missing.append("Alex")
                    failed_checks.append(f"agent did not send confirmation to: {', '.join(missing)}")
                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
