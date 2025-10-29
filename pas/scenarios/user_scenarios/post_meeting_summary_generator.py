"""
Scenario: post_meeting_summary_generator
Agent detects recently ended meetings, summarizes them,
and sends meeting summaries to participants automatically.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, EventRegisterer

from pas.apps.calendar import StatefulCalendarApp
from pas.apps.messaging import StatefulMessagingApp


@dataclass
class PostMeetingParams:
    summary_template: str


@register_scenario("post_meeting_summary_generator")
class ScenarioPostMeetingSummaryGenerator(Scenario):
    """Detect recently ended meetings, generate summaries, and notify participants."""

    def __init__(self) -> None:
        super().__init__()
        self._params = PostMeetingParams(
            summary_template="Summary of '{title}':\n- Discussed progress updates\n- Assigned next steps\n- Scheduled next sync for next week"
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        print("[DEBUG] post_meeting_summary_generator: init_and_populate_apps called")
        self.apps = [
            AgentUserInterface(),
            SystemApp(),
            StatefulCalendarApp(),
            StatefulMessagingApp(),
        ]
        print("[DEBUG] post_meeting_summary_generator: apps initialized")

    def build_events_flow(self) -> None:
        print("[DEBUG] post_meeting_summary_generator: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(StatefulCalendarApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Step 1: System triggers check
            trigger = aui.send_message_to_agent(
                content="[System] Checking for recently ended meetings."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Get current time
            now = system.get_current_time().oracle().depends_on(trigger, delay_seconds=1)

            # Step 3: Get today's calendar events
            events = calendar.read_today_calendar_events().oracle().depends_on(now, delay_seconds=1)

            # Step 4: Notify user of detected meetings
            found = aui.send_message_to_user(
                content="Found completed meetings today. Preparing summaries..."
            ).depends_on(events, delay_seconds=1)

            # Step 5: Generate and send summary
            summary_content = p.summary_template.format(title="Product Sprint Sync")
            send_summary = messaging.send_message(
                user_id="user_001",  # mock participant
                content=summary_content,
            ).oracle().depends_on(found, delay_seconds=1)

            # Step 6: Confirm completion
            finish = aui.send_message_to_user(
                content="Meeting summaries sent successfully."
            ).depends_on(send_summary, delay_seconds=1)

        self.events = [trigger, now, events, found, send_summary, finish]
        print(f"[DEBUG] post_meeting_summary_generator: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Confirm that meeting summaries were sent."""
        print("[DEBUG] post_meeting_summary_generator: validate() called")
        try:
            events = env.event_log.list_view()

            def stringify(e) -> str:
                parts = []
                if hasattr(e, "action"):
                    parts.extend([
                        getattr(e.action, "function_name", ""),
                        getattr(e.action, "app_name", ""),
                    ])
                return " ".join(parts).lower()

            sent_msg = any("send_message" in stringify(e) for e in events)
            print(f"[INFO] post_meeting_summary_generator: Validation success={sent_msg}")
            return ScenarioValidationResult(success=sent_msg)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
