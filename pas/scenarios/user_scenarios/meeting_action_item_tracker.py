"""
Scenario: meeting_action_item_tracker
Agent reviews meeting notes, extracts action items, confirms responsible contacts,
and schedules follow-up reminders.
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
from pas.apps.contacts import StatefulContactsApp
from pas.apps.messaging import StatefulMessagingApp


@dataclass
class ActionItemParams:
    meeting_title: str
    action_items: list[tuple[str, str]]
    followup_date: str


@register_scenario("meeting_action_item_tracker")
class ScenarioMeetingActionItemTracker(Scenario):
    """Summarize meeting tasks and schedule follow-ups for each responsible contact."""

    def __init__(self) -> None:
        super().__init__()
        self._params = self._get_default_params()

    def _get_default_params(self) -> ActionItemParams:
        return ActionItemParams(
            meeting_title="Product Sprint Sync",
            action_items=[
                ("Prepare new API documentation", "Alice"),
                ("Finalize UI mockups", "Bob"),
                ("Test login flow", "Carol"),
            ],
            followup_date="2025-10-31T17:00:00Z",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        print("[DEBUG] meeting_action_item_tracker: init_and_populate_apps called")
        self.apps = [
            AgentUserInterface(),
            SystemApp(),
            StatefulCalendarApp(),
            StatefulContactsApp(),
            StatefulMessagingApp(),
        ]
        print("[DEBUG] meeting_action_item_tracker: apps initialized")

    def build_events_flow(self) -> None:
        print("[DEBUG] meeting_action_item_tracker: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        contacts = self.get_typed_app(StatefulContactsApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        action_summary = "\n  - ".join([f"{t} → {a}" for t, a in p.action_items])

        with EventRegisterer.capture_mode():
            detect_meeting = aui.send_message_to_agent(
                content=f"[System] Detected notes from '{p.meeting_title}'"
            ).depends_on(None, delay_seconds=1)

            summarize_tasks = aui.send_message_to_user(
                content=(
                    f"From the meeting '{p.meeting_title}', I extracted these action items:\n"
                    f"  - {action_summary}"
                )
            ).depends_on(detect_meeting, delay_seconds=1)

            propose_followup = aui.send_message_to_user(
                content=f"Would you like me to set reminders for these on {p.followup_date.split('T')[0]}?"
            ).depends_on(summarize_tasks, delay_seconds=1)

            user_confirm = aui.send_message_to_agent(
                content="Yes, please set reminders for everyone."
            ).depends_on(propose_followup, delay_seconds=1)

            create_event = calendar.add_calendar_event(
                title=f"Follow-up: {p.meeting_title}",
                start_datetime=p.followup_date,
                end_datetime=p.followup_date,
                description="Automated reminder for action items",
                location="Office",
                attendees=[a for _, a in p.action_items],
                tag="followup",
            ).oracle().depends_on(user_confirm, delay_seconds=1)

            notify = messaging.send_message(
                user_id="demo_user",
                content=(
                    f"📢 Follow-up scheduled for '{p.meeting_title}'. "
                    f"Action items:\n  - {action_summary}"
                ),
            ).depends_on(create_event, delay_seconds=1)

            final_msg = aui.send_message_to_user(
                content=f"Reminders set and team notified for '{p.meeting_title}'."
            ).depends_on(notify, delay_seconds=1)

        self.events = [
            detect_meeting,
            summarize_tasks,
            propose_followup,
            user_confirm,
            create_event,
            notify,
            final_msg,
        ]
        print(f"[DEBUG] meeting_action_item_tracker: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """More robust validation that adapts to ARE event log formats."""
        print("[DEBUG] meeting_action_item_tracker: validate() called")
        try:
            events = env.event_log.list_view()

            def stringify(e) -> str:
                """Extract action-related info as lowercase string for fuzzy match."""
                parts = []
                if hasattr(e, "action_id"):
                    parts.append(str(e.action_id))
                if hasattr(e, "action"):
                    parts.extend([
                        getattr(e.action, "class_name", ""),
                        getattr(e.action, "function_name", ""),
                        getattr(e.action, "app_name", ""),
                        getattr(e.action, "tool_name", ""),
                    ])
                return " ".join(parts).lower()

            # Look for any event related to calendar creation
            created = any("calendar" in stringify(e) and "add" in stringify(e) for e in events)
            # Look for any messaging send action
            notified = any("messaging" in stringify(e) and "send" in stringify(e) for e in events)

            ok = created and notified
            print(f"[INFO] meeting_action_item_tracker: Validation success={ok}")
            return ScenarioValidationResult(success=ok)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
