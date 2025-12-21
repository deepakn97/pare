"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("missing_attachment_followup")
class MissingAttachmentFollowup(PASScenario):
    """Agent detects missing attachment in document review request and proactively follows up with sender.

    The user receives an email from colleague Sarah Park requesting urgent review of a project proposal document by November 22nd. The email mentions an attached document ("please see the attached proposal"), but no attachment is actually present. The agent must: 1. Parse the email and detect the missing attachment inconsistency. 2. Propose sending a follow-up email to Sarah requesting the missing document. 3. Send the follow-up email after user acceptance. 4. Wait for Sarah's reply containing the actual attachment. 5. Create a calendar reminder for the November 22nd review deadline. 6. Notify the user that the document has arrived and the deadline is tracked.

    This scenario exercises attachment validation, proactive communication for incomplete requests, multi-turn email coordination with the same sender, calendar deadline tracking (not meeting scheduling), and cross-app workflow completion that spans multiple incoming messages..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails", user_email="user@example.com")

        # Initialize calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Populate contacts: the user and Sarah Park (colleague)
        sarah = Contact(
            first_name="Sarah",
            last_name="Park",
            email="sarah.park@example.com",
            phone="+1-555-0123",
            job="Project Manager",
        )
        self.email.contacts_manager.add_contact(sarah) if hasattr(self.email, "contacts_manager") else None

        # No baseline emails or calendar events - all interactions happen during event flow
        # The initial email from Sarah will arrive as an environment event

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Event 1: Initial email from Sarah mentioning attachment but without one (environment event)
            initial_email_event = email_app.send_email_to_user_with_id(
                email_id="email-sarah-missing-attachment",
                sender="sarah.park@example.com",
                subject="Urgent: Project Proposal Review Needed",
                content="Hi! I need your review on the project proposal by November 22nd. Please see the attached proposal and let me know your thoughts by the deadline. This is time-sensitive for our client meeting.",
            ).delayed(20)

            # Event 2: Agent proposes following up about missing attachment (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="Sarah Park sent an email requesting review of a project proposal by November 22nd. The email mentions an attachment, but no file is attached. Would you like me to follow up with Sarah to request the missing document?"
                )
                .oracle()
                .depends_on(initial_email_event, delay_seconds=3)
            )

            # Event 3: User accepts proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please ask Sarah to send the document, and add a calendar reminder for the deadline."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 4: Agent sends follow-up email to Sarah (oracle)
            followup_email_event = (
                email_app.reply_to_email(
                    email_id="email-sarah-missing-attachment",
                    content="Hi Sarah, I'd be happy to review the proposal by November 22nd. However, I don't see any attachment in your email. Could you please resend the document?",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Event 5: Sarah's reply with the actual attachment (environment event)
            sarah_reply_event = email_app.reply_to_email_from_user(
                sender="sarah.park@example.com",
                email_id="email-sarah-missing-attachment",
                content="Oh no, sorry about that! Here's the proposal document attached. Thanks for catching that!",
                attachment_paths=["proposal_document.pdf"],
            ).delayed(30)

            # Event 6: Agent creates calendar reminder for review deadline (oracle)
            calendar_reminder_event = (
                calendar_app.add_calendar_event(
                    title="Review Project Proposal for Sarah Park",
                    start_datetime="2025-11-22 09:00:00",
                    end_datetime="2025-11-22 10:00:00",
                    description="Deadline to review project proposal from Sarah Park",
                )
                .oracle()
                .depends_on(sarah_reply_event, delay_seconds=2)
            )

            # Event 7: Agent notifies user that document arrived and deadline is tracked (oracle)
            completion_notification_event = (
                aui.send_message_to_user(
                    content="Sarah Park has sent the project proposal document. I've added a calendar reminder for November 22nd to ensure you review it by the deadline."
                )
                .oracle()
                .depends_on(calendar_reminder_event, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            initial_email_event,
            proposal_event,
            acceptance_event,
            followup_email_event,
            sarah_reply_event,
            calendar_reminder_event,
            completion_notification_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent initial proposal about missing attachment
            # STRICT: Must detect missing attachment and mention Sarah Park
            # FLEXIBLE: Exact wording can vary
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 2: Agent sent follow-up email to Sarah requesting the document
            # STRICT: Must reply to the original email about missing attachment
            # FLEXIBLE: Exact email content can vary
            followup_email_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email-sarah-missing-attachment"
                for e in log_entries
            )

            # Check Step 3: Agent created calendar reminder for November 22nd deadline
            # STRICT: Must create event on correct date for the review deadline
            # FLEXIBLE: Title and exact time can vary slightly
            calendar_reminder_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-11-22" in e.action.args.get("start_datetime", "")
                and any(
                    keyword in e.action.args.get("title", "").lower() for keyword in ["review", "proposal", "sarah"]
                )
                for e in log_entries
            )

            # Determine success - all critical checks must pass
            success = proposal_found and followup_email_found and calendar_reminder_found

            # Build rationale if validation fails
            rationale = None
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal about missing attachment not found")
                if not followup_email_found:
                    missing_checks.append("follow-up email to Sarah Park not found")
                if not calendar_reminder_found:
                    missing_checks.append("calendar reminder for November 22nd deadline not found")
                rationale = "; ".join(missing_checks)

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
