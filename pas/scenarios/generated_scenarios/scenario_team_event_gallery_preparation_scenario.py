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
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType


@register_scenario("scenario_team_event_gallery_preparation")
class ScenarioTeamEventGalleryPreparation(Scenario):
    """Scenario: The user asks the assistant to sort photographs from a team event.

    An organizer sends an email with event pictures; the assistant offers to:
        - Save the images into a dedicated folder in the file system
        - Send a message to the design team to select the best photos
        - Create a calendar reminder for the presentation deadline

    This scenario emphasizes multi-step reasoning through file organization,
    communication coordination, and scheduling.
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate contacts and apps for the scenario."""
        ui = AgentUserInterface()
        contacts = ContactsApp()
        mail = EmailClientApp()
        calendar = CalendarApp()
        messenger = MessagingApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        system = SystemApp()
        default_fs_folders(fs)

        # Populate relevant contacts
        contacts.add_contact(
            Contact(
                first_name="Nadia",
                last_name="Griffin",
                email="nadia.griffin@eventops.org",
                phone="+1 404 223 9980",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                job="Event Coordinator",
            )
        )
        contacts.add_contact(
            Contact(
                first_name="Aaron",
                last_name="Keller",
                email="aaron.keller@corporate.org",
                phone="+1 212 455 2300",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                job="Design Lead",
            )
        )

        self.apps = [ui, contacts, mail, calendar, messenger, fs, system]

    def build_events_flow(self) -> None:
        """Define a unique flow for managing event photo attachments."""
        ui = self.get_typed_app(AgentUserInterface)
        mail = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)
        messenger = self.get_typed_app(MessagingApp)
        fs = self.get_typed_app(SandboxLocalFileSystem)

        event_gallery_folder = f"TeamEventGallery_{uuid.uuid4().hex[:5]}"
        photo_bytes = base64.b64encode(b"Great team building photo archive").decode("utf-8")

        with EventRegisterer.capture_mode():
            # 1. User initial request
            request = ui.send_message_to_agent(
                content="Assistant, please help me manage any incoming event photo emails."
            ).depends_on(None, delay_seconds=1)

            # 2. Event coordinator sends photo email
            email_trigger = mail.send_email_to_user(
                email=Email(
                    sender="nadia.griffin@eventops.org",
                    recipients=[mail.user_email],
                    subject="Photos from the Corporate Team Event",
                    content="Attached are the final photos from the corporate event. Please organize them for the internal gallery.",
                    attachments={"team_event_photos.zip": photo_bytes},
                    email_id="em_" + uuid.uuid4().hex[:5],
                )
            ).depends_on(request, delay_seconds=2)

            # 3. Assistant notices and offers structured help
            suggestion = ui.send_message_to_user(
                content=(
                    "I received team event photos from Nadia Griffin. "
                    "Shall I create a new gallery folder, notify Aaron Keller to select the best images, "
                    "and add a calendar reminder for the presentation deadline?"
                )
            ).depends_on(email_trigger, delay_seconds=2)

            # 4. User confirms
            confirmation = ui.send_message_to_agent(content="Yes, do that please.").depends_on(
                suggestion, delay_seconds=1
            )

            # 5. Assistant organizes the folder and saves attachment
            create_dir = (
                fs.makedirs(path=event_gallery_folder, exist_ok=True).oracle().depends_on(confirmation, delay_seconds=1)
            )

            save_attachment = (
                fs.cp(path1="Downloads/team_event_photos.zip", path2=f"{event_gallery_folder}/team_event_photos.zip")
                .oracle()
                .depends_on(create_dir, delay_seconds=1)
            )

            # 6. Assistant messages design lead
            message_notify = (
                messenger.send_message_to_user(
                    message="The event photos have been organized in the gallery folder. Aaron, please shortlist key visuals."
                )
                .oracle()
                .depends_on(save_attachment, delay_seconds=1)
            )

            # 7. Assistant creates a calendar reminder
            make_event = (
                calendar.add_calendar_event(
                    title="Gallery Presentation Review",
                    start_datetime="1970-01-08 10:00:00",
                    end_datetime="1970-01-08 11:00:00",
                    description="Review the team event gallery before presentation deadline.",
                    tag="media",
                )
                .oracle()
                .depends_on(message_notify, delay_seconds=1.5)
            )

        self.events = [
            request,
            email_trigger,
            suggestion,
            confirmation,
            create_dir,
            save_attachment,
            message_notify,
            make_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that files, notifications, and reminder were all completed."""
        try:
            logs = env.event_log.list_view()

            # Assistant recognized the photo email
            detected_photo_email = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "AgentUserInterface"
                and "photos from" in e.action.args.get("content", "").lower()
                for e in logs
            )

            # Folder created in filesystem
            folder_created = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "SandboxLocalFileSystem"
                and e.action.function_name == "makedirs"
                for e in logs
            )

            # File copied successfully
            file_copied = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "SandboxLocalFileSystem"
                and "team_event_photos.zip" in str(e.action.args)
                for e in logs
            )

            # Notification sent to design lead
            message_sent = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "MessagingApp"
                and "aaron" in e.action.args.get("message", "").lower()
                for e in logs
            )

            # Calendar event created
            reminder_created = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "CalendarApp"
                and "gallery presentation" in str(e.action.args.get("title", "")).lower()
                for e in logs
            )

            all_success = detected_photo_email and folder_created and file_copied and message_sent and reminder_created
            return ScenarioValidationResult(success=all_success)

        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
