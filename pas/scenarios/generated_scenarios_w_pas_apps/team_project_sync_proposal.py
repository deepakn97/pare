from __future__ import annotations

from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("team_project_sync_proposal")
class TeamProjectSyncProposal(Scenario):
    """Scenario: Agent receives a message about project sync, proposes adding a reminder to calendar, waits for user's approval, and then does it."""

    start_time: float | None = 0
    duration: float | None = 4000

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all apps and populate with initial state."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")
        self.calendar = StatefulCalendarApp(name="StatefulCalendarApp")
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")

        # Add a sample calendar event for context
        self.calendar.add_calendar_event(
            title="Sprint Planning",
            start_datetime="2024-05-15 09:00:00",
            end_datetime="2024-05-15 10:00:00",
            description="Planning meeting for sprint 24",
            tag="work",
            location="Meeting Room 2A",
            attendees=["Jordan Sparks", "User"],
        )

        self.apps = [self.agent_ui, self.system_app, self.calendar, self.messaging]

    def build_events_flow(self) -> None:
        """Build event flow where a teammate sends a message and agent proposes to schedule a follow-up."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp)
        cal = self.get_typed_app(StatefulCalendarApp)
        msg = self.get_typed_app(StatefulMessagingApp)

        with EventRegisterer.capture_mode():
            # 1. Environment event: a teammate sends a message about project updates
            incoming_msg = msg.create_and_add_message(
                sender="Jordan Sparks",
                content="We made great progress on the project presentation, should we review it together tomorrow?",
            ).delayed(3)

            # 2. Agent checks system time just for context
            current_time_event = system_app.get_current_time().oracle().depends_on(incoming_msg, delay_seconds=1)

            # 3. Agent sends a proactive message proposing to add a reminder event
            proposal_event = (
                aui.send_message_to_user(
                    content="Jordan suggested a project review tomorrow. Do you want me to add a reminder for that in your calendar?"
                )
                .oracle()
                .depends_on(current_time_event, delay_seconds=2)
            )

            # 4. User approves with a clear and contextual message
            user_response = (
                aui.send_message_to_agent(content="Yes, please add the reminder at 10 AM tomorrow.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # 5. Agent creates calendar event based on approval
            add_event_action = (
                cal.add_calendar_event(
                    title="Project Review with Jordan",
                    start_datetime="2024-05-16 10:00:00",
                    end_datetime="2024-05-16 10:30:00",
                    description="Discuss project progress and presentation with Jordan",
                    location="Virtual - Teams",
                    attendees=["Jordan Sparks"],
                    tag="reminder",
                )
                .oracle()
                .depends_on(user_response, delay_seconds=2)
            )

            # 6. Agent notifies user the event was added
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've added the 'Project Review with Jordan' reminder to your calendar for tomorrow at 10 AM."
                )
                .oracle()
                .depends_on(add_event_action, delay_seconds=2)
            )

            # 7. System waits for notification after everything is completed
            wait_event = (
                system_app.wait_for_notification(timeout=5).oracle().depends_on(confirmation_event, delay_seconds=1)
            )

        self.events = [
            incoming_msg,
            current_time_event,
            proposal_event,
            user_response,
            add_event_action,
            confirmation_event,
            wait_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation: Ensure the agent's proactive offer and subsequent event creation flow happened."""
        try:
            log_entries = env.event_log.list_view()

            # Check that the proactive proposal exists
            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and "project" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # Validate that a calendar event was added for project review
            calendar_event_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Project Review" in e.action.args.get("title", "")
                for e in log_entries
            )

            # Ensure confirmation message was sent
            confirmation_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and "added" in e.action.args.get("content", "").lower()
                and "calendar" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            success = proposal_sent and calendar_event_added and confirmation_sent
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
