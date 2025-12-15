"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact
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


@register_scenario("lab_results_appointment_scheduling")
class LabResultsAppointmentScheduling(PASScenario):
    """The user receives an email from their doctor's office containing lab test results that flag an abnormal value requiring a follow-up consultation within the next week. The email includes a link to schedule an appointment and mentions that a new prescription will be issued during the visit. The user's calendar shows they have back-to-back work commitments Monday through Wednesday, with only Thursday afternoon and Friday morning showing availability. Their contacts app contains the doctor's office phone number, the pharmacy details, and a family member who has previously helped with medical appointment transportation. A messaging thread with this family member from two weeks ago discussed their availability to provide rides on Thursdays.

    The proactive agent detects the incoming lab results email and identifies the urgency keyword "abnormal" and the temporal constraint "within the next week." It cross-references the user's calendar to find the Thursday afternoon gap that aligns with both the medical timeline and the family member's stated availability in the messaging history. The agent recognizes that medical appointments often require follow-up actions like prescription pickup, and notes the pharmacy contact information is readily available.

    The agent proactively offers to draft an email reply to the doctor's office requesting a Thursday afternoon appointment slot, compose a message to the family member asking if they can still provide transportation that day, and pre-emptively add a calendar event placeholder for the appointment with a note to pick up the new prescription afterward. The user reviews the drafted communications, confirms the proposed time works, accepts the assistance, and the agent coordinates the scheduling across email, messaging, and calendar while ensuring the pharmacy contact is easily accessible for the subsequent prescription pickup..
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
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.contacts = StatefulContactsApp(name="Contacts")
        self.messaging = StatefulMessagingApp(name="Messages")

        # Populate contacts with doctor's office, pharmacy, and family member
        doctor_contact = Contact(
            first_name="Dr. Sarah",
            last_name="Chen",
            phone="555-0123",
            email="appointments@chenmedical.com",
            job="Physician",
            description="Primary care doctor",
        )
        pharmacy_contact = Contact(
            first_name="Green Valley",
            last_name="Pharmacy",
            phone="555-0456",
            email="info@greenvalleyrx.com",
            description="Local pharmacy for prescription pickup",
        )
        family_member_contact = Contact(
            first_name="Michael",
            last_name="Rodriguez",
            phone="555-0789",
            email="michael.rodriguez@email.com",
            description="Brother - helps with transportation",
        )
        user_contact = Contact(
            first_name="Alex", last_name="Johnson", phone="555-0999", email="alex.johnson@email.com", is_user=True
        )

        self.contacts.add_contact(doctor_contact)
        self.contacts.add_contact(pharmacy_contact)
        self.contacts.add_contact(family_member_contact)
        self.contacts.add_contact(user_contact)

        # Set user email in the email app
        self.email.user_email = "alex.johnson@email.com"

        # Populate calendar with work commitments (Monday-Wednesday packed)
        # Monday Nov 18, 2025 - packed schedule
        monday_morning = CalendarEvent(
            title="Team Standup",
            start_datetime=datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 18, 10, 0, 0, tzinfo=UTC).timestamp(),
            tag="work",
            description="Weekly team meeting",
        )
        monday_midday = CalendarEvent(
            title="Project Review Meeting",
            start_datetime=datetime(2025, 11, 18, 10, 30, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 18, 12, 0, 0, tzinfo=UTC).timestamp(),
            tag="work",
            description="Q4 project review",
        )
        monday_afternoon = CalendarEvent(
            title="Client Presentation",
            start_datetime=datetime(2025, 11, 18, 14, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 18, 16, 0, 0, tzinfo=UTC).timestamp(),
            tag="work",
            description="Present quarterly results",
        )

        # Tuesday Nov 19, 2025 - packed schedule
        tuesday_morning = CalendarEvent(
            title="Budget Planning",
            start_datetime=datetime(2025, 11, 19, 9, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 19, 11, 0, 0, tzinfo=UTC).timestamp(),
            tag="work",
            description="2026 budget discussion",
        )
        tuesday_afternoon = CalendarEvent(
            title="All-Hands Meeting",
            start_datetime=datetime(2025, 11, 19, 13, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 19, 15, 0, 0, tzinfo=UTC).timestamp(),
            tag="work",
            description="Company-wide announcements",
        )
        tuesday_late = CalendarEvent(
            title="Training Session",
            start_datetime=datetime(2025, 11, 19, 15, 30, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 19, 17, 0, 0, tzinfo=UTC).timestamp(),
            tag="work",
            description="New software training",
        )

        # Wednesday Nov 20, 2025 - packed schedule
        wednesday_morning = CalendarEvent(
            title="Strategy Workshop",
            start_datetime=datetime(2025, 11, 20, 9, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 20, 12, 0, 0, tzinfo=UTC).timestamp(),
            tag="work",
            description="Strategic planning session",
        )
        wednesday_afternoon = CalendarEvent(
            title="Department Sync",
            start_datetime=datetime(2025, 11, 20, 14, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 20, 17, 0, 0, tzinfo=UTC).timestamp(),
            tag="work",
            description="Cross-department coordination",
        )

        # Thursday Nov 21, 2025 - FREE AFTERNOON (morning has one meeting)
        thursday_morning = CalendarEvent(
            title="Quick Team Sync",
            start_datetime=datetime(2025, 11, 21, 9, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 21, 10, 0, 0, tzinfo=UTC).timestamp(),
            tag="work",
            description="Brief check-in",
        )

        # Friday Nov 22, 2025 - FREE MORNING
        friday_afternoon = CalendarEvent(
            title="End of Week Review",
            start_datetime=datetime(2025, 11, 22, 14, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 22, 15, 0, 0, tzinfo=UTC).timestamp(),
            tag="work",
            description="Weekly wrap-up",
        )

        self.calendar.events[monday_morning.event_id] = monday_morning
        self.calendar.events[monday_midday.event_id] = monday_midday
        self.calendar.events[monday_afternoon.event_id] = monday_afternoon
        self.calendar.events[tuesday_morning.event_id] = tuesday_morning
        self.calendar.events[tuesday_afternoon.event_id] = tuesday_afternoon
        self.calendar.events[tuesday_late.event_id] = tuesday_late
        self.calendar.events[wednesday_morning.event_id] = wednesday_morning
        self.calendar.events[wednesday_afternoon.event_id] = wednesday_afternoon
        self.calendar.events[thursday_morning.event_id] = thursday_morning
        self.calendar.events[friday_afternoon.event_id] = friday_afternoon

        # Populate messaging with historical conversation about Thursday rides
        # Conversation from two weeks ago (Nov 4, 2025)
        self.messaging.add_users(["Michael Rodriguez"])
        michael_id = self.messaging.name_to_id["Michael Rodriguez"]

        old_conversation = ConversationV2(
            participant_ids=[michael_id],
            title="Michael Rodriguez",
            conversation_id="conv_michael_old",
            last_updated=datetime(2025, 11, 4, 15, 0, 0, tzinfo=UTC).timestamp(),
        )

        # Historical messages about Thursday availability
        msg1 = MessageV2(
            sender_id="user",
            content="Hey Michael, are you still available to help with rides on Thursdays?",
            timestamp=datetime(2025, 11, 4, 15, 0, 0, tzinfo=UTC).timestamp(),
        )
        msg2 = MessageV2(
            sender_id=michael_id,
            content="Yeah! Thursdays work great for me. I'm off in the afternoons.",
            timestamp=datetime(2025, 11, 4, 15, 5, 0, tzinfo=UTC).timestamp(),
        )
        msg3 = MessageV2(
            sender_id="user",
            content="Perfect, I'll let you know if I need help getting to appointments.",
            timestamp=datetime(2025, 11, 4, 15, 7, 0, tzinfo=UTC).timestamp(),
        )

        old_conversation.messages.extend([msg1, msg2, msg3])
        self.messaging.conversations[old_conversation.conversation_id] = old_conversation

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar, self.contacts, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Lab results email arrives from doctor's office
            lab_results_email_event = email_app.send_email_to_user_with_id(
                email_id="lab_results_email_001",
                sender="appointments@chenmedical.com",
                subject="Lab Test Results - Follow-up Required",
                content="Dear Alex,\n\nYour recent lab test results have been reviewed by Dr. Chen. We noticed an abnormal value in your cholesterol panel that requires a follow-up consultation within the next week.\n\nPlease schedule an appointment at your earliest convenience. You can reply to this email with your preferred time, or call our office at 555-0123.\n\nDuring your visit, Dr. Chen will discuss the results and issue a new prescription to help manage your levels. Please bring your current medication list.\n\nBest regards,\nDr. Sarah Chen's Office",
            ).delayed(30)

            # Oracle Event 2: Agent checks calendar availability for the week
            check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 00:00:00",
                    end_datetime="2025-11-25 23:59:59",
                )
                .oracle()
                .depends_on(lab_results_email_event, delay_seconds=3)
            )

            # Oracle Event 3: Agent checks messaging history with Michael
            check_messages_event = (
                messaging_app.list_recent_conversations(limit=10)
                .oracle()
                .depends_on(check_calendar_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends proposal to user
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you received lab results from Dr. Chen requiring a follow-up appointment within the next week. I checked your calendar and found that Thursday afternoon (Nov 21) is free. I also see that Michael confirmed he's available for rides on Thursdays. Would you like me to:\n1. Draft a reply to Dr. Chen requesting a Thursday afternoon appointment\n2. Message Michael to ask if he can provide transportation\n3. Add a calendar placeholder with a reminder to pick up your new prescription?"
                )
                .oracle()
                .depends_on(check_messages_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, that sounds perfect. Please coordinate everything.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent replies to doctor's email requesting Thursday appointment
            reply_doctor_event = (
                email_app.reply_to_email(
                    email_id="lab_results_email_001",
                    content="Hello,\n\nThank you for the follow-up regarding my lab results. I would like to schedule an appointment with Dr. Chen this Thursday afternoon, November 21st, if possible. Please let me know what times are available between 2:00 PM and 5:00 PM.\n\nI will bring my current medication list as requested.\n\nBest regards,\nAlex Johnson",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent sends message to Michael about transportation
            # Message Michael about transportation
            michael_id = messaging_app.name_to_id["Michael Rodriguez"]

            send_michael_message_event = (
                messaging_app.send_message(
                    user_id=michael_id,
                    content="Hey Michael! I have a doctor's appointment this Thursday afternoon (Nov 21). You mentioned you're free on Thursday afternoons - would you still be able to give me a ride?",
                )
                .oracle()
                .depends_on(reply_doctor_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent adds calendar event placeholder for doctor appointment
            add_calendar_event = (
                calendar_app.add_calendar_event(
                    title="Dr. Chen Follow-up Appointment",
                    start_datetime="2025-11-21 14:00:00",
                    end_datetime="2025-11-21 15:30:00",
                    location="Dr. Chen's Medical Office",
                    description="Follow-up for lab results. NEW PRESCRIPTION to pick up at Green Valley Pharmacy (555-0456) after appointment. Bring current medication list.",
                    attendees=["Dr. Sarah Chen"],
                )
                .oracle()
                .depends_on(send_michael_message_event, delay_seconds=2)
            )

            # Oracle Event 9: Agent confirms completion to user
            confirmation_event = (
                aui.send_message_to_user(
                    content="All set! I've:\n1. Replied to Dr. Chen's office requesting a Thursday afternoon appointment (Nov 21)\n2. Messaged Michael asking if he can provide transportation\n3. Added a calendar event for Thursday 2:00-3:30 PM with a note to pick up your prescription at Green Valley Pharmacy (555-0456) afterward\n\nYou should receive a confirmation from the doctor's office soon with the exact time."
                )
                .oracle()
                .depends_on(add_calendar_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events: list[Event] = [
            lab_results_email_event,
            check_calendar_event,
            check_messages_event,
            proposal_event,
            acceptance_event,
            reply_doctor_event,
            send_michael_message_event,
            add_calendar_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user mentioning lab results, appointment, and coordination plan
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Dr. Chen" in e.action.args.get("content", "")
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["lab results", "follow-up", "appointment"]
                )
                and any(keyword in e.action.args.get("content", "") for keyword in ["Thursday", "Michael"])
                for e in log_entries
            )

            # Check Step 2a: Agent checked calendar availability (detection action)
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                for e in log_entries
            )

            # Check Step 2b: Agent checked messaging history (detection action)
            messaging_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "list_recent_conversations"
                for e in log_entries
            )

            # Check Step 3a: Agent replied to doctor's email requesting Thursday appointment
            email_reply_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "lab_results_email_001"
                and "Thursday" in e.action.args.get("content", "")
                and "November 21" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Check Step 3b: Agent sent message to Michael about transportation
            michael_message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["Thursday", "ride", "appointment", "doctor"]
                )
                for e in log_entries
            )

            # Check Step 3c: Agent created calendar event with prescription reminder
            calendar_event_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("start_datetime") == "2025-11-21 14:00:00"
                and any(
                    keyword in e.action.args.get("description", "").lower() for keyword in ["prescription", "pharmacy"]
                )
                for e in log_entries
            )

            # Check Step 3d: Agent confirmed completion to user
            confirmation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(keyword in e.action.args.get("content", "") for keyword in ["replied", "messaged", "added"])
                and "Michael" in e.action.args.get("content", "")
                and "calendar" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # Strict checks (required for success): proposal, core detections, and email reply
            strict_checks = proposal_found and calendar_check_found and email_reply_found

            # Flexible checks (nice-to-have): messaging check, Michael message, calendar event, confirmation
            flexible_checks = (
                messaging_check_found and michael_message_found and calendar_event_created and confirmation_found
            )

            # Success requires all strict checks plus at least 3 out of 4 flexible checks
            success = (
                strict_checks
                and sum([messaging_check_found, michael_message_found, calendar_event_created, confirmation_found]) >= 3
            )

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
