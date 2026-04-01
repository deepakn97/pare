from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType


@register_scenario("productivity_sync_flow")
class ProductivitySyncFlow(Scenario):
    """A comprehensive productivity sync scenario linking email, calendar, reminders, and contacts.

    This scenario demonstrates a realistic workflow where the user receives an email requesting
    a project meeting. The agent inspects the email, proposes creating a calendar event,
    follows up with reminders, updates contacts, and confirms schedule with the user.

    It includes proactive agent behavior: the agent proposes scheduling the meeting,
    the user consents in detail, and then the agent carries out the action.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate all required applications."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        email_client = EmailClientApp()
        contacts = ContactsApp()
        reminder = ReminderApp()
        system = SystemApp(name="MainSystem")

        # Populate contacts
        contacts.add_new_contact(
            first_name="Nora",
            last_name="Svensson",
            gender=Gender.FEMALE,
            job="Project Manager",
            status=Status.EMPLOYED,
            email="nora.svensson@firm.com",
            phone="+46 700123456",
            city_living="Stockholm",
            country="Sweden",
            description="Manages the marketing project scheduling.",
        )

        contacts.add_new_contact(
            first_name="Alex",
            last_name="Nguyen",
            gender=Gender.MALE,
            job="Designer",
            status=Status.EMPLOYED,
            email="alex.nguyen@firm.com",
            phone="+46 700654321",
            city_living="Stockholm",
            country="Sweden",
            description="Team designer for marketing materials.",
        )

        # Add current user details (represented in contacts)
        contacts.get_current_user_details()

        # List in self.apps to register environment
        self.apps = [aui, calendar, email_client, contacts, reminder, system]

    def build_events_flow(self) -> None:
        """Define step-by-step oracle flow through all the available apps."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)
        contacts = self.get_typed_app(ContactsApp)
        reminder = self.get_typed_app(ReminderApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # 1. User load start
            user_starts = aui.send_message_to_agent(
                content="Hi Assistant, can you check if I received any new meeting requests from Nora?"
            ).depends_on(None, delay_seconds=1)

            # 2. Simulate Nora's email arrival
            incoming_email = email_client.send_email_to_user(
                email=Email(
                    email_id="proj_meeting1",
                    sender="nora.svensson@firm.com",
                    recipients=["user@company.com"],
                    subject="Project Kickoff Meeting Request",
                    content="Hi! Let's schedule the kickoff meeting for the new marketing campaign next Tuesday at 10:00. Please prepare the agenda.",
                )
            ).depends_on(user_starts, delay_seconds=1)

            # 3. System retrieves current time (reference point)
            system_time_check = system.get_current_time().depends_on(incoming_email, delay_seconds=1)

            # 4. Agent reads the email details
            agent_reads_email = (
                email_client.get_email_by_id(email_id="proj_meeting1")
                .oracle()
                .depends_on(system_time_check, delay_seconds=1)
            )

            # 5. Agent proactively proposes creating a meeting event
            propose_meeting = aui.send_message_to_user(
                content="I found an email from Nora requesting a project kickoff meeting next Tuesday at 10:00. Should I add it to your calendar and set a preparation reminder?"
            ).depends_on(agent_reads_email, delay_seconds=1)

            # 6. User approves with detailed confirmation
            user_approval = aui.send_message_to_agent(
                content="Yes, please add the event to my calendar and remind me an hour before. Include Alex Nguyen as well."
            ).depends_on(propose_meeting, delay_seconds=1)

            # 7. Agent searches for contact Alex
            search_contact = contacts.search_contacts(query="Alex Nguyen").depends_on(user_approval, delay_seconds=1)

            # 8. Agent creates the event in the calendar after approval
            calendar_add_id = (
                calendar.add_calendar_event(
                    title="Project Kickoff Meeting",
                    start_datetime="1970-01-06 10:00:00",
                    end_datetime="1970-01-06 11:00:00",
                    tag="marketing",
                    description="First project meeting for the marketing campaign with Nora and Alex.",
                    location="Stockholm HQ - Conference B",
                    attendees=["Nora Svensson", "Alex Nguyen"],
                )
                .oracle()
                .depends_on(search_contact, delay_seconds=1)
            )

            # 9. Create a reminder related to the meeting
            create_reminder = (
                reminder.add_reminder(
                    title="Prepare agenda for kickoff meeting",
                    due_datetime="1970-01-06 09:00:00",
                    description="Finalize and print meeting agenda materials before the kickoff meeting.",
                )
                .oracle()
                .depends_on(calendar_add_id, delay_seconds=1)
            )

            # 10. Search back today's events for confirmation message
            check_events_today = calendar.read_today_calendar_events().depends_on(create_reminder, delay_seconds=1)

            # 11. Agent confirms success to user
            confirm_to_user = (
                aui.send_message_to_user(
                    content="The meeting has been added to your calendar with Alex and Nora. I've set a reminder one hour before the meeting."
                )
                .oracle()
                .depends_on(check_events_today, delay_seconds=1)
            )

            # 12. Agent clears stale reminders after the meeting (later cleanup)
            cleanup_old = reminder.get_all_reminders().depends_on(confirm_to_user, delay_seconds=1)

            # 13. Agent finishes day by waiting for notifications
            wait_idle = system.wait_for_notification(timeout=3).depends_on(cleanup_old, delay_seconds=1)

        self.events = [
            user_starts,
            incoming_email,
            system_time_check,
            agent_reads_email,
            propose_meeting,
            user_approval,
            search_contact,
            calendar_add_id,
            create_reminder,
            check_events_today,
            confirm_to_user,
            cleanup_old,
            wait_idle,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent executed all linked productivity actions successfully."""
        try:
            logs = env.event_log.list_view()

            email_read = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "EmailClientApp"
                and e.action.function_name == "get_email_by_id"
                and e.action.args.get("email_id") == "proj_meeting1"
                for e in logs
            )

            event_created = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Project Kickoff" in e.action.args.get("title", "")
                for e in logs
            )

            reminder_created = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                and "Prepare agenda" in e.action.args.get("title", "")
                for e in logs
            )

            proactive_proposal = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Should I add" in e.action.args.get("content", "")
                for e in logs
            )

            confirmation_message = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "meeting has been added" in e.action.args.get("content", "")
                for e in logs
            )

            # Ensure system and contacts used
            system_used = any(e.event_type == EventType.AGENT and e.action.class_name == "SystemApp" for e in logs)
            contacts_used = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "ContactsApp"
                and e.action.function_name == "search_contacts"
                for e in logs
            )

            success = (
                email_read
                and event_created
                and reminder_created
                and proactive_proposal
                and confirmation_message
                and system_used
                and contacts_used
            )
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
