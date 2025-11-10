from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_tour_coordination")
class ApartmentTourCoordination(Scenario):
    """Scenario: Agent helps user plan an apartment tour and set a reminder after user approval.

    This scenario demonstrates the coordinated use of Contacts, System, Reminder,
    ApartmentListing, and AgentUserInterface apps.

    Flow summary:
    1. User asks agent to find potential apartments near specified area.
    2. Agent uses ApartmentListingApp to search appropriate apartments.
    3. Agent proposes to share a list of shortlisted apartments with a contact ("Jordan Smith").
    4. User confirms and provides contextual approval.
    5. Agent then uses ContactsApp to fetch Jordan's contact and confirms sharing.
    6. Agent sets a reminder for the scheduled tour date using ReminderApp.
    7. Agent checks system time and waits for confirmation event to simulate real tracking workflow.
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate the environment apps."""
        # Initialize apps
        aui = AgentUserInterface()
        system = SystemApp(name="system_core")
        contacts = ContactsApp()
        reminders = ReminderApp()
        apartments = ApartmentListingApp()

        # Add user's contact details
        contacts.get_current_user_details()

        # Create and add a contact for sharing the shortlist
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Smith",
            gender=Gender.MALE,
            age=31,
            nationality="USA",
            city_living="Seattle",
            country="USA",
            status=Status.EMPLOYED,
            job="Interior Designer",
            description="Friend helping review apartments",
            phone="+1-555-124-7789",
            email="jordan.smith@example.com",
        )

        # Add to scenario context
        self.apps = [aui, system, contacts, reminders, apartments]

    def build_events_flow(self) -> None:
        """Construct the flow of events."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        contacts = self.get_typed_app(ContactsApp)
        reminders = self.get_typed_app(ReminderApp)
        apartments = self.get_typed_app(ApartmentListingApp)

        with EventRegisterer.capture_mode():
            # Step 1: User starts by asking to find apartments
            event0 = aui.send_message_to_agent(
                content="Hey, can you find some 2-bedroom apartments in downtown Seattle under $2500?"
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent performs apartment search
            apartment_search = apartments.search_apartments(
                location="Seattle downtown", max_price=2500, number_of_bedrooms=2, property_type="Apartment"
            ).depends_on(event0, delay_seconds=1)

            # Step 3: Agent proactively proposes sharing shortlist with Jordan
            propose_action = aui.send_message_to_user(
                content="I found a few options that match your request. Would you like me to share them with Jordan Smith for her feedback?"
            ).depends_on(apartment_search, delay_seconds=1)

            # Step 4: User gives detailed approval
            user_confirms = aui.send_message_to_agent(
                content="Yes, please share the apartment list with Jordan and schedule a reminder for our visit next Saturday morning."
            ).depends_on(propose_action, delay_seconds=1)

            # Step 5: Agent retrieves Jordan's contact details for sharing
            contact_lookup = contacts.search_contacts(query="Jordan").depends_on(user_confirms, delay_seconds=1)

            # Step 6: Agent gets current system time to calculate reminder
            current_time = system.get_current_time().depends_on(contact_lookup, delay_seconds=1)

            # Step 7: Agent adds a reminder for viewing apartments
            create_reminder = (
                reminders.add_reminder(
                    title="Apartment tour with Jordan",
                    due_datetime="2024-06-22 09:00:00",
                    description="Meet Jordan to tour shortlisted apartments.",
                )
                .oracle()
                .depends_on(current_time, delay_seconds=1)
            )

            # Step 8: Agent waits after scheduling
            wait_event = system.wait_for_notification(timeout=10).depends_on(create_reminder, delay_seconds=2)

        self.events = [
            event0,
            apartment_search,
            propose_action,
            user_confirms,
            contact_lookup,
            current_time,
            create_reminder,
            wait_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate scenario success conditions."""
        try:
            events_log = env.event_log.list_view()

            shared_proposal = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "AgentUserInterface"
                and ev.action.function_name == "send_message_to_user"
                and "share" in ev.action.args.get("content", "").lower()
                and "jordan" in ev.action.args.get("content", "").lower()
                for ev in events_log
            )
            reminder_created = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "ReminderApp"
                and ev.action.function_name == "add_reminder"
                and "Apartment tour with Jordan" in ev.action.args.get("title", "")
                for ev in events_log
            )
            contact_referenced = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "ContactsApp"
                and ev.action.function_name in ["search_contacts", "get_contact"]
                for ev in events_log
            )
            all_required = shared_proposal and reminder_created and contact_referenced

            return ScenarioValidationResult(success=all_required)
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
