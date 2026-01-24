"""Scenario: Agent detects scheduling consensus in group chat and creates calendar event."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.messaging_v2 import ConversationV2
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

    The user participates in a group conversation titled "Weekend Plans" with three friends: Alex Rivera,
    Jordan Lee, and Casey Morgan. Messages arrive in real-time where Alex suggests brunch on Saturday at 11,
    Jordan confirms the 23rd works, and Casey confirms she's in. The agent detects the consensus, checks
    the user's calendar to confirm availability at 11 AM on Saturday Nov 23rd, then proposes creating a
    calendar event and sending a confirmation message to the group. After user acceptance, the agent creates
    the calendar event and sends a message to the group confirming the plans.

    This scenario exercises messaging-to-calendar workflow, natural language temporal parsing from unstructured
    chat, multi-party consensus detection, calendar availability checking, and proactive formalization of
    informally agreed plans.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add the three friends to the messaging app
        self.messaging.add_users(["Alex Rivera", "Jordan Lee", "Casey Morgan"])

        # Store user IDs as instance variables for use in build_events_flow
        self.alex_id = self.messaging.name_to_id["Alex Rivera"]
        self.jordan_id = self.messaging.name_to_id["Jordan Lee"]
        self.casey_id = self.messaging.name_to_id["Casey Morgan"]
        self.user_id = self.messaging.current_user_id

        # Create empty group conversation - messages will arrive during event flow
        self.weekend_plans_conversation = ConversationV2(
            participant_ids=[self.user_id, self.alex_id, self.jordan_id, self.casey_id],
            title="Weekend Plans",
            messages=[],
            last_updated=datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp(),
        )
        self.messaging.add_conversation(self.weekend_plans_conversation)
        self.conv_id = self.weekend_plans_conversation.conversation_id

        # Initialize calendar app (empty initially - user is free)
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.calendar]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Alex suggests brunch
            alex_msg_event = messaging_app.create_and_add_message(
                conversation_id=self.conv_id,
                sender_id=self.alex_id,
                content="let's do brunch this Saturday around 11?",
            ).delayed(5)

            # Environment Event 2: Jordan confirms availability
            jordan_msg_event = messaging_app.create_and_add_message(
                conversation_id=self.conv_id,
                sender_id=self.jordan_id,
                content="Saturday the 23rd works, I'm free all morning",
            ).depends_on(alex_msg_event, delay_seconds=10)

            # Environment Event 3: Casey confirms
            casey_msg_event = messaging_app.create_and_add_message(
                conversation_id=self.conv_id,
                sender_id=self.casey_id,
                content="count me in for Saturday brunch at 11!",
            ).depends_on(jordan_msg_event, delay_seconds=10)

            # Oracle Event 1: Agent reads conversation to understand context
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id=self.conv_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(casey_msg_event, delay_seconds=5)
            )

            # Oracle Event 2: Agent checks calendar to verify user is free on Saturday Nov 23 at 11 AM
            check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-23 10:00:00",
                    end_datetime="2025-11-23 14:00:00",
                )
                .oracle()
                .depends_on(read_conversation_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent proposes creating calendar event and sending confirmation to group
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed in your Weekend Plans chat that Alex, Jordan, and Casey want to do brunch on Saturday, November 23rd at 11 AM. I checked your calendar and you're free at that time. Would you like me to create a calendar event and send a confirmation message to the group?"
                )
                .oracle()
                .depends_on(check_calendar_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please do that.").oracle().depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent creates the calendar event
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

            # Oracle Event 6: Agent sends confirmation message to the group
            group_confirmation_event = (
                messaging_app.send_message(
                    user_id=self.alex_id,  # Any participant to identify the conversation
                    content="I'm in for Saturday brunch at 11! I've added it to my calendar.",
                )
                .oracle()
                .depends_on(create_event_event, delay_seconds=1)
            )

        self.events = [
            alex_msg_event,
            jordan_msg_event,
            casey_msg_event,
            read_conversation_event,
            check_calendar_event,
            proposal_event,
            acceptance_event,
            create_event_event,
            group_confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects consensus, checks calendar, creates event, and confirms to group."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent read the messaging conversation
            conversation_read_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                for e in log_entries
            )

            # Check 2: Agent checked calendar for availability
            # Accept: get_calendar_events_from_to (time range) or list_events (all events)
            calendar_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name in ["get_calendar_events_from_to", "list_events"]
                for e in log_entries
            )

            # Check 3: Agent sent proposal mentioning brunch and calendar
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "brunch" in e.action.args.get("content", "").lower()
                and "calendar" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # Check 4: Agent created calendar event with correct date/time and attendees
            event_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-11-23 11:00:00" in e.action.args.get("start_datetime", "")
                and "Alex Rivera" in e.action.args.get("attendees", [])
                and "Jordan Lee" in e.action.args.get("attendees", [])
                and "Casey Morgan" in e.action.args.get("attendees", [])
                for e in log_entries
            )

            # Check 5: Agent sent confirmation message to the group
            group_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                for e in log_entries
            )

            success = (
                conversation_read_found and calendar_checked and proposal_found and event_created and group_message_sent
            )

            if not success:
                missing = []
                if not conversation_read_found:
                    missing.append("conversation read")
                if not calendar_checked:
                    missing.append("calendar availability check")
                if not proposal_found:
                    missing.append("proposal with brunch/calendar mention")
                if not event_created:
                    missing.append("calendar event with correct details")
                if not group_message_sent:
                    missing.append("confirmation message to group")
                return ScenarioValidationResult(success=False, rationale=f"Missing: {', '.join(missing)}")

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
