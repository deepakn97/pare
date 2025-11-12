from __future__ import annotations

from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("team_brainstorm_coordination")
class TeamBrainstormCoordination(Scenario):
    """Scenario demonstrating proactive agent scheduling a team brainstorming session."""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all applications and some example data."""
        self.aui = PASAgentUserInterface(name="PASAgentUserInterface")
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.calendar = StatefulCalendarApp(name="StatefulCalendarApp")

        self.apps = [self.aui, self.system_app, self.messaging, self.calendar]

    def build_events_flow(self) -> None:
        """Create the event flow for the scenario - proactive scheduling proposal and confirmation."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system = self.get_typed_app(HomeScreenSystemApp)
        msg_app = self.get_typed_app(StatefulMessagingApp)
        cal = self.get_typed_app(StatefulCalendarApp)

        with EventRegisterer.capture_mode():
            # 1. Environment context — a new group message arrives about planning a brainstorming session.
            group_discussion = (
                msg_app.env_action(
                    name="create_group_conversation",
                    args={"user_ids": ["user-alpha", "user-beta"], "title": "Marketing Brainstorm Chat"},
                )
                .env()
                .event("A group conversation is created between teammates discussing next week's ideas.")
            )

            incoming_message = (
                msg_app.env_action(
                    name="send_message_to_group_conversation",
                    args={
                        "conversation_id": "chat-brainstorm",
                        "content": "Hey team, any updates on scheduling the campaign brainstorming?",
                    },
                )
                .env()
                .delayed(1)
            )

            system_notification = (
                system.env_action(name="wait_for_notification", args={"timeout": 10})
                .env()
                .event("User receives a system notification for a new message in the brainstorming chat.")
                .depends_on(incoming_message)
            )

            # 2. Agent proposes an action proactively after detecting the team's uncoordinated messages.
            propose_to_user = (
                aui.send_message_to_user(
                    content=(
                        "I noticed your teammates want to set up a brainstorming meeting. "
                        "Would you like me to create a calendar event for Thursday morning at 10 AM? "
                        "I can invite Jordan and Taylor."
                    )
                )
                .oracle()
                .depends_on(system_notification, delay_seconds=3)
            )

            # 3. User responds affirmatively to the agent's proposition.
            user_confirms = (
                aui.send_message_to_agent(
                    content="Yes, please schedule it for Thursday morning and include Jordan and Taylor."
                )
                .oracle()
                .depends_on(propose_to_user, delay_seconds=3)
            )

            # 4. Agent executes the scheduling action based on approval.
            calendar_update = (
                cal.add_calendar_event(
                    title="Marketing Campaign Brainstorm",
                    start_datetime="1970-01-08 10:00:00",
                    end_datetime="1970-01-08 11:30:00",
                    tag="team_meeting",
                    description="Discuss creative angles for the new marketing campaign.",
                    location="Meeting Room B",
                    attendees=["Jordan Lee", "Taylor Kim"],
                )
                .oracle()
                .depends_on(user_confirms, delay_seconds=2)
            )

            # 5. Agent sends a confirmation message to both the user and the group.
            final_notification = (
                msg_app.send_message_to_group_conversation(
                    conversation_id="chat-brainstorm",
                    content="I have scheduled the brainstorming for Thursday at 10 AM in Room B. See you all there!",
                )
                .oracle()
                .depends_on(calendar_update, delay_seconds=1)
            )

        self.events = [
            group_discussion,
            incoming_message,
            system_notification,
            propose_to_user,
            user_confirms,
            calendar_update,
            final_notification,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the proactive scheduling workflow was executed successfully."""
        try:
            logs = env.event_log.list_view()

            # Verify that the agent proactively made a proposal to the user.
            proposal_ok = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Would you like me to create a calendar event" in e.action.args.get("content", "")
                for e in logs
            )

            # Verify that a calendar event was added by the agent.
            event_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Brainstorm" in e.action.args.get("title", "")
                for e in logs
            )

            # Ensure a follow-up confirmation was broadcast to the group.
            confirmation_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "scheduled the brainstorming" in e.action.args.get("content", "")
                for e in logs
            )

            success = proposal_ok and event_created and confirmation_sent
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
