from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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


@register_scenario("duplicate_commitment_detection")
class DuplicateCommitmentDetection(PASScenario):
    """Agent detects duplicate social commitment across calendar and messages, then helps user resolve the conflict. User has a calendar event "Dinner with Mom" on Saturday 7 PM (created two weeks ago). On Friday afternoon, user receives a group message from friends saying "See you tomorrow night at 7 for the birthday dinner! Can't wait!" - referring to a friend's birthday celebration the user agreed to weeks ago but never calendared. The agent must: 1. Recognize the temporal collision (both Saturday 7 PM) from cross-app signals. 2. Infer these are distinct, conflicting commitments (not the same event mentioned in two places). 3. Understand the user cannot attend both simultaneously. 4. Proactively alert the user with a specific proposal: "I noticed you have 'Dinner with Mom' on your calendar for Saturday 7 PM, but your group chat mentions a birthday dinner at the same time. Would you like me to reschedule 'Dinner with Mom' to Sunday evening at 7 PM and notify her?" 5. After user confirms with a simple yes/no response, execute the rescheduling and draft an appropriate message to the affected party.

    This scenario exercises cross-app conflict detection where neither source explicitly signals a problem, duplicate vs. same-event disambiguation (critical reasoning challenge), implicit commitment tracking from conversational context without calendar confirmation, and proactive conflict alerting before the user manually notices the collision. The user interaction is simplified to a yes/no decision on the agent's specific proposal.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        # Initialize apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.messaging = StatefulMessagingApp(name="Messages")
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Populate calendar - Add "Dinner with Mom" event on Saturday, Nov 23 at 7 PM
        # This event was created two weeks ago and represents the calendared commitment
        self.dinner_with_mom_event_id = self.calendar.add_calendar_event(
            title="Dinner with Mom",
            start_datetime="2025-11-23 19:00:00",
            end_datetime="2025-11-23 21:00:00",
            location="Mom's House",
            description="Weekly dinner with Mom",
        )

        # Populate messaging - Add contacts for the friend group
        # These are the friends involved in the birthday dinner plan
        self.messaging.add_users(["Sarah", "Mike", "Emma"])

        # Add Mom as a reachable messaging contact so the agent can message her directly.
        # StatefulMessagingApp.add_contacts maps (name -> phone/user_id) for `send_message(user_id=...)`.
        self.messaging.add_contacts([("Mom", "555-000-1111")])
        self.mom_user_id = self.messaging.name_to_id["Mom"]

        # Create a group conversation about the birthday dinner
        # This conversation contains prior context about the birthday plan
        friend_group_id = self.messaging.create_group_conversation(
            user_ids=[
                self.messaging.get_user_id("Sarah"),
                self.messaging.get_user_id("Mike"),
                self.messaging.get_user_id("Emma"),
            ],
            title="Friend Squad",
        )

        # Add older messages showing the user agreed to the birthday dinner weeks ago
        # These establish the implicit commitment that wasn't added to calendar
        sarah_id = self.messaging.get_user_id("Sarah")
        mike_id = self.messaging.get_user_id("Mike")

        # Message from 3 weeks ago about planning the birthday
        self.messaging.add_message(
            conversation_id=friend_group_id,
            sender_id=sarah_id,
            content="Hey everyone! Let's plan Mike's birthday dinner! How about Saturday Nov 23rd at 7 PM at Antonio's?",
            timestamp=datetime(2025, 11, 2, 14, 30, 0, tzinfo=UTC).timestamp(),
        )

        # User's reply agreeing to the plan (this is the implicit commitment)
        self.messaging.add_message(
            conversation_id=friend_group_id,
            sender_id=self.messaging.current_user_id,
            content="Sounds great! I'll be there!",
            timestamp=datetime(2025, 11, 2, 15, 0, 0, tzinfo=UTC).timestamp(),
        )

        # Emma's confirmation
        self.messaging.add_message(
            conversation_id=friend_group_id,
            sender_id=self.messaging.get_user_id("Emma"),
            content="Perfect! Can't wait to celebrate!",
            timestamp=datetime(2025, 11, 2, 15, 15, 0, tzinfo=UTC).timestamp(),
        )

        # Store the conversation ID for later use
        self.friend_group_id = friend_group_id

        # Register all apps
        self.apps = [self.calendar, self.messaging, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        # Get user IDs BEFORE entering capture_mode
        sarah_id = messaging_app.name_to_id["Sarah"]

        with EventRegisterer.capture_mode():
            # Environment Event 1: Reminder message from Sarah on Friday afternoon
            # This message creates the trigger for conflict detection
            reminder_message_event = messaging_app.create_and_add_message(
                conversation_id=self.friend_group_id,
                sender_id=sarah_id,
                content="See you tomorrow night at 7 for the birthday dinner! Can't wait! Mike's going to be so surprised!",
            ).delayed(60)

            # Oracle Event 1: Agent lists recent conversations to detect new messages
            list_conversations_event = (
                messaging_app.list_recent_conversations(
                    offset=0,
                    limit=5,
                    offset_recent_messages_per_conversation=0,
                    limit_recent_messages_per_conversation=10,
                )
                .oracle()
                .depends_on(reminder_message_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent reads the conversation to see the reminder
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id=self.friend_group_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(list_conversations_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent checks calendar for Saturday Nov 23 at 7 PM
            check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-23 19:00:00",
                    end_datetime="2025-11-23 21:00:00",
                )
                .oracle()
                .depends_on(read_conversation_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends proposal alerting user of the conflict
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you have 'Dinner with Mom' on your calendar for Saturday Nov 23 at 7 PM, but your group chat mentions Mike's birthday dinner at the same time tomorrow. These appear to be two different commitments. Would you like me to reschedule 'Dinner with Mom' to Sunday evening at 7 PM and notify her?",
                )
                .oracle()
                .depends_on(check_calendar_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts proposal with simple yes/no response
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please.",
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent checks Sunday evening availability
            check_sunday_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-24 19:00:00",
                    end_datetime="2025-11-24 21:00:00",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent reschedules the existing calendar event to Sunday evening
            reschedule_event = (
                calendar_app.edit_calendar_event(
                    event_id=self.dinner_with_mom_event_id,
                    title="Dinner with Mom",
                    start_datetime="2025-11-24 19:00:00",
                    end_datetime="2025-11-24 21:00:00",
                    description="Weekly dinner with Mom",
                    location="Mom's House",
                    tag=None,
                )
                .oracle()
                .depends_on(check_sunday_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent sends a confirmation message to Mom about the reschedule
            message_mom_event = (
                messaging_app.send_message(
                    user_id=self.mom_user_id,
                    content="Hi Mom — I rescheduled our dinner from Saturday at 7 PM to Sunday evening at 7 PM due to a scheduling conflict. See you then at your place.",
                )
                .oracle()
                .depends_on(reschedule_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent confirms to the user that the event was rescheduled and Mom was notified (content-flexible).
            user_confirmation_event = (
                aui.send_message_to_user(
                    content="Done — I moved 'Dinner with Mom' to Sunday evening at 7 PM on your calendar and sent your mom a confirmation message.",
                )
                .oracle()
                .depends_on(message_mom_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            reminder_message_event,
            list_conversations_event,
            read_conversation_event,
            check_calendar_event,
            proposal_event,
            acceptance_event,
            check_sunday_event,
            reschedule_event,
            message_mom_event,
            user_confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent an initial proposal/alert to the user
            # Do NOT over-constrain on the exact message content.
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent read messaging conversation to detect the reminder
            # Must demonstrate the agent examined the message thread
            messaging_read_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["read_conversation", "list_recent_conversations"]
                for e in log_entries
            )

            # STRICT Check 3: Agent checked calendar to identify the conflict
            # Must verify the agent queried calendar around Saturday Nov 23 at 7 PM
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                and (
                    "2025-11-23" in e.action.args.get("start_datetime", "")
                    or "2025-11-23" in e.action.args.get("end_datetime", "")
                )
                for e in log_entries
            )

            # STRICT Check 4: Agent provided follow-up assistance after user acceptance
            # Must reschedule the event and notify Mom, plus send at least one additional message to the user.
            reschedule_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "edit_calendar_event"
                for e in log_entries
            )

            notify_mom_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                for e in log_entries
            )

            # All strict checks must pass
            success = (
                proposal_found
                and messaging_read_found
                and calendar_check_found
                and reschedule_found
                and notify_mom_found
            )

            if not success:
                rationale = "Missing critical checks: "
                missing = []
                if not proposal_found:
                    missing.append("no conflict alert proposal found in log")
                if not messaging_read_found:
                    missing.append("agent did not read messaging conversation")
                if not calendar_check_found:
                    missing.append("agent did not check calendar for Saturday Nov 23")
                if not reschedule_found:
                    missing.append("calendar event not rescheduled")
                if not notify_mom_found:
                    missing.append("mom not notified via messaging")
                rationale += ", ".join(missing)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
