"""
Scenario: proactive_subscription_email_summary
Agent scans recent subscription-related emails, summarizes upcoming renewals,
notifies the user about auto-renew dates, and asks if they wish to cancel any.
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
class SubscriptionEmailParams:
    keywords: List[str]
    summary_template: str


# ---------- Scenario ----------
@register_scenario("proactive_subscription_email_summary")
class ScenarioProactiveSubscriptionEmailSummary(Scenario):
    """Proactively summarizes subscription and renewal emails, warns about auto-renewals."""

    def __init__(self) -> None:
        super().__init__()
        self._params = SubscriptionEmailParams(
            keywords=["subscription", "renewal", "membership", "auto-renew", "invoice"],
            summary_template=" I found {count} active subscriptions: {services}. "
                             "The nearest renewal is on {nearest_date}.",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize core apps for proactive subscription summarization."""
        aui = AgentUserInterface()
        system = SystemApp()
        email = StatefulEmailApp()
        messaging = StatefulMessagingApp()
        self.apps = [aui, system, email, messaging]
        print("[DEBUG] proactive_subscription_email_summary: Apps initialized")

    def build_events_flow(self) -> None:
        """Build proactive email summarization and renewal reminder workflow."""
        print("[DEBUG] proactive_subscription_email_summary: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        email = self.get_typed_app(StatefulEmailApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # Agent proactively detects recurring subscription emails
            proactive_detect = aui.send_message_to_user(
                content="I noticed several subscription-related emails in your inbox — would you like me to summarize your active memberships and renewal dates?"
            ).depends_on(None, delay_seconds=1)

            # User confirms summarization
            user_confirm = aui.send_message_to_agent(
                content="Yes, please summarize my active subscriptions."
            ).depends_on(proactive_detect, delay_seconds=1)

            # Get current time
            current_time = system.get_current_time().oracle().depends_on(user_confirm, delay_seconds=1)

            # Email app searches subscription-related messages
            fetch_subscriptions = email.search_emails(
                query=" OR ".join(p.keywords)
            ).oracle().depends_on(current_time, delay_seconds=1)

            # Agent summarizes found subscriptions
            summary_msg = aui.send_message_to_user(
                content=p.summary_template.format(
                    count=3,
                    services="Netflix, Spotify, Adobe Creative Cloud",
                    nearest_date="2025-11-20",
                )
            ).depends_on(fetch_subscriptions, delay_seconds=1)

            # Agent proactively warns about auto-renewals
            warn_msg = aui.send_message_to_user(
                content="⚠️ Netflix and Adobe Creative Cloud are set to auto-renew this month. Would you like me to cancel or pause any of them?"
            ).depends_on(summary_msg, delay_seconds=1)

            # User replies with instruction
            user_decision = aui.send_message_to_agent(
                content="Cancel Adobe Creative Cloud auto-renewal, keep the others."
            ).depends_on(warn_msg, delay_seconds=1)

            # Messaging app confirms simulated action
            confirm_msg = messaging.send_message(
                user_id="demo_user",
                content="I've noted your decision — Adobe Creative Cloud renewal will be canceled.",
            ).oracle().depends_on(user_decision, delay_seconds=1)

            # Final completion message
            finish = aui.send_message_to_user(
                content="Subscription summary and renewal preferences updated successfully."
            ).depends_on(confirm_msg, delay_seconds=1)

        self.events = [
            proactive_detect,
            user_confirm,
            current_time,
            fetch_subscriptions,
            summary_msg,
            warn_msg,
            user_decision,
            confirm_msg,
            finish,
        ]
        print(f"[DEBUG] proactive_subscription_email_summary: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate proactive trigger, email search, and user decision steps."""
        print("[DEBUG] proactive_subscription_email_summary: validate() called")

        try:
            events = env.event_log.list_view()
            p = self._params

            proactive_triggered = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "subscription" in e.action.args.get("content", "").lower()
                for e in events
            )

            email_search_executed = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["search_emails", "read_emails"]
                for e in events
            )

            cancel_decision_detected = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "cancel" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = proactive_triggered and email_search_executed and cancel_decision_detected

            print("\n[VALIDATION SUMMARY]")
            print(f"  - Proactive detection triggered:  {'PASS' if proactive_triggered else 'FAIL'}")
            print(f"  - Email search executed:          {'PASS' if email_search_executed else 'FAIL'}")
            print(f"  - User cancel decision detected:  {'PASS' if cancel_decision_detected else 'FAIL'}")
            print(f"  => Scenario result: {'PASS' if success else 'FAIL'}\n")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            print(f"[ERROR] proactive_subscription_email_summary: Validation failed: {e}")
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
