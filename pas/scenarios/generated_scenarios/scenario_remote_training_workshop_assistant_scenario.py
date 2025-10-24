from __future__ import annotations

import base64
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


@register_scenario("scenario_remote_training_workshop_assistant")
class ScenarioRemoteTrainingWorkshopAssistant(Scenario):
    """Agent identifies a new remote training opportunity from an email and assists in organizing follow-up and registration."""

    start_time: float | None = 0
    duration: float | None = 50

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize applications and setup context."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        contacts = ContactsApp()
        email_app = EmailClientApp()
        messaging = MessagingApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        system = SystemApp()

        default_fs_folders(fs)

        # Register a corporate contact
        contacts.add_contact(
            Contact(
                first_name="Priya",
                last_name="Deshmukh",
                phone="+91 98202 45081",
                email="priya.deshmukh@learnhub.in",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                job="Training Coordinator",
                city_living="Mumbai",
                country="India",
                age=29,
            )
        )

        # Another collaborator
        contacts.add_contact(
            Contact(
                first_name="Jason",
                last_name="Lee",
                phone="+1 312 772 9911",
                email="jason.lee@skilltech.io",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                job="Developer Advocate",
                city_living="Chicago",
                country="USA",
                age=34,
            )
        )

        self.apps = [aui, calendar, contacts, email_app, messaging, fs, system]

    def build_events_flow(self) -> None:
        """Construct event-driven narrative for the scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        email_app = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)
        messaging = self.get_typed_app(MessagingApp)

        discussion_chat = messaging.create_conversation(
            participants=["Priya Deshmukh", "Jason Lee"], title="Remote Training Workshop Discussion"
        )

        flyer_data = b"This PDF outlines schedule and topics for 'AI in Workplace Productivity' workshop."
        encoded_pdf = base64.b64encode(flyer_data).decode("utf-8")

        with EventRegisterer.capture_mode():
            # Step 1: User asks agent to identify professional learning opportunities automatically.
            e0 = aui.send_message_to_agent(
                content="Assistant, keep an eye out for professional training or workshop announcements."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Email arrives from Priya with training information.
            e1 = email_app.send_email_to_user(
                email=Email(
                    sender="priya.deshmukh@learnhub.in",
                    recipients=[email_app.user_email],
                    subject="Invitation: AI in Workplace Productivity Workshop",
                    content=(
                        "Dear team, we are hosting a two-day virtual training session on 'AI in Workplace Productivity' "
                        "on Feb 4-5. Please confirm interest to secure a slot."
                    ),
                    attachments={"WorkshopFlyer.pdf": encoded_pdf},
                    email_id="workshop_invite_" + str(uuid.uuid4()),
                )
            ).depends_on(e0, delay_seconds=2)

            # Step 3: Agent detects the opportunity and notifies user proactively.
            e2 = aui.send_message_to_user(
                content=(
                    "I noticed an email from Priya mentioning an 'AI in Workplace Productivity' workshop. "
                    "Would you like me to register and schedule it in your calendar?"
                )
            ).depends_on(e1, delay_seconds=3)

            # Step 4: User requests to confirm attendance and add to calendar.
            e3 = aui.send_message_to_agent(
                content="Yes, register me for it and add both days to my calendar, 10am-4pm IST."
            ).depends_on(e2, delay_seconds=2)

            # Step 5: Oracle action: Calendar event creation.
            e4 = (
                calendar.add_calendar_event(
                    title="AI in Workplace Productivity - Day 1",
                    start_datetime="1970-01-05 10:00:00",
                    end_datetime="1970-01-05 16:00:00",
                    attendees=["Priya Deshmukh"],
                    description="Virtual training, Day 1 of 2 (AI in Workplace Productivity).",
                )
                .oracle()
                .depends_on(e3, delay_seconds=2)
            )

            e5 = (
                calendar.add_calendar_event(
                    title="AI in Workplace Productivity - Day 2",
                    start_datetime="1970-01-06 10:00:00",
                    end_datetime="1970-01-06 16:00:00",
                    attendees=["Priya Deshmukh"],
                    description="Virtual training, Day 2 of 2 (AI in Workplace Productivity).",
                )
                .oracle()
                .depends_on(e4, delay_seconds=2)
            )

            # Step 6: Agent posts confirmation to training discussion chat.
            e6 = messaging.send_message(
                conversation_id=discussion_chat,
                content=(
                    "I've registered for the AI workshop and added both days to my calendar. "
                    "Looking forward to collaborating with you, Priya!"
                ),
            ).depends_on(e5, delay_seconds=2)

        self.events = [e0, e1, e2, e3, e4, e5, e6]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure workshop registration and communication steps are properly simulated."""
        try:
            logs = env.event_log.list_view()

            events_created = 0
            message_confirmation = False
            proactive_detection = False

            for ev in logs:
                if ev.event_type == EventType.AGENT and isinstance(ev.action, Action):
                    if (
                        ev.action.class_name == "CalendarApp"
                        and ev.action.function_name == "add_calendar_event"
                        and "AI in Workplace Productivity" in ev.action.args.get("title", "")
                    ):
                        events_created += 1

                    if (
                        ev.action.class_name == "AgentUserInterface"
                        and ev.action.function_name == "send_message_to_user"
                        and "workshop" in ev.action.args.get("content", "").lower()
                        and "register" in ev.action.args.get("content", "").lower()
                    ):
                        proactive_detection = True

                    if (
                        ev.action.class_name == "MessagingApp"
                        and ev.action.function_name == "send_message"
                        and "registered" in ev.action.args.get("content", "").lower()
                        and "calendar" in ev.action.args.get("content", "").lower()
                    ):
                        message_confirmation = True

            success = events_created >= 2 and proactive_detection and message_confirmation
            return ScenarioValidationResult(success=success)
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
