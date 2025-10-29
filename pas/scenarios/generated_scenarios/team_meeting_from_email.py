from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_meeting_from_email")
class TeamMeetingFromEmail(Scenario):
    """Scenario: Agent identifies a meeting request in an email and proposes to schedule it in the calendar after user approval.

    This scenario demonstrates the integration of all available applications:
      - EmailClientApp: for searching and reading emails
      - CalendarApp: to add an event based on an email
      - AgentUserInterface: to communicate proactively with the user (proposal and confirmation)
      - SystemApp: to obtain current time and pause waiting for user response
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate the applications."""
        aui = AgentUserInterface()
        email_client = EmailClientApp()
        calendar = CalendarApp()
        system = SystemApp(name="timekeeper")

        # Prepopulate an inbox with a meeting request email
        self.email_id = "email_request_001"
        self.sender = "nora_hughes@workplace.com"
        self.subject = "Project Update Meeting"
        self.content = (
            "Hi Team, can we have a project update meeting on Friday at 10 AM? "
            "Let's review the latest progress and next steps."
        )

        # Add this email to the client's inbox manually
        email_client.send_email_to_user(
            email=Email(
                sender=self.sender,
                recipients=["user@example.com"],
                subject=self.subject,
                content=self.content,
                email_id=self.email_id,
            )
        )

        self.apps = [aui, email_client, calendar, system]

    def build_events_flow(self) -> None:
        """Define the ordered event flow for the scenario, including proactive proposal."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Event 1: User starts the scenario asking to check today's new emails
            user_starts = aui.send_message_to_agent(
                content="Check if I received any important work email today."
            ).depends_on(None, delay_seconds=1)

            # Event 2: Agent searches emails by query (using EmailClientApp__search_emails)
            search_action = (
                email_client.search_emails(query="project update").oracle().depends_on(user_starts, delay_seconds=1)
            )

            # Event 3: Agent reads the found email (using EmailClientApp__get_email_by_id)
            read_email = (
                email_client.get_email_by_id(email_id=self.email_id).oracle().depends_on(search_action, delay_seconds=1)
            )

            # Event 4: Agent checks current time via SystemApp__get_current_time
            get_time = system.get_current_time().oracle().depends_on(read_email, delay_seconds=1)

            # Event 5: Agent proactively proposes to the user to create a meeting
            proposal = aui.send_message_to_user(
                content=(
                    "I found an email from Nora Hughes suggesting a meeting on Friday at 10 AM. "
                    "Would you like me to add this meeting to your calendar?"
                )
            ).depends_on(get_time, delay_seconds=1)

            # Event 6: User responds with meaningful confirmation
            user_accepts = aui.send_message_to_agent(
                content="Yes, please schedule the meeting in my calendar and include Nora as attendee."
            ).depends_on(proposal, delay_seconds=2)

            # Event 7: Agent adds the calendar event (CalendarApp__add_calendar_event) after approval
            add_event = (
                calendar.add_calendar_event(
                    title="Project Update Meeting",
                    start_datetime="1970-01-01 10:00:00",
                    end_datetime="1970-01-01 11:00:00",
                    tag="Work",
                    description="Team project update meeting with Nora.",
                    location="Conference Room 2A",
                    attendees=["Nora Hughes", "User"],
                )
                .oracle()
                .depends_on(user_accepts, delay_seconds=1)
            )

            # Event 8: Agent double-checks event creation (CalendarApp__search_events)
            verify_event = (
                calendar.search_events(query="Project Update").oracle().depends_on(add_event, delay_seconds=1)
            )

            # Event 9: Agent informs the user that the meeting is scheduled
            confirmation = (
                aui.send_message_to_user(
                    content="The Project Update Meeting has been scheduled on Friday at 10:00 AM with Nora Hughes."
                )
                .oracle()
                .depends_on(verify_event, delay_seconds=1)
            )

            # Event 10: Agent uses SystemApp__wait_for_notification to idle while user reviews
            system_pause = system.wait_for_notification(timeout=3).oracle().depends_on(confirmation, delay_seconds=2)

        self.events = [
            user_starts,
            search_action,
            read_email,
            get_time,
            proposal,
            user_accepts,
            add_event,
            verify_event,
            confirmation,
            system_pause,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the scenario success."""
        try:
            events = env.event_log.list_view()

            # Check that the proposal was made
            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "meeting" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Check if user approved with context
            approval_given = any(
                e.event_type == EventType.USER and "schedule" in e.content.lower() and "meeting" in e.content.lower()
                for e in events
            )

            # Check if a calendar event was created
            meeting_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Project Update Meeting" in e.action.args.get("title", "")
                for e in events
            )

            # Check that the agent notified the user about scheduling
            notified_user = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "scheduled" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = proposal_sent and approval_given and meeting_created and notified_user
            return ScenarioValidationResult(success=success)
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
