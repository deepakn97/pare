from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("meeting_invite_coordination")
class MeetingInviteCoordination(Scenario):
    """Scenario where the agent reviews an incoming meeting invitation.

    Suggests adding it to the user's calendar, asks for explicit approval,
    and upon confirmation, schedules the meeting and replies to the invitation email.
    """

    start_time: float | None = 0
    duration: float | None = 18

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize applications and populate them with relevant data."""
        aui = AgentUserInterface()
        email_client = EmailClientApp()
        calendar = CalendarApp()

        # Simulating an inbox with a meeting invitation email
        meeting_email = Email(
            email_id="invitation_789",
            sender="alex.richter@projectsuite.com",
            recipients=["user@personalmail.com"],
            subject="Team Sync Invitation for Thursday",
            content=(
                "Hello! I'd like to schedule a quick sync with you and Nina this Thursday at 10:30 AM."
                " Please confirm if this works for you."
            ),
        )
        email_client.INBOX = [meeting_email]

        self.apps = [aui, email_client, calendar]

    def build_events_flow(self) -> None:
        """Defines the flow of interaction events for this scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)

        with EventRegisterer.capture_mode():
            # User initiates the process, asking the agent to check for new invitations
            user_start = aui.send_message_to_agent(
                content="Assistant, could you check my inbox for new meeting invites?"
            ).depends_on(None, delay_seconds=1)

            # Agent lists inbox emails (non-oracle, intermediate)
            list_inbox = email_client.list_emails(folder_name="INBOX", limit=5).depends_on(user_start, delay_seconds=1)

            # Agent reads the first new invitation in full detail
            read_invite = email_client.get_email_by_index(idx=0, folder_name="INBOX").depends_on(
                list_inbox, delay_seconds=1
            )

            # Agent proactively proposes adding the meeting to the calendar
            propose_add = aui.send_message_to_user(
                content=(
                    "I found an invitation from Alex Richter for a team sync on Thursday at 10:30 AM. "
                    "Should I add this event to your calendar and notify Alex that you've accepted?"
                )
            ).depends_on(read_invite, delay_seconds=1)

            # User approves the proposal
            confirm_add = aui.send_message_to_agent(
                content="Yes, add it to my calendar and send Alex a confirmation email."
            ).depends_on(propose_add, delay_seconds=1)

            # Agent adds the event to the calendar (oracle)
            calendar_add_event = (
                calendar.add_calendar_event(
                    title="Team Sync with Alex and Nina",
                    start_datetime="2024-08-15 10:30:00",
                    end_datetime="2024-08-15 11:00:00",
                    description="Accepted meeting invitation from Alex Richter.",
                    location="Conference Room 2A",
                    attendees=["Alex Richter", "Nina Jakobsen", "User"],
                    tag="team_sync_event",
                )
                .oracle()
                .depends_on(confirm_add, delay_seconds=1)
            )

            # Agent replies to Alex confirming the meeting
            reply_to_invite = (
                email_client.reply_to_email(
                    email_id="invitation_789",
                    folder_name="INBOX",
                    content="Hi Alex, Thursday at 10:30 AM works perfectly. I've added it to my calendar. See you then!",
                )
                .oracle()
                .depends_on(calendar_add_event, delay_seconds=1)
            )

            # Agent moves the processed email to a custom folder for organization (demonstrating another tool)
            move_processed = email_client.move_email(
                email_id="invitation_789", source_folder_name="INBOX", dest_folder_name="TRASH"
            ).depends_on(reply_to_invite, delay_seconds=1)

        self.events = [
            user_start,
            list_inbox,
            read_invite,
            propose_add,
            confirm_add,
            calendar_add_event,
            reply_to_invite,
            move_processed,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validates that the scenario was completed correctly."""
        try:
            events = env.event_log.list_view()
            # Check that the agent created the corresponding calendar event
            event_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Team Sync" in e.action.args.get("title", "")
                for e in events
            )

            # Verify the confirmation email reply was sent to Alex
            confirm_replied = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "EmailClientApp"
                and e.action.function_name == "reply_to_email"
                and "Alex" in e.action.args.get("content", "")
                for e in events
            )

            # Check if the agent communicated the proactive proposal
            proactive_prompt = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Should I add" in e.action.args.get("content", "")
                for e in events
            )

            success = all([event_added, confirm_replied, proactive_prompt])
            return ScenarioValidationResult(success=success)
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
