from __future__ import annotations

from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("team_brainstorm_digest_followup_reminder")
class TeamBrainstormDigestFollowupReminder(Scenario):
    """Novel Scenario: Team Brainstorm Digest Follow-Up Reminder.

    The user receives an email summary of a "Product Redesign Brainstorm" session.
    The agent proactively offers to draft a digest message for the design chat group
    and schedule a short reminder meeting for capturing feedback from the team.
    This focuses on team collaboration follow-up, not expense or meeting summaries.
    """

    start_time: float | None = 0
    duration: float | None = 2400
    is_benchmark_ready: bool = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize required apps for this new scenario."""
        self.email_app = StatefulEmailApp(name="BrainstormEmailApp")
        self.calendar_app = StatefulCalendarApp(name="BrainstormCalendarApp")
        self.msg_app = StatefulMessagingApp(name="BrainstormMessagingApp")
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="BrainstormHomeScreen")

        # Messaging context setup for the design team
        self.msg_app.current_user_id = "user-designer-root"
        self.msg_app.current_user_name = "Morgan Rivers"

        self.msg_app.add_users([
            {"id": "des-jenna", "name": "Jenna Patel"},
            {"id": "des-kai", "name": "Kai Turner"},
            {"id": "des-liam", "name": "Liam Soto"},
        ])

        # Create design group chat for sharing digests
        self.design_chat_id = self.msg_app.create_group_conversation(
            user_ids=["des-jenna", "des-kai", "des-liam"],
            title="Design Collaboration Group",
        )

        self.apps = [
            self.email_app,
            self.calendar_app,
            self.msg_app,
            self.agent_ui,
            self.system_app,
        ]

    def build_events_flow(self) -> None:
        """Defines a distinct proactive flow for this design brainstorming scenario."""
        email = self.get_typed_app(StatefulEmailApp)
        calendar = self.get_typed_app(StatefulCalendarApp)
        msg = self.get_typed_app(StatefulMessagingApp)
        aui = self.get_typed_app(PASAgentUserInterface)
        system = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            # Step 1: User receives an email containing the brainstorm summary
            brainstorm_email = email.send_email_to_user_with_id(
                email_id="brainstorm-101",
                sender="notes@conferencehub.com",
                subject="Highlights from Product Redesign Brainstorm Session",
                content=(
                    "Key themes: Simplified onboarding, visual consistency, and adaptive layouts. "
                    "Next suggested steps: evaluate testing prototypes, decide color palette updates."
                ),
            ).delayed(2)

            # Step 2: Agent proactively approaches user with suggestion
            proactive_digest_offer = (
                aui.send_message_to_user(
                    content=(
                        "I just noticed the 'Product Redesign Brainstorm' summary email. "
                        "Would you like me to create a short digest and post it to your "
                        "'Design Collaboration Group' chat, and also set a quick follow-up "
                        "meeting for the team to decide next steps?"
                    )
                )
                .oracle()
                .depends_on(brainstorm_email, delay_seconds=3)
            )

            # Step 3: User accepts the agent's proactive offer
            user_approval = (
                aui.accept_proposal(content="Yes, please share the digest and set up the reminder meeting.")
                .oracle()
                .depends_on(proactive_digest_offer, delay_seconds=2)
            )

            # Step 4: Agent posts digest message in design chat
            digest_message_event = (
                msg.send_message_to_group_conversation(
                    conversation_id=self.design_chat_id,
                    content=(
                        "Quick Digest: Brainstorm session focused on onboarding simplification "
                        "and visual consistency. Next up - prepare prototype feedback session."
                    ),
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=2)
            )

            # Step 5: Agent sets a reminder meeting on the calendar
            followup_meeting_event = (
                calendar.add_calendar_event(
                    title="Design Team Follow-Up - Prototype Discussion",
                    start_datetime="2025-05-12 15:00:00",
                    end_datetime="2025-05-12 15:30:00",
                    tag="design-followup",
                    description="Team sync to decide on prototype refinements from brainstorm outcomes.",
                    attendees=["Morgan Rivers", "Jenna Patel", "Kai Turner", "Liam Soto"],
                )
                .oracle()
                .depends_on(digest_message_event, delay_seconds=3)
            )

            # Step 6: Agent gracefully returns to home screen
            back_to_home = system.go_home().oracle().depends_on(followup_meeting_event, delay_seconds=1)

        self.events = [
            brainstorm_email,
            proactive_digest_offer,
            user_approval,
            digest_message_event,
            followup_meeting_event,
            back_to_home,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure the scenario executed correctly."""
        try:
            logs = env.event_log.list_view()

            proactive_offer_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and "Brainstorm" in e.action.args.get("content", "")
                and "Design Collaboration Group" in e.action.args.get("content", "")
                for e in logs
            )

            chat_digest_posted = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and "Quick Digest" in e.action.args.get("content", "")
                for e in logs
            )

            followup_event_created = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.args.get("tag", "") == "design-followup"
                and "Prototype Discussion" in e.action.args.get("title", "")
                for e in logs
            )

            success = proactive_offer_found and chat_digest_posted and followup_event_created
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
