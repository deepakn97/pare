"""Scenario: message_summary_and_action
Agent proactively summarizes a conversation and offers to create a meeting or related action.
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


@dataclass
class MessageSummaryParams:
    """Parameters for proactive message summary and action creation."""
    conversation_snippet: str
    suggested_action: str
    title: str
    start_time: str
    end_time: str


@register_scenario("message_summary_and_action")
class ScenarioMessageSummaryAndAction(Scenario):
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
        print("[DEBUG] message_summary_and_action: init_and_populate_apps called")
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        self.apps = [agui, system, calendar]
        print("[DEBUG] message_summary_and_action: apps initialized")

    def build_events_flow(self) -> None:
        print("[DEBUG] message_summary_and_action: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Step 1️ Simulate system detecting conversation
            detect_conversation = aui.send_message_to_agent(
                content=f"[System detected conversation context]: {p.conversation_snippet}"
            ).depends_on(None, delay_seconds=1)

            # Step 2️ Agent proposes action
            agent_propose = aui.send_message_to_user(
                content=(
                    f"I noticed in your chat: \"{p.conversation_snippet}\".\n"
                    f"Would you like me to create a meeting titled '{p.title}' "
                    f"for {p.start_time}?"
                )
            ).depends_on(detect_conversation, delay_seconds=1)

            # Step 3️ User confirms
            user_confirm = aui.send_message_to_agent(
                content=f"Yes, please create the meeting '{p.title}'."
            ).depends_on(agent_propose, delay_seconds=1)

            # Step 4️ Oracle performs calendar action
            oracle_create = calendar.add_calendar_event(
                title=p.title,
                start_datetime=p.start_time,
                end_datetime=p.end_time,
                description="Auto-created from conversation summary",
                location="TBD",
                attendees=None,
                tag=None,
            ).oracle().depends_on(user_confirm, delay_seconds=1)

            # Step 5️ Agent confirms success
            agent_confirm = aui.send_message_to_user(
                content=f"I've created the calendar event '{p.title}' as discussed."
            ).depends_on(oracle_create, delay_seconds=1)

        self.events = [detect_conversation, agent_propose, user_confirm, oracle_create, agent_confirm]
        print(f"[DEBUG] message_summary_and_action: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        print("[DEBUG] message_summary_and_action: validate() called")

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

            print(f"[DEBUG] message_summary_and_action: event_created={event_created}")
            print(f"[INFO] message_summary_and_action: Validation result: success={event_created}")
            return ScenarioValidationResult(success=event_created)

        except Exception as e:
            print(f"[ERROR] message_summary_and_action: Validation failed: {e}")
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
