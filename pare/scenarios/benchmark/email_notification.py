"""Simple demo scenario with contacts for testing TwoAgentScenarioRunner."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import HomeScreenSystemApp, PAREAgentUserInterface, StatefulContactsApp, StatefulEmailApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("email_notification")
class EmailNotification(PAREScenario):
    """Simple contacts scenario - user views contact, proactive agent offers help."""

    start_time = datetime(2025, 11, 11, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.email = StatefulEmailApp(name="Emails")
        self.contacts = StatefulContactsApp(name="Contacts")
        self.contacts.add_contact(
            Contact(
                first_name="Alice",
                last_name="Smith",
                contact_id="contact-alice",
                phone="111-222-3333",
                email="alice.smith@example.com",
            )
        )

        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        self.apps = [self.email, self.contacts, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow - user browses contacts, agent offers help."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        contacts = self.get_typed_app(StatefulContactsApp, "Contacts")
        emails = self.get_typed_app(StatefulEmailApp, "Emails")
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")

        with EventRegisterer.capture_mode():
            # Incoming message from Alice (environment event with known ID)
            email_event = self.email.send_email_to_user_with_id(
                email_id="email-from-alice",
                sender="alice.smith@example.com",
                subject="Let's Hangout?",
                content="Hello, how are you? I was thinking we could go out for a drink today. Are you free at 7 PM?",
            ).delayed(20)

            # Agent proactively offers to help (oracle - simulates proactive agent action)
            propose_event = (
                aui.send_message_to_user(
                    content="Do you want me to check your calendar for a good time to hang out with Alice?"
                )
                .oracle()
                .depends_on(email_event, delay_seconds=2)
            )

            # User responds
            response_event = (
                aui.accept_proposal(content="Yes, please check my calendar for a good time.")
                .oracle()
                .depends_on(propose_event, delay_seconds=2)
            )

            # Agent replies to Alice's email
            send_email_event = (
                emails.reply_to_email(
                    email_id="email-from-alice",
                    content="Hi Alice, yeah let's hangout at 7 PM today. See you there!",
                )
                .oracle()
                .depends_on(response_event, delay_seconds=2)
            )

        self.events = [email_event, propose_event, response_event, send_email_event]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent offered help."""
        try:
            log_entries = env.event_log.list_view()

            # Check if agent sent proposal
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Alice" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Check if agent replied to Alice's email
            reply_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email-from-alice"
                for e in log_entries
            )

            return ScenarioValidationResult(success=(proposal_found and reply_found))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
