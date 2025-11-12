from __future__ import annotations

from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("team_sync_followup_meeting")
class TeamSyncFollowupMeeting(Scenario):
    """Scenario demonstrating cross-app coordination.

    The agent detects a delayed follow-up and proactively offers to schedule a new meeting,
    message the team, guide via the voice interface, and integrate system home screen context.
    """

    start_time: float | None = 0
    duration: float | None = 5400
    is_benchmark_ready: bool = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and preload all apps in the PAS ecosystem."""
        self.calendar = StatefulCalendarApp(name="StatefulCalendarApp")
        self.messaging = StatefulMessagingApp(name="StatefulMessagingApp")
        self.agent_ui = PASAgentUserInterface(name="PASAgentUserInterface")
        self.system = HomeScreenSystemApp(name="HomeScreenSystemApp")

        # Populate the calendar with an existing team meeting
        self.calendar.add_calendar_event(
            title="Weekly Team Sync",
            start_datetime="2024-06-10 10:00:00",
            end_datetime="2024-06-10 10:45:00",
            tag="team-meeting",
            description="Review tasks and blockers",
            location="Conference Room A",
            attendees=["Jordan Wright", "Samira Khan", "Alex Lee"],
        )

        self.apps = [self.calendar, self.messaging, self.agent_ui, self.system]

    def build_events_flow(self) -> None:
        """Create the event sequence demonstrating assistant coordination across apps."""
        cal = self.get_typed_app(StatefulCalendarApp)
        msg = self.get_typed_app(StatefulMessagingApp)
        aui = self.get_typed_app(PASAgentUserInterface)
        system = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            # --- 1. User begins on the Home Screen ---
            open_home = system.open_home_screen().environment().delayed(1)

            # --- 2. User views their home agenda widget ---
            view_agenda = system.view_home_agenda().oracle().depends_on(open_home, delay_seconds=1)
            open_calendar = cal.open_calendar_app_view().oracle().depends_on(view_agenda, delay_seconds=1)

            # --- 3. Notification arrives that "Team Sync" finished ---
            notif_event = (
                Action(class_name="ENV", function_name="wait_for_notification", args={"timeout": 20})
                .environment()
                .depends_on(open_calendar, delay_seconds=2)
            )

            # --- 4. Agent checks if a follow-up is scheduled ---
            check_event = cal.search_events(query="Team Sync").oracle().depends_on(notif_event, delay_seconds=1)

            # --- 5. Agent proactively proposes scheduling a follow-up ---
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "It looks like the 'Weekly Team Sync' just concluded. "
                        "Would you like me to schedule a follow-up meeting for next Monday and notify the team?"
                    )
                )
                .oracle()
                .depends_on(check_event, delay_seconds=3)
            )

            # --- 6. User approves the suggestion via voice or text ---
            approval_event = (
                aui.send_message_to_agent(content="Yes, please set it for next Monday at 10 AM and inform everyone.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # --- 7. Assistant schedules the follow-up meeting ---
            event_create = (
                cal.add_calendar_event(
                    title="Weekly Team Sync - Follow-up",
                    start_datetime="2024-06-17 10:00:00",
                    end_datetime="2024-06-17 10:45:00",
                    tag="team-meeting",
                    description="Continuation of last week's discussion.",
                    location="Conference Room A",
                    attendees=["Jordan Wright", "Samira Khan", "Alex Lee"],
                )
                .oracle()
                .depends_on(approval_event, delay_seconds=1)
            )

            # --- 8. Assistant identifies participants and notifies them ---
            jordan_id = msg.get_user_id(user_name="Jordan Wright").oracle().depends_on(event_create, delay_seconds=1)
            samira_id = msg.get_user_id(user_name="Samira Khan").oracle().depends_on(event_create, delay_seconds=1)
            alex_id = msg.get_user_id(user_name="Alex Lee").oracle().depends_on(event_create, delay_seconds=1)

            group_chat = (
                msg.create_group_conversation(
                    user_ids=[jordan_id.output, samira_id.output, alex_id.output],
                    title="Team Sync Follow-up Discussion",
                )
                .oracle()
                .depends_on(event_create, delay_seconds=1)
            )

            msg_to_group = (
                msg.send_message_to_group_conversation(
                    conversation_id=group_chat.output,
                    content="Hey team! The follow-up meeting is scheduled for next Monday at 10 AM. See you then.",
                )
                .oracle()
                .depends_on(group_chat, delay_seconds=1)
            )

            # --- 9. Agent confirms back to user through AUI ---
            confirm_event = (
                aui.send_message_to_user(
                    content="All set! The follow-up is on your calendar and the team has been notified."
                )
                .oracle()
                .depends_on(msg_to_group, delay_seconds=2)
            )

            # --- 10. Agent navigates back to Home Screen ---
            return_home = system.return_to_home_screen().oracle().depends_on(confirm_event, delay_seconds=2)
            refresh_widget = system.refresh_home_widgets().oracle().depends_on(return_home, delay_seconds=1)

            # --- 11. System invokes voice assistant as a demonstration of multimodal use ---
            voice_trigger = system.activate_voice_assistant().environment().depends_on(refresh_widget, delay_seconds=2)
            voice_response = (
                aui.send_message_to_user(
                    content="You can check updated meetings or ask for the next team sync details using voice commands."
                )
                .oracle()
                .depends_on(voice_trigger, delay_seconds=1)
            )

        self.events = [
            open_home,
            view_agenda,
            open_calendar,
            notif_event,
            check_event,
            proposal_event,
            approval_event,
            event_create,
            jordan_id,
            samira_id,
            alex_id,
            group_chat,
            msg_to_group,
            confirm_event,
            return_home,
            refresh_widget,
            voice_trigger,
            voice_response,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the follow-up was scheduled, team notified, and home screen activities occurred."""
        try:
            logs = env.event_log.list_view()

            followup_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Follow-up" in e.action.args.get("title", "")
                for e in logs
            )

            notification_sent = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "next Monday" in e.action.args.get("content", "")
                for e in logs
            )

            home_screen_activity = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "HomeScreenSystemApp"
                and e.action.function_name
                in [
                    "open_home_screen",
                    "view_home_agenda",
                    "return_to_home_screen",
                    "refresh_home_widgets",
                    "activate_voice_assistant",
                ]
                for e in logs
            )

            return ScenarioValidationResult(success=followup_found and notification_sent and home_screen_activity)

        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
