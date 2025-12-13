"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, Event, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulMessagingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("teammate_coverage_urgent_absence")
class TeammateCoverageUrgentAbsence(PASScenario):
    """The user wakes up feeling ill on a Tuesday morning and sends a message to their manager explaining they need to take a sick day. Their calendar shows three important commitments for that day: a 10 AM client presentation they are leading, a 2 PM project review meeting where they were supposed to present status updates, and a 4 PM interview with a job candidate. The contacts app contains work colleagues who have the necessary expertise to cover each responsibility. Shortly after the sick day message is sent, the user receives an email from the client confirming their attendance at the morning presentation and expressing how eager they are to see the proposed solution.

    The proactive agent detects the sick day notification in the messaging app and immediately cross-references the user's calendar to identify same-day commitments that now lack coverage. It analyzes each event's attendee list and matches required skills to colleagues in the contacts app who could potentially step in. The agent recognizes the email from the client indicates high stakeholder expectations for the presentation, elevating the urgency of finding coverage for that specific meeting. It understands that the interview and project review also cannot simply be canceled without coordination.

    The agent proactively offers to draft three separate messages: one to a senior colleague asking if they can deliver the client presentation using the existing slide deck, another to the project lead offering to reschedule the review meeting or have a teammate present on the user's behalf, and a third to HR and the hiring manager proposing alternative interview slots later in the week. The agent also suggests sending a brief email reply to the client explaining the situation and introducing the covering colleague. The user reviews the drafted communications, makes minor adjustments, and accepts the coordination plan, allowing the agent to execute the coverage strategy across messaging, email, and calendar updates.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.messaging = StatefulMessagingApp(name="Messages")
        self.contacts = StatefulContactsApp(name="Contacts")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.email = StatefulEmailApp(name="Emails", user_email="user@company.com")

        # Populate contacts with work colleagues
        manager_contact = Contact(
            first_name="Sarah",
            last_name="Johnson",
            email="sarah.johnson@company.com",
            phone="+1-555-0101",
            job="Engineering Manager",
        )
        senior_colleague = Contact(
            first_name="Michael",
            last_name="Chen",
            email="michael.chen@company.com",
            phone="+1-555-0102",
            job="Senior Software Engineer",
        )
        project_lead = Contact(
            first_name="Emily",
            last_name="Rodriguez",
            email="emily.rodriguez@company.com",
            phone="+1-555-0103",
            job="Project Lead",
        )
        hr_contact = Contact(
            first_name="David",
            last_name="Williams",
            email="david.williams@company.com",
            phone="+1-555-0104",
            job="HR Coordinator",
        )
        hiring_manager = Contact(
            first_name="Jennifer",
            last_name="Lee",
            email="jennifer.lee@company.com",
            phone="+1-555-0105",
            job="Hiring Manager",
        )
        client_contact = Contact(
            first_name="Robert",
            last_name="Thompson",
            email="robert.thompson@clientcorp.com",
            phone="+1-555-0201",
            job="VP of Engineering",
        )
        candidate_contact = Contact(
            first_name="Alex",
            last_name="Martinez",
            email="alex.martinez@email.com",
            phone="+1-555-0301",
        )

        self.contacts.add_contact(manager_contact)
        self.contacts.add_contact(senior_colleague)
        self.contacts.add_contact(project_lead)
        self.contacts.add_contact(hr_contact)
        self.contacts.add_contact(hiring_manager)
        self.contacts.add_contact(client_contact)
        self.contacts.add_contact(candidate_contact)

        # Populate messaging app with users
        self.messaging.add_users([
            "Sarah Johnson",
            "Michael Chen",
            "Emily Rodriguez",
            "David Williams",
            "Jennifer Lee",
        ])

        # Create conversation with manager (existing message history)
        manager_id = self.messaging.name_to_id["Sarah Johnson"]
        manager_conversation = ConversationV2(
            participant_ids=[self.messaging.current_user_id, manager_id],
            title="Sarah Johnson",
        )
        # Previous message from yesterday about project status
        previous_message_time = datetime(2025, 11, 17, 16, 30, 0, tzinfo=UTC).timestamp()
        manager_conversation.messages.append(
            MessageV2(
                sender_id=manager_id,
                content="Thanks for the update on the client presentation. See you tomorrow!",
                timestamp=previous_message_time,
            )
        )
        manager_conversation.update_last_updated(previous_message_time)
        self.messaging.add_conversation(manager_conversation)

        # Populate calendar with three important meetings for today
        # 10 AM Client Presentation
        presentation_start = datetime(2025, 11, 18, 10, 0, 0, tzinfo=UTC).timestamp()
        presentation_end = datetime(2025, 11, 18, 11, 30, 0, tzinfo=UTC).timestamp()
        client_presentation = CalendarEvent(
            title="Client Presentation - Q4 Platform Demo",
            start_datetime=presentation_start,
            end_datetime=presentation_end,
            location="Conference Room A / Zoom",
            description="Present our Q4 platform updates and new features to ClientCorp stakeholders",
            attendees=["Robert Thompson", "Michael Chen"],
            tag="client-meeting",
        )
        self.calendar.set_calendar_event(client_presentation)

        # 2 PM Project Review Meeting
        review_start = datetime(2025, 11, 18, 14, 0, 0, tzinfo=UTC).timestamp()
        review_end = datetime(2025, 11, 18, 15, 0, 0, tzinfo=UTC).timestamp()
        project_review = CalendarEvent(
            title="Project Review - Sprint 23 Status",
            start_datetime=review_start,
            end_datetime=review_end,
            location="Conference Room B",
            description="Present sprint progress and discuss blockers with the project team",
            attendees=["Emily Rodriguez", "Sarah Johnson", "Michael Chen"],
            tag="internal-meeting",
        )
        self.calendar.set_calendar_event(project_review)

        # 4 PM Candidate Interview
        interview_start = datetime(2025, 11, 18, 16, 0, 0, tzinfo=UTC).timestamp()
        interview_end = datetime(2025, 11, 18, 17, 0, 0, tzinfo=UTC).timestamp()
        candidate_interview = CalendarEvent(
            title="Interview - Senior Engineer Candidate",
            start_datetime=interview_start,
            end_datetime=interview_end,
            location="Zoom",
            description="Technical interview with Alex Martinez for Senior Engineer position",
            attendees=["Jennifer Lee", "David Williams"],
            tag="hiring",
        )
        self.calendar.set_calendar_event(candidate_interview)

        # Populate email with some existing work correspondence
        # Email from client about the presentation (will arrive as environment event)
        # Previous email thread about project
        previous_email_time = datetime(2025, 11, 17, 10, 0, 0, tzinfo=UTC).timestamp()
        project_email = Email(
            sender="emily.rodriguez@company.com",
            recipients=["user@company.com"],
            subject="Sprint 23 Review Agenda",
            content="Hi,\n\nJust confirming we're all set for tomorrow's review at 2 PM. Looking forward to your status update on the authentication module.\n\nBest,\nEmily",
            timestamp=previous_email_time,
            is_read=True,
        )
        self.email.add_email(project_email, EmailFolderName.INBOX)

        # Register all apps
        self.apps = [
            self.agent_ui,
            self.system_app,
            self.messaging,
            self.contacts,
            self.calendar,
            self.email,
        ]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Environment Event 1: User sends sick day message to manager
            manager_id = messaging_app.name_to_id["Sarah Johnson"]
            manager_conversation_id = None
            for conv_id, conv in messaging_app.conversations.items():
                if set(conv.participant_ids) == {messaging_app.current_user_id, manager_id}:
                    manager_conversation_id = conv_id
                    break

            sick_message_event = messaging_app.create_and_add_message(
                conversation_id=manager_conversation_id,
                sender_id=messaging_app.current_user_id,
                content="Hi Sarah, I'm not feeling well this morning and need to take a sick day. I have the client presentation at 10 AM, the project review at 2 PM, and the candidate interview at 4 PM today. I'm really sorry for the short notice.",
            ).delayed(10)

            # Environment Event 2: Client sends eager confirmation email about presentation
            client_email_id = "client_presentation_confirmation_001"
            client_email_event = email_app.send_email_to_user_with_id(
                email_id=client_email_id,
                sender="robert.thompson@clientcorp.com",
                subject="Re: Q4 Platform Demo Meeting Today",
                content="Hi,\n\nJust wanted to confirm that our team will be joining the presentation at 10 AM today. We're very excited to see the new features you've been working on. This demo will be critical for our Q4 planning decisions.\n\nLooking forward to it!\n\nBest regards,\nRobert Thompson\nVP of Engineering, ClientCorp",
            ).depends_on(sick_message_event, delay_seconds=15)

            # Oracle Event 1: Agent detects sick day and calendar conflicts, sends proposal
            agent_proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you're taking a sick day but have three important commitments today: a client presentation at 10 AM, a project review at 2 PM, and a candidate interview at 4 PM. I also see Robert Thompson just sent an email emphasizing how critical the presentation is for ClientCorp's Q4 planning. Would you like me to help coordinate coverage for these meetings?",
                )
                .oracle()
                .depends_on(client_email_event, delay_seconds=5)
            )

            # Oracle Event 2: User accepts the agent's proposal
            user_acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please help me arrange coverage. This is urgent.",
                )
                .oracle()
                .depends_on(agent_proposal_event, delay_seconds=3)
            )

            # Oracle Event 3: Agent checks calendar events for today
            calendar_check_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 09:00:00",
                    end_datetime="2025-11-18 18:00:00",
                )
                .oracle()
                .depends_on(user_acceptance_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends message to Michael Chen for presentation coverage
            michael_id = messaging_app.name_to_id["Michael Chen"]
            michael_message_event = (
                messaging_app.send_message(
                    user_id=michael_id,
                    content="Hi Michael, I'm out sick today but have a critical client presentation at 10 AM with ClientCorp. Robert Thompson just emphasized how important this demo is for their Q4 planning. Could you please deliver the presentation using the slide deck in our shared drive? You're already listed as an attendee. Let me know if you can cover this.",
                )
                .oracle()
                .depends_on(calendar_check_event, delay_seconds=3)
            )

            # Oracle Event 5: Agent sends message to Emily Rodriguez for project review
            emily_id = messaging_app.name_to_id["Emily Rodriguez"]
            emily_message_event = (
                messaging_app.send_message(
                    user_id=emily_id,
                    content="Hi Emily, I'm out sick today and won't be able to present at the 2 PM Sprint 23 review. Could we either reschedule the meeting or have Michael present the authentication module status on my behalf? I can send you my notes. What works best for the team?",
                )
                .oracle()
                .depends_on(calendar_check_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent sends message to Jennifer Lee for interview rescheduling
            jennifer_id = messaging_app.name_to_id["Jennifer Lee"]
            jennifer_message_event = (
                messaging_app.send_message(
                    user_id=jennifer_id,
                    content="Hi Jennifer, I'm out sick today and need to reschedule the 4 PM interview with Alex Martinez for the Senior Engineer position. Could we move it to later this week? Thursday or Friday afternoon would work well for me. Please let David know as well.",
                )
                .oracle()
                .depends_on(calendar_check_event, delay_seconds=3)
            )

            # Oracle Event 7: Agent sends email reply to client explaining the situation
            client_reply_event = (
                email_app.reply_to_email(
                    email_id=client_email_id,
                    folder_name="INBOX",
                    content="Hi Robert,\n\nThank you for confirming. Unfortunately, I'm out sick today, but my colleague Michael Chen will be delivering the presentation at 10 AM as planned. Michael is a senior engineer on the team and is fully prepared to walk through all the Q4 platform features. You'll be in excellent hands.\n\nApologies for any inconvenience, and I hope the demo meets your expectations.\n\nBest regards,\nUser",
                )
                .oracle()
                .depends_on(michael_message_event, delay_seconds=5)
            )

            # Oracle Event 8: Agent sends confirmation summary to user
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've coordinated coverage for all three meetings:\n\n1. Client Presentation (10 AM): Messaged Michael Chen to deliver the presentation and replied to Robert Thompson's email introducing Michael as the presenter.\n\n2. Project Review (2 PM): Messaged Emily Rodriguez to either reschedule or have Michael present your status update.\n\n3. Candidate Interview (4 PM): Messaged Jennifer Lee to reschedule the interview with Alex Martinez to later this week.\n\nAll critical stakeholders have been notified. Focus on getting better!",
                )
                .oracle()
                .depends_on(client_reply_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events: list[Event] = [
            sick_message_event,
            client_email_event,
            agent_proposal_event,
            user_acceptance_event,
            calendar_check_event,
            michael_message_event,
            emily_message_event,
            jennifer_message_event,
            client_reply_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user
            # The agent should detect the sick day message and urgent client email, then offer help
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "coordinate coverage" in e.action.args.get("content", "").lower()
                and "three important commitments" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # Check Step 2: Agent detected calendar conflicts by querying calendar
            # The agent should call get_calendar_events_from_to to identify today's meetings
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                and "2025-11-18" in str(e.action.args)
                for e in log_entries
            )

            # Check Step 3a: Agent sent message to Michael Chen for presentation coverage
            # Strict check: must message Michael and mention the client presentation
            michael_message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and "michael" in e.action.args.get("content", "").lower()
                and "presentation" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # Check Step 3b: Agent sent message to Emily Rodriguez for project review
            # Flexible check: should message Emily about the 2 PM meeting
            emily_message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and "emily" in e.action.args.get("content", "").lower()
                and (
                    "project review" in e.action.args.get("content", "").lower()
                    or "sprint 23" in e.action.args.get("content", "").lower()
                    or "2 pm" in e.action.args.get("content", "").lower()
                )
                for e in log_entries
            )

            # Check Step 3c: Agent sent message to Jennifer Lee for interview rescheduling
            # Flexible check: should message Jennifer about the interview
            jennifer_message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and "jennifer" in e.action.args.get("content", "").lower()
                and (
                    "interview" in e.action.args.get("content", "").lower()
                    or "reschedule" in e.action.args.get("content", "").lower()
                )
                for e in log_entries
            )

            # Check Step 3d: Agent replied to client email introducing Michael
            # Strict check: must reply to the client email and mention Michael Chen
            client_reply_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "client_presentation_confirmation_001"
                and "michael" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # Check Step 3e: Agent sent confirmation summary to user
            # Flexible check: should summarize the coordination actions
            confirmation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "coordinated coverage" in e.action.args.get("content", "").lower()
                and "three meetings" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # Success requires all critical checks to pass
            success = (
                proposal_found
                and calendar_check_found
                and michael_message_found
                and emily_message_found
                and jennifer_message_found
                and client_reply_found
                and confirmation_found
            )

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
