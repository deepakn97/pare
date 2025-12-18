from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_meeting_sync_proactive")
class TeamMeetingSyncProactive(Scenario):
    """Scenario: Agent proactively helps user organize a team sync-up meeting after checking schedule conflicts.

    This scenario demonstrates integration across SystemApp, CalendarApp, and AgentUserInterface:
    - SystemApp: Retrieves current date to create time-appropriate events.
    - CalendarApp: Handles event creation, searching, and tagging.
    - AgentUserInterface: Mediates a proactive proposal and confirmation with the user.

    Core Flow:
    1. User messages the agent requesting team meeting setup.
    2. Agent checks the current time and determines next available day.
    3. Agent proactively proposes to schedule the meeting for that day at a specific time.
    4. User approves the proposal.
    5. Agent adds the meeting to the calendar and confirms to the user.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize applications and seed initial calendar data."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        system = SystemApp(name="system_agent")

        # Add a pre-existing event to demonstrate search and conflict checking
        calendar.add_calendar_event(
            title="Product Review Session",
            start_datetime="2024-04-10 09:30:00",
            end_datetime="2024-04-10 10:15:00",
            tag="work",
            description="Discuss upcoming product updates",
            location="Room 201",
            attendees=["Alice Brown", "David Zhang"],
        )

        # Another event for testing tag retrieval
        calendar.add_calendar_event(
            title="One-on-One",
            start_datetime="2024-04-09 14:00:00",
            end_datetime="2024-04-09 14:30:00",
            tag="performance",
            description="Bi-weekly check-in",
            location="Call Room 3",
            attendees=["Chris Thompson"],
        )

        self.apps = [aui, calendar, system]

    def build_events_flow(self) -> None:
        """Define the full interaction and proactive proposal sequence."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User initiates the request to plan a meeting
            user_request = aui.send_message_to_agent(
                content="Could you help me schedule a sync-up with the marketing team next week?"
            ).depends_on(None, delay_seconds=1)

            # Agent checks current time to contextualize scheduling
            agent_check_time = system.get_current_time().depends_on(user_request, delay_seconds=1)

            # Agent searches for existing work events to avoid overlaps
            check_events = calendar.search_events(query="work").depends_on(agent_check_time, delay_seconds=1)

            # Agent proactively asks confirmation to set a meeting slot
            proactive_proposal = aui.send_message_to_user(
                content="I found a free slot on Wednesday 10:30 AM. Should I schedule the marketing team sync-up there?"
            ).depends_on(check_events, delay_seconds=1)

            # User responds with contextual confirmation
            user_confirms = aui.send_message_to_agent(
                content="Yes, please go ahead and add the meeting for that time."
            ).depends_on(proactive_proposal, delay_seconds=2)

            # Agent executes event creation after approval (oracle)
            add_sync_event = (
                calendar.add_calendar_event(
                    title="Marketing Team Sync-up",
                    start_datetime="2024-04-10 10:30:00",
                    end_datetime="2024-04-10 11:15:00",
                    tag="meeting",
                    description="Weekly marketing alignment session",
                    location="Conference Room B",
                    attendees=["Alice Brown", "Chris Thompson", "David Zhang"],
                )
                .oracle()
                .depends_on(user_confirms, delay_seconds=1)
            )

            # Agent confirms creation to user
            confirm_message = (
                aui.send_message_to_user(
                    content="The marketing team sync-up has been scheduled on Wednesday 10:30 AM in Conference Room B!"
                )
                .oracle()
                .depends_on(add_sync_event, delay_seconds=1)
            )

            # Wait for possible follow-up input (idle state)
            system_idle = system.wait_for_notification(timeout=10).depends_on(confirm_message, delay_seconds=1)

        self.events = [
            user_request,
            agent_check_time,
            check_events,
            proactive_proposal,
            user_confirms,
            add_sync_event,
            confirm_message,
            system_idle,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the scenario success by verifying both message interaction and event creation."""
        try:
            events = env.event_log.list_view()

            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "schedule" in e.action.args.get("content", "").lower()
                for e in events
            )

            event_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Marketing Team Sync-up" in e.action.args.get("title", "")
                for e in events
            )

            user_approval_present = any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_agent"
                and "go ahead" in e.action.args.get("content", "").lower()
                for e in events
            )

            return ScenarioValidationResult(success=(proposal_sent and event_added and user_approval_present))
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
