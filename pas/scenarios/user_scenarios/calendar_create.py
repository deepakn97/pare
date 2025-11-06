"""proactive_calendar_create: ProactiveScheduleEventScenario.

Agent detects meeting intent and proactively proposes scheduling a calendar event.
"""

from __future__ import annotations

import logging
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


# ---------- Logger ----------
logger = logging.getLogger(__name__)


@dataclass
class ScheduleParams:
    """Parameters for proactive meeting scheduling."""

    start_time_ms: int
    end_time_ms: int
    title: str
    location: str = ""
    description: str = ""


def ms_to_str(ms: int) -> str:
    """Convert milliseconds timestamp to datetime string."""
    dt = datetime.fromtimestamp(ms / 1000, tz=UTC)
    return dt.strftime(DATETIME_FORMAT)


@register_scenario("proactive_calendar_create")
class ProactiveScheduleEventScenario(Scenario):
    """Proactive variant: agent detects intent and offers to schedule meeting."""

    start_time: float | None = 0
    duration: float | None = 1  # Duration in hours

    def __init__(self) -> None:
        super().__init__()
        self._params = self._get_default_params()

    def _get_default_params(self) -> ScheduleParams:
        """Get default meeting parameters."""
        return ScheduleParams(
            start_time_ms=1761420000000,  # Oct 24, 2025 3:00 PM UTC
            end_time_ms=1761423600000,    # Oct 24, 2025 4:00 PM UTC
            title="Team Sync",
            location="ESB 1001",
            description="Bring slides and progress updates.",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps."""
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        self.apps = [agui, system, calendar]
        logger.debug("proactive_calendar_create: Apps initialized")

    def build_events_flow(self) -> None:
        """Define proactive event flow."""
        logger.debug("proactive_calendar_create: Building events flow")
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Context trigger: user receives a message from collaborator
            context_event = aui.send_message_to_agent(
                content="Hey, we should meet tomorrow at 3PM to sync up on slides."
            ).depends_on(None, delay_seconds=1)

            # Agent proactively interprets intent and asks user
            propose_event = aui.send_message_to_user(
                content=(
                    "I noticed your collaborator mentioned a meeting tomorrow at 3PM. "
                    "Would you like me to schedule a 'Team Sync' in your calendar?"
                )
            ).depends_on(context_event, delay_seconds=2)

            # User confirms scheduling
            confirm_event = aui.send_message_to_agent(
                content="Yes, please add it to my calendar."
            ).depends_on(propose_event, delay_seconds=2)

            # Agent creates calendar event (oracle)
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
                .depends_on(confirm_event, delay_seconds=1)
            )

            # Agent confirms creation
            done_event = aui.send_message_to_user(
                content=f"I've scheduled '{p.title}' from 3PM–4PM at {p.location}."
            ).depends_on(oracle_create, delay_seconds=1)

        self.events = [context_event, propose_event, confirm_event, oracle_create, done_event]
        logger.debug(f"proactive_calendar_create: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate proactive scheduling behavior."""
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

            # Check proactive message (agent offering scheduling)
            proactive_msg = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    kw in e.action.args.get("content", "").lower()
                    for kw in ["meeting", "schedule", "calendar", "sync"]
                )
                for e in events
                if e.event_type in (EventType.ENV, EventType.AGENT)
            )

            # Check that a calendar event was created
            event_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("title") == p.title
                for e in events
            )

            success = proactive_msg and event_created

            logger.debug("[VALIDATION SUMMARY]")
            logger.debug(f"  - Proactive scheduling detected: {'PASS' if proactive_msg else 'FAIL'}")
            logger.debug(f"  - Calendar event created:        {'PASS' if event_created else 'FAIL'}")
            logger.debug(f"  => Scenario result: {'PASS' if success else 'FAIL'}")

            return ScenarioValidationResult(success=success)

        except Exception as exc:
            logger.error(f"proactive_calendar_create validation failed: {exc}")
            return ScenarioValidationResult(success=False, exception=exc)
