from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("unified_communication_followup")
class UnifiedCommunicationFollowup(Scenario):
    """Scenario: Demonstrates unified messaging and email workflow with proactive task proposal and reminder creation.

    The agent integrates across contacts, messaging, email, and reminders, proposing to follow up on a message
    received from a new partner, and sets a reminder upon user approval. The agent leverages system time to timestamp actions.
    """

    start_time: float | None = 0
    duration: float | None = 35

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all apps and populate them with contextual test data."""
        aui = AgentUserInterface()
        email_app = EmailClientApp()
        msg_app = MessagingApp()
        contact_app = ContactsApp()
        reminder_app = ReminderApp()
        system_app = SystemApp(name="system")

        # Add some initial contacts
        contact_app.add_new_contact(
            first_name="Lara",
            last_name="Fitzgerald",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            email="lara@example.com",
            phone="+1-444-221-3321",
            job="Marketing Lead",
            description="Long-time client contact",
            city_living="Boston",
            country="USA",
        )

        contact_app.add_new_contact(
            first_name="Marco",
            last_name="Bianchi",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            email="marco.bianchi@partnerco.com",
            phone="+39 02 8901 1234",
            job="Business Development Manager",
            description="Potential new partner lead",
            city_living="Milan",
            country="Italy",
        )

        # Add conversation with Lara
        conv_id = msg_app.create_conversation(participants=["Lara Fitzgerald"], title="Lara Weekly Check-in")

        # Add sample email in inbox from Marco
        email_app.send_email(
            recipients=["me@workmail.com"],
            subject="Partnership Proposal",
            content=(
                "Hi! It was great meeting at the Expo. "
                "Looking forward to discussing a collaboration opportunity next week."
            ),
        )

        # Keep for state tracking
        self.conv_id_with_lara = conv_id

        # Register all
        self.apps = [aui, email_app, msg_app, contact_app, reminder_app, system_app]

    def build_events_flow(self) -> None:
        """Create the oracle event flow demonstrating the full integrated workflow."""
        aui = self.get_typed_app(AgentUserInterface)
        msg = self.get_typed_app(MessagingApp)
        email_client = self.get_typed_app(EmailClientApp)
        reminder_app = self.get_typed_app(ReminderApp)
        contacts = self.get_typed_app(ContactsApp)
        system_app = self.get_typed_app(SystemApp)

        # The agent uses system time to propose follow-up scheduling.
        current_time_info = system_app.get_current_time()
        base_dt = current_time_info["datetime"]

        with EventRegisterer.capture_mode():
            # User initiates scenario
            user_init = aui.send_message_to_agent(
                content="I want to make sure I reply to new business messages properly."
            ).depends_on(None, delay_seconds=1)

            # Marco sends new message via email
            incoming_mail_event = email_client.list_emails(folder_name="INBOX", offset=0, limit=1).depends_on(
                user_init, delay_seconds=1
            )

            # Agent recognizes and matches contact Marco, then proposes follow-up task
            propose_action = aui.send_message_to_user(
                content=(
                    "You have a new partnership email from Marco Bianchi. "
                    "Would you like me to create a reminder to follow up with him tomorrow?"
                )
            ).depends_on(incoming_mail_event, delay_seconds=1)

            # User agrees contextually
            user_reply = aui.send_message_to_agent(
                content=("Yes, please set a reminder for tomorrow morning and also let Lara know about this lead.")
            ).depends_on(propose_action, delay_seconds=1)

            # Agent creates reminder after confirmation
            oracle_reminder_creation = (
                reminder_app.add_reminder(
                    title="Follow up with Marco Bianchi",
                    due_datetime="1970-01-02 09:00:00",
                    description="Reach out regarding collaboration proposal after Expo meeting",
                )
                .oracle()
                .depends_on(user_reply, delay_seconds=1)
            )

            # Agent updates Marco contact with follow-up status
            oracle_contact_edit = contacts.search_contacts(query="Marco").depends_on(
                oracle_reminder_creation, delay_seconds=1
            )

            # Agent sends summary to Lara via MessagingApp
            summary_msg = (
                msg.send_message(
                    conversation_id=self.conv_id_with_lara,
                    content=(
                        "Hi Lara, just a note: I received a message from Marco Bianchi about a new partnership lead. "
                        "I'll follow up tomorrow morning."
                    ),
                )
                .oracle()
                .depends_on(oracle_contact_edit, delay_seconds=1)
            )

            # Agent checks time again before closing
            final_time_check = system_app.get_current_time().depends_on(summary_msg, delay_seconds=1)

            # Final user notification
            oracle_final_notify = (
                aui.send_message_to_user(
                    content="Reminder created and message sent to Lara. Task successfully scheduled."
                )
                .oracle()
                .depends_on(final_time_check, delay_seconds=1)
            )

        self.events = [
            user_init,
            incoming_mail_event,
            propose_action,
            user_reply,
            oracle_reminder_creation,
            oracle_contact_edit,
            summary_msg,
            final_time_check,
            oracle_final_notify,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate success by ensuring reminder creation, communication proposal, and message to Lara exist."""
        try:
            logs = env.event_log.list_view()

            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                and "Marco Bianchi" in e.action.args["title"]
                for e in logs
            )

            message_forwarded = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "MessagingApp"
                and e.action.function_name == "send_message"
                and "Lara" in e.action.args["content"]
                for e in logs
            )

            proposal_made = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Marco Bianchi" in e.action.args.get("content", "")
                for e in logs
            )

            final_notify = any(
                "Reminder created" in getattr(e.action.args, "get", lambda x, y=None: "")("content", "")
                if isinstance(e.action, Action) and e.action.class_name == "AgentUserInterface"
                else False
                for e in logs
            )

            success = all([reminder_created, proposal_made, message_forwarded, final_notify])
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
