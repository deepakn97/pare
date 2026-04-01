from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("business_meeting_coordination")
class BusinessMeetingCoordination(Scenario):
    """Comprehensive scenario demonstrating cross-app workflow for meeting coordination.

    Objective:
    1. The user asks the agent to check recent emails for client meeting requests.
    2. The agent finds an email from a client requesting a business meeting.
    3. The agent proactively proposes scheduling the meeting, asking for user confirmation.
    4. The user approves with details.
    5. The agent creates the calendar event, adds participants from ContactsApp, and confirms back to user.

    Apps used:
    - AgentUserInterface: agent-user communication
    - SystemApp: get current time
    - EmailClientApp: email search and retrieve emails
    - CalendarApp: manage meeting scheduling
    - ContactsApp: find or add contact and attendees
    """

    start_time: float | None = 0
    duration: float | None = 28

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate the required apps with realistic business data."""
        aui = AgentUserInterface()
        system = SystemApp(name="sys_business")
        email_client = EmailClientApp()
        calendar = CalendarApp()
        contacts = ContactsApp()

        # Add known contacts (team members, client)
        contacts.add_new_contact(
            first_name="Alice",
            last_name="Reynolds",
            gender=Gender.FEMALE,
            age=34,
            nationality="USA",
            city_living="New York",
            country="USA",
            status=Status.EMPLOYED,
            job="Marketing Director",
            email="alice.reynolds@clientcorp.com",
            phone="+1 555 0198 232",
        )
        contacts.add_new_contact(
            first_name="Brian",
            last_name="Smith",
            gender=Gender.MALE,
            age=29,
            nationality="USA",
            city_living="Boston",
            country="USA",
            status=Status.EMPLOYED,
            job="Sales Executive",
            email="brian.smith@ourcompany.com",
            phone="+1 555 2124 884",
        )

        # Populate email inbox with a client request
        email_client.send_email_to_user(
            email=Email(
                sender="alice.reynolds@clientcorp.com",
                recipients=["user@ourcompany.com"],
                subject="Request for partnership meeting",
                content=(
                    "Hello, we would like to schedule a meeting next week to discuss our partnership roadmap. "
                    "Please let me know when you are available."
                ),
                email_id="client_request_email",
            )
        )

        self.apps = [aui, system, email_client, calendar, contacts]

    def build_events_flow(self) -> None:
        """Build the scenario event workflow demonstrating proactive meeting scheduling."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        contacts = self.get_typed_app(ContactsApp)
        calendar = self.get_typed_app(CalendarApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # 1. User asks agent to check recent emails for client meeting requests
            user_request = aui.send_message_to_agent(
                content="Please check if there are any new emails requesting a business meeting."
            ).depends_on(None, delay_seconds=0)

            # 2. Agent retrieves current system time for context
            time_check = system.get_current_time().depends_on(user_request, delay_seconds=1)

            # 3. Agent lists inbox messages
            inbox_list = email_client.list_emails(folder_name="INBOX", offset=0, limit=5).depends_on(
                time_check, delay_seconds=1
            )

            # 4. Agent reads the email from the client (found in inbox)
            read_email = email_client.get_email_by_id(email_id="client_request_email").depends_on(
                inbox_list, delay_seconds=1
            )

            # 5. Agent proactively proposes scheduling
            agent_propose_action = aui.send_message_to_user(
                content=(
                    "I found an email from Alice Reynolds requesting a partnership meeting next week. "
                    "Would you like me to schedule a 1-hour meeting with her on Tuesday morning and invite Brian as well?"
                )
            ).depends_on(read_email, delay_seconds=1)

            # 6. User approves proactively proposed action
            user_approval = aui.send_message_to_agent(
                content="Yes, please go ahead and schedule that meeting and include both Alice and Brian."
            ).depends_on(agent_propose_action, delay_seconds=1)

            # 7. Agent searches for contacts Alice and Brian
            search_alice = contacts.search_contacts(query="Alice Reynolds").depends_on(user_approval, delay_seconds=1)
            search_brian = contacts.search_contacts(query="Brian Smith").depends_on(search_alice, delay_seconds=1)

            # 8. Agent adds the calendar event (oracle action)
            meeting_add = (
                calendar.add_calendar_event(
                    title="Partnership Roadmap Meeting",
                    start_datetime="2024-07-09 09:00:00",
                    end_datetime="2024-07-09 10:00:00",
                    tag="business_meeting",
                    description="Partnership strategy and roadmap",
                    location="Zoom Conference",
                    attendees=["Alice Reynolds", "Brian Smith"],
                )
                .oracle()
                .depends_on(search_brian, delay_seconds=1)
            )

            # 9. Agent confirms the meeting was scheduled
            meeting_confirm = aui.send_message_to_user(
                content="The meeting with Alice and Brian has been scheduled for Tuesday at 9 AM."
            ).depends_on(meeting_add, delay_seconds=1)

            # 10. Wait for completion
            wait_final = system.wait_for_notification(timeout=5).depends_on(meeting_confirm, delay_seconds=1)

        self.events = [
            user_request,
            time_check,
            inbox_list,
            read_email,
            agent_propose_action,
            user_approval,
            search_alice,
            search_brian,
            meeting_add,
            meeting_confirm,
            wait_final,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the meeting was created successfully after user approval."""
        try:
            events = env.event_log.list_view()

            # Agent proposed action and confirmation steps
            agent_proposed = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "AgentUserInterface"
                and ev.action.function_name == "send_message_to_user"
                and "schedule" in ev.action.args.get("content", "").lower()
                for ev in events
            )

            # User approval captured
            user_approved = any(
                ev.event_type != EventType.AGENT
                and hasattr(ev, "action")
                and isinstance(ev.action, Action)
                and "please go ahead and schedule" in ev.action.args.get("content", "").lower()
                for ev in events
            )

            # Meeting added to calendar
            event_added = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "CalendarApp"
                and ev.action.function_name == "add_calendar_event"
                and "Alice Reynolds" in str(ev.action.args.get("attendees", ""))
                and "Brian Smith" in str(ev.action.args.get("attendees", ""))
                for ev in events
            )

            # Confirmation message sent
            confirmation_sent = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "AgentUserInterface"
                and "has been scheduled" in ev.action.args.get("content", "").lower()
                for ev in events
            )

            success = agent_proposed and user_approved and event_added and confirmation_sent
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
