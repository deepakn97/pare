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


@register_scenario("scenario_project_migration_support")
class ScenarioProjectMigrationSupport(Scenario):
    """Scenario: After a migration manager sends project migration plans via email.

    the assistant assists the user in archiving old files, creating new folders,
    scheduling a migration kickoff meeting, and notifying IT colleagues.
    """

    start_time: float | None = 0
    duration: float | None = 80

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all required apps and prepopulate contacts."""
        aui = AgentUserInterface()
        email_client = EmailClientApp()
        cal = CalendarApp()
        contacts = ContactsApp()
        messenger = MessagingApp()
        fsys = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        system = SystemApp()
        default_fs_folders(fsys)

        # Team contacts
        contacts.add_contact(
            Contact(
                first_name="Helen",
                last_name="Morrison",
                email="helen.morrison@datahub.io",
                phone="+1 222 901 3377",
                job="Migration Manager",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
            )
        )
        contacts.add_contact(
            Contact(
                first_name="Victor",
                last_name="Liu",
                email="victor.liu@datahub.io",
                phone="+1 222 988 1111",
                job="Systems Engineer",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
            )
        )

        self.apps = [aui, email_client, cal, contacts, messenger, fsys, system]

    def build_events_flow(self) -> None:
        """Construct the sequence of activities for migration coordination."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        cal = self.get_typed_app(CalendarApp)
        messenger = self.get_typed_app(MessagingApp)
        fsys = self.get_typed_app(SandboxLocalFileSystem)

        migration_chat = messenger.create_conversation(
            participants=["Victor Liu"], title="Migration Preparation Coordination"
        )

        with EventRegisterer.capture_mode():
            # 1. User instructs assistant to handle migrations
            initialize_instr = aui.send_message_to_agent(
                content="Assistant, monitor any emails about the data center migration and help prepare tasks and meetings accordingly."
            ).depends_on(None, delay_seconds=1.0)

            # 2. Helen sends the migration plan email
            plan_attachment = base64.b64encode(b"Migration plan v1.3 - Server Migrations").decode("utf-8")
            email_plan = email_client.send_email_to_user(
                email=Email(
                    sender="helen.morrison@datahub.io",
                    recipients=[email_client.user_email],
                    subject="Migration Kickoff - Documentation and Schedule Draft",
                    content=(
                        "Hello, please go through the attached migration plan and schedule a kickoff session with IT early next week."
                    ),
                    attachments={"migration_plan.pdf": plan_attachment},
                    email_id=f"plan_{uuid.uuid4()}",
                )
            ).depends_on(initialize_instr, delay_seconds=1.5)

            # 3. Assistant offers to create new workspace and meeting
            propose_action = aui.send_message_to_user(
                content="I noticed Helen shared a migration plan. Would you like me to archive last year's project folder, create a Migration2024 workspace, and schedule a kickoff on Monday?"
            ).depends_on(email_plan, delay_seconds=1.0)

            # 4. User confirms the action
            user_confirmation = aui.send_message_to_agent(
                content="Yes, go ahead. Please archive the old project files and set a kickoff for Monday 10 AM."
            ).depends_on(propose_action, delay_seconds=0.9)

            # 5. Assistant archives old folder
            archive_action = (
                fsys.makedirs(path="Archives/ProjectMigration2023", exist_ok=True)
                .oracle()
                .depends_on(user_confirmation, delay_seconds=1.0)
            )

            # 6. Assistant creates a new workspace directory
            create_workspace = (
                fsys.makedirs(path="Workspaces/Migration2024", exist_ok=True)
                .oracle()
                .depends_on(archive_action, delay_seconds=1.0)
            )

            # 7. Assistant saves the email attachment documentation into workspace
            save_plan_file = (
                fsys.open(path="Workspaces/Migration2024/migration_plan_notes.txt", mode="w")
                .oracle()
                .depends_on(create_workspace, delay_seconds=1.0)
            )

            # 8. Assistant schedules the kickoff
            kickoff_event = (
                cal.add_calendar_event(
                    title="Migration Kickoff Meeting - DataHub Team",
                    start_datetime="1970-01-12 10:00:00",
                    end_datetime="1970-01-12 11:00:00",
                    tag="migration",
                    description="Initial discussion of migration tasks and review of plan from Helen Morrison.",
                )
                .oracle()
                .depends_on(save_plan_file, delay_seconds=1.2)
            )

            # 9. Notify Victor about meeting
            notify_victor = (
                messenger.add_message(
                    conversation_id=migration_chat,
                    sender="User",
                    content="Migration kickoff meeting set for Monday at 10 AM. Please review Helen`s plan beforehand.",
                )
                .oracle()
                .depends_on(kickoff_event, delay_seconds=1.0)
            )

            # 10. Confirm with user
            summary_notice = (
                aui.send_message_to_user(
                    content="All done — old project archived, Migration2024 folder ready, kickoff scheduled, and Victor notified."
                )
                .oracle()
                .depends_on(notify_victor, delay_seconds=0.8)
            )

        self.events = [
            initialize_instr,
            email_plan,
            propose_action,
            user_confirmation,
            archive_action,
            create_workspace,
            save_plan_file,
            kickoff_event,
            notify_victor,
            summary_notice,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Confirm all migration preparation steps completed logically."""
        try:
            events = env.event_log.list_view()

            email_detected = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "AgentUserInterface"
                and "helen" in e.action.args.get("content", "").lower()
                and "migration" in e.action.args.get("content", "").lower()
                for e in events
            )

            archive_done = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "SandboxLocalFileSystem"
                and "archives" in e.action.args.get("path", "").lower()
                for e in events
            )

            workspace_ready = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "SandboxLocalFileSystem"
                and "migration2024" in e.action.args.get("path", "").lower()
                for e in events
            )

            calendar_entry = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "CalendarApp"
                and "kickoff" in e.action.args.get("title", "").lower()
                for e in events
            )

            msg_alert = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "MessagingApp"
                and "victor" in e.action.args.get("content", "").lower()
                and "migration" in e.action.args.get("content", "").lower()
                for e in events
            )

            finish_ack = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "AgentUserInterface"
                and "archived" in e.action.args.get("content", "").lower()
                and "kickoff" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = all([email_detected, archive_done, workspace_ready, calendar_entry, msg_alert, finish_ack])
            return ScenarioValidationResult(success=success)

        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
