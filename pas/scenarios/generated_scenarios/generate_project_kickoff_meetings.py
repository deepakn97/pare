from __future__ import annotations

import base64
import uuid
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp, CalendarEvent
from are.simulation.apps.contacts import Contact, ContactsApp, Gender, Status
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.data.population_scripts.sandbox_file_system_population import default_fs_folders
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("generate_project_kickoff_meetings")
class ScenarioAutoGenerateProjectKickoffMeetings(Scenario):
    """Scenario: The agent observes an email about a new project and automatically sets up kickoff meetings in the calendar."""

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize required apps and populate with initial data."""
        aui = AgentUserInterface()
        mail = EmailClientApp()
        calendar = CalendarApp()
        contacts = ContactsApp()
        messenger = MessagingApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        system = SystemApp()

        default_fs_folders(fs)

        # Add project-related contacts
        contacts.add_contact(
            Contact(
                first_name="Nisha",
                last_name="Malhotra",
                phone="+91 9988776655",
                email="nisha@productzen.ai",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                job="Product Lead",
                city_living="Bangalore",
                country="India",
                age=34,
            )
        )

        contacts.add_contact(
            Contact(
                first_name="Aaron",
                last_name="Lopez",
                phone="+1 415 321 7789",
                email="aaron@productzen.ai",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                job="Engineering Manager",
                city_living="San Francisco",
                country="USA",
                age=40,
            )
        )

        self.apps = [aui, mail, calendar, contacts, messenger, fs, system]

    def build_events_flow(self) -> None:
        """Define a novel sequence of interactions around a new project email and automatic meeting creation."""
        aui = self.get_typed_app(AgentUserInterface)
        mail = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)
        messenger = self.get_typed_app(MessagingApp)

        collab_conversation = messenger.create_conversation(
            participants=["Nisha Malhotra", "Aaron Lopez"], title="Project Phoenix Collaboration"
        )

        encoded_doc = base64.b64encode(b"Project Phoenix: Goals and initial milestones").decode("utf-8")

        with EventRegisterer.capture_mode():
            # Step 0: User instructs the assistant to prepare for new project communications
            setup_prompt = aui.send_message_to_agent(
                content="Assistant, watch for any emails mentioning 'Project Phoenix' and help organize related tasks."
            ).depends_on(None, delay_seconds=1)

            # Step 1: A message appears in the project conversation
            message_update = messenger.add_message(
                conversation_id=collab_conversation,
                sender="Nisha Malhotra",
                content="Hi team, I've just shared our official Project Phoenix kickoff email. Take a look!",
            ).depends_on(setup_prompt, delay_seconds=3)

            # Step 2: The email about Project Phoenix arrives
            project_email = mail.send_email_to_user(
                email=Email(
                    sender="nisha@productzen.ai",
                    recipients=[mail.user_email],
                    subject="Project Phoenix Initiation",
                    content=(
                        "Hello Team,\nWe're kicking off Project Phoenix next week. "
                        "Please review the attached outline and confirm your availability for a kickoff session."
                    ),
                    attachments={"Project_Phoenix_Outline.txt": encoded_doc},
                    email_id=f"proj_phoenix_{uuid.uuid4()}",
                )
            ).depends_on(message_update, delay_seconds=2)

            # Step 3: Agent detects project and suggests organizing kickoff schedule
            proactive_suggestion = aui.send_message_to_user(
                content="I spotted an email for a new initiative 'Project Phoenix'. Would you like me to schedule a kickoff meeting?"
            ).depends_on(project_email, delay_seconds=3)

            # Step 4: The user agrees
            affirmative_response = aui.send_message_to_agent(
                content="Yes, please set up the kickoff meetings."
            ).depends_on(proactive_suggestion, delay_seconds=2)

            # Step 5: Oracle creates kickoff meeting event
            kickoff_event = (
                calendar.add_event(
                    CalendarEvent(
                        title="Project Phoenix Kickoff - Global Team",
                        start_time="2024-08-05T10:00:00",
                        end_time="2024-08-05T11:30:00",
                        description="Initial kickoff with ProductZen team members",
                    )
                )
                .oracle()
                .depends_on(affirmative_response, delay_seconds=3)
            )

            # Step 6: Oracle adds internal sync follow-up event
            followup_event = (
                calendar.add_event(
                    CalendarEvent(
                        title="Phoenix Internal Sync",
                        start_time="2024-08-06T09:30:00",
                        end_time="2024-08-06T10:00:00",
                        description="Engineering and product alignment sync after kickoff.",
                    )
                )
                .oracle()
                .depends_on(kickoff_event, delay_seconds=1)
            )

            # Step 7: Agent confirms to user
            confirmation_message = aui.send_message_to_user(
                content="I've added two events for Project Phoenix: the main kickoff and a follow-up sync."
            ).depends_on(followup_event, delay_seconds=2)

            # Step 8: Messenger follow-up
            messenger_note = messenger.send_message(
                conversation_id=collab_conversation, content="Kickoff and sync have been added to the team calendar."
            ).depends_on(confirmation_message, delay_seconds=2)

        self.events = [
            setup_prompt,
            message_update,
            project_email,
            proactive_suggestion,
            affirmative_response,
            kickoff_event,
            followup_event,
            confirmation_message,
            messenger_note,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the kickoff meetings were added and user notified."""
        try:
            logs = env.event_log.list_view()

            kickoff_event_created = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "CalendarApp"
                and ev.action.function_name == "add_event"
                and "kickoff" in ev.action.args.get("title", "").lower()
                for ev in logs
            )

            followup_event_created = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "CalendarApp"
                and ev.action.function_name == "add_event"
                and "sync" in ev.action.args.get("title", "").lower()
                for ev in logs
            )

            user_informed = any(
                ev.event_type == EventType.AGENT
                and ev.action.class_name == "AgentUserInterface"
                and "project phoenix" in ev.action.args.get("content", "").lower()
                and "added" in ev.action.args.get("content", "").lower()
                for ev in logs
            )

            messenger_update_sent = any(
                ev.event_type == EventType.AGENT
                and ev.action.class_name == "MessagingApp"
                and ev.action.function_name == "send_message"
                and "added to the team calendar" in ev.action.args.get("content", "").lower()
                for ev in logs
            )

            success = kickoff_event_created and followup_event_created and user_informed and messenger_update_sent
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
