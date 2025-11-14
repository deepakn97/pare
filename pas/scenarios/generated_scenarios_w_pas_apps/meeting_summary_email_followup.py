from __future__ import annotations

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("meeting_summary_email_followup")
class MeetingSummaryEmailFollowup(Scenario):
    """Scenario: After receiving a summary email from a project meeting.

    The agent proposes to forward it to the dev team via chat and mark focus time on the calendar.
    """

    start_time: float | None = 0.0
    duration: float | None = 3600.0

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and configure apps needed by the scenario."""
        # Initialize all apps
        self.email = StatefulEmailApp(name="StatefulEmailApp")
        self.calendar = StatefulCalendarApp(name="StatefulCalendarApp")
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.agent_ui = PASAgentUserInterface(name="PASAgentUserInterface")
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")

        # Configure messaging participants
        self.messaging.current_user_id = "user-00"
        self.messaging.current_user_name = "Taylor Reed"
        self.messaging.add_users([
            {"id": "u-1", "name": "Jordan Smith"},
            {"id": "u-2", "name": "Chris Nguyen"},
            {"id": "u-3", "name": "Dev Team"},
        ])

        # Create dev-group chat
        self.dev_team_conversation_id = self.messaging.create_group_conversation(
            user_ids=["u-1", "u-2", "u-3"], title="Dev Team Daily Thread"
        ).result()

        # Store in apps
        self.apps = [
            self.email,
            self.calendar,
            self.messaging,
            self.agent_ui,
            self.system_app,
        ]

    def build_events_flow(self) -> None:
        """Build the event sequence for this scenario."""
        aui = self.get_typed_app(PASAgentUserInterface)
        email = self.get_typed_app(StatefulEmailApp)
        calendar = self.get_typed_app(StatefulCalendarApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        system_app = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            # Context: The user receives a summary email from project lead
            project_email = email.send_email_to_user_with_id(
                email_id="email-001",
                sender="project.lead@example.com",
                subject="Summary: Backend Refactor Discussion",
                content="Highlights from today's meeting:\n- API schema finalized\n- Migration steps documented\nNext review: Friday 2 PM.",
            )

            # Proactive proposal after email received
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "You just received a meeting summary email from your project lead. "
                        "Would you like me to forward it to the dev team chat and block focus time for Friday morning?"
                    )
                )
                .oracle()
                .depends_on(project_email, delay_seconds=2)
            )

            # User approves
            approval_event = (
                aui.accept_proposal(content="Yes, please share it with the dev team and block some focus hours.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Agent acts based on approval
            forward_message = (
                messaging.send_message_to_group_conversation(
                    conversation_id=self.dev_team_conversation_id,
                    content="Forwarded summary from project lead:\nAPI schema finalized and migration steps ready—review set for Friday.",
                )
                .oracle()
                .depends_on(approval_event, delay_seconds=2)
            )

            # Agent also creates calendar focus block
            focus_block = (
                calendar.add_calendar_event(
                    title="Focus Time - Review Backend Refactor Notes",
                    start_datetime="2025-05-16 09:00:00",
                    end_datetime="2025-05-16 11:00:00",
                    tag="Focus",
                    description="Reserved time to review refactor steps before Friday's meeting.",
                    attendees=["Taylor Reed"],
                )
                .oracle()
                .depends_on(forward_message, delay_seconds=2)
            )

            # Return to home screen (closing context)
            go_home_action = system_app.go_home().oracle().depends_on(focus_block)

        self.events = [
            project_email,
            proposal_event,
            approval_event,
            forward_message,
            focus_block,
            go_home_action,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation checks.

        - Agent made proactive proposal referencing summary email
        - User approved proposal
        - Message sent to dev team conversation
        - Calendar event created with "Focus" tag
        """
        try:
            logs = env.event_log.list_view()

            proposal_ok = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "meeting summary" in e.action.args.get("content", "")
                for e in logs
            )

            message_forwarded = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "Forwarded summary" in e.action.args.get("content", "")
                for e in logs
            )

            focus_event_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Focus Time" in e.action.args.get("title", "")
                for e in logs
            )

            return ScenarioValidationResult(success=(proposal_ok and message_forwarded and focus_event_created))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
