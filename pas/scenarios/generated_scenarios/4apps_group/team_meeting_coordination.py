from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_meeting_coordination")
class TeamMeetingCoordination(Scenario):
    """A scenario where the agent proposes scheduling a weekly meeting by retrieving contact info and creating a calendar event."""

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate the applications."""
        aui = AgentUserInterface()
        system = SystemApp(name="SystemApp_Main")
        calendar = CalendarApp()
        contacts = ContactsApp()

        # Add some contacts to make the scenario realistic
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Smith",
            gender=Gender.MALE,
            age=33,
            nationality="US",
            city_living="New York",
            country="USA",
            status=Status.EMPLOYED,
            job="Product Manager",
            email="jordan.smith@company.com",
            phone="+1-555-889-2034",
            description="Works in the Product department.",
        )

        contacts.add_new_contact(
            first_name="Taylor",
            last_name="Reed",
            gender=Gender.FEMALE,
            age=28,
            nationality="US",
            city_living="Boston",
            country="USA",
            status=Status.EMPLOYED,
            job="Developer",
            email="taylor.reed@company.com",
            phone="+1-555-880-2021",
            description="Backend developer in the Engineering team.",
        )

        # Store the app instances
        self.apps = [aui, system, calendar, contacts]

    def build_events_flow(self) -> None:
        """Define the event flow for the scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        system = self.get_typed_app(SystemApp)
        contacts = self.get_typed_app(ContactsApp)

        with EventRegisterer.capture_mode():
            # User requests a summary of today's tasks
            user_intro = aui.send_message_to_agent(
                content="Hello Assistant, can you help me plan a recurring weekly sync with Jordan and Taylor?"
            ).depends_on(None, delay_seconds=1)

            # The system retrieves the current time for scheduling
            get_now = system.get_current_time().depends_on(user_intro, delay_seconds=1)

            # The agent checks today's calendar entries
            get_today_events = calendar.read_today_calendar_events().depends_on(get_now, delay_seconds=1)

            # The agent searches contacts to gather info about "Jordan"
            search_contacts = contacts.search_contacts(query="Jordan Smith").depends_on(
                get_today_events, delay_seconds=1
            )

            # Then for "Taylor"
            search_contacts2 = contacts.search_contacts(query="Taylor Reed").depends_on(
                search_contacts, delay_seconds=1
            )

            # The agent proactively proposes scheduling a new calendar event for next week
            propose_event = aui.send_message_to_user(
                content="I can create a 'Weekly Team Sync' with Jordan and Taylor next Monday at 10:00 AM. Would you like me to add it to your calendar?"
            ).depends_on(search_contacts2, delay_seconds=1)

            # User approves in a detailed contextual way
            user_approval = aui.send_message_to_agent(
                content="Yes, go ahead and schedule that meeting for next Monday morning."
            ).depends_on(propose_event, delay_seconds=1)

            # Agent proceeds to create the event after confirmation
            add_event = (
                calendar.add_calendar_event(
                    title="Weekly Team Sync",
                    start_datetime="1970-01-05 10:00:00",
                    end_datetime="1970-01-05 11:00:00",
                    tag="TeamMeeting",
                    description="Weekly sync to review progress and priorities.",
                    location="Conference Room B",
                    attendees=["Jordan Smith", "Taylor Reed"],
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Agent fetches all tags to confirm the tag-based structure
            get_tags = calendar.get_all_tags().depends_on(add_event, delay_seconds=1)

            # Agent retrieves events by tag "TeamMeeting"
            get_by_tag = calendar.get_calendar_events_by_tag(tag="TeamMeeting").depends_on(get_tags, delay_seconds=1)

            # Wait for any notifications or user messages for a short period (simulation pause)
            wait_period = system.wait_for_notification(timeout=2).depends_on(get_by_tag, delay_seconds=1)

        self.events = [
            user_intro,
            get_now,
            get_today_events,
            search_contacts,
            search_contacts2,
            propose_event,
            user_approval,
            add_event,
            get_tags,
            get_by_tag,
            wait_period,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent created the correct event only after user approval."""
        try:
            # Check event logs for correct sequence
            logs = env.event_log.list_view()

            # Verify that the proposal was sent
            proposed = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "AgentUserInterface"
                and ev.action.function_name == "send_message_to_user"
                and "would you like me to add it" in ev.action.args["content"].lower()
                for ev in logs
            )

            # Verify the user gave approval
            approved = any(
                ev.event_type == EventType.USER
                and isinstance(ev.action, Action)
                and ev.action.function_name == "send_message_to_agent"
                and "schedule that meeting" in ev.action.args["content"].lower()
                for ev in logs
            )

            # Verify that a calendar event was added with the correct title & attendees
            created_event = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "CalendarApp"
                and ev.action.function_name == "add_calendar_event"
                and "Weekly Team Sync" in ev.action.args["title"]
                and "Jordan Smith" in ev.action.args["attendees"]
                and "Taylor Reed" in ev.action.args["attendees"]
                for ev in logs
            )

            # Ensure order: proposal → approval → creation
            order_valid = proposed and approved and created_event

            return ScenarioValidationResult(success=order_valid)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
