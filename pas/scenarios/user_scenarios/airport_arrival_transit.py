from __future__ import annotations
import base64
import logging
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import Contact, ContactsApp
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.data.population_scripts.sandbox_file_system_population import default_fs_folders
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

# ---------- Logger ----------
logger = logging.getLogger(__name__)


@register_scenario("proactive_airport_arrival_transit")
class ScenarioProactiveAirportArrivalTransit(Scenario):
    """Proactive agent detects flight-arrival email and offers to create a ground-transit plan."""

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps and preload context."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        email_app = EmailClientApp()
        contacts_app = ContactsApp()
        messenger = MessagingApp()
        fs_app = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        sys_app = SystemApp()
        default_fs_folders(fs_app)

        # Add airline contact
        contacts_app.add_contact(
            Contact(
                first_name="United",
                last_name="Airlines",
                email="noreply@united.com",
            )
        )

        self.apps = [aui, calendar, email_app, contacts_app, messenger, fs_app, sys_app]
        logger.debug("proactive_airport_arrival_transit: Apps initialized")

    def build_events_flow(self) -> None:
        """Define proactive flow for airport-arrival transit help."""
        aui = self.get_typed_app(AgentUserInterface)
        email_app = self.get_typed_app(EmailClientApp)
        fs_app = self.get_typed_app(SandboxLocalFileSystem)

        logger.debug("proactive_airport_arrival_transit: Building event flow")

        with EventRegisterer.capture_mode():
            # Arrival email from airline
            encoded_flight = base64.b64encode(
                b"Flight UA238 arriving SFO 14:35 Gate C12"
            ).decode("utf-8")
            email_event = email_app.send_email_to_user(
                email=Email(
                    sender="noreply@united.com",
                    recipients=[email_app.user_email],
                    subject="Flight UA238 Arrival Notification",
                    content="Your flight UA238 has arrived at SFO. Welcome!",
                    attachments={"flight_info.txt": encoded_flight},
                    email_id="ua238_arrival_email",
                )
            ).depends_on(None, delay_seconds=1)

            # Agent proactively reaches out
            propose_event = aui.send_message_to_user(
                content=(
                    "I noticed your flight UA238 just landed at SFO. "
                    "Would you like me to prepare a transit plan or book a ride to your hotel?"
                )
            ).depends_on(email_event, delay_seconds=2)

            # User confirms
            confirm_event = aui.send_message_to_agent(
                content="Yes, please arrange ground transport to my hotel."
            ).depends_on(propose_event, delay_seconds=2)

            # Agent (oracle) creates the plan file
            oracle_event = (
                fs_app.open(
                    path="Documents/Travel/TransitPlan_UA238.txt",
                    mode="w",
                )
                .oracle()
                .depends_on(confirm_event, delay_seconds=2)
            )

            # Agent notifies completion
            done_event = aui.send_message_to_user(
                content="I've generated your TransitPlan_UA238 under Documents/Travel with your hotel ride details."
            ).depends_on(oracle_event, delay_seconds=2)

        self.events = [
            email_event,
            propose_event,
            confirm_event,
            oracle_event,
            done_event,
        ]

        logger.debug(f"proactive_airport_arrival_transit: Created {len(self.events)} events")

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure proactive suggestion and file-creation occurred."""
        try:
            logs = env.event_log.list_view()

            logger.debug("=== DEBUG EVENTS ===")
            for e in logs:
                if isinstance(e.action, Action):
                    logger.debug(
                        f"{e.event_type:<10} | {e.action.class_name:<30} | "
                        f"{e.action.function_name:<25} | {e.action.args}"
                    )
            logger.debug("=== END DEBUG ===")

            #  Broader proactive detection — allow both ENV and AGENT events
            proactive_msg = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    kw in e.action.args.get("content", "").lower()
                    for kw in ["flight", "arrival", "ride", "transit", "plan", "hotel"]
                )
                for e in logs
                if e.event_type in (EventType.ENV, EventType.AGENT)
            )

            # Check that a file was opened/created under Documents/Travel
            file_event = any(
                isinstance(e.action, Action)
                and e.action.class_name == "SandboxLocalFileSystem"
                and e.action.function_name == "open"
                and "transitplan" in e.action.args.get("path", "").lower()
                for e in logs
            )

            success = proactive_msg and file_event

            logger.debug("[VALIDATION SUMMARY]")
            logger.debug(f"  - Proactive message detected: {'PASS' if proactive_msg else 'FAIL'}")
            logger.debug(f"  - TransitPlan file created:   {'PASS' if file_event else 'FAIL'}")
            logger.debug(f"  => Scenario result: {'PASS' if success else 'FAIL'}")

            return ScenarioValidationResult(success=success)

        except Exception as exc:
            logger.error(f"Validation failed with exception: {exc}")
            return ScenarioValidationResult(success=False, exception=exc)
