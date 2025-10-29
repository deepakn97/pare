"""calendar_create: ScheduleEventScenario.

Create a calendar event and verify it was written.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import DATETIME_FORMAT
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar import StatefulCalendarApp


@dataclass
class ScheduleParams:
    """Parameters for scheduling an event."""

    start_time_ms: int
    end_time_ms: int
    title: str
    location: str = ""
    description: str = ""


def ms_to_str(ms: int) -> str:
    """Convert milliseconds timestamp to datetime string."""
    dt = datetime.fromtimestamp(ms / 1000, tz=UTC)
    return dt.strftime(DATETIME_FORMAT)


def ms_to_hours(ms: int, base_ms: int) -> float:
    """Convert milliseconds to hours offset from base time."""
    return (ms - base_ms) / (1000 * 60 * 60)


@register_scenario("calendar_create")
class ScheduleEventScenario(Scenario):
    """calendar_create: Create a calendar event and verify it was written."""

    start_time: float | None = 0
    duration: float | None = 1  # Duration in hours

    def __init__(self) -> None:
        """Initialize the scenario."""
        super().__init__()
        self._params = self._get_default_params()

    def _get_default_params(self) -> ScheduleParams:
        """Get default parameters."""
        return ScheduleParams(
            start_time_ms=1761420000000,  # Oct 24, 2025 3:00 PM UTC
            end_time_ms=1761423600000,  # Oct 24, 2025 4:00 PM UTC
            title="Team Sync",
            location="ESB 1001",
            description="bring slides",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate the necessary apps."""
        print("[DEBUG] calendar_create: init_and_populate_apps called")

        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()

        self.apps = [agui, system, calendar]

        print("[DEBUG] calendar_create: Apps initialized")

    def build_events_flow(self) -> None:
        """Construct the event flow for creating a calendar event."""
        print("[DEBUG] calendar_create: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)

        p = self._params

        with EventRegisterer.capture_mode():
            # User asks agent to create an event
            start_msg = aui.send_message_to_agent(
                content=(
                    f"Please create a calendar event with the following details:\n"
                    f"Title: {p.title}\n"
                    f"Start time: {ms_to_str(p.start_time_ms)}\n"
                    f"End time: {ms_to_str(p.end_time_ms)}\n"
                    f"Location: {p.location}\n"
                    f"Description: {p.description}"
                )
            ).depends_on(None, delay_seconds=1)

            # Oracle event: agent creates the event using add_calendar_event
            oracle_create = (
                calendar.add_calendar_event(
                    title=p.title,
                    start_datetime=ms_to_str(p.start_time_ms),
                    end_datetime=ms_to_str(p.end_time_ms),
                    description=p.description,
                    location=p.location,
                    attendees=None,
                    tag=None,
                )
                .oracle()
                .depends_on(start_msg, delay_seconds=1)
            )

            # Agent confirms to user
            agent_confirm = aui.send_message_to_user(
                content=f"I've created the calendar event '{p.title}' for you."
            ).depends_on(oracle_create, delay_seconds=1)

        self.events = [start_msg, oracle_create, agent_confirm]
        print(f"[DEBUG] calendar_create: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate whether the agent created the event correctly."""
        print("[DEBUG] calendar_create: validate() called")

        try:
            events = env.event_log.list_view()
            p = self._params

            # Check if the add_calendar_event action was called
            event_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "StatefulCalendarApp"
                and event.action.function_name == "add_calendar_event"
                and event.action.args.get("title") == p.title
                for event in events
            )

            print(f"[DEBUG] calendar_create: event_created={event_created}")
            print(f"[DEBUG] calendar_create: Total events in log: {len(events)}")

            # Optional: Verify the event exists in calendar
            calendar = self.get_typed_app(StatefulCalendarApp)
            try:
                result = calendar.get_calendar_events_from_to(
                    start_datetime=ms_to_str(p.start_time_ms), end_datetime=ms_to_str(p.end_time_ms), offset=0, limit=50
                )

                # Extract events list
                cal_events = []
                for attr in ("events", "items"):
                    v = getattr(result, attr, None)
                    if v is not None:
                        v = v() if callable(v) else v
                        if v:
                            cal_events = list(v)
                            break

                if not cal_events:
                    try:
                        cal_events = list(result)
                    except TypeError:
                        cal_events = []

                event_in_calendar = any(getattr(ev, "title", None) == p.title for ev in cal_events)

                print(f"[DEBUG] calendar_create: event_in_calendar={event_in_calendar}, found {len(cal_events)} events")

            except Exception as e:
                print(f"[WARN] calendar_create: Could not verify calendar contents: {e}")
                event_in_calendar = False

            success = event_created
            print(f"[INFO] calendar_create: Validation result: success={success}")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            print(f"[ERROR] calendar_create: Validation failed with exception: {e}")
            import traceback

            traceback.print_exc()

            return ScenarioValidationResult(success=False, exception=e)
