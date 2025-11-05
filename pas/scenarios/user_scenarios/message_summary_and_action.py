"""
Scenario: proactive_message_summary_and_action
Agent proactively summarizes a recent conversation and offers to create a meeting or related action.
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


# ---------- Parameters ----------
@dataclass
class MessageSummaryParams:
    """Parameters for proactive message summary and meeting creation."""
    conversation_snippet: str
    suggested_action: str
    title: str
    start_time: str
    end_time: str


# ---------- Scenario ----------
@register_scenario("proactive_message_summary_and_action")
class ScenarioProactiveMessageSummaryAndAction(Scenario):
    """Agent proactively summarizes conversation and proposes creating a meeting."""

    def __init__(self) -> None:
        super().__init__()
        self._params = self._get_default_params()

    def _get_default_params(self) -> MessageSummaryParams:
        return MessageSummaryParams(
            conversation_snippet="Bob: let's finalize the project update tomorrow at 10am\nYou: sounds good!",
            suggested_action="create_meeting",
            title="Project Update Discussion",
            start_time="2025-10-28T10:00:00Z",
            end_time="2025-10-28T11:00:00Z",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the required apps."""
        print("[DEBUG] proactive_message_summary_and_action: init_and_populate_apps called")
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        self.apps = [agui, system, calendar]
        print("[DEBUG] proactive_message_summary_and_action: apps initialized")

    def build_events_flow(self) -> None:
        """Define proactive flow: summarize → propose → confirm → create → acknowledge."""
        print("[DEBUG] proactive_message_summary_and_action: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Agent proactively summarizes the chat
            proactive_summary = aui.send_message_to_user(
                content=(
                    f"I noticed your recent conversation with Bob:\n"
                    f"\"{p.conversation_snippet}\"\n\n"
                    f"It sounds like you're planning a discussion. "
                    f"Would you like me to schedule a meeting titled '{p.title}' at {p.start_time}?"
                )
            ).depends_on(None, delay_seconds=1)

            # User confirms meeting creation
            user_confirm = aui.send_message_to_agent(
                content=f"Yes, please schedule '{p.title}' for that time."
            ).depends_on(proactive_summary, delay_seconds=1)

            # Oracle creates the calendar event
            create_event = calendar.add_calendar_event(
                title=p.title,
                start_datetime=p.start_time,
                end_datetime=p.end_time,
                description="Auto-created from conversation summary.",
                location="TBD",
                attendees=["bob@example.com"],
                tag=None,
            ).oracle().depends_on(user_confirm, delay_seconds=1)

            # Agent confirms event creation
            agent_confirm = aui.send_message_to_user(
                content=f"The meeting '{p.title}' has been scheduled for {p.start_time}."
            ).depends_on(create_event, delay_seconds=1)

        self.events = [proactive_summary, user_confirm, create_event, agent_confirm]
        print(f"[DEBUG] proactive_message_summary_and_action: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Verify both proactive summary and successful event creation."""
        print("[DEBUG] proactive_message_summary_and_action: validate() called")

        try:
            events = env.event_log.list_view()
            p = self._params

            # Check proactive summary
            proactive_detected = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "conversation" in e.action.args.get("content", "").lower()
                and "schedule" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Check calendar event creation
            event_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("title") == p.title
                for e in events
            )

            success = proactive_detected and event_created

            print("\n[VALIDATION SUMMARY]")
            print(f"  - Proactive summary detected: {'PASS' if proactive_detected else 'FAIL'}")
            print(f"  - Calendar event created:     {'PASS' if event_created else 'FAIL'}")
            print(f"  => Scenario result: {'PASS' if success else 'FAIL'}\n")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            print(f"[ERROR] proactive_message_summary_and_action: Validation failed: {e}")
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
