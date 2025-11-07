"""
Scenario: proactive_advertisement_email_unsubscribe
Agent proactively detects promotional advertisement emails,
summarizes frequent senders, and asks the user whether to unsubscribe from any of them.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, List

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.email import StatefulEmailApp
from pas.apps.messaging import StatefulMessagingApp


# ---------- Logger ----------
logger = logging.getLogger(__name__)


# ---------- Parameters ----------
@dataclass
class AdEmailParams:
    keywords: List[str]
    summary_template: str


# ---------- Scenario ----------
@register_scenario("proactive_advertisement_email_unsubscribe")
class ScenarioProactiveAdvertisementEmailUnsubscribe(Scenario):
    """Agent proactively summarizes promotional emails and offers to unsubscribe the user."""

    def __init__(self) -> None:
        super().__init__()
        self._params = AdEmailParams(
            keywords=["sale", "promotion", "offer", "discount", "deal", "new product"],
            summary_template="I found {count} promotional emails from: {senders}. Would you like me to unsubscribe from any of them?",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize required apps."""
        aui = AgentUserInterface()
        system = SystemApp()
        email = StatefulEmailApp()
        messaging = StatefulMessagingApp()
        self.apps = [aui, system, email, messaging]
        logger.debug("proactive_advertisement_email_unsubscribe: Apps initialized")

    def build_events_flow(self) -> None:
        """Define proactive flow for detecting and unsubscribing promotional emails."""
        logger.debug("proactive_advertisement_email_unsubscribe: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        email = self.get_typed_app(StatefulEmailApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # 1. Agent proactively detects advertisement emails
            proactive_detect = aui.send_message_to_user(
                content="I noticed several promotional and advertisement emails in your inbox. Would you like me to summarize them and check for unsubscribe options?"
            ).depends_on(None, delay_seconds=1)

            # 2. User confirms summarization
            user_confirm = aui.send_message_to_agent(
                content="Yes, please summarize and help me unsubscribe from unwanted senders."
            ).depends_on(proactive_detect, delay_seconds=1)

            # 3. System gets current time
            current_time = system.get_current_time().oracle().depends_on(user_confirm, delay_seconds=1)

            # 4. Email app searches advertisement messages
            fetch_ads = email.search_emails(
                query=" OR ".join(p.keywords)
            ).oracle().depends_on(current_time, delay_seconds=1)

            # 5. Agent summarizes top senders (simulated)
            summary_msg = aui.send_message_to_user(
                content=p.summary_template.format(
                    count=4,
                    senders="Amazon Deals, BestBuy, Adobe Creative Cloud, and Nike",
                )
            ).depends_on(fetch_ads, delay_seconds=1)

            # 6. Agent asks whether to unsubscribe
            unsubscribe_prompt = aui.send_message_to_user(
                content="Would you like me to unsubscribe you from any of these promotional senders?"
            ).depends_on(summary_msg, delay_seconds=1)

            # 7. User replies with decision
            user_decision = aui.send_message_to_agent(
                content="Unsubscribe from Adobe Creative Cloud and Nike, keep the others."
            ).depends_on(unsubscribe_prompt, delay_seconds=1)

            # 8. Messaging app confirms simulated unsubscription
            confirm_msg = messaging.send_message(
                user_id="demo_user",
                content="You have been unsubscribed from Adobe Creative Cloud and Nike promotional emails. Amazon and BestBuy remain subscribed.",
            ).oracle().depends_on(user_decision, delay_seconds=1)

            # 9. Agent finalizes the confirmation
            finish = aui.send_message_to_user(
                content="Your email subscriptions have been updated successfully."
            ).depends_on(confirm_msg, delay_seconds=1)

        self.events = [
            proactive_detect,
            user_confirm,
            current_time,
            fetch_ads,
            summary_msg,
            unsubscribe_prompt,
            user_decision,
            confirm_msg,
            finish,
        ]
        logger.debug(f"proactive_advertisement_email_unsubscribe: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate proactive detection, email search, and unsubscribe confirmation."""
        logger.debug("proactive_advertisement_email_unsubscribe: validate() called")

        try:
            events = env.event_log.list_view()

            # Check proactive trigger
            proactive_triggered = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "promotional" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Check email search executed
            email_search_executed = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["search_emails", "read_emails"]
                for e in events
            )

            # Check unsubscribe detected
            unsubscribe_detected = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "unsubscribe" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = proactive_triggered and email_search_executed and unsubscribe_detected

            logger.debug("[VALIDATION SUMMARY]")
            logger.debug(f"  - Proactive detection triggered: {'PASS' if proactive_triggered else 'FAIL'}")
            logger.debug(f"  - Email search executed:         {'PASS' if email_search_executed else 'FAIL'}")
            logger.debug(f"  - Unsubscribe decision detected: {'PASS' if unsubscribe_detected else 'FAIL'}")
            logger.debug(f"  => Scenario result: {'PASS' if success else 'FAIL'}")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            logger.error(f"[ERROR] proactive_advertisement_email_unsubscribe: Validation failed: {e}")
            return ScenarioValidationResult(success=False, exception=e)
