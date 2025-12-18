from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("rental_inquiry_proactive_forward")
class RentalInquiryProactiveForward(Scenario):
    """Agent assists user in responding to a new apartment inquiry email with proactive confirmation."""

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps and populate them with relevant data."""
        aui = AgentUserInterface()
        email_client = EmailClientApp()
        contacts = ContactsApp()
        apartment_list_app = ApartmentListingApp()
        system = SystemApp(name="SystemUtility")

        # Populate contact data
        contacts.add_new_contact(
            first_name="Sarah",
            last_name="Lopez",
            gender=Gender.FEMALE,
            age=29,
            status=Status.EMPLOYED,
            job="Software Engineer",
            email="sarah.lopez@example.com",
            phone="+1-202-555-0134",
            city_living="New York",
            country="USA",
            description="Potential tenant asking about the Maple Garden apartment.",
        )

        contacts.add_new_contact(
            first_name="Alex",
            last_name="Thompson",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            job="Property Manager",
            email="alex.thompson@realestatehub.com",
            phone="+1-202-555-0192",
            city_living="New York",
            country="USA",
            description="Property manager for downtown apartments.",
        )

        # Populate a few apartments
        apartment_list_app.list_all_apartments()  # initialize internal listings
        # (In a real simulation, apartment details would be added by the environment population process.)

        # Save one apartment (tenant might inquire about this)
        apartment_list_app.save_apartment(apartment_id="APT-MAPLE-GARDEN")

        # Keep apps list
        self.apps = [aui, email_client, contacts, apartment_list_app, system]

    def build_events_flow(self) -> None:
        """Construct event sequence including proactive agent proposal."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 1: User requests: ask agent to help with apartment inquiries
            user_intro = aui.send_message_to_agent(
                content="Assistant, please monitor new apartment inquiries and help me respond to them professionally."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Email arrives from prospective tenant Sarah
            new_inquiry_email = email_client.get_email_by_id(
                email_id="EMAIL-INQUIRY-001", folder_name="INBOX"
            ).depends_on(user_intro, delay_seconds=1)

            # Step 3: Agent proposes forwarding the inquiry to the property manager for handling
            proposal = aui.send_message_to_user(
                content="Sarah Lopez asked about the Maple Garden apartment. Should I forward her email to Alex Thompson, the property manager?"
            ).depends_on(new_inquiry_email, delay_seconds=1)

            # Step 4: User approves with detailed, contextual confirmation
            user_approval = aui.send_message_to_agent(
                content="Yes, please forward Sarah's inquiry email to Alex Thompson right now."
            ).depends_on(proposal, delay_seconds=1)

            # Step 5: Agent acts by forwarding the email upon approval (oracle action)
            forward_action = (
                email_client.forward_email(
                    email_id="EMAIL-INQUIRY-001", recipients=["alex.thompson@realestatehub.com"], folder_name="INBOX"
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Step 6: System logs the current time for the forward event (for realistic completeness)
            system_time_log = system.get_current_time().depends_on(forward_action, delay_seconds=1)

            # Step 7: Wait for any notifications after execution (dummy wait)
            wait_end = system.wait_for_notification(timeout=3).depends_on(system_time_log, delay_seconds=1)

        # Register all events
        self.events = [
            user_intro,
            new_inquiry_email,
            proposal,
            user_approval,
            forward_action,
            system_time_log,
            wait_end,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the forward and confirmation occurred as intended."""
        try:
            logs = env.event_log.list_view()

            # Check that the agent proposed an action involving 'Sarah' and 'forward'
            proposed_forward = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and "forward" in event.action.args["content"].lower()
                and "sarah" in event.action.args["content"].lower()
                for event in logs
            )

            # Check that the email was forwarded to Alex
            forward_occurred = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "EmailClientApp"
                and event.action.function_name == "forward_email"
                and "alex.thompson@realestatehub.com" in event.action.args["recipients"]
                and event.action.args["email_id"] == "EMAIL-INQUIRY-001"
                for event in logs
            )

            # Check if system time was logged
            system_logged = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "SystemApp"
                and event.action.function_name == "get_current_time"
                for event in logs
            )

            return ScenarioValidationResult(success=(proposed_forward and forward_occurred and system_logged))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
