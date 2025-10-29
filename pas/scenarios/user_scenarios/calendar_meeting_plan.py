"""calendar_meeting_plan: ProposeAndScheduleMeetingScenario.

Aggregate participant availability, propose options, then schedule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import DATETIME_FORMAT
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar import StatefulCalendarApp


# ---------- Parameter definitions ----------
@dataclass
class MeetingParams:
    """Parameters for a meeting."""

    start_time_ms: int
    end_time_ms: int
    title: str
    location: str = ""
    description: str = ""
    attendees: list[str] | None = None


# ---------- Time conversion helpers ----------
def ms_to_str(ms: int) -> str:
    """Convert milliseconds timestamp to datetime string."""
    dt = datetime.fromtimestamp(ms / 1000, tz=UTC)
    return dt.strftime(DATETIME_FORMAT)


# ---------- Scenario definition ----------
@register_scenario("calendar_meeting_plan")
class ProposeAndScheduleMeetingScenario(Scenario):
    """Cal002: Check multi-participant availability, then create a meeting."""

    def __init__(self) -> None:
        """Initialize the scenario."""
        super().__init__()
        self._params = self._get_default_params()

    # ---------- Default meeting parameters ----------
    def _get_default_params(self) -> MeetingParams:
        now = datetime.now(tz=UTC)
        tomorrow = (now + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
        return MeetingParams(
            start_time_ms=int(tomorrow.timestamp() * 1000),
            end_time_ms=int((tomorrow + timedelta(hours=1)).timestamp() * 1000),
            title="Cross-Timezone Team Sync",
            location="Zoom Room A",
            description="Quarterly planning meeting",
            attendees=["alice@example.com", "bob@example.com", "charlie@example.com"],
        )

    # ---------- App initialization ----------
    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate the necessary apps."""
        print("[DEBUG] calendar_meeting_plan: init_and_populate_apps called")
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        self.apps = [agui, system, calendar]
        print("[DEBUG] calendar_meeting_plan: Apps initialized")

    # ---------- Build event flow ----------
    def build_events_flow(self) -> None:
        """Build the event flow."""
        print("[DEBUG] calendar_meeting_plan: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        p = self._params

        start_str = ms_to_str(p.start_time_ms)
        end_str = ms_to_str(p.end_time_ms)

        with EventRegisterer.capture_mode():
            # Step 1: User → Agent
            start_msg = aui.send_message_to_agent(
                content=(
                    f"Please create a calendar event with the following details:\n"
                    f"Title: {p.title}\n"
                    f"Start time: {start_str}\n"
                    f"End time: {end_str}\n"
                    f"Location: {p.location}\n"
                    f"Description: {p.description}\n"
                    f"Attendees: {', '.join(p.attendees) if p.attendees else 'None'}\n\n"
                    f"Before creating, please check whether all participants are free during that time."
                )
            ).depends_on(None, delay_seconds=1)

            # Step 2: Oracle checks availability for each attendee
            availability_checks = []
            if p.attendees is not None:
                for _ in p.attendees:
                    check = (
                        calendar.get_calendar_events_from_to(start_datetime=start_str, end_datetime=end_str)
                        .oracle()
                        .depends_on(start_msg, delay_seconds=1)
                    )
                    availability_checks.append(check)

            # Step 3: Oracle adds event (if all free)
            oracle_create = (
                calendar.add_calendar_event(
                    title=p.title,
                    start_datetime=start_str,
                    end_datetime=end_str,
                    description=p.description,
                    location=p.location,
                    attendees=p.attendees,
                    tag=None,
                )
                .oracle()
                .depends_on(availability_checks[-1], delay_seconds=1)
            )

            # Step 4: Agent confirms creation
            agent_confirm = aui.send_message_to_user(
                content=f"I've confirmed everyone is available and created the event '{p.title}'."
            ).depends_on(oracle_create, delay_seconds=1)

        self.events = [start_msg, *availability_checks, oracle_create, agent_confirm]
        print(f"[DEBUG] calendar_meeting_plan: Created {len(self.events)} events (with availability checks)")

    # ---------- Validation ----------
    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the scenario."""
        print("[DEBUG] calendar_meeting_plan: validate() called")

        try:
            events = env.event_log.list_view()
            p = self._params

            event_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "StatefulCalendarApp"
                and event.action.function_name == "add_calendar_event"
                and event.action.args.get("title") == p.title
                for event in events
            )

            print(f"[DEBUG] calendar_meeting_plan: event_created={event_created}")
            print(f"[DEBUG] calendar_meeting_plan: Total events in log: {len(events)}")

            success = event_created
            print(f"[INFO] calendar_meeting_plan: Validation result: success={success}")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            print(f"[ERROR] calendar_meeting_plan: Validation failed with exception: {e}")
            import traceback

            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
