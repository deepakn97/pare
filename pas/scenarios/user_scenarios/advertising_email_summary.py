"""
Scenario: proactive_advertising_email_summary
Agent detects a surge of promotional or marketing emails in the inbox,
summarizes their content (e.g., brands, discounts, offers),
and suggests actions like unsubscribing or moving them to a separate folder.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, List

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, EventRegisterer, Action, EventType

from pas.apps.email import StatefulEmailApp
from pas.apps.messaging import StatefulMessagingApp


# ---------- Parameters ----------
@dataclass
class AdEmailParams:
    keyword_filters: List[str]
    summary_template: str


# ---------- Scenario ----------
@register_scenario("proactive_advertising_email_summary")
class ScenarioProactiveAdvertisingEmailSummary(Scenario):
    """Proactively detects promotional emails and summarizes recent offers."""

    def __init__(self) -> None:
        super().__init__()
        self._params = AdEmailParams(
            keyword_filters=["sale", "discount", "deal", "promotion", "offer"],
            summary_template=" I found {count} promotional emails this week. Top brands: {brands}.",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps used in this scenario."""
        aui = AgentUserInterface()
        system = SystemApp()
        email = StatefulEmailApp()
        messaging = StatefulMessagingApp()
        self.apps = [aui, system, email, messaging]
        print("[DEBUG] proactive_advertising_email_summary: Apps initialized")

    def build_events_flow(self) -> None:
        """Define proactive advertising email summarization flow."""
        print("[DEBUG] proactive_advertising_email_summary: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        email = self.get_typed_app(StatefulEmailApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Agent proactively detects surge of advertising emails
            proactive_detect = aui.send_message_to_user(
                content="I've noticed you've been receiving many promotional emails lately. Would you like me to summarize them for you?"
            ).depends_on(None, delay_seconds=1)

            # User agrees to summarization
            user_confirm = aui.send_message_to_agent(
                content="Yes, please summarize the recent promotional emails."
            ).depends_on(proactive_detect, delay_seconds=1)

            # System gets current time
            current_time = system.get_current_time().oracle().depends_on(user_confirm, delay_seconds=1)

            # Email app searches promotional messages by keywords
            fetch_ads = email.search_emails(
                query=" OR ".join(p.keyword_filters)
            ).oracle().depends_on(current_time, delay_seconds=1)

            # Agent summarizes detected promotional content
            summary = aui.send_message_to_user(
                content=p.summary_template.format(count=8, brands="Amazon, Nike, Apple")
            ).depends_on(fetch_ads, delay_seconds=1)

            # Suggest action to user
            suggest_action = aui.send_message_to_user(
                content="Would you like me to move these to a 'Promotions' folder or unsubscribe from them?"
            ).depends_on(summary, delay_seconds=1)

            # Send confirmation message to wrap up
            finish = messaging.send_message(
                user_id="demo_user",
                content="Summary and recommendations sent successfully."
            ).oracle().depends_on(suggest_action, delay_seconds=1)

        self.events = [
            proactive_detect,
            user_confirm,
            current_time,
            fetch_ads,
            summary,
            suggest_action,
            finish,
        ]
        print(f"[DEBUG] proactive_advertising_email_summary: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate proactive trigger, email search, and summary generation."""
        print("[DEBUG] proactive_advertising_email_summary: validate() called")
        try:
            events = env.event_log.list_view()
            p = self._params

            proactive_triggered = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "promotional emails" in e.action.args.get("content", "").lower()
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
                and "summary" in e.action.args.get("content", "")
                for e in events
            )

            success = proactive_triggered and email_search_executed and summary_sent

            print("\n[VALIDATION SUMMARY]")
            print(f"  - Proactive detection triggered: {'PASS' if proactive_triggered else 'FAIL'}")
            print(f"  - Email search executed:         {'PASS' if email_search_executed else 'FAIL'}")
            print(f"  - Summary message sent:          {'PASS' if summary_sent else 'FAIL'}")
            print(f"  => Scenario result: {'PASS' if success else 'FAIL '}\n")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            print(f"[ERROR] proactive_advertising_email_summary: Validation failed: {e}")
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
