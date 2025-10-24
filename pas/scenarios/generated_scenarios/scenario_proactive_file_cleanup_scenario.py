from __future__ import annotations

import base64
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import Contact, ContactsApp, Gender, Status
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.data.population_scripts.sandbox_file_system_population import default_fs_folders
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("scenario_proactive_file_cleanup")
class ScenarioProactiveFileCleanup(Scenario):
    """Proactive agent variant: assistant detects large file and offers deletion; user confirms."""

    start_time: float | None = 0
    duration: float | None = 20

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate environment with apps and mock data."""
        aui = AgentUserInterface()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        email = EmailClientApp()
        calendar = CalendarApp()
        system = SystemApp()
        messaging = MessagingApp()
        contacts = ContactsApp()

        default_fs_folders(fs)

        # Populate contacts (for uniqueness, not functional requirement)
        contacts.add_contact(
            Contact(
                first_name="Clara",
                last_name="Green",
                phone="+44 7123 456 789",
                email="claragreen@example.com",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                city_living="London",
            )
        )

        contacts.add_contact(
            Contact(
                first_name="Oliver",
                last_name="Gray",
                phone="+44 7980 234 567",
                email="olivergray@example.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                city_living="Manchester",
            )
        )

        # Pre-populate file system content
        fs.makedirs("Documents", exist_ok=True)
        fs.makedirs("Downloads", exist_ok=True)
        fs.makedirs("TempFiles", exist_ok=True)

        # Create normal file and large temporary file
        # Using base64 to differ from examples
        fs.open("Documents/report.docx", mode="wb")
        large_data = base64.b64encode(b"x" * 1024 * 1024 * 20)  # 20 MB
        fs.open("TempFiles/temp_backup.tmp", mode="wb")
        fs.cat(path="TempFiles/temp_backup.tmp")  # reading (placeholder)

        self.apps = [aui, fs, email, calendar, system, messaging, contacts]

    def build_events_flow(self) -> None:
        """Define flow of events for proactive file cleanup scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        fs = self.get_typed_app(SandboxLocalFileSystem)

        with EventRegisterer.capture_mode():
            # User asks agent to monitor disk usage
            start_req = aui.send_message_to_agent(
                content="Hi assistant, please keep an eye on my disk usage and warn me if something gets too big."
            ).depends_on(None, delay_seconds=1)

            # System event: simulate discovery of large temporary file
            file_detected = fs.info(path="TempFiles/temp_backup.tmp").depends_on(start_req, delay_seconds=3)

            # Agent proactively asks about large file cleanup
            proactive_msg = aui.send_message_to_user(
                content="I found a large temporary file 'temp_backup.tmp' (~20MB). Should I delete it to free space?"
            ).depends_on(file_detected, delay_seconds=1)

            # User confirms deletion action
            user_confirm = aui.send_message_to_agent(content="Yes, please remove it.").depends_on(
                proactive_msg, delay_seconds=1
            )

            # Oracle: agent deletes the file
            oracle_cleanup = fs.rm(path="TempFiles/temp_backup.tmp").oracle().depends_on(user_confirm, delay_seconds=1)

        self.events = [start_req, file_detected, proactive_msg, user_confirm, oracle_cleanup]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent properly detected and removed the large file after confirmation."""
        try:
            events = env.event_log.list_view()
            # Check that file remove action happened
            file_removed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "SandboxLocalFileSystem"
                and e.action.function_name == "rm"
                and "temp_backup.tmp" in e.action.args.get("path", "")
                for e in events
            )

            # Verify the agent proposed the cleanup proactively to the user
            agent_prompted = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "delete" in e.action.args.get("content", "").lower()
                and "temp_backup" in e.action.args.get("content", "").lower()
                for e in events
            )

            return ScenarioValidationResult(success=(file_removed and agent_prompted))
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
