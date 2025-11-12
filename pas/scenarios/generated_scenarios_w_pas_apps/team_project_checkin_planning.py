from __future__ import annotations

from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("team_project_checkin_planning")
class TeamProjectCheckinPlanning(Scenario):
    """Scenario: agent helps user coordinate a team project check-in after team messages about rescheduling."""

    start_time: float | None = 0
    duration: float | None = 4800

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Set up required applications."""
        self.agent_ui = PASAgentUserInterface(name="PASAgentUserInterface")
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.calendar = StatefulCalendarApp(name="StatefulCalendarApp")
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.calendar]

    def build_events_flow(self) -> None:
        """Simulate event flow: agent organizes follow-up meeting after project update messages."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system = self.get_typed_app(HomeScreenSystemApp)
        messenger = self.get_typed_app(StatefulMessagingApp)
        calendar = self.get_typed_app(StatefulCalendarApp)

        with EventRegisterer.capture_mode():
            # Context: environment notification — the user receives a group message about rescheduling
            incoming_message = EventRegisterer.env_event(
                "incoming_group_message",
                {
                    "conversation_id": "conv-q2-checkin",
                    "from_user": "Alex Johnson",
                    "participants": ["alex-id", "sandy-id", "user-id"],
                    "title": "Q2 Project Check-in",
                    "content": "We need to confirm our check-in time for this week.",
                },
            ).depends_on(None, delay_seconds=1)

            # Add a follow-up message from Sandy in the same conversation (environmental)
            group_message = EventRegisterer.env_event(
                "group_message_received",
                {
                    "conversation_id": "conv-q2-checkin",
                    "from_user": "Sandy Li",
                    "content": "Hey team, can we move our check-in to next week? Some of us are unavailable on Friday.",
                },
            ).depends_on(incoming_message, delay_seconds=1)

            # Agent proactively proposes to user checking calendar and scheduling a new time slot
            agent_proposal = (
                aui.send_message_to_user(
                    content="It looks like Sandy suggested moving the Q2 project check-in. "
                    "Would you like me to check your calendar for next week and suggest a new meeting time?"
                )
                .oracle()
                .depends_on(group_message, delay_seconds=2)
            )

            # User responds approving the automated scheduling
            user_response = (
                aui.send_message_to_agent(content="Yes, go ahead and find a new slot next week and invite the team.")
                .oracle()
                .depends_on(agent_proposal, delay_seconds=2)
            )

            # Agent checks current date/time to find available slots
            check_time = system.get_current_time().oracle().depends_on(user_response, delay_seconds=1)

            # Agent adds new event to calendar for next week (execution of approved action)
            add_event = (
                calendar.add_calendar_event(
                    title="Q2 Project Check-in (Rescheduled)",
                    start_datetime="1970-01-08 10:00:00",
                    end_datetime="1970-01-08 11:00:00",
                    tag="Q2Project",
                    description="Rescheduled weekly project check-in per team request.",
                    location="Zoom link in invite",
                    attendees=["Alex Johnson", "Sandy Li", "Jordan West"],
                )
                .oracle()
                .depends_on(check_time, delay_seconds=1)
            )

            # Agent shares confirmation message to the group conversation
            send_confirmation = (
                messenger.send_message_to_group_conversation(
                    conversation_id="conv-q2-checkin",
                    content="I've scheduled the new check-in for Thursday 10-11 AM next week. Everyone has been invited.",
                )
                .oracle()
                .depends_on(add_event, delay_seconds=2)
            )

            # Agent waits for any further notifications
            system_wait = (
                system.wait_for_notification(timeout=1800).oracle().depends_on(send_confirmation, delay_seconds=2)
            )

        self.events = [
            incoming_message,
            group_message,
            agent_proposal,
            user_response,
            check_time,
            add_event,
            send_confirmation,
            system_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation: ensure event creation and proactive confirmation occurred."""
        try:
            logs = env.event_log.list_view()

            # Did the agent make a proactive proposal to schedule?
            proposal_detected = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "check your calendar" in e.action.args.get("content", "")
                for e in logs
            )

            # Did the calendar get updated accordingly?
            calendar_event_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Q2 Project Check-in" in e.action.args.get("title", "")
                for e in logs
            )

            # Did the messaging app confirm scheduling with the group?
            confirmation_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "scheduled the new check-in" in e.action.args.get("content", "")
                for e in logs
            )

            success = all([proposal_detected, calendar_event_created, confirmation_sent])
            return ScenarioValidationResult(success=success)
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
