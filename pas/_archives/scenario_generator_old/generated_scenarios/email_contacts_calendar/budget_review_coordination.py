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


@register_scenario("budget_review_coordination")
class BudgetReviewCoordination(Scenario):
    """Scenario where an agent helps organize a budget review session based on incoming communication."""

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps and prepopulate with contextual data."""
        aui = AgentUserInterface()
        contacts = ContactsApp()
        calendar = CalendarApp()
        email_client = EmailClientApp()
        system = SystemApp(name="core")

        # Contacts added to simulate organization members
        contacts.add_new_contact(
            first_name="Harper",
            last_name="Nguyen",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            job="Finance Director",
            email="harper.nguyen@enterprise.org",
            phone="+44 7012 223 456",
            country="UK",
            city_living="Liverpool",
        )
        contacts.add_new_contact(
            first_name="Owen",
            last_name="Singh",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            job="Operations Manager",
            email="owen.singh@enterprise.org",
            phone="+44 7023 445 888",
            city_living="Leeds",
        )

        # Incoming email representing a real event trigger
        email_client.send_email(
            recipients=["user@enterprise.org"],
            subject="Budget Review Preparation",
            content="Harper here: Can we schedule a budget review this Thursday afternoon with Owen and me to finalize Q4 plans?",
        )

        # Pre-create a calendar entry for another unrelated event
        calendar.add_calendar_event(
            title="Procurement Meeting",
            start_datetime="2024-07-12 09:00:00",
            end_datetime="2024-07-12 10:00:00",
            location="Boardroom 5",
            description="Weekly procurement update with logistics team.",
            attendees=["Owen Singh"],
        )

        self.apps = [aui, contacts, calendar, email_client, system]

    def build_events_flow(self) -> None:
        """Defines event sequence: user triggers action, agent processes and handles coordination."""
        aui = self.get_typed_app(AgentUserInterface)
        contacts = self.get_typed_app(ContactsApp)
        calendar = self.get_typed_app(CalendarApp)
        email_client = self.get_typed_app(EmailClientApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # 1. User prompts agent to check for important messages
            u_init = aui.send_message_to_agent(
                content="See if there are any important emails from Harper and help me handle them."
            ).depends_on(None, delay_seconds=1)

            # 2. Agent checks system time for reference
            s_time = system.get_current_time().depends_on(u_init, delay_seconds=1)

            # 3. Agent inspects the inbox for any recent messages
            inbox_msgs = email_client.list_emails(folder_name="INBOX", limit=3).depends_on(s_time, delay_seconds=1)

            # 4. Agent reads the most recent email
            latest_mail = email_client.get_email_by_index(idx=0, folder_name="INBOX").depends_on(
                inbox_msgs, delay_seconds=1
            )

            # 5. Agent searches relevant contacts mentioned in the email
            contact_harper = contacts.search_contacts(query="Harper").depends_on(latest_mail, delay_seconds=1)
            contact_owen = contacts.search_contacts(query="Owen").depends_on(contact_harper, delay_seconds=1)

            # 6. Agent proactively proposes a calendar action
            propose_action = aui.send_message_to_user(
                content="Harper requested a budget review this Thursday afternoon with Owen. Would you like me to schedule that and notify them both?"
            ).depends_on(contact_owen, delay_seconds=2)

            # 7. User gives explicit approval with details
            u_confirms = aui.send_message_to_agent(
                content="Yes, schedule the budget review for Thursday at 2:30 PM and send confirmations to them."
            ).depends_on(propose_action, delay_seconds=2)

            # 8. Agent retrieves current time and schedules the event (oracle)
            timing_reference = system.get_current_time().depends_on(u_confirms, delay_seconds=1)

            new_calendar_event = (
                calendar.add_calendar_event(
                    title="Q4 Budget Review",
                    start_datetime="2024-07-11 14:30:00",
                    end_datetime="2024-07-11 15:30:00",
                    location="Meeting Room 3B",
                    description="Review upcoming Q4 budget allocations with Harper and Owen.",
                    tag="BudgetSession",
                    attendees=["Harper Nguyen", "Owen Singh"],
                )
                .oracle()
                .depends_on(timing_reference, delay_seconds=1)
            )

            # 9. Agent composes and sends follow-up email (oracle)
            send_confirmation = (
                email_client.send_email(
                    recipients=["harper.nguyen@enterprise.org", "owen.singh@enterprise.org"],
                    subject="Budget Review Confirmed - Thursday 2:30 PM",
                    content="The budget review session has been scheduled for Thursday at 2:30 PM in Meeting Room 3B. See you both there.",
                )
                .oracle()
                .depends_on(new_calendar_event, delay_seconds=1)
            )

            # 10. Agent informs user of successful actions and waits for updates
            notify_completion = aui.send_message_to_user(
                content="The budget review is now on your calendar, and both attendees have been notified."
            ).depends_on(send_confirmation, delay_seconds=1)

            idle_hold = system.wait_for_notification(timeout=4).depends_on(notify_completion, delay_seconds=1)

        self.events = [
            u_init,
            s_time,
            inbox_msgs,
            latest_mail,
            contact_harper,
            contact_owen,
            propose_action,
            u_confirms,
            timing_reference,
            new_calendar_event,
            send_confirmation,
            notify_completion,
            idle_hold,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check that the event creation, proactive message, and confirmations occurred correctly."""
        try:
            events = env.event_log.list_view()

            event_made = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Budget Review" in e.action.args.get("title", "")
                for e in events
            )

            mail_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "EmailClientApp"
                and e.action.function_name == "send_email"
                and "Budget Review Confirmed" in e.action.args.get("subject", "")
                for e in events
            )

            proactive_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "AgentUserInterface"
                and "requested a budget review" in e.action.args.get("content", "").lower()
                for e in events
            )

            user_approved = any(
                e.event_type == EventType.USER and "schedule the budget review" in e.raw_human_input.lower()
                for e in events
            )

            success = event_made and mail_sent and proactive_found and user_approved
            return ScenarioValidationResult(success=success)
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
