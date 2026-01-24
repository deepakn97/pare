"""Scenario: Agent downloads and organizes email attachments for hiking trip planning."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps import SandboxLocalFileSystem
from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("group_attachment_consolidation")
class GroupAttachmentConsolidation(PASScenario):
    """Agent downloads and organizes email attachments from friends planning a hiking trip.

    The user receives emails from three friends (Alex Rivera, Jordan Lee, and Casey Morgan)
    who are planning a weekend hiking trip together. Each friend sends an email with a
    relevant attachment: Alex sends a trail map PDF, Jordan sends camping regulations PDF,
    and Casey sends a weather forecast image. The agent notices these related attachments
    about the same upcoming event and proposes downloading and organizing them into a
    dedicated folder for easy access.

    This scenario tests:
    - Multi-email attachment detection and consolidation
    - Proactive file organization without explicit user request
    - Download management across multiple senders
    - Contextual understanding that related materials should be organized together
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You are planning a hiking trip with three friends: Alex Rivera, Jordan Lee, and Casey Morgan.
They will each send you an email with an attachment related to the trip.

BEFORE all three emails arrive:
- Check your email inbox periodically
- Do NOT accept any proposals from the agent

AFTER all three emails have arrived (trail map from Alex, regulations from Jordan, forecast from Casey):

ACCEPT proposals that:
- Recognize all three attachments are related to the hiking trip
- Offer to download and organize the attachments for easy access

REJECT proposals that:
- Arrive before all three emails have been received
- Only mention some of the attachments, not all three
- Do not offer to download the attachments"""

    # Email IDs for reference in build_events_flow
    ALEX_EMAIL_ID = "email-alex-trail-map"
    JORDAN_EMAIL_ID = "email-jordan-regulations"
    CASEY_EMAIL_ID = "email-casey-forecast"

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize filesystem for attachment handling
        self.files = SandboxLocalFileSystem(name="Files")

        # Initialize contacts app with hiking trip participants
        self.contacts = StatefulContactsApp(name="Contacts")

        # Add contacts for the three friends
        self.contacts.add_contact(
            Contact(
                first_name="Alex",
                last_name="Rivera",
                contact_id="contact-alex-rivera",
                phone="555-201-3001",
                email="alex.rivera@email.com",
            )
        )

        self.contacts.add_contact(
            Contact(
                first_name="Jordan",
                last_name="Lee",
                contact_id="contact-jordan-lee",
                phone="555-201-3002",
                email="jordan.lee@email.com",
            )
        )

        self.contacts.add_contact(
            Contact(
                first_name="Casey",
                last_name="Morgan",
                contact_id="contact-casey-morgan",
                phone="555-201-3003",
                email="casey.morgan@email.com",
            )
        )

        # Initialize email app with filesystem for attachments
        self.email = StatefulEmailApp(name="Email")
        self.email.internal_fs = self.files

        # Write simulated attachment files to filesystem
        # These will be attached to incoming emails during build_events_flow
        with self.files.open("/trail_map.pdf", "wb") as f:
            f.write(b"[Simulated PDF: Eagle Peak Trail Map - Parking coordinates, trail markers, summit viewpoint]")

        with self.files.open("/regulations.pdf", "wb") as f:
            f.write(
                b"[Simulated PDF: Camping Regulations - No fires above 8000ft, bear canisters required, permits at ranger station]"
            )

        with self.files.open("/forecast.png", "wb") as f:
            f.write(b"[Simulated PNG: Weather forecast - Saturday clear 65F/42F, Sunday afternoon clouds]")

        # Create the Downloads directory for downloaded attachments
        self.files.makedirs("/Downloads", exist_ok=True)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.files, self.contacts, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        email_app = self.get_typed_app(StatefulEmailApp, "Email")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Alex sends email with trail map attachment
            alex_email_event = email_app.send_email_to_user_with_id(
                email_id=self.ALEX_EMAIL_ID,
                sender="alex.rivera@email.com",
                subject="Trail Map for Saturday's Hike",
                content="Hey! Here's the trail map for Eagle Peak. I've marked the parking coordinates and the summit viewpoint. See you Saturday!",
                attachment_paths=["/trail_map.pdf"],
            ).delayed(10)

            # Environment Event 2: Jordan sends email with regulations attachment
            jordan_email_event = email_app.send_email_to_user_with_id(
                email_id=self.JORDAN_EMAIL_ID,
                sender="jordan.lee@email.com",
                subject="Camping Regulations - Important!",
                content="Found the official camping regulations for the area. Key points: no fires above 8000ft, bear canisters required, and we can get overnight permits at the ranger station. Attached the full PDF.",
                attachment_paths=["/regulations.pdf"],
            ).delayed(15)

            # Environment Event 3: Casey sends email with forecast attachment
            casey_email_event = email_app.send_email_to_user_with_id(
                email_id=self.CASEY_EMAIL_ID,
                sender="casey.morgan@email.com",
                subject="Weather looks great for the hike!",
                content="Just checked the forecast - we're in luck! Clear skies Saturday with highs around 65F and lows 42F overnight. Sunday might have some afternoon clouds but should be fine. Screenshot attached!",
                attachment_paths=["/forecast.png"],
            ).delayed(20)

            # Oracle Event 1: Agent lists emails to see the incoming messages
            list_emails_event = (
                email_app.list_emails(folder_name="INBOX").oracle().depends_on(casey_email_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent proposes downloading and organizing the attachments
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you received emails from Alex, Jordan, and Casey about your hiking trip, each with an attachment (trail map, camping regulations, and weather forecast). Would you like me to download all the attachments and organize them for easy access?"
                )
                .oracle()
                .depends_on(list_emails_event, delay_seconds=2)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please download and organize them.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent downloads Alex's trail map attachment
            download_alex_event = (
                email_app.download_attachments(
                    email_id=self.ALEX_EMAIL_ID,
                    folder_name="INBOX",
                    path_to_save="/Downloads/",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent downloads Jordan's regulations attachment
            download_jordan_event = (
                email_app.download_attachments(
                    email_id=self.JORDAN_EMAIL_ID,
                    folder_name="INBOX",
                    path_to_save="/Downloads/",
                )
                .oracle()
                .depends_on(download_alex_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent downloads Casey's forecast attachment
            download_casey_event = (
                email_app.download_attachments(
                    email_id=self.CASEY_EMAIL_ID,
                    folder_name="INBOX",
                    path_to_save="/Downloads/",
                )
                .oracle()
                .depends_on(download_jordan_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent confirms completion to user
            confirmation_event = (
                aui.send_message_to_user(
                    content="Done! I've downloaded all the hiking trip attachments to your Downloads folder:\n- trail_map.pdf (from Alex)\n- regulations.pdf (from Jordan)\n- forecast.png (from Casey)\n\nEverything is ready for Saturday's hike!"
                )
                .oracle()
                .depends_on(download_casey_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            alex_email_event,
            jordan_email_event,
            casey_email_event,
            list_emails_event,
            proposal_event,
            acceptance_event,
            download_alex_event,
            download_jordan_event,
            download_casey_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent downloads the attachments after user approval."""
        try:
            log_entries = env.event_log.list_view()

            # Essential outcome 1: Agent sent proposal to user about organizing attachments
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Essential outcome 2: Agent downloaded at least one attachment
            # (flexible - agent might download differently, but must download something)
            download_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "download_attachments"
                for e in log_entries
            )

            success = proposal_found and download_found

            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not propose organizing attachments")
                if not download_found:
                    failed_checks.append("agent did not download any attachments")

                rationale = "Validation failed: " + ", ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
