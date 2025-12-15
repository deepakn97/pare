"""start of the template to build scenario for Proactive Agent."""

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


@register_scenario("wedding_menu_allergen_cascade")
class WeddingMenuAllergenCascade(PASScenario):
    """The user is coordinating their wedding reception scheduled in ten days and receives an email from their caterer on Tuesday confirming the final guest count and locked menu selections for 85 attendees. That evening, a close family friend messages apologetically to say they just learned their eight-year-old daughter (who is attending as part of their family) was diagnosed with a severe tree nut allergy following an emergency room visit last weekend. The friend asks if the reception menu contains any nut products because they need to know whether to bring separate safe food for their child or if the venue can accommodate. The user's calendar shows the caterer's contract required menu finalization 14 days before the event, meaning this request arrives after the change deadline. Their contacts app contains the catering manager, the venue coordinator who handles kitchen safety protocols, and six other wedding guests whose RSVP notes mention various dietary restrictions (vegetarian, gluten-free, shellfish allergy) that were already accommodated in the planned menu.

    The proactive agent correlates the allergy disclosure with the calendar deadline showing menu changes are contractually prohibited, then cross-references the caterer's confirmation email to identify that the dessert course includes a walnut-crusted tart and the salad features candied pecans as garnish. The agent recognizes this creates both an immediate safety obligation (protecting the child from allergen exposure) and a potential legal liability issue (cross-contamination in venues serving multiple dietary restriction meals). By examining contacts and previous email threads about menu planning, the agent discovers the user already negotiated allergen-safe meal preparation for other guests, suggesting the kitchen has protocols in place but may not know about this new restriction. The agent infers that simply telling the family to bring outside food might violate venue policies, while doing nothing risks a medical emergency at the wedding, requiring coordination across the caterer, venue, family, and possibly other nut-allergic guests who haven't disclosed yet.

    The agent proactively offers to draft an urgent email to the catering manager explaining the new severe allergy and requesting confirmation of which specific dishes contain tree nuts, asking whether the contracted dessert and salad can be modified for one child's plate or if a completely separate nut-free meal option exists within their kitchen capabilities, send a message to the venue coordinator asking about their allergen cross-contamination protocols and whether they can guarantee a safe meal prep environment given other dietary restrictions already in play, compose a reassuring reply to the family friend confirming the user is working with vendors to ensure their daughter's safety and will provide details within 24 hours, search the user's email history for other guests' RSVP messages to check if anyone else mentioned nut allergies that might have been overlooked during initial planning, and create a calendar reminder to follow up with the catering manager tomorrow morning if they haven't confirmed accommodations. The user accepts this safety-critical coordination plan, recognizing the agent understood that wedding vendor contracts create inflexibility but child safety supersedes contractual deadlines, that kitchen allergen protocols require explicit verification rather than assumptions, and that one disclosed restriction might indicate other similar undisclosed needs requiring proactive outreach to the full guest list..
    """

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


"""end of the template to build scenario for Proactive Agent."""
