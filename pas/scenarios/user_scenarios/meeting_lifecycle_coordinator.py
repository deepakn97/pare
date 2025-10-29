"""
Scenario: meeting_lifecycle_coordinator
Orchestrates the full proactive meeting lifecycle:
Preparation → Action Tracking → Summary → Follow-up.
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
class CoordinatorParams:
    """Holds configurable templates for sub-scenario steps."""
    prep_msg: str
    tracker_msg: str
    summary_msg: str
    followup_msg: str


@register_scenario("meeting_lifecycle_coordinator")
class ScenarioMeetingLifecycleCoordinator(Scenario):
    """Run all four meeting stages in sequence."""

    def __init__(self) -> None:
        super().__init__()
        self._params = CoordinatorParams(
            prep_msg="Stage 1: Preparing upcoming meeting and notifying participants.",
            tracker_msg="Stage 2: Tracking in-meeting action items.",
            summary_msg="Stage 3: Generating post-meeting summary and distributing notes.",
            followup_msg="Stage 4: Sending follow-up reminders for pending tasks.",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        print("[DEBUG] meeting_lifecycle_coordinator: init_and_populate_apps called")
        self.apps = [
            AgentUserInterface(),
            SystemApp(),
            StatefulCalendarApp(),
            StatefulMessagingApp(),
        ]
        print("[DEBUG] meeting_lifecycle_coordinator: apps initialized")

    def build_events_flow(self) -> None:
        print("[DEBUG] meeting_lifecycle_coordinator: build_events_flow called")
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(StatefulCalendarApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Stage 1: Meeting preparation
            prep_notify = aui.send_message_to_user(content=p.prep_msg).depends_on(None, delay_seconds=1)
            get_time = system.get_current_time().oracle().depends_on(prep_notify, delay_seconds=1)
            get_events = calendar.read_today_calendar_events().oracle().depends_on(get_time, delay_seconds=1)

            # Stage 2: Action item tracker
            tracker = messaging.send_message(
                user_id="user_team",
                content=p.tracker_msg,
            ).oracle().depends_on(get_events, delay_seconds=1)

            # Stage 3: Post-meeting summary
            summary = messaging.send_message(
                user_id="user_team",
                content=p.summary_msg,
            ).oracle().depends_on(tracker, delay_seconds=1)

            # Stage 4: Task follow-up reminder
            followup = messaging.send_message(
                user_id="user_team",
                content=p.followup_msg,
            ).oracle().depends_on(summary, delay_seconds=1)

            # Final confirmation
            finish = aui.send_message_to_user(
                content="All four stages executed successfully."
            ).depends_on(followup, delay_seconds=1)

        self.events = [prep_notify, get_time, get_events, tracker, summary, followup, finish]
        print(f"[DEBUG] meeting_lifecycle_coordinator: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure that all four sub-stages executed successfully."""
        print("[DEBUG] meeting_lifecycle_coordinator: validate() called")
        try:
            events = env.event_log.list_view()

            def stringify(e) -> str:
                parts = []
                if hasattr(e, "action"):
                    parts.extend([
                        getattr(e.action, "function_name", ""),
                        getattr(e.action, "app_name", ""),
                        getattr(e.action, "args", []),
                    ])
                return " ".join(map(str, parts)).lower()

            all_msgs = [stringify(e) for e in events]
            all_stages = all(stage.lower() in " ".join(all_msgs)
                             for stage in ["preparing", "tracking", "summary", "follow-up"])

            success = any("send_message" in s for s in all_msgs) and all_stages
            print(f"[INFO] meeting_lifecycle_coordinator: Validation success={success}")
            return ScenarioValidationResult(success=success)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
