"""
Scenario: proactive_price_evaluation_ad_summary
Agent detects promotional product-discount emails, cross-checks historical online pricing,
evaluates whether the current deal is among the best, and suggests to the user whether to buy now or wait.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, List

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.email import StatefulEmailApp
from pas.apps.messaging import StatefulMessagingApp

@dataclass
class PriceEvalParams:
    keyword_filters: List[str]
    summary_template: str
    threshold_best_percent: float

@register_scenario("proactive_price_evaluation_ad_summary")
class ScenarioProactivePriceEvaluationAdSummary(Scenario):
    """Agent proactively summarises discount ads, checks historical prices, and advises purchase timing."""

    def __init__(self) -> None:
        super().__init__()
        self._params = PriceEvalParams(
            keyword_filters=["discount", "sale", "deal", "save", "off"],
            summary_template="I found {count} discount offers. Item: {item}. Current price: {current_price}. Historical low: {historical_low}. Verdict: {verdict}.",
            threshold_best_percent=5.0,  # if current price is within 5% of historical low → “best deal”
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        aui = AgentUserInterface()
        system = SystemApp()
        email = StatefulEmailApp()
        messaging = StatefulMessagingApp()
        self.apps = [aui, system, email, messaging]
        print("[DEBUG] proactive_price_evaluation_ad_summary: Apps initialized")

    def build_events_flow(self) -> None:
        print("[DEBUG] proactive_price_evaluation_ad_summary: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        email = self.get_typed_app(StatefulEmailApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        system = self.get_typed_app(SystemApp)
        p = self._params
        user_id = "demo_user"

        with EventRegisterer.capture_mode():
            # Agent proactively detects discount-offer emails
            proactive_detect = aui.send_message_to_user(
                content="I have noticed several discount/promotional product emails in your inbox. Would you like me to evaluate whether the current prices are truly a best deal?"
            ).depends_on(None, delay_seconds=1)

            # User confirms
            user_confirm = aui.send_message_to_agent(
                content="Yes, please evaluate those offers for me."
            ).depends_on(proactive_detect, delay_seconds=1)

            # Get current time (for reference)
            current_time = system.get_current_time().oracle().depends_on(user_confirm, delay_seconds=1)

            # Email app searches for discount offer emails
            fetch_ads = email.search_emails(
                query=" OR ".join(p.keyword_filters)
            ).oracle().depends_on(current_time, delay_seconds=1)

            # Agent cross-checks historical pricing (simulated)
            # Simulated: item “4K TV Model X”, current price $799, historical low $750
            item = "4K TV Model X"
            current_price = 799
            historical_low = 750
            price_diff = ((current_price - historical_low) / historical_low) * 100
            verdict = "Best deal" if price_diff <= p.threshold_best_percent else "Could be better"

            summary = aui.send_message_to_user(
                content=p.summary_template.format(
                    count=1,
                    item=item,
                    current_price=f"${current_price}",
                    historical_low=f"${historical_low}",
                    verdict=verdict
                )
            ).depends_on(fetch_ads, delay_seconds=1)

            # Agent proposes an action
            propose = aui.send_message_to_user(
                content=("Would you like me to set a price-watch alert if this isn't the best deal, or buy it now?")
            ).depends_on(summary, delay_seconds=1)

            # Simulate user decision
            user_decision = aui.send_message_to_agent(
                content="Set a price-watch alert please."
            ).depends_on(propose, delay_seconds=1)

            # Messaging app confirms the action
            confirm = messaging.send_message(
                user_id=user_id,
                content=" Got it. I will monitor that item and alert you if the price drops further."
            ).oracle().depends_on(user_decision, delay_seconds=1)

        self.events = [
            proactive_detect,
            user_confirm,
            current_time,
            fetch_ads,
            summary,
            propose,
            user_decision,
            confirm
        ]
        print(f"[DEBUG] proactive_price_evaluation_ad_summary: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        print("[DEBUG] proactive_price_evaluation_ad_summary: validate() called")

        try:
            events = env.event_log.list_view()
            p = self._params

            proactive_triggered = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "discount/promotional product emails" in e.action.args.get("content", "").lower()
                for e in events
            )
            email_search_executed = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["search_emails", "read_emails"]
                for e in events
            )
            summary_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "verdict" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = proactive_triggered and email_search_executed and summary_sent

            print("\n[VALIDATION SUMMARY]")
            print(f"  - Proactive detection triggered: {'PASS' if proactive_triggered else 'FAIL'}")
            print(f"  - Email search executed:            {'PASS' if email_search_executed else 'FAIL'}")
            print(f"  - Summary message sent:             {'PASS' if summary_sent else 'FAIL'}")
            print(f"  => Scenario result: {'PASS' if success else 'FAIL'}\n")

            return ScenarioValidationResult(success=success)
        except Exception as e:
            print(f"[ERROR] proactive_price_evaluation_ad_summary: Validation failed: {e}")
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
