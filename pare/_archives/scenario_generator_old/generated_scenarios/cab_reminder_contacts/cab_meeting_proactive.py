from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("cab_meeting_proactive")
class CabMeetingProactive(Scenario):
    """Scenario demonstrating a proactive meeting transportation proposal.

    The agent helps the user plan a trip to a meeting by consulting contacts for the destination address,
    suggesting a cab booking, and offering to set a reminder for departure time upon user confirmation.

    Demonstrates:
    - System time usage for contextual timing
    - Contacts management (search and retrieval)
    - Reminder creation for trip planning
    - Cab booking workflow and quotation validation
    - A proactive agent-to-user interaction requiring approval
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the applications for the simulation."""
        aui = AgentUserInterface()
        contacts = ContactsApp()
        reminder = ReminderApp()
        cab = CabApp()
        system = SystemApp(name="system_core")

        # Populate user contact info
        contacts.get_current_user_details()

        # Add a business contact (meeting location person)
        contact_id = contacts.add_new_contact(
            first_name="Lydia",
            last_name="Marin",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            job="Project Manager",
            email="lydia.marin@proteams.com",
            phone="+44 7000 222333",
            city_living="Liverpool",
            country="UK",
            description="Colleague hosting the meeting",
            address="199 Dale Street, Liverpool, UK",
        )
        # Keep references
        self.contact_id_lydia = contact_id

        self.apps = [aui, contacts, reminder, cab, system]

    def build_events_flow(self) -> None:
        """Build the logical flow of events in the scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        contacts = self.get_typed_app(ContactsApp)
        reminder = self.get_typed_app(ReminderApp)
        cab = self.get_typed_app(CabApp)
        system = self.get_typed_app(SystemApp)

        current_time = system.get_current_time()
        current_dt = current_time["datetime"]

        with EventRegisterer.capture_mode():
            # Event0: user initiates conversation
            user_init = aui.send_message_to_agent(
                content="Hey assistant, I have a meeting with Lydia at her office later today. Can you check the details and help me plan my ride?"
            ).depends_on(None, delay_seconds=1)

            # Event1: agent searches Lydia in contacts
            agent_search_lydia = contacts.search_contacts(query="Lydia").depends_on(user_init, delay_seconds=1)

            # Event2: agent retrieves Lydia's full contact info
            agent_get_contact = contacts.get_contact(contact_id=self.contact_id_lydia).depends_on(
                agent_search_lydia, delay_seconds=1
            )

            # Event3: agent sends a proactive proposal to the user
            proactive_proposal = aui.send_message_to_user(
                content="I found Lydia's address at 199 Dale Street, Liverpool. Would you like me to book a cab and set a reminder 15 minutes before departure?"
            ).depends_on(agent_get_contact, delay_seconds=1)

            # Event4: user confirms
            user_confirm_trip = aui.send_message_to_agent(
                content="Yes, please go ahead and handle both the cab and the reminder."
            ).depends_on(proactive_proposal, delay_seconds=2)

            # Event5: agent checks quotation for cab
            cab_quote = cab.get_quotation(
                start_location="12 Howard Lane, Manchester, UK",
                end_location="199 Dale Street, Liverpool, UK",
                service_type="Premium",
                ride_time=None,
            ).depends_on(user_confirm_trip, delay_seconds=1)

            # Event6: agent books the cab after receiving approval
            cab_book = (
                cab.order_ride(
                    start_location="12 Howard Lane, Manchester, UK",
                    end_location="199 Dale Street, Liverpool, UK",
                    service_type="Premium",
                    ride_time=None,
                )
                .oracle()
                .depends_on(cab_quote, delay_seconds=1)
            )

            # Event7: agent adds a reminder for trip
            reminder_add = (
                reminder.add_reminder(
                    title="Leave for meeting with Lydia",
                    due_datetime=current_dt,
                    description="Get ready and leave for your meeting with Lydia.",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(cab_book, delay_seconds=1)
            )

            # Event8: agent confirms both tasks to user
            confirmation_message = aui.send_message_to_user(
                content="Great! The Premium cab has been booked and a reminder to leave for Lydia's meeting has been set."
            ).depends_on(reminder_add, delay_seconds=1)

            # Event9: wait for any system notification or idle pause before ending
            system_idle_wait = system.wait_for_notification(timeout=5).depends_on(confirmation_message, delay_seconds=1)

        self.events = [
            user_init,
            agent_search_lydia,
            agent_get_contact,
            proactive_proposal,
            user_confirm_trip,
            cab_quote,
            cab_book,
            reminder_add,
            confirmation_message,
            system_idle_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation logic to ensure the flow completed successfully."""
        try:
            events = env.event_log.list_view()
            booked_cab: bool = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "CabApp"
                and event.action.function_name == "order_ride"
                for event in events
            )
            reminder_created: bool = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "ReminderApp"
                and event.action.function_name == "add_reminder"
                for event in events
            )
            proactive_prompt_sent: bool = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and "Would you like me to book a cab" in event.action.args.get("content", "")
                for event in events
            )
            user_agreed: bool = any(
                event.event_type == EventType.USER
                and isinstance(event.action, Action)
                and "Yes, please go ahead" in event.action.args.get("content", "")
                for event in events
            )
            success = booked_cab and reminder_created and proactive_prompt_sent and user_agreed
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
