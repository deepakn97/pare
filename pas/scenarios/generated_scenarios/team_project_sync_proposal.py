from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_project_sync_proposal")
class TeamProjectSyncProposal(Scenario):
    """Scenario: Agent organizes a project sync meeting after user approval.

    The scenario demonstrates the agent proposing a meeting to the user after analyzing context messages,
    the user's explicit approval, and subsequent scheduling of the event.
    It integrates all apps: system for time, contacts for people, messaging for coordination,
    calendar for scheduling, and AUI for communication.
    """

    start_time: float | None = 0
    duration: float | None = 20

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all apps and populate data."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        contacts = ContactsApp()
        messaging = MessagingApp()
        system = SystemApp(name="system")

        # Add contacts representing a project team
        contacts.add_new_contact(
            first_name="Mia",
            last_name="Nguyen",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            email="mia.nguyen@example.com",
            phone="+44 7123 678901",
            job="Project Lead",
            description="Lead contact for design sprint coordination",
        )
        contacts.add_new_contact(
            first_name="Carlos",
            last_name="Ramos",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            email="carlos.ramos@example.com",
            phone="+44 7890 456783",
            job="Developer",
            description="Backend developer for the project",
        )
        contacts.get_current_user_details()  # Load the user's information context

        # Prepare messaging threads
        conversation_mia = messaging.create_conversation(participants=["Mia Nguyen"], title="Design sprint planning")
        conversation_group = messaging.create_conversation(
            participants=["Mia Nguyen", "Carlos Ramos"], title="Project Discussion"
        )

        # Context note: self references for later linking
        self.apps = [aui, calendar, contacts, messaging, system]
        self._conversations = {"mia": conversation_mia, "group": conversation_group}

    def build_events_flow(self) -> None:
        """Define event flow (message exchange → proactive proposal → confirmation → calendar action)."""
        messaging = self.get_typed_app(MessagingApp)
        calendar = self.get_typed_app(CalendarApp)
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)

        mia_convid = self._conversations["mia"]
        group_convid = self._conversations["group"]

        # Set up current time as reference for scheduling
        current_datetime_info = system.get_current_time()
        base_dt = current_datetime_info["datetime"]  # Simplified reference

        with EventRegisterer.capture_mode():
            # Step 1: user asks the agent to monitor messages for project sync context
            e0 = aui.send_message_to_agent(
                content="Hey Assistant, could you watch for messages about project syncs and help organize them?"
            ).depends_on(None, delay_seconds=1)

            # Step 2: Mia sends a message about project sync context
            e1 = messaging.send_message(
                conversation_id=mia_convid,
                content="Hi! Could we arrange a sync with Carlos next week to check on design sprint progress?",
            ).depends_on(e0, delay_seconds=1)

            # Step 3: Agent proposes a suitable action to the user — scheduling a meeting
            proposal = aui.send_message_to_user(
                content="Mia asked about a sync next week. Would you like me to schedule a 30-minute meeting with her and Carlos for next Tuesday morning?"
            ).depends_on(e1, delay_seconds=1)

            # Step 4: User provides explicit confirmation
            approval = aui.send_message_to_agent(
                content="Yes, go ahead and schedule that meeting for next Tuesday morning."
            ).depends_on(proposal, delay_seconds=1)

            # Step 5: Agent acts upon confirmation — adds event to the calendar
            oracle_schedule = (
                calendar.add_calendar_event(
                    title="Project Sync with Mia & Carlos",
                    start_datetime="2024-03-19 10:00:00",
                    end_datetime="2024-03-19 10:30:00",
                    description="Design sprint status review and next-step planning",
                    location="Conference Room A",
                    tag="project-sync",
                    attendees=["Mia Nguyen", "Carlos Ramos"],
                )
                .oracle()
                .depends_on(approval, delay_seconds=1)
            )

            # Step 6: Agent informs the group in messaging that the event has been scheduled
            inform_msg = (
                messaging.send_message(
                    conversation_id=group_convid,
                    content="Hi team, the project sync has been scheduled for Tuesday 10 AM. Calendar invite has been sent.",
                )
                .oracle()
                .depends_on(oracle_schedule, delay_seconds=1)
            )

            # Step 7: System waits for possible confirmation notifications (demonstrating wait usage)
            system_wait = system.wait_for_notification(timeout=5).depends_on(inform_msg, delay_seconds=1)

        self.events = [e0, e1, proposal, approval, oracle_schedule, inform_msg, system_wait]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Custom validation: check that calendar event was created after approval and messages followed."""
        try:
            events = env.event_log.list_view()

            scheduled_event = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "CalendarApp"
                and event.action.function_name == "add_calendar_event"
                and "Project Sync" in event.action.args.get("title", "")
                and "Mia" in " ".join(event.action.args.get("attendees", []))
                and "Carlos" in " ".join(event.action.args.get("attendees", []))
                for event in events
            )

            informed_group = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "MessagingApp"
                and event.action.function_name == "send_message"
                and "project sync" in event.action.args.get("content", "").lower()
                for event in events
            )

            proposal_detected = any(
                event.event_type == EventType.AGENT
                and event.action.class_name == "AgentUserInterface"
                and event.action.function_name == "send_message_to_user"
                and "schedule" in event.action.args.get("content", "").lower()
                for event in events
            )

            user_confirmed = any(
                event.event_type == EventType.USER
                and "schedule" in event.action.args.get("content", "").lower()
                and "yes" in event.action.args.get("content", "").lower()
                for event in events
            )

            all_conditions = scheduled_event and informed_group and proposal_detected and user_confirmed
            return ScenarioValidationResult(success=all_conditions)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
