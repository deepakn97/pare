"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulMessagingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("study_group_availability_synthesis")
class StudyGroupAvailabilitySynthesis(PASScenario):
    """Agent coordinates study group scheduling by synthesizing availability constraints from separate one-on-one message conversations. The user is organizing a study session for an upcoming exam and receives individual messages from three classmates (Jordan Lee, Casey Morgan, and Alex Rivera) in three separate conversations, each stating their available time windows over the next few days. Jordan can meet "Tuesday afternoon or Wednesday morning," Casey says "I'm free Tuesday after 2 PM or Thursday anytime," and Alex mentions "Tuesday works best for me, anytime after 3 PM." The agent must: 1. Parse availability statements from three independent conversations. 2. Identify the overlapping time window that accommodates all four participants (Tuesday afternoon starting at 3 PM). 3. Create a calendar event titled "Study Group - Exam Prep" for Tuesday at 3:00 PM with all three classmates as attendees. 4. Send individual confirmation messages to each participant in their respective conversations stating the finalized time.

    This scenario exercises multi-conversation information aggregation without group chat, temporal constraint satisfaction across disconnected messaging threads, availability inference from natural language expressions, calendar event creation with synthesized participant list, and individualized follow-up communication to close the coordination loop with each stakeholder separately..
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
        self.messaging.current_user_id = "user_self"
        self.messaging.current_user_name = "Me"

        # Create contacts for the three classmates
        jordan_id = "jordan_lee_id"
        casey_id = "casey_morgan_id"
        alex_id = "alex_rivera_id"

        # Add users to messaging app
        self.messaging.add_users(["Jordan Lee", "Casey Morgan", "Alex Rivera"])
        # Map the IDs
        self.messaging.name_to_id["Jordan Lee"] = jordan_id
        self.messaging.id_to_name[jordan_id] = "Jordan Lee"
        self.messaging.name_to_id["Casey Morgan"] = casey_id
        self.messaging.id_to_name[casey_id] = "Casey Morgan"
        self.messaging.name_to_id["Alex Rivera"] = alex_id
        self.messaging.id_to_name[alex_id] = "Alex Rivera"

        # Create three separate 1:1 conversations with minimal prior history
        # Conversation with Jordan Lee
        jordan_conv = ConversationV2(
            conversation_id="conv_jordan",
            participant_ids=["user_self", jordan_id],
            title="Jordan Lee",
            messages=[
                MessageV2(
                    sender_id="user_self",
                    content="Hey Jordan, we should organize a study group for the exam next week. When are you free?",
                    timestamp=datetime(2025, 11, 17, 14, 0, 0, tzinfo=UTC).timestamp(),
                )
            ],
        )

        # Conversation with Casey Morgan
        casey_conv = ConversationV2(
            conversation_id="conv_casey",
            participant_ids=["user_self", casey_id],
            title="Casey Morgan",
            messages=[
                MessageV2(
                    sender_id="user_self",
                    content="Hi Casey! Trying to set up a study session for the exam. What times work for you?",
                    timestamp=datetime(2025, 11, 17, 15, 0, 0, tzinfo=UTC).timestamp(),
                )
            ],
        )

        # Conversation with Alex Rivera
        alex_conv = ConversationV2(
            conversation_id="conv_alex",
            participant_ids=["user_self", alex_id],
            title="Alex Rivera",
            messages=[
                MessageV2(
                    sender_id="user_self",
                    content="Alex, want to join the study group for next week's exam? Let me know when you're available.",
                    timestamp=datetime(2025, 11, 17, 16, 0, 0, tzinfo=UTC).timestamp(),
                )
            ],
        )

        self.messaging.add_conversation(jordan_conv)
        self.messaging.add_conversation(casey_conv)
        self.messaging.add_conversation(alex_conv)

        # Initialize calendar app with minimal baseline (user's existing schedule)
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Add a baseline event to show the user has some existing commitments
        existing_event = CalendarEvent(
            event_id="existing_meeting",
            title="Class Lecture",
            start_datetime=datetime(2025, 11, 18, 10, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 18, 11, 30, 0, tzinfo=UTC).timestamp(),
            location="Room 301",
            description="Regular class session",
        )
        self.calendar.events[existing_event.event_id] = existing_event

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.calendar]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        # Store IDs for use in oracle events
        jordan_id = "jordan_lee_id"
        casey_id = "casey_morgan_id"
        alex_id = "alex_rivera_id"

        with EventRegisterer.capture_mode():
            # Environment Event 1: Jordan responds with availability
            jordan_msg_event = messaging_app.create_and_add_message(
                conversation_id="conv_jordan",
                sender_id=jordan_id,
                content="Sure! I can do Tuesday afternoon or Wednesday morning. Let me know what works!",
            ).delayed(15)

            # Environment Event 2: Casey responds with availability
            casey_msg_event = messaging_app.create_and_add_message(
                conversation_id="conv_casey",
                sender_id=casey_id,
                content="I'm free Tuesday after 2 PM or Thursday anytime. Whatever works for everyone!",
            ).delayed(18)

            # Environment Event 3: Alex responds with availability
            alex_msg_event = messaging_app.create_and_add_message(
                conversation_id="conv_alex",
                sender_id=alex_id,
                content="Tuesday works best for me, anytime after 3 PM. Looking forward to studying together!",
            ).delayed(22)

            # Oracle Event 1: Agent reads Jordan's conversation to extract availability
            jordan_read_event = (
                messaging_app.read_conversation(conversation_id="conv_jordan", offset=0, limit=10)
                .oracle()
                .depends_on(alex_msg_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent reads Casey's conversation to extract availability
            casey_read_event = (
                messaging_app.read_conversation(conversation_id="conv_casey", offset=0, limit=10)
                .oracle()
                .depends_on(jordan_read_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent reads Alex's conversation to extract availability
            alex_read_event = (
                messaging_app.read_conversation(conversation_id="conv_alex", offset=0, limit=10)
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
                    user_id=jordan_id,
                    content="Study group scheduled! Tuesday, November 19 at 3:00 PM. See you there!",
                )
                .oracle()
                .depends_on(calendar_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent sends confirmation to Casey
            casey_confirm_event = (
                messaging_app.send_message(
                    user_id=casey_id,
                    content="Study group scheduled! Tuesday, November 19 at 3:00 PM. See you there!",
                )
                .oracle()
                .depends_on(jordan_confirm_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent sends confirmation to Alex
            alex_confirm_event = (
                messaging_app.send_message(
                    user_id=alex_id,
                    content="Study group scheduled! Tuesday, November 19 at 3:00 PM. See you there!",
                )
                .oracle()
                .depends_on(casey_confirm_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
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
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent read the three separate conversations to gather availability
            jordan_read_found = any(
                (e.event_type == EventType.AGENT)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                and e.action.args.get("conversation_id") == "conv_jordan"
                for e in log_entries
                if hasattr(e, "action") and isinstance(e.action, Action)
            )

            casey_read_found = any(
                (e.event_type == EventType.AGENT)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                and e.action.args.get("conversation_id") == "conv_casey"
                for e in log_entries
                if hasattr(e, "action") and isinstance(e.action, Action)
            )

            alex_read_found = any(
                (e.event_type == EventType.AGENT)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                and e.action.args.get("conversation_id") == "conv_alex"
                for e in log_entries
                if hasattr(e, "action") and isinstance(e.action, Action)
            )

            # Check Step 2: Agent sent proposal mentioning availability synthesis (FLEXIBLE on exact wording)
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
                if hasattr(e, "action") and isinstance(e.action, Action)
            )

            # Check Step 3: Agent created calendar event with correct date and all three attendees (STRICT)
            calendar_event_found = any(
                (e.event_type == EventType.AGENT)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                for e in log_entries
                if hasattr(e, "action") and isinstance(e.action, Action)
            )

            # Check Step 4: Agent sent confirmation messages to all three participants (STRICT on recipients, FLEXIBLE on content)
            jordan_confirmation = any(
                (e.event_type == EventType.AGENT)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == "jordan_lee_id"
                and len(e.action.args.get("content", "")) > 0
                for e in log_entries
                if hasattr(e, "action") and isinstance(e.action, Action)
            )

            casey_confirmation = any(
                (e.event_type == EventType.AGENT)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == "casey_morgan_id"
                and len(e.action.args.get("content", "")) > 0
                for e in log_entries
                if hasattr(e, "action") and isinstance(e.action, Action)
            )

            alex_confirmation = any(
                (e.event_type == EventType.AGENT)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == "alex_rivera_id"
                and len(e.action.args.get("content", "")) > 0
                for e in log_entries
                if hasattr(e, "action") and isinstance(e.action, Action)
            )

            all_reads_found = jordan_read_found and casey_read_found and alex_read_found
            all_confirmations_sent = jordan_confirmation and casey_confirmation and alex_confirmation

            success = all_reads_found and proposal_found and calendar_event_found and all_confirmations_sent

            if not success:
                rationale_parts = []
                if not all_reads_found:
                    rationale_parts.append("not all conversations read")
                if not proposal_found:
                    rationale_parts.append("no coordination proposal to user")
                if not calendar_event_found:
                    rationale_parts.append("calendar event not created with correct details")
                if not all_confirmations_sent:
                    rationale_parts.append("not all participants received confirmation")
                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
