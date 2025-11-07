"""
Scenario: proactive_interview_preparation_helper
Agent proactively detects interview-related emails,
asks the user if they would like a preparation summary,
and helps gather information about the company and the interview position.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer

from pas.apps.email import StatefulEmailApp
from pas.apps.messaging import StatefulMessagingApp
from pas.apps.websearch import StatefulWebSearchApp  # 假设 PAS 集成了 web search 或 custom info fetch app


# ---------- Logger ----------
logger = logging.getLogger(__name__)


# ---------- Parameters ----------
@dataclass
class InterviewPrepParams:
    email_keywords: list[str]
    preparation_template: str


# ---------- Scenario ----------
@register_scenario("proactive_interview_preparation_helper")
class ScenarioProactiveInterviewPreparationHelper(Scenario):
    """Agent detects interview invitation emails and offers to help the user prepare."""

    def __init__(self) -> None:
        super().__init__()
        self._params = InterviewPrepParams(
            email_keywords=["interview", "invitation", "schedule", "recruiter", "job opportunity"],
            preparation_template="Here is a summary for your upcoming interview with {company}:\n"
                                 "- Position: {position}\n"
                                 "- Interview Date: {date}\n"
                                 "- Suggested preparation topics: {topics}\n"
                                 "- Company research summary: {summary}\n"
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize required apps for proactive interview preparation."""
        aui = AgentUserInterface()
        system = SystemApp()
        email = StatefulEmailApp()
        messaging = StatefulMessagingApp()
        websearch = StatefulWebSearchApp()
        self.apps = [aui, system, email, messaging, websearch]
        logger.debug("proactive_interview_preparation_helper: Apps initialized")

    def build_events_flow(self) -> None:
        """Define the proactive interview preparation workflow."""
        logger.debug("proactive_interview_preparation_helper: build_events_flow called")

        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        email = self.get_typed_app(StatefulEmailApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        websearch = self.get_typed_app(StatefulWebSearchApp)
        p = self._params

        with EventRegisterer.capture_mode():
            # 1. Agent detects interview-related emails
            proactive_detect = aui.send_message_to_user(
                content="I noticed a new interview-related email in your inbox. Would you like me to summarize the interview details and help you prepare?"
            ).depends_on(None, delay_seconds=1)

            # 2. User confirms preparation help
            user_confirm = aui.send_message_to_agent(
                content="Yes, please help me prepare for the interview."
            ).depends_on(proactive_detect, delay_seconds=1)

            # 3. Get current system time
            current_time = system.get_current_time().oracle().depends_on(user_confirm, delay_seconds=1)

            # 4. Email app searches for recent interview invitations
            fetch_interview_emails = email.search_emails(
                query=" OR ".join(p.email_keywords)
            ).oracle().depends_on(current_time, delay_seconds=1)

            # 5. Agent extracts example data (simulated parsing)
            company = "OpenAI"
            position = "Machine Learning Engineer"
            interview_date = "2025-11-10"
            topics = "Transformer architecture, coding interview tips, and behavioral questions."

            # 6. Agent queries web for preparation materials
            search_info = websearch.search_web(
                query=f"{company} interview process {position}"
            ).oracle().depends_on(fetch_interview_emails, delay_seconds=1)

            # 7. Agent composes preparation summary
            summary_msg = aui.send_message_to_user(
                content=p.preparation_template.format(
                    company=company,
                    position=position,
                    date=interview_date,
                    topics=topics,
                    summary="The company focuses on applied AI research. Recent interviewees mention emphasis on reasoning ability and system design."
                )
            ).depends_on(search_info, delay_seconds=1)

            # 8. Agent offers to schedule reminders or tasks
            followup_prompt = aui.send_message_to_user(
                content="Would you like me to set reminders for mock interviews or save this preparation summary?"
            ).depends_on(summary_msg, delay_seconds=1)

            # 9. User replies with action
            user_decision = aui.send_message_to_agent(
                content="Yes, please set a reminder for mock interview tomorrow."
            ).depends_on(followup_prompt, delay_seconds=1)

            # 10. Messaging app confirms reminder creation
            confirm_msg = messaging.send_message(
                user_id="demo_user",
                content="Your mock interview reminder for tomorrow has been set."
            ).oracle().depends_on(user_decision, delay_seconds=1)

            # 11. Completion message
            finish = aui.send_message_to_user(
                content="Interview preparation workflow completed successfully."
            ).depends_on(confirm_msg, delay_seconds=1)

        self.events = [
            proactive_detect,
            user_confirm,
            current_time,
            fetch_interview_emails,
            search_info,
            summary_msg,
            followup_prompt,
            user_decision,
            confirm_msg,
            finish,
        ]
        logger.debug(f"proactive_interview_preparation_helper: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate proactive detection, web search, and preparation summary generation."""
        logger.debug("proactive_interview_preparation_helper: validate() called")

        try:
            events = env.event_log.list_view()

            proactive_detected = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "interview-related email" in e.action.args.get("content", "").lower()
                for e in events
            )

            email_search_done = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["search_emails", "read_emails"]
                for e in events
            )

            web_search_done = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulWebSearchApp"
                and e.action.function_name == "search_web"
                for e in events
            )

            summary_generated = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "summary for your upcoming interview" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = proactive_detected and email_search_done and web_search_done and summary_generated

            logger.debug("[VALIDATION SUMMARY]")
            logger.debug(f"  - Proactive detection triggered: {'PASS' if proactive_detected else 'FAIL'}")
            logger.debug(f"  - Email search executed:         {'PASS' if email_search_done else 'FAIL'}")
            logger.debug(f"  - Web search executed:           {'PASS' if web_search_done else 'FAIL'}")
            logger.debug(f"  - Preparation summary created:   {'PASS' if summary_generated else 'FAIL'}")
            logger.debug(f"  => Scenario result: {'PASS' if success else 'FAIL'}")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            logger.error(f"[ERROR] proactive_interview_preparation_helper: Validation failed: {e}")
            return ScenarioValidationResult(success=False, exception=e)
