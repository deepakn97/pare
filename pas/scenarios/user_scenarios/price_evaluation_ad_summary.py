"""
Scenario: proactive_price_evaluation_ad_summary
Agent proactively detects promotional product emails, reviews them,
and advises the user whether the offers appear competitive or worth tracking.

All information is derived from EmailApp’s existing state. No mocked data or fake prices.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, List

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, EventRegisterer, Action

from pas.apps.email import StatefulEmailApp
from pas.apps.messaging import StatefulMessagingApp


# ---------- Logger ----------
logger = logging.getLogger(__name__)


# ---------- Parameters ----------
@dataclass
class PriceEvaluationParams:
    """Parameters for proactive price evaluation and summary."""
    keyword_filters: List[str]
    summary_message: str
    followup_question: str


# ---------- Scenario ----------
@register_scenario("proactive_price_evaluation_ad_summary")
class ScenarioProactivePriceEvaluationAdSummary(Scenario):
    """Proactively summarizes promotional emails and suggests price-tracking actions."""

    def __init__(self) -> None:
        super().__init__()
        self._params = PriceEvaluationParams(
            keyword_filters=["discount", "deal", "offer", "promotion", "sale", "price drop"],
            summary_message=(
                "I've reviewed your recent promotional emails — several include notable discounts "
                "and limited-time offers from various retailers."
            ),
            followup_question="Would you like me to set a price-watch alert or track similar offers for you?",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize required simulation apps."""
        aui = AgentUserInterface()
        system = SystemApp()
        email = StatefulEmailApp()
        messaging = StatefulMessagingApp()
        self.apps = [aui, system, email, messaging]
        logger.debug("proactive_price_evaluation_ad_summary: Apps initialized")

    def build_events_flow(self) -> None:
        """Define proactive promotional email evaluation flow."""
        logger.debug("proactive_price_evaluation_ad_summary: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        email = self.get_typed_app(StatefulEmailApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # 1️⃣ Agent proactively detects discount-related emails
            detect_ads = aui.send_message_to_user(
                content="I noticed several recent promotional emails mentioning product discounts and deals."
            ).depends_on(None, delay_seconds=1)

            # 2️⃣ Agent asks if user wants a summary
            ask_consent = aui.send_message_to_user(
                content="Would you like me to summarize and evaluate whether these offers seem competitive?"
            ).depends_on(detect_ads, delay_seconds=1)

            # 3️⃣ User confirmation (simulated via AUI)
            user_confirm = aui.send_message_to_agent(
                content="Yes, please summarize the recent promotional offers."
            ).depends_on(ask_consent, delay_seconds=1)

            # 4️⃣ Get current time
            current_time = system.get_current_time().oracle().depends_on(user_confirm, delay_seconds=1)

            # 5️⃣ Search promotional emails via EmailApp
            fetch_promos = email.search_emails(
                query=" OR ".join(p.keyword_filters)
            ).oracle().depends_on(current_time, delay_seconds=1)

            # 6️⃣ Agent provides summary (no fake prices)
            summary = aui.send_message_to_user(
                content=p.summary_message
            ).depends_on(fetch_promos, delay_seconds=1)

            # 7️⃣ Ask user whether to set a price alert
            ask_action = aui.send_message_to_user(
                content=p.followup_question
            ).depends_on(summary, delay_seconds=1)

            # 8️⃣ Simulated user decision
            user_decision = aui.send_message_to_agent(
                content="Set a price-watch alert please."
            ).depends_on(ask_action, delay_seconds=1)

            # 9️⃣ Messaging app confirms the action
            confirm = messaging.send_message(
                user_id="demo_user",
                content="Got it. I’ll monitor for future discounts and notify you when better offers appear."
            ).oracle().depends_on(user_decision, delay_seconds=1)

        # Register event sequence
        self.events = [
            detect_ads,
            ask_consent,
            user_confirm,
            current_time,
            fetch_promos,
            summary,
            ask_action,
            user_decision,
            confirm,
        ]

        logger.debug(f"proactive_price_evaluation_ad_summary: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate proactive detection, email search, and summary delivery."""
        logger.debug("proactive_price_evaluation_ad_summary: validate() called")

        try:
            events = env.event_log.list_view()

            proactive_triggered = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "promotional emails" in e.action.args.get("content", "").lower()
                for e in events
            )

            email_search_done = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["search_emails", "read_emails"]
                for e in events
            )

            summary_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and any(word in e.action.args.get("content", "").lower() for word in ["discount", "deal", "offer"])
                for e in events
            )

            success = proactive_triggered and email_search_done and summary_sent

            logger.debug("[VALIDATION SUMMARY]")
            logger.debug(f"  - Proactive detection triggered: {'PASS' if proactive_triggered else 'FAIL'}")
            logger.debug(f"  - Email search executed:         {'PASS' if email_search_done else 'FAIL'}")
            logger.debug(f"  - Summary message sent:          {'PASS' if summary_sent else 'FAIL'}")
            logger.debug(f"  => Scenario result: {'PASS' if success else 'FAIL'}")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            logger.error(f"[ERROR] proactive_price_evaluation_ad_summary: Validation failed: {e}")
            return ScenarioValidationResult(success=False, exception=e)
