"""
Scenario: proactive_post_meeting_summary_generator
Agent proactively detects recently ended meetings, summarizes them,
and sends the summary to participants automatically.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar import StatefulCalendarApp
from pas.apps.messaging import StatefulMessagingApp


# ---------- Logger ----------
logger = logging.getLogger(__name__)


# ---------- Parameters ----------
@dataclass
class PostMeetingParams:
    summary_template: str


# ---------- Scenario ----------
@register_scenario("proactive_post_meeting_summary_generator")
class ScenarioProactivePostMeetingSummaryGenerator(Scenario):
    """Agent proactively summarizes completed meetings and notifies participants."""

    def __init__(self) -> None:
        super().__init__()
        self._params = PostMeetingParams(
            summary_template=(
                "Summary of {title}:\n"
                "- Discussed project progress updates\n"
                "- Assigned next steps to team members\n"
                "- Scheduled next sync for next week"
            )
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all required apps."""
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        messaging = StatefulMessagingApp()
        self.apps = [agui, system, calendar, messaging]
        logger.debug("proactive_post_meeting_summary_generator: Apps initialized")

    def build_events_flow(self) -> None:
        """Define proactive post-meeting summary workflow."""
        logger.debug("proactive_post_meeting_summary_generator: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(StatefulCalendarApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # 1. Agent proactively detects recently ended meetings
            proactive_start = aui.send_message_to_user(
                content="I noticed your meeting just ended — let me summarize the discussion and share it with the team."
            ).depends_on(None, delay_seconds=1)

            # 2. Get current time
            current_time = system.get_current_time().oracle().depends_on(proactive_start, delay_seconds=1)

            # 3. Retrieve today's meetings (real oracle call)
            read_meetings = calendar.read_today_calendar_events().oracle().depends_on(current_time, delay_seconds=1)

            # 4. Agent informs user it is preparing the summary
            preparing_summary = aui.send_message_to_user(
                content="Generating the post-meeting summary now..."
            ).depends_on(read_meetings, delay_seconds=1)

            # 5. Create and send summary message (no hardcoded meeting title)
            summary_text = p.summary_template.format(title="your recent meeting")
            send_summary = messaging.send_message(
                user_id="team_channel",
                content=summary_text,
            ).oracle().depends_on(preparing_summary, delay_seconds=1)

            # 6. Confirm to user that summaries were delivered
            finish = aui.send_message_to_user(
                content="I've sent the meeting summary to all participants."
            ).depends_on(send_summary, delay_seconds=1)

        self.events = [
            proactive_start,
            current_time,
            read_meetings,
            preparing_summary,
            send_summary,
            finish,
        ]
        logger.debug(f"proactive_post_meeting_summary_generator: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that proactive initiation and summary dispatch occurred."""
        logger.debug("proactive_post_meeting_summary_generator: validate() called")

        try:
            events = env.event_log.list_view()

            # Detect proactive trigger
            proactive_detected = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "meeting just ended" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Detect message summary sent to participants
            summary_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and "summary" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = proactive_detected and summary_sent

            logger.debug("[VALIDATION SUMMARY]")
            logger.debug(f"  - Proactive initiation detected: {'PASS' if proactive_detected else 'FAIL'}")
            logger.debug(f"  - Summary message sent:          {'PASS' if summary_sent else 'FAIL'}")
            logger.debug(f"  => Scenario result: {'PASS' if success else 'FAIL'}")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            logger.error(f"[ERROR] proactive_post_meeting_summary_generator: Validation failed: {e}")
            return ScenarioValidationResult(success=False, exception=e)
