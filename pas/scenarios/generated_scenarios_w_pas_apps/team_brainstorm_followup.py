from __future__ import annotations

from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("team_brainstorm_followup")
class TeamBrainstormFollowupScenario(Scenario):
    """Scenario: The agent helps plan and confirm a follow-up brainstorming session after a chat message."""

    start_time: float | None = 0
    duration: float | None = 5400  # 1.5 hours
    is_benchmark_ready: bool = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate all required apps."""
        self.calendar = StatefulCalendarApp(name="StatefulCalendarApp")
        # Create a base event in the calendar
        self.calendar.add_calendar_event(
            title="Marketing Brainstorm",
            start_datetime="2024-06-10 14:00:00",
            end_datetime="2024-06-10 15:00:00",
            description="Initial brainstorming for new campaign ideas.",
            location="Conference Room 1",
            tag="meeting",
            attendees=["Jordan Lee", "Sam Patel"],
        )

        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.agent_ui = PASAgentUserInterface(name="PASAgentUserInterface")
        self.system = HomeScreenSystemApp(name="HomeScreenSystemApp")

        self.apps = [self.calendar, self.messaging, self.agent_ui, self.system]

    def build_events_flow(self) -> None:
        """Build sequence of events for the scenario."""
        aui = self.get_typed_app(PASAgentUserInterface)
        cal = self.get_typed_app(StatefulCalendarApp)
        msg = self.get_typed_app(StatefulMessagingApp)
        sys = self.get_typed_app(HomeScreenSystemApp)

        # Environment context setup: incoming message after meeting
        with EventRegisterer.capture_mode():
            # A message arrives from Jordan suggesting a follow-up discussion
            incoming_msg = msg.create_and_add_message(
                user_name="Jordan Lee",
                content="The brainstorming session was good today. Let's schedule a follow-up to finalize the campaign plan.",
            ).delayed(3)

            # Agent read today's date/time context
            time_check = sys.get_current_time().oracle().depends_on(incoming_msg, delay_seconds=1)

            # Agent proactively proposes scheduling a follow-up
            proposal = (
                aui.send_message_to_user(
                    content="Jordan suggested a follow-up for the marketing campaign discussion. "
                    "Would you like me to schedule a 30-minute meeting with the same attendees tomorrow afternoon?"
                )
                .oracle()
                .depends_on(time_check, delay_seconds=2)
            )

            # User gives explicit confirmation
            user_approval = (
                aui.send_message_to_agent(
                    content="Yes, that sounds perfect. Please schedule it around 2:30 PM tomorrow."
                )
                .oracle()
                .depends_on(proposal, delay_seconds=3)
            )

            # Agent acts based on approval by adding a calendar event
            add_followup_event = (
                cal.add_calendar_event(
                    title="Marketing Campaign Follow-up",
                    start_datetime="2024-06-11 14:30:00",
                    end_datetime="2024-06-11 15:00:00",
                    description="Continuing discussion to finalize marketing campaign ideas.",
                    location="Conference Room 2",
                    tag="follow-up",
                    attendees=["Jordan Lee", "Sam Patel"],
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=2)
            )

            # Agent sends message confirmation to the chat group
            followup_message = (
                msg.send_message(
                    user_id="JordanLee",
                    content="I've scheduled our follow-up meeting for tomorrow at 2:30 PM in Conference Room 2.",
                )
                .oracle()
                .depends_on(add_followup_event, delay_seconds=2)
            )

        self.events = [
            incoming_msg,
            time_check,
            proposal,
            user_approval,
            add_followup_event,
            followup_message,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the follow-up was properly suggested and scheduled after user approval."""
        try:
            log = env.event_log.list_view()

            # Agent proposal detection
            proposal_detected = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and "Would you like me to schedule" in e.action.args.get("content", "")
                for e in log
            )

            # Calendar addition of the follow-up meeting
            followup_scheduled = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Marketing Campaign Follow-up" in e.action.args.get("title", "")
                for e in log
            )

            # Confirmation message sent to Jordan
            message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and "I've scheduled our follow-up" in e.action.args.get("content", "")
                for e in log
            )

            return ScenarioValidationResult(success=(proposal_detected and followup_scheduled and message_sent))
        except Exception as error:
            return ScenarioValidationResult(success=False, exception=error)
