from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import RentAFlat
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_viewing_coordination")
class ApartmentViewingCoordination(Scenario):
    """Scenario demonstrating coordination of apartment listings, contacts, calendar scheduling, and reminders.

    The assistant helps the user select a flat to view, proposes scheduling a viewing,
    waits for the user's approval, then schedules the viewing in the calendar and
    sets a reminder for a follow-up call.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate the apps with representative data."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        contacts = ContactsApp()
        reminder = ReminderApp()
        system = SystemApp("system_app")
        flats = RentAFlat()

        # Populate contacts: User, landlord, agency rep
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Reed",
            gender=Gender.MALE,
            age=34,
            nationality="American",
            city_living="Paris",
            country="France",
            status=Status.EMPLOYED,
            job="Real Estate Agent",
            phone="+33 623 475 982",
            email="jordan.reed@parisflats.com",
            description="Primary agent contact for flat viewings.",
        )

        contacts.add_new_contact(
            first_name="Sophie",
            last_name="Chen",
            gender=Gender.FEMALE,
            age=29,
            nationality="French",
            city_living="Lyon",
            country="France",
            status=Status.EMPLOYED,
            job="Landlord",
            phone="+33 588 120 450",
            email="sophie.chen@owners.fr",
            description="Landlord of the Rue Cler apartment.",
        )

        # Pre-load system time for realistic scheduling logic
        self.current_time_info = system.get_current_time()
        self.apps = [aui, calendar, contacts, reminder, system, flats]

    def build_events_flow(self) -> None:
        """Define event flow for apartment viewing and scheduling scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        contacts = self.get_typed_app(ContactsApp)
        reminder = self.get_typed_app(ReminderApp)
        flats = self.get_typed_app(RentAFlat)

        with EventRegisterer.capture_mode():
            # Event 0: User initiates the conversation asking for apartment options
            user_request = aui.send_message_to_agent(
                content="Could you help me find a 2-bedroom apartment in Paris under €2000? I might want to schedule a viewing."
            ).depends_on(None, delay_seconds=1)

            # Event 1: Agent searches for apartments matching criteria
            search_results = flats.search_apartments(
                location="Paris", max_price=2000, number_of_bedrooms=2, furnished_status="Furnished"
            ).depends_on(user_request, delay_seconds=1)

            # Event 2: Agent proactively proposes scheduling one of the flats to visit
            proactive_proposal = aui.send_message_to_user(
                content=(
                    "I found a furnished 2-bedroom flat on Rue Cler in Paris for €1850 per month. "
                    "Would you like me to schedule a viewing this Friday at 3 PM and invite Jordan Reed from Paris Flats?"
                )
            ).depends_on(search_results, delay_seconds=1)

            # Event 3: User responds affirmatively providing contextual agreement
            user_confirm = aui.send_message_to_agent(
                content="Yes, that sounds perfect! Go ahead and schedule the Rue Cler viewing with Jordan."
            ).depends_on(proactive_proposal, delay_seconds=1)

            # Event 4: Agent performs the proposed action (schedule calendar event)
            add_event_id = (
                calendar.add_calendar_event(
                    title="Viewing: Rue Cler Apartment",
                    start_datetime="2024-06-14 15:00:00",
                    end_datetime="2024-06-14 16:00:00",
                    description="Apartment viewing with agency rep Jordan Reed for Rue Cler flat.",
                    tag="Apartment Viewing",
                    location="Rue Cler, Paris",
                    attendees=["Jordan Reed"],
                )
                .oracle()
                .depends_on(user_confirm, delay_seconds=1)
            )

            # Event 5: Agent adds a reminder for the viewing follow-up
            add_reminder_id = (
                reminder.add_reminder(
                    title="Follow up with Jordan about the Rue Cler flat",
                    due_datetime="2024-06-15 10:00:00",
                    description="Call or email Jordan to confirm your impressions after the visiting.",
                )
                .oracle()
                .depends_on(add_event_id, delay_seconds=1)
            )

            # Event 6: System waits for notification after the follow-up reminder
            wait_action = (
                self.get_typed_app(SystemApp)
                .wait_for_notification(timeout=5)
                .depends_on(add_reminder_id, delay_seconds=1)
            )

        self.events = [
            user_request,
            search_results,
            proactive_proposal,
            user_confirm,
            add_event_id,
            add_reminder_id,
            wait_action,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent scheduled the apartment viewing and added a reminder."""
        try:
            events = env.event_log.list_view()
            found_calendar_action = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "add_calendar_event"
                and event.action.class_name == "CalendarApp"
                and "Rue Cler" in str(event.action.args.get("title", ""))
                for event in events
            )
            found_reminder_action = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "add_reminder"
                and event.action.class_name == "ReminderApp"
                and "Jordan" in str(event.action.args.get("description", ""))
                for event in events
            )
            proposed_before = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "send_message_to_user"
                and "schedule" in event.action.args["content"].lower()
                and "Rue Cler" in event.action.args["content"]
                for event in events
            )
            user_approved = any(
                event.event_type != EventType.AGENT
                and "yes" in event.content.lower()
                and "schedule" in event.content.lower()
                for event in events
            )

            success = found_calendar_action and found_reminder_action and proposed_before and user_approved
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
