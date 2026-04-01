from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("sync_contact_from_email_proactive")
class SyncContactFromEmailProactive(Scenario):
    """Scenario where the agent helps the user update their contacts list based on data from a new email.

    The agent:
    - Receives an email from an unknown sender.
    - Reads the email and extracts the sender's name.  # noqa: RUF002
    - Proactively asks the user if this new sender should be added as a contact.
    - Upon confirmation, adds the contact.
    - Uses SystemApp to get time and handle a brief wait to simulate processing delay.

    Demonstrates integration across:
      - EmailClientApp
      - ContactsApp
      - AgentUserInterface
      - SystemApp
    """

    start_time: float | None = 0
    duration: float | None = 20

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and set up apps."""
        aui = AgentUserInterface()
        email_client = EmailClientApp()
        contacts_app = ContactsApp()
        system_app = SystemApp(name="sys_main")

        # Populate inbox with an email from an unlisted sender
        self.new_email = Email(
            sender="lia.novak@example.com",
            recipients=["user@example.com"],
            subject="Collaboration Opportunity at NovaTech",
            content=(
                "Hello! I'm Lia Novak from NovaTech. It would be great to collaborate "
                "on your upcoming project. Feel free to contact me anytime."
            ),
            email_id="lia_novak_email",
        )
        # Simulate this email being received in INBOX
        email_client.receive_email(self.new_email)

        # Initialize environment apps
        self.apps = [aui, email_client, contacts_app, system_app]

    def build_events_flow(self) -> None:
        """Construct the ordered event sequence including the proactive pattern."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        contacts = self.get_typed_app(ContactsApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Event 0: User asks for new messages
            user_check_inbox = aui.send_message_to_agent(
                content="Hey Assistant, check if there are any new messages in my inbox."
            ).depends_on(None, delay_seconds=1)

            # Event 1: Agent lists emails
            list_emails_event = (
                email_client.list_emails(folder_name="INBOX", limit=10)
                .oracle()
                .depends_on(user_check_inbox, delay_seconds=1)
            )

            # Event 2: Agent reads details of the first email
            read_email_event = (
                email_client.get_email_by_id(email_id="lia_novak_email", folder_name="INBOX")
                .oracle()
                .depends_on(list_emails_event, delay_seconds=1)
            )

            # Event 3: Agent checks current time (maybe to log timestamp)
            get_time_event = system.get_current_time().oracle().depends_on(read_email_event, delay_seconds=1)

            # Event 4: Agent waits briefly (simulate processing)
            wait_event = system.wait_for_notification(timeout=3).oracle().depends_on(get_time_event, delay_seconds=1)

            # PROACTIVE PROPOSAL: Agent asks user if they want to add Lia to contacts
            proactive_prompt = aui.send_message_to_user(
                content=(
                    "I noticed you have a new email from Lia Novak at NovaTech. "
                    "Would you like me to add Lia Novak to your contacts?"
                )
            ).depends_on(wait_event, delay_seconds=1)

            # USER RESPONSE: Approves the addition
            user_approval = aui.send_message_to_agent(
                content="Yes, please add Lia Novak from NovaTech to my contacts."
            ).depends_on(proactive_prompt, delay_seconds=2)

            # Event 5: Agent adds contact to ContactsApp after approval
            add_contact_event = (
                contacts.add_new_contact(
                    first_name="Lia",
                    last_name="Novak",
                    gender=Gender.FEMALE,
                    status=Status.EMPLOYED,
                    job="Project Manager",
                    email="lia.novak@example.com",
                    country="U.S.",
                    city_living="New York",
                    description="Contacted about NovaTech collaboration",
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Event 6: Agent confirms that the contact has been saved
            confirm_message = aui.send_message_to_user(
                content="Lia Novak has been successfully added to your contacts list."
            ).depends_on(add_contact_event, delay_seconds=1)

        self.events = [
            user_check_inbox,
            list_emails_event,
            read_email_event,
            get_time_event,
            wait_event,
            proactive_prompt,
            user_approval,
            add_contact_event,
            confirm_message,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate: ensure Lia Novak was added and user was notified."""
        try:
            events = env.event_log.list_view()
            # Contact added?
            added_contact = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ContactsApp"
                and e.action.function_name == "add_new_contact"
                and "Novak" in str(e.action.args.get("last_name"))
                for e in events
            )
            # Confirmation sent to user
            user_informed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Lia Novak" in str(e.action.args.get("content"))
                for e in events
            )
            return ScenarioValidationResult(success=(added_contact and user_informed))
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
