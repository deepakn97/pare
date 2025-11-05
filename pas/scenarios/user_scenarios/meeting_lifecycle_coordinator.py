"""
Scenario: proactive_meeting_lifecycle_coordinator
Agent proactively manages the full meeting lifecycle:
Preparation → Action Tracking → Summary → Follow-up.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar import StatefulCalendarApp
from pas.apps.messaging import StatefulMessagingApp


# ---------- Parameters ----------
@dataclass
class CoordinatorParams:
    """Holds configurable templates for sub-scenario steps."""
    prep_msg: str
    tracker_msg: str
    summary_msg: str
    followup_msg: str


# ---------- Scenario ----------
@register_scenario("proactive_meeting_lifecycle_coordinator")
class ScenarioMeetingLifecycleCoordinator(Scenario):
    """Agent orchestrates all four meeting lifecycle stages proactively."""

    def __init__(self) -> None:
        super().__init__()
        self._params = CoordinatorParams(
            prep_msg="Stage 1️: Preparing for upcoming meeting — notifying participants.",
            tracker_msg="Stage 2️: Tracking in-meeting action items and key decisions.",
            summary_msg="Stage 3️: Generating post-meeting summary and distributing notes.",
            followup_msg="Stage 4️: Sending follow-up reminders for pending action items.",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all necessary apps."""
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        messaging = StatefulMessagingApp()
        self.apps = [agui, system, calendar, messaging]
        print("[DEBUG] proactive_meeting_lifecycle_coordinator: Apps initialized")

    def build_events_flow(self) -> None:
        """Define event chain for the proactive lifecycle."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(StatefulCalendarApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Agent proactively initiates meeting lifecycle coordination
            proactive_start = aui.send_message_to_user(
                content="Good morning! I’ll coordinate today’s meeting lifecycle automatically."
            ).depends_on(None, delay_seconds=1)

            # Preparation
            prep_notify = aui.send_message_to_user(content=p.prep_msg).depends_on(proactive_start, delay_seconds=1)
            get_time = system.get_current_time().oracle().depends_on(prep_notify, delay_seconds=1)
            read_calendar = calendar.read_today_calendar_events().oracle().depends_on(get_time, delay_seconds=1)

            # Tracking
            tracker_msg = messaging.send_message(
                user_id="team_channel",
                content=p.tracker_msg,
            ).oracle().depends_on(read_calendar, delay_seconds=1)

            # Summary
            summary_msg = messaging.send_message(
                user_id="team_channel",
                content=p.summary_msg,
            ).oracle().depends_on(tracker_msg, delay_seconds=1)

            # Follow-up reminders
            followup_msg = messaging.send_message(
                user_id="team_channel",
                content=p.followup_msg,
            ).oracle().depends_on(summary_msg, delay_seconds=1)

            # Final Agent confirmation
            finish_msg = aui.send_message_to_user(
                content="All four stages completed successfully. Meeting lifecycle fully coordinated."
            ).depends_on(followup_msg, delay_seconds=1)

        self.events = [
            proactive_start,
            prep_notify,
            get_time,
            read_calendar,
            tracker_msg,
            summary_msg,
            followup_msg,
            finish_msg,
        ]
        print(f"[DEBUG] proactive_meeting_lifecycle_coordinator: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that all four proactive lifecycle stages executed correctly."""
        print("[DEBUG] proactive_meeting_lifecycle_coordinator: validate() called")

        try:
            events = env.event_log.list_view()

            # Detect proactive start
            proactive_detected = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "coordinate" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Stage-specific checks
            prep_done = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "preparing" in e.action.args.get("content", "").lower()
                for e in events
            )

            tracker_done = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and "tracking" in e.action.args.get("content", "").lower()
                for e in events
            )

            summary_done = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and "summary" in e.action.args.get("content", "").lower()
                for e in events
            )

            followup_done = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and "follow-up" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = proactive_detected and prep_done and tracker_done and summary_done and followup_done

            print("\n[VALIDATION SUMMARY]")
            print(f"  - Proactive initiation detected: {'PASS' if proactive_detected else 'FAIL'}")
            print(f"  - Preparation message sent:     {'PASS' if prep_done else 'FAIL'}")
            print(f"  - Action tracking executed:     {'PASS' if tracker_done else 'FAIL'}")
            print(f"  - Summary stage completed:      {'PASS' if summary_done else 'FAIL'}")
            print(f"  - Follow-up reminders sent:     {'PASS' if followup_done else 'FAIL'}")
            print(f"  => Scenario result: {'PASS' if success else 'FAIL'}\n")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
