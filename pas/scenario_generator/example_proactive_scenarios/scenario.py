"""Proactive variants of the tutorial scenario.

Contains:
- ScenarioTutorialProactiveConfirm
- ScenarioTutorialProactiveReject
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

from are.simulation.apps.agent_user_interface import AgentUserInterface

if TYPE_CHECKING:
    from are.simulation.types import AbstractEnvironment
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import Contact, ContactsApp, Gender, Status
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.data.population_scripts.sandbox_file_system_population import default_fs_folders
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import Action, EventRegisterer, EventType


@register_scenario("scenario_tutorial_proactive_confirm")
class ScenarioTutorialProactiveConfirm(Scenario):
    """Proactive variant: agent proposes forward; user confirms; agent forwards email (oracle)."""

    # Keep the same timing defaults
    start_time: float | None = 0
    duration: float | None = 20

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate applications with data."""
        agui = AgentUserInterface()  # User interface for the agent
        calendar = CalendarApp()  # Calendar application
        email_client = EmailClientApp()  # Email client application
        contacts = ContactsApp()  # Contacts application
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))  # File system application
        messaging = MessagingApp()  # Messaging application
        system = SystemApp()  # System application

        default_fs_folders(fs)  # Set up default folders in the file system

        # TODO: insert other population methods for additional applications if needed

        # Manually add specific contacts to the contacts application
        contacts.add_contact(
            Contact(
                first_name="John",
                last_name="Doe",
                phone="+33 345 678 9120",
                email="johndoe@example.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                age=20,
            )
        )

        contacts.add_contact(
            Contact(
                first_name="Greg",
                last_name="Barty",
                phone="+33 291 193 1892",
                email="gregb@example.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                age=27,
            )
        )

        # List of all initialized applications
        self.apps = [agui, calendar, email_client, contacts, fs, messaging, system]

    def build_events_flow(self) -> None:
        """Build the flow of events for the scenario."""
        messaging = self.get_typed_app(MessagingApp)
        email_client = self.get_typed_app(EmailClientApp)
        aui = self.get_typed_app(AgentUserInterface)

        conv1_key = messaging.create_conversation(participants=["John Doe"], title="John Doe and I")

        with EventRegisterer.capture_mode():
            # Define action0: Simulate receiving a message from user
            event0 = aui.send_message_to_agent(
                content="Hey Assistant, can you capture the messages and emails I'll receive and propose new tasks to me?"
            ).depends_on(None, delay_seconds=1)

            # Event 1: John messages the user (context for future action)
            event1 = messaging.add_message(
                conversation_id=conv1_key,
                sender="John Doe",
                content=(
                    "Hey man how are you doing? Greg wanted to send me a pdf with the list of music we should "
                    "listen to via email. He didn't manage to send it to me but will try to send it to you. Can you send it "
                    "to me as soon as you get it?"
                ),
            ).depends_on(event0, delay_seconds=1)

            # Event 2: Greg sends the email with PDF (arrives later)
            event2 = email_client.send_email_to_user(
                email=Email(
                    sender="gregb@example.com",
                    recipients=[email_client.user_email],
                    subject="List of music",
                    content=("Hey man, here is attached the list of music you should listen to. I hope you like it."),
                    attachments={"music.pdf": base64.b64encode(b"This file contains a music list.")},
                    email_id="greg_email",
                )
            ).depends_on(event1, delay_seconds=1)

            # Agent proactively proposes forwarding to the user
            agent_propose = aui.send_message_to_user(
                content=("I received Greg's email with the PDF. Would you like me to forward it to John Doe now?")
            ).depends_on(event2, delay_seconds=1)

            # User confirms after the proposal
            user_confirm = aui.send_message_to_agent(
                content=("Yes, please forward Greg's PDF to John Doe.")
            ).depends_on(agent_propose, delay_seconds=1)

            # Oracle ground-truth: agent forwards the email after confirmation
            oracle_forward = (
                email_client.forward_email(email_id="greg_email", recipients=["johndoe@example.com"])
                .oracle()
                .depends_on(user_confirm, delay_seconds=1)
            )

        self.events = [event0, event1, event2, agent_propose, user_confirm, oracle_forward]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the scenario."""
        try:
            events = env.event_log.list_view()
            email_forwarded = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "forward_email"
                and event.action.class_name == "EmailClientApp"
                and "johndoe@example.com" in event.action.args["recipients"]
                and event.action.args["email_id"] == "greg_email"
                for event in events
            )
            # Agent should also notify the user about proceeding
            notified_user = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "send_message_to_user"
                and event.action.class_name == "AgentUserInterface"
                and isinstance(event.action.args.get("content", None), str)
                and (
                    "forward" in event.action.args["content"].lower()
                    or "pdf" in event.action.args["content"].lower()
                    or "john doe" in event.action.args["content"].lower()
                )
                for event in events
            )
            return ScenarioValidationResult(success=(email_forwarded and notified_user))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


@register_scenario("scenario_tutorial_proactive_reject")
class ScenarioTutorialProactiveReject(Scenario):
    """Proactive variant: agent proposes forward; user rejects; agent does not forward (oracle ack)."""

    start_time: float | None = 0
    duration: float | None = 20

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate applications with data."""
        agui = AgentUserInterface()  # User interface for the agent
        calendar = CalendarApp()  # Calendar application
        email_client = EmailClientApp()  # Email client application
        contacts = ContactsApp()  # Contacts application
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))  # File system application
        messaging = MessagingApp()  # Messaging application
        system = SystemApp()  # System application

        default_fs_folders(fs)  # Set up default folders in the file system

        # TODO: insert other population methods for additional applications if needed

        # Manually add specific contacts to the contacts application
        contacts.add_contact(
            Contact(
                first_name="John",
                last_name="Doe",
                phone="+33 345 678 9120",
                email="johndoe@example.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                age=20,
            )
        )

        contacts.add_contact(
            Contact(
                first_name="Greg",
                last_name="Barty",
                phone="+33 291 193 1892",
                email="gregb@example.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                age=27,
            )
        )

        # List of all initialized applications
        self.apps = [agui, calendar, email_client, contacts, fs, messaging, system]

    def build_events_flow(self) -> None:
        """Build the flow of events for the scenario."""
        messaging = self.get_typed_app(MessagingApp)
        email_client = self.get_typed_app(EmailClientApp)
        aui = self.get_typed_app(AgentUserInterface)

        conv1_key = messaging.create_conversation(participants=["John Doe"], title="John Doe and I")

        with EventRegisterer.capture_mode():
            # Define action0: Simulate receiving a message from user
            event0 = aui.send_message_to_agent(
                content="Hey Assistant, can you capture the messages and emails I'll receive and propose new tasks to me?"
                + "when you received my decision on the new tasks, you can stop monitoring the messages and emails and focus on the new tasks."
            ).depends_on(None, delay_seconds=1)

            # Event 1: John context
            event1 = messaging.add_message(
                conversation_id=conv1_key,
                sender="John Doe",
                content=(
                    "Hey man how are you doing? Greg wanted to send me a pdf with the list of music we should "
                    "listen to. He didn't manage to send it to me but will try to send it to you. Can you send it "
                    "to me as soon as you get it?"
                ),
            ).depends_on(event0, delay_seconds=5)

            # Event 2: Greg email arrives
            event2 = email_client.send_email_to_user(
                email=Email(
                    sender="gregb@example.com",
                    recipients=[email_client.user_email],
                    subject="List of music",
                    content=("Hey man, here is attached the list of music you should listen to. I hope you like it."),
                    attachments={"music.pdf": base64.b64encode(b"This file contains a music list.")},
                    email_id="greg_email",
                )
            ).depends_on(event1, delay_seconds=10)

            # Agent proactively proposes forwarding to the user
            agent_propose = aui.send_message_to_user(
                content=(
                    "I received Greg's email with the PDF. Would you like me to forward it to John Doe now? please reply with 'yes' or 'no'?"
                )
            ).depends_on(event2, delay_seconds=1)

            # User rejects after the proposal
            user_reject = aui.send_message_to_agent(content=("No, do not forward Greg's email.")).depends_on(
                agent_propose, delay_seconds=1
            )

        self.events = [event0, event1, event2, agent_propose, user_reject]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the scenario."""
        try:
            events = env.event_log.list_view()
            email_forwarded = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "forward_email"
                and event.action.class_name == "EmailClientApp"
                for event in events
            )
            # Agent should also notify the user about proceeding
            notified_user = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "send_message_to_user"
                and event.action.class_name == "AgentUserInterface"
                and isinstance(event.action.args.get("content", None), str)
                and (
                    "forward" in event.action.args["content"].lower()
                    or "pdf" in event.action.args["content"].lower()
                    or "john doe" in event.action.args["content"].lower()
                )
                for event in events
            )
            return ScenarioValidationResult(success=(not email_forwarded and notified_user))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
