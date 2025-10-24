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


@register_scenario("scenario_personal_travel_itinerary_manager")
class ScenarioPersonalTravelItineraryManager(Scenario):
    """The agent detects an upcoming travel itinerary from an email, extracts important files.

    stores them in a travel folder, and automatically schedules notifications for trip details.
    """

    start_time: float | None = 0
    duration: float | None = 70

    def init_and_populate_apps(self, *_: Any, **kwargs: Any) -> None:
        """Set up mock applications and prepopulate contact data."""
        ui = AgentUserInterface()
        email = EmailClientApp()
        calendar = CalendarApp()
        messenger = MessagingApp()
        contacts = ContactsApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        system = SystemApp()
        default_fs_folders(fs)

        contacts.add_contact(
            Contact(
                first_name="Lina",
                last_name="Rossi",
                phone="+39 339 555 1101",
                email="lina.rossi@tripadvisor.com",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                job="Travel Coordinator",
                age=29,
                country="Italy",
                city_living="Rome",
            )
        )

        contacts.add_contact(
            Contact(
                first_name="Marcus",
                last_name="Lee",
                phone="+44 7780 330 112",
                email="marcus.lee@airwayconnect.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                job="Airline Support",
                age=41,
                country="UK",
                city_living="London",
            )
        )

        self.apps = [ui, email, calendar, messenger, contacts, fs, system]

    def build_events_flow(self) -> None:
        """Sequential events modeling travel detection and management."""
        ui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)
        fs = self.get_typed_app(SandboxLocalFileSystem)
        messenger = self.get_typed_app(MessagingApp)

        convo = messenger.create_conversation(participants=["Lina Rossi"], title="Travel Coordination")

        with EventRegisterer.capture_mode():
            # 1. The user initially requests the assistant to help manage travel plans.
            e0 = ui.send_message_to_agent(
                content="Assistant, please organize my travel documents and notify me of flight details automatically."
            ).depends_on(None, delay_seconds=1)

            # 2. Lina sends an email with travel itinerary and boarding pass attachments.
            itinerary_bytes = base64.b64encode(b"Itinerary details: Milan to Tokyo, departure 9AM.").decode("utf-8")
            ticket_bytes = base64.b64encode(b"BoardingPass#: TK992, Gate 31").decode("utf-8")

            e1 = email_client.send_email_to_user(
                email=Email(
                    sender="lina.rossi@tripadvisor.com",
                    recipients=[email_client.user_email],
                    subject="Your Tokyo Trip Package",
                    content="Attached is your itinerary and boarding pass for the upcoming Tokyo trip.",
                    attachments={"Tokyo_Itinerary.pdf": itinerary_bytes, "BoardingPass_Tokyo.pdf": ticket_bytes},
                    email_id=str(uuid.uuid4()),
                )
            ).depends_on(e0, delay_seconds=3)

            # 3. Agent recognizes trip-related info in the email.
            e2 = ui.send_message_to_user(
                content="I noticed Lina sent your Tokyo itinerary and boarding pass. Would you like me to file them under Documents/Travel/Tokyo and set a reminder for departure?"
            ).depends_on(e1, delay_seconds=2)

            # 4. User approves.
            e3 = ui.send_message_to_agent(
                content="Yes, create the travel folder and schedule reminders, please."
            ).depends_on(e2, delay_seconds=2)

            # 5. Oracle actions — saving attachments to file system.
            e4a = (
                fs.open(path="Documents/Travel/Tokyo/Tokyo_Itinerary.pdf", mode="w")
                .oracle()
                .depends_on(e3, delay_seconds=2)
            )
            e4b = (
                fs.open(path="Documents/Travel/Tokyo/BoardingPass_Tokyo.pdf", mode="w")
                .oracle()
                .depends_on(e4a, delay_seconds=1)
            )

            # 6. Oracle — create a reminder in calendar for the trip.
            e5 = (
                calendar.create_event(
                    title="Flight to Tokyo",
                    start_time="2024-08-10T09:00:00",
                    end_time="2024-08-10T09:30:00",
                    attendees=[],
                )
                .oracle()
                .depends_on(e4b, delay_seconds=1)
            )

            # 7. The agent confirms and asks if user wants to let Lina know.
            e6 = ui.send_message_to_user(
                content="I've organized your Tokyo travel files and added the flight to your calendar. Would you like to notify Lina?"
            ).depends_on(e5, delay_seconds=1)

            # 8. The user agrees to inform Lina.
            e7 = ui.send_message_to_agent(content="Yes, please let her know everything is organized.").depends_on(
                e6, delay_seconds=1
            )

            # 9. The assistant sends a message to Lina.
            e8 = messenger.send_message(
                conversation_id=convo,
                content="Hi Lina, I've received and organized my Tokyo travel documents. Thanks for your help!",
            ).depends_on(e7, delay_seconds=2)

        self.events = [e0, e1, e2, e3, e4a, e4b, e5, e6, e7, e8]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation ensures files created, event scheduled, and confirmation sent."""
        try:
            evs = env.event_log.list_view()

            files_created = [
                e
                for e in evs
                if e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "SandboxLocalFileSystem"
                and e.action.function_name == "open"
                and "Documents/Travel/Tokyo" in e.action.args.get("path", "")
            ]

            calendar_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "create_event"
                and "Tokyo" in e.action.args.get("title", "")
                for e in evs
            )

            message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "MessagingApp"
                and e.action.function_name == "send_message"
                and "tokyo travel" in e.action.args.get("content", "").lower()
                for e in evs
            )

            success = len(files_created) >= 2 and calendar_added and message_sent
            return ScenarioValidationResult(success=success)
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
