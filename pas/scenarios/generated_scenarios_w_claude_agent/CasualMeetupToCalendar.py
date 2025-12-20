"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
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


@register_scenario("casual_meetup_to_calendar")
class CasualMeetupToCalendar(PASScenario):
    """Agent detects scheduling consensus in group chat and proactively creates calendar event for casual meetup.

    The user participates in a group conversation titled "Weekend Plans" with three friends: Alex Rivera, Jordan Lee, and Casey Morgan. Over several messages, the group casually discusses meeting for brunch on Saturday: Alex suggests "let's do brunch this Saturday around 11?", Jordan replies "Saturday the 23rd works, I'm free all morning", Casey confirms "count me in for Saturday brunch at 11!", and the user says "sounds great". However, no formal calendar event has been created despite the group reaching consensus. The agent must: 1. Parse the conversational messages to extract the scheduled activity details (brunch with friends). 2. Identify the agreed date (Saturday the 23rd) and time (11 AM) from informal natural language references. 3. Recognize that all four participants have confirmed availability and reached consensus. 4. Propose creating a calendar event to formalize the casual plan. 5. After user acceptance, create a calendar event titled "Brunch with Alex, Jordan, Casey" on Saturday November 23rd at 11:00 AM with all three friends listed as attendees.

    This scenario exercises pure messaging-to-calendar workflow without email involvement, natural language temporal parsing from unstructured chat ("this Saturday", "the 23rd", "around 11"), multi-party consensus detection across separate messages in group conversations, casual social context distinct from formal work meetings, and proactive calendar formalization of informally agreed plans to prevent scheduling conflicts or forgotten commitments..
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

        # Add the three friends to the messaging app
        self.messaging.add_users(["Alex Rivera", "Jordan Lee", "Casey Morgan"])

        # Get user IDs for the three friends
        alex_id = self.messaging.name_to_id["Alex Rivera"]
        jordan_id = self.messaging.name_to_id["Jordan Lee"]
        casey_id = self.messaging.name_to_id["Casey Morgan"]
        user_id = self.messaging.current_user_id

        # Create the group conversation "Weekend Plans" with existing messages
        # Timestamps are in the past (before start_time of November 18, 9:00 AM UTC)
        # Messages occurred on November 17 evening
        nov_17_base = datetime(2025, 11, 17, 20, 0, 0, tzinfo=UTC).timestamp()

        weekend_plans_conversation = ConversationV2(
            participant_ids=[user_id, alex_id, jordan_id, casey_id],
            title="Weekend Plans",
            messages=[
                MessageV2(
                    sender_id=alex_id,
                    content="let's do brunch this Saturday around 11?",
                    timestamp=nov_17_base + 60,  # 20:01
                ),
                MessageV2(
                    sender_id=jordan_id,
                    content="Saturday the 23rd works, I'm free all morning",
                    timestamp=nov_17_base + 180,  # 20:03
                ),
                MessageV2(
                    sender_id=casey_id,
                    content="count me in for Saturday brunch at 11!",
                    timestamp=nov_17_base + 300,  # 20:05
                ),
                MessageV2(
                    sender_id=user_id,
                    content="sounds great",
                    timestamp=nov_17_base + 420,  # 20:07
                ),
            ],
            last_updated=nov_17_base + 420,
        )

        self.messaging.add_conversation(weekend_plans_conversation)

        # Initialize calendar app (empty initially, no pre-existing events)
        self.calendar = StatefulCalendarApp(name="Calendar")

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

        with EventRegisterer.capture_mode():
            # No environment events - all baseline data exists in the group chat already
            # The agent should proactively notice the consensus in the existing messages

            # Oracle Event 1: Agent reads the conversation to understand the context
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id=next(iter(messaging_app.conversations.keys())),
                    offset=0,
                    limit=10,
                )
                .oracle()
                .delayed(10)
            )

            # Oracle Event 2: Agent proposes creating a calendar event
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed in your Weekend Plans chat that you and your friends (Alex Rivera, Jordan Lee, and Casey Morgan) have agreed to meet for brunch on Saturday, November 23rd at 11 AM. Would you like me to create a calendar event for this?"
                )
                .oracle()
                .depends_on(read_conversation_event, delay_seconds=3)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please create the calendar event.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent creates the calendar event
            create_event_event = (
                calendar_app.add_calendar_event(
                    title="Brunch with Alex, Jordan, Casey",
                    start_datetime="2025-11-23 11:00:00",
                    end_datetime="2025-11-23 13:00:00",
                    description="Brunch meetup with friends",
                    attendees=["Alex Rivera", "Jordan Lee", "Casey Morgan"],
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent confirms completion
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've created a calendar event for brunch with Alex, Jordan, and Casey on Saturday, November 23rd at 11:00 AM."
                )
                .oracle()
                .depends_on(create_event_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            read_conversation_event,
            proposal_event,
            acceptance_event,
            create_event_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent read the messaging conversation to detect the scheduling consensus
            conversation_read_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                for e in log_entries
            )

            # Check 2: Agent sent proposal mentioning brunch and the three friends
            # Be flexible on exact wording but strict on logical content
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    friend in e.action.args.get("content", "")
                    for friend in ["Alex Rivera", "Jordan Lee", "Casey Morgan"]
                )
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["brunch", "saturday", "november 23", "calendar"]
                )
                for e in log_entries
            )

            # Check 3: Agent created calendar event with correct structural details
            # Strict on date/time, attendees list presence; flexible on exact title wording
            event_created = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("start_datetime") == "2025-11-23 11:00:00"
                and "Alex Rivera" in e.action.args.get("attendees", [])
                and "Jordan Lee" in e.action.args.get("attendees", [])
                and "Casey Morgan" in e.action.args.get("attendees", [])
                for e in log_entries
            )

            # Check 4: Agent sent confirmation message after creating the event
            # Flexible on wording; strict on presence of confirmation
            confirmation_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["created", "added", "calendar event"]
                )
                for e in log_entries
                if log_entries.index(e)
                > next(
                    (
                        i
                        for i, evt in enumerate(log_entries)
                        if (evt.event_type == EventType.AGENT or evt.event_type == EventType.ENV)
                        and isinstance(evt.action, Action)
                        and evt.action.class_name == "StatefulCalendarApp"
                        and evt.action.function_name == "add_calendar_event"
                    ),
                    len(log_entries),
                )
            )

            # Determine success and rationale
            success = conversation_read_found and proposal_found and event_created and confirmation_found

            if not success:
                missing_checks = []
                if not conversation_read_found:
                    missing_checks.append("conversation read not found")
                if not proposal_found:
                    missing_checks.append("proposal mentioning brunch and friends not found")
                if not event_created:
                    missing_checks.append("calendar event creation with correct details not found")
                if not confirmation_found:
                    missing_checks.append("confirmation message after event creation not found")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
