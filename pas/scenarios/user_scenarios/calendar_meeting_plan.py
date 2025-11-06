"""proactive_calendar_meeting_plan: ProposeAndScheduleMeetingScenario.

Agent detects discussion about scheduling and proactively proposes and creates a meeting.
"""

from __future__ import annotations

import logging
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


# ---------- Logger ----------
logger = logging.getLogger(__name__)


# ---------- Parameter definitions ----------
@dataclass
class MeetingParams:
    """Parameters for a proactive meeting."""

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
@register_scenario("proactive_calendar_meeting_plan")
class ProposeAndScheduleMeetingScenario(Scenario):
    """Cal002 (Proactive): Agent proposes meeting time and schedules after confirmation."""

    def __init__(self) -> None:
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
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        self.apps = [agui, system, calendar]
        logger.debug("proactive_calendar_meeting_plan: Apps initialized")

    # ---------- Build proactive event flow ----------
    def build_events_flow(self) -> None:
        """Build proactive flow where agent proposes and confirms a meeting."""
        logger.debug("proactive_calendar_meeting_plan: Building events flow")

        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        p = self._params

        start_str = ms_to_str(p.start_time_ms)
        end_str = ms_to_str(p.end_time_ms)

        with EventRegisterer.capture_mode():
            # Context: team chat detected (not a command)
            context_event = aui.send_message_to_agent(
                content="Hey team, we should have a sync tomorrow to review quarterly plans."
            ).depends_on(None, delay_seconds=1)

            # Agent proactively suggests a meeting
            propose_event = aui.send_message_to_user(
                content=(
                    "I noticed a discussion about having a team sync tomorrow. "
                    f"Would you like me to check everyone's availability and schedule '{p.title}'?"
                )
            ).depends_on(context_event, delay_seconds=2)

            # User confirms scheduling
            confirm_event = aui.send_message_to_agent(
                content="Yes, please find a good time and set it up."
            ).depends_on(propose_event, delay_seconds=2)

            # Agent checks availability of all attendees (oracle)
            availability_checks = []
            if p.attendees:
                for _ in p.attendees:
                    check = (
                        calendar.get_calendar_events_from_to(
                            start_datetime=start_str, end_datetime=end_str
                        )
                        .oracle()
                        .depends_on(confirm_event, delay_seconds=1)
                    )
                    availability_checks.append(check)

            # Agent creates meeting (oracle)
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
                .depends_on(availability_checks[-1] if availability_checks else confirm_event, delay_seconds=1)
            )

            # Agent confirms success
            done_event = aui.send_message_to_user(
                content=f"Everyone is free. I've scheduled '{p.title}' at {p.location} from 3PM–4PM."
            ).depends_on(oracle_create, delay_seconds=1)

        self.events = [
            context_event,
            propose_event,
            confirm_event,
            *availability_checks,
            oracle_create,
            done_event,
        ]
        logger.debug(f"proactive_calendar_meeting_plan: Created {len(self.events)} events")

    # ---------- Validation ----------
    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate proactive meeting proposal and creation."""
        try:
            events = env.event_log.list_view()
            p = self._params

            logger.debug("=== DEBUG EVENTS ===")
            for e in events:
                if isinstance(e.action, Action):
                    logger.debug(
                        f"{e.event_type:<10} | {e.action.class_name:<30} | "
                        f"{e.action.function_name:<25} | {e.action.args}"
                    )
            logger.debug("=== END DEBUG ===")

            # Check that proactive suggestion occurred
            proactive_msg = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    kw in e.action.args.get("content", "").lower()
                    for kw in ["meeting", "schedule", "availability", "sync"]
                )
                for e in events
                if e.event_type in (EventType.ENV, EventType.AGENT)
            )

            # Check that meeting was created
            event_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("title") == p.title
                for e in events
            )

            success = proactive_msg and event_created

            logger.debug("[VALIDATION SUMMARY]")
            logger.debug(f"  - Proactive proposal detected: {'PASS' if proactive_msg else 'FAIL'}")
            logger.debug(f"  - Calendar event created:      {'PASS' if event_created else 'FAIL'}")
            logger.debug(f"  => Scenario result: {'PASS' if success else 'FAIL'}")

            return ScenarioValidationResult(success=success)

        except Exception as exc:
            logger.error(f"proactive_calendar_meeting_plan validation failed: {exc}")
            return ScenarioValidationResult(success=False, exception=exc)

