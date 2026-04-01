from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_briefing_and_followup_email")
class TeamBriefingAndFollowupEmail(Scenario):
    """Comprehensive scenario demonstrating cross-app use.

    Context:
        The user received an email from their manager asking to set up
        a 'team briefing' event, involve specific contacts, and send
        a follow-up email summary after the meeting. The agent should:
        - Read incoming email request,
        - Propose to add the event to the calendar,
        - Wait for user's approval,
        - Create the event if approved,
        - Finally send the confirmation email after meeting creation.
    """

    start_time: float | None = 0
    duration: float | None = 45

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate applications with initial data."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        contacts = ContactsApp()
        email_client = EmailClientApp()
        system = SystemApp(name="core-system")

        # Create existing contacts
        contacts.add_new_contact(
            first_name="Mia",
            last_name="Torres",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            job="Team Manager",
            phone="+44 709 1839 223",
            email="mia.torres@company.org",
            country="UK",
            city_living="London",
        )

        contacts.add_new_contact(
            first_name="Eli",
            last_name="Walker",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            job="Developer",
            phone="+44 700 902 338",
            email="eli.walker@company.org",
            country="UK",
            city_living="Manchester",
        )

        # Simulate an incoming email from the manager requesting the meeting
        email_client.send_email(
            recipients=["user@company.org"],
            subject="Team Briefing Request",
            content="Please schedule a briefing this Friday at 10 AM with Eli and me to discuss the new sprint items.",
        )

        self.apps = [aui, calendar, contacts, email_client, system]

    def build_events_flow(self) -> None:
        """Define scenario interactions with proactive confirmation."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        contacts = self.get_typed_app(ContactsApp)
        email_client = self.get_typed_app(EmailClientApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 1: User prompt
            msg_from_user = aui.send_message_to_agent(
                content="I just got an email from Mia. Can you check what she needs and handle it for me?"
            ).depends_on(None, delay_seconds=1)

            # Step 2: System checks current date/time
            now = system.get_current_time().depends_on(msg_from_user, delay_seconds=1)

            # Step 3: Agent reads the manager's email
            email_read = email_client.get_email_by_index(idx=0, folder_name="INBOX").depends_on(now, delay_seconds=1)

            # Step 4: Agent proactively proposes creating the event
            proposal = aui.send_message_to_user(
                content="Mia asked to set a team briefing this Friday at 10 AM with Eli and her. Shall I add it to your calendar and notify them?"
            ).depends_on(email_read, delay_seconds=2)

            # Step 5: User confirms with context
            user_response = aui.send_message_to_agent(
                content="Yes, go ahead and schedule that meeting, please send both of them a confirmation."
            ).depends_on(proposal, delay_seconds=1)

            # Step 6: Retrieve contacts before adding calendar event
            find_mia = contacts.search_contacts(query="Mia").depends_on(user_response, delay_seconds=1)
            find_eli = contacts.search_contacts(query="Eli").depends_on(find_mia, delay_seconds=1)

            # Step 7: Add event in calendar (oracle expected)
            add_event = (
                calendar.add_calendar_event(
                    title="Team Briefing",
                    start_datetime="2024-05-10 10:00:00",
                    end_datetime="2024-05-10 11:00:00",
                    tag="Work",
                    description="Sprint planning discussion with Mia and Eli.",
                    location="Conference Room 2",
                    attendees=["Mia Torres", "Eli Walker"],
                )
                .oracle()
                .depends_on(find_eli, delay_seconds=2)
            )

            # Step 8: Agent sends follow-up confirmation email
            followup = (
                email_client.send_email(
                    recipients=["mia.torres@company.org", "eli.walker@company.org"],
                    subject="Team Briefing Scheduled",
                    content="The team briefing is confirmed for Friday at 10 AM in Conference Room 2.",
                )
                .oracle()
                .depends_on(add_event, delay_seconds=1)
            )

            # Step 9: Agent informs user of successful scheduling
            notify_user = aui.send_message_to_user(
                content="The meeting has been scheduled, and both Mia and Eli are notified."
            ).depends_on(followup, delay_seconds=1)

            # Step 10: System waits for any updates afterward
            wait = system.wait_for_notification(timeout=5).depends_on(notify_user, delay_seconds=1)

        self.events = [
            msg_from_user,
            now,
            email_read,
            proposal,
            user_response,
            find_mia,
            find_eli,
            add_event,
            followup,
            notify_user,
            wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Verify validation signals: event created & notifications sent."""
        try:
            events = env.event_log.list_view()

            event_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "CalendarApp"
                and event.action.function_name == "add_calendar_event"
                and "Team Briefing" in event.action.args.get("title", "")
                for event in events
            )

            followup_sent = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "EmailClientApp"
                and event.action.function_name == "send_email"
                and "Team Briefing Scheduled" in event.action.args.get("subject", "")
                for event in events
            )

            proactive_dialogue = any(
                event.event_type == EventType.AGENT
                and event.action.class_name == "AgentUserInterface"
                and "briefing" in event.action.args.get("content", "").lower()
                and "calendar" in event.action.args.get("content", "").lower()
                and "schedule" not in event.action.args.get("content", "").lower()
                for event in events
            )

            approval_response = any(
                event.event_type == EventType.USER and "schedule that meeting" in event.raw_human_input.lower()
                for event in events
            )

            return ScenarioValidationResult(
                success=(event_created and followup_sent and proactive_dialogue and approval_response)
            )
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
