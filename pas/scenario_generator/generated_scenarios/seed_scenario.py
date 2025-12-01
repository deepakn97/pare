"""A template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Event, EventRegisterer

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("seed_scenario")
class ScenarioName(PASScenario):
    """<<scenario_description>>."""

    # you can just reuse the start_time below
    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # TODO: Initialize scenario specific apps here

        # TODO: Populate apps with scenario specific data here

        # TODO: Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")

        with EventRegisterer.capture_mode():
            # TODO: Add environment events here

            # TODO: Add oracle events here
            # -- Agent will detect environment events, check App state changes(if necessary), send proposal to user via aui.send_message_to_user(...)
            # -- User will choose to accept the Agent proposal via aui.accept_proposal(...)
            # -- Agent will again detect environment events(if has), check App state changes(if necessary), and interacts with available methods in Apps based on its findings

            pass

        # TODO: Register ALL events here in self.events
        self.events: list[Event] = []

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # TODO: Check Step 1: Agent sent proposal to the user
            # example: proposal_found = ...

            # TODO: Check Step 2(contains one or more checks based on Agent detections): Agent detected one or more app states according to previous happened environment events
            # example: detect_action1_found = ...

            # TODO: Check Step 3(contains one or more checks based on Agent actions): Agent's actions -- Agent interacted with methods in Apps based on previous findings
            # example: execute_action1_found = ...

            # TODO: get the success result
            # example: success = (proposal_found and detect_action1_found and execute_action1_found and ...)
            success = True
            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
