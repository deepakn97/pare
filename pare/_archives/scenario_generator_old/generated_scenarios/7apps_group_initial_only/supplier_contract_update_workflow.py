from __future__ import annotations

import uuid
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import Contact, ContactsApp, Gender, Status
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.data.population_scripts.sandbox_file_system_population import default_fs_folders
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("supplier_contract_update_workflow")
class ScenarioSupplierContractUpdateWorkflow(Scenario):
    """Scenario: The user gets a contract renewal email from a supplier.

    The assistant offers to add a follow-up event to review the contract and remind a colleague to join the discussion.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Setup all necessary apps and prepopulate with contextual contacts and data."""
        aui = AgentUserInterface()
        email_client = EmailClientApp()
        contacts = ContactsApp()
        calendar = CalendarApp()
        messaging = MessagingApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        system = SystemApp()
        default_fs_folders(fs)

        # Supplier contact and internal colleague
        contacts.add_contact(
            Contact(
                first_name="Mira",
                last_name="Patel",
                email="mira.patel@supplies-unite.com",
                phone="+1 713 222 8943",
                job="Account Manager",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
            )
        )
        contacts.add_contact(
            Contact(
                first_name="Julian",
                last_name="Price",
                email="julian.price@usercorp.com",
                phone="+1 713 557 6604",
                job="Procurement Analyst",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
            )
        )

        self.apps = [aui, email_client, contacts, calendar, messaging, fs, system]

    def build_events_flow(self) -> None:
        """Define scenario narrative: detecting supplier email, scheduling a review, then notifying a teammate."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)
        messaging = self.get_typed_app(MessagingApp)

        with EventRegisterer.capture_mode():
            # Step 1: The user activates monitoring mode for contract-related emails
            user_starts_monitor = aui.send_message_to_agent(
                content="Assistant, please monitor for supplier contract updates and help me prepare a review event."
            ).depends_on(None, delay_seconds=1)

            # Step 2: The supplier (Mira Patel) sends an email about a contract renewal
            contract_email = email_client.send_email_to_user(
                email=Email(
                    sender="mira.patel@supplies-unite.com",
                    recipients=[email_client.user_email],
                    subject="Annual Service Contract Renewal 2024",
                    content="Our annual contract is approaching renewal. Please confirm if you`d like to arrange a review meeting next week.",
                    email_id=f"contract_{uuid.uuid4().hex}",
                )
            ).depends_on(user_starts_monitor, delay_seconds=3)

            # Step 3: Assistant identifies the email and suggests scheduling a review meeting
            assistant_suggestion = aui.send_message_to_user(
                content="I noticed a message from Mira Patel about renewing your service contract. Would you like me to schedule a contract review meeting?"
            ).depends_on(contract_email, delay_seconds=2)

            # Step 4: The user instructs the agent to create the event and include a colleague
            user_directive = aui.send_message_to_agent(
                content="Yes, schedule one this Thursday at 10 AM and invite Julian Price to join."
            ).depends_on(assistant_suggestion, delay_seconds=2)

            # Step 5: Agent creates a calendar event (oracle)
            make_review_event = (
                calendar.add_calendar_event(
                    title="Service Contract Renewal Review",
                    start_datetime="1970-01-04 10:00:00",
                    end_datetime="1970-01-04 11:00:00",
                    tag="contract",
                    description="Discussion with Mira Patel on renewal terms, joined by Julian Price.",
                )
                .oracle()
                .depends_on(user_directive, delay_seconds=2)
            )

            # Step 6: Assistant sends an internal message to Julian Price to confirm attendance
            convo_id = messaging.create_conversation(participants=["Julian Price"], title="Contract Renewal Prep")
            followup_msg = (
                messaging.add_message(
                    conversation_id=convo_id,
                    sender="Assistant",
                    content="Julian, a contract renewal review with Mira Patel is set for this Thursday at 10 AM. Please prepare the previous year's purchase metrics.",
                )
                .oracle()
                .depends_on(make_review_event, delay_seconds=2)
            )

        self.events = [
            user_starts_monitor,
            contract_email,
            assistant_suggestion,
            user_directive,
            make_review_event,
            followup_msg,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate if a calendar event and follow-up message were properly created after the email trigger."""
        try:
            log_entries = env.event_log.list_view()

            event_created = any(
                evt.event_type == EventType.AGENT
                and isinstance(evt.action, Action)
                and evt.action.class_name == "CalendarApp"
                and evt.action.function_name == "add_calendar_event"
                and "Contract Renewal" in evt.action.args.get("title", "")
                for evt in log_entries
            )

            msg_to_julian = any(
                evt.event_type == EventType.AGENT
                and isinstance(evt.action, Action)
                and evt.action.class_name == "MessagingApp"
                and evt.action.function_name == "add_message"
                and "Julian" in evt.action.args.get("content", "")
                and "contract" in evt.action.args.get("content", "").lower()
                for evt in log_entries
            )

            user_instruction_confirmed = any(
                evt.event_type == EventType.USER
                and isinstance(evt.action, Action)
                and evt.action.class_name == "AgentUserInterface"
                and "schedule" in evt.action.args.get("content", "").lower()
                and "julian" in evt.action.args.get("content", "").lower()
                for evt in log_entries
            )

            success = event_created and msg_to_julian and user_instruction_confirmed
            return ScenarioValidationResult(success=success)

        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
