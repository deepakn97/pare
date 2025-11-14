"""Simple demo scenario with contacts for testing TwoAgentScenarioRunner."""

from __future__ import annotations

from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import Scenario, ScenarioStatus, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import HomeScreenSystemApp, PASAgentUserInterface, StatefulContactsApp, StatefulEmailApp


@register_scenario("demo_simple_contact")
class DemoSimpleContact(Scenario):
    """Simple contacts scenario - user views contact, proactive agent offers help."""

    start_time: float | None = 0
    duration: float | None = 3600
    status: ScenarioStatus = ScenarioStatus.Valid
    is_benchmark_ready: bool = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.email = StatefulEmailApp(name="StatefulEmailApp")
        self.contacts = StatefulContactsApp(name="StatefulContactsApp")
        self.contacts.add_contact(
            Contact(
                first_name="Alice",
                last_name="Smith",
                contact_id="contact-alice",
                phone="111-222-3333",
                email="alice.smith@example.com",
            )
        )

        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")

        self.apps = [self.email, self.contacts, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow - user browses contacts, agent offers help."""
        aui = self.get_typed_app(PASAgentUserInterface)
        contacts = self.get_typed_app(StatefulContactsApp)
        emails = self.get_typed_app(StatefulEmailApp)
        system_app = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            # Incoming message from Alice
            email_event = self.email.send_email_to_user_only(
                sender="alice.smith@example.com",
                subject="Let's Hangout?",
                content="Hello, how are you? I was thinking we could go out for a drink today. Are you free at 7 PM?",
            ).delayed(2)

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

        self.events = [email_event, propose_event, response_event]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent offered help."""
        try:
            log_entries = env.event_log.list_view()

            # Check if agent sent proposal
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Alice" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Check if agent sent message to Alice
            message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "alice.smith@example.com" in e.action.args.get("recipients", [])
                for e in log_entries
            )

            return ScenarioValidationResult(success=(proposal_found and message_found))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
