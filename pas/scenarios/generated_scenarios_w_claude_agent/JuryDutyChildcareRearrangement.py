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


@register_scenario("jury_duty_childcare_rearrangement")
class JuryDutyChildcareRearrangement(PASScenario):
    """The user receives an official email summons for jury duty on Wednesday and Thursday of next week, requiring full-day attendance at the courthouse from 8 AM to 5 PM with no ability to reschedule. Their calendar shows a standing pattern of school pickup responsibilities at 3:15 PM on both days for their child, plus a parent-teacher conference already scheduled for Wednesday at 4 PM that took months to arrange. The contacts app contains their co-parent who travels frequently for work, their retired neighbor who has emergency contact authorization at the school, and the teacher's direct contact information. A messaging thread with the co-parent from last week confirms they will be at a client site in another state throughout next week with no flexibility to return early.

    The proactive agent detects the mandatory jury duty obligation and immediately identifies the calendar conflicts with both the daily pickup routine and the rare parent-teacher conference. It recognizes that jury duty, unlike most work obligations, cannot be delegated or rescheduled easily once summoned, and represents a civic duty the user is legally bound to fulfill. By examining the messaging history, the agent understands the co-parent is unavailable for backup coverage. It identifies the retired neighbor in contacts who has both the trust relationship (emergency contact status) and likely availability to handle the two-day pickup responsibility, though this requires coordination with the school for authorization.

    The agent proactively offers to draft a message to the retired neighbor requesting help with Wednesday and Thursday pickups, compose an email to the teacher explaining the jury duty conflict and proposing to reschedule the conference to the following week, send a courtesy message to the co-parent informing them of the situation even though they cannot help, prepare a reply to the court confirming attendance, and update the calendar by blocking the full days for jury duty while adding the arranged pickup coverage details. The user accepts this comprehensive coordination plan, recognizing the agent understood the legal obligation hierarchy, custody logistics, school authorization protocols, and the relative importance of preserving the parent-teacher conference through rescheduling rather than cancellation..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts App
        self.contacts = StatefulContactsApp(name="Contacts")

        # User (the parent with jury duty)
        user_contact = Contact(
            first_name="Alex", last_name="Johnson", is_user=True, phone="555-0100", email="alex.johnson@email.com"
        )

        # Co-parent (travels frequently for work)
        coparent_contact = Contact(
            first_name="Jordan",
            last_name="Miller",
            phone="555-0101",
            email="jordan.miller@email.com",
            description="Co-parent, frequently travels for work",
        )

        # Retired neighbor (emergency contact for school)
        neighbor_contact = Contact(
            first_name="Margaret",
            last_name="Chen",
            phone="555-0102",
            email="margaret.chen@email.com",
            status="Retired",
            description="Retired neighbor, emergency contact for school",
        )

        # Teacher
        teacher_contact = Contact(
            first_name="Ms. Sarah",
            last_name="Williams",
            phone="555-0103",
            email="sarah.williams@lincolnelementary.edu",
            job="Elementary School Teacher",
            description="Emma's 3rd grade teacher at Lincoln Elementary",
        )

        self.contacts.add_contact(user_contact)
        self.contacts.add_contact(coparent_contact)
        self.contacts.add_contact(neighbor_contact)
        self.contacts.add_contact(teacher_contact)

        # Initialize Calendar App
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Calculate dates: start_time is Tuesday Nov 18, 2025 at 9 AM UTC
        # Next week Wednesday is Nov 26, Thursday is Nov 27
        wed_pickup_start = datetime(2025, 11, 26, 15, 15, 0, tzinfo=UTC).timestamp()  # 3:15 PM
        wed_pickup_end = datetime(2025, 11, 26, 15, 45, 0, tzinfo=UTC).timestamp()  # 3:45 PM

        thu_pickup_start = datetime(2025, 11, 27, 15, 15, 0, tzinfo=UTC).timestamp()  # 3:15 PM
        thu_pickup_end = datetime(2025, 11, 27, 15, 45, 0, tzinfo=UTC).timestamp()  # 3:45 PM

        wed_conference_start = datetime(2025, 11, 26, 16, 0, 0, tzinfo=UTC).timestamp()  # 4:00 PM
        wed_conference_end = datetime(2025, 11, 26, 16, 30, 0, tzinfo=UTC).timestamp()  # 4:30 PM

        # School pickup events
        wed_pickup_event = CalendarEvent(
            title="School Pickup - Emma",
            start_datetime=wed_pickup_start,
            end_datetime=wed_pickup_end,
            location="Lincoln Elementary School",
            description="Daily pickup responsibility",
            tag="Family",
        )

        thu_pickup_event = CalendarEvent(
            title="School Pickup - Emma",
            start_datetime=thu_pickup_start,
            end_datetime=thu_pickup_end,
            location="Lincoln Elementary School",
            description="Daily pickup responsibility",
            tag="Family",
        )

        # Parent-teacher conference
        conference_event = CalendarEvent(
            title="Parent-Teacher Conference",
            start_datetime=wed_conference_start,
            end_datetime=wed_conference_end,
            location="Lincoln Elementary School, Room 204",
            description="Scheduled conference with Ms. Williams to discuss Emma's progress",
            attendees=["Ms. Sarah Williams"],
            tag="Family",
        )

        self.calendar.add_event(wed_pickup_event)
        self.calendar.add_event(thu_pickup_event)
        self.wed_conference_event_id = self.calendar.add_event(conference_event)

        # Initialize Messaging App
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.current_user_id = "555-0100"
        self.messaging.current_user_name = "Alex Johnson"

        # Add contacts to messaging
        self.messaging.add_contacts([
            ("Jordan Miller", "555-0101"),
            ("Margaret Chen", "555-0102"),
            ("Ms. Sarah Williams", "555-0103"),
        ])

        # Create conversation with co-parent about their upcoming travel
        coparent_convo_id = "conv_coparent_001"
        coparent_conversation = ConversationV2(
            conversation_id=coparent_convo_id,
            participant_ids=["555-0100", "555-0101"],
            title="Jordan Miller",
            last_updated=datetime(2025, 11, 11, 14, 0, 0, tzinfo=UTC).timestamp(),  # Last week
        )

        # Message history: co-parent confirms unavailability
        msg1_timestamp = datetime(2025, 11, 11, 14, 0, 0, tzinfo=UTC).timestamp()
        msg1 = MessageV2(
            sender_id="555-0100",
            content="Hey, are you available next week if I need backup with Emma's pickup?",
            timestamp=msg1_timestamp,
        )

        msg2_timestamp = datetime(2025, 11, 11, 14, 15, 0, tzinfo=UTC).timestamp()
        msg2 = MessageV2(
            sender_id="555-0101",
            content="Unfortunately no - I'll be at the Chicago client site all week. No flexibility to leave early. Is something coming up?",
            timestamp=msg2_timestamp,
        )

        msg3_timestamp = datetime(2025, 11, 11, 14, 20, 0, tzinfo=UTC).timestamp()
        msg3 = MessageV2(
            sender_id="555-0100",
            content="Just checking in case. I'll figure it out if needed. Safe travels!",
            timestamp=msg3_timestamp,
        )

        coparent_conversation.messages = [msg1, msg2, msg3]
        self.messaging.add_conversation(coparent_conversation)

        # Initialize Email App
        self.email = StatefulEmailApp(name="Emails")
        self.email.user_email = "alex.johnson@email.com"

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.calendar, self.messaging, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # Event 1: User receives jury duty summons email (environment event)
            jury_summons_event = email_app.send_email_to_user_with_id(
                email_id="jury_summons_001",
                sender="jury.services@county.court.gov",
                subject="Official Jury Duty Summons - Report Nov 26-27, 2025",
                content="You are hereby summoned to serve as a juror at the County Courthouse. You must report on Wednesday, November 26, 2025 and Thursday, November 27, 2025. Attendance is required from 8:00 AM to 5:00 PM each day. This is a legal obligation and cannot be postponed except for extreme medical emergencies. Please confirm your attendance by replying to this email. Failure to appear may result in penalties.",
            ).delayed(15)

            # Event 2: Agent checks calendar for conflicts on jury duty dates (oracle)
            check_wed_conflicts = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-26 08:00:00", end_datetime="2025-11-26 17:00:00"
                )
                .oracle()
                .depends_on(jury_summons_event, delay_seconds=3)
            )

            # Event 3: Agent checks Thursday conflicts (oracle)
            check_thu_conflicts = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-27 08:00:00", end_datetime="2025-11-27 17:00:00"
                )
                .oracle()
                .depends_on(check_wed_conflicts, delay_seconds=1)
            )

            # Event 4: Agent proposes comprehensive coordination plan (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="I received your jury duty summons for Wednesday and Thursday, Nov 26-27. This is a mandatory legal obligation that conflicts with Emma's school pickups (3:15 PM both days) and your parent-teacher conference (Wednesday 4 PM). Your co-parent Jordan is unavailable (traveling in Chicago all week). I can coordinate coverage by: (1) asking your neighbor Margaret Chen to handle both pickups, (2) emailing Ms. Williams to reschedule the conference to the following week, (3) updating Jordan about the situation, and (4) confirming your jury duty attendance. Would you like me to proceed?"
                )
                .oracle()
                .depends_on(check_thu_conflicts, delay_seconds=3)
            )

            # Event 5: User accepts the coordination plan (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Yes, please coordinate everything. This is really helpful!")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 6: Agent adds jury duty to calendar for Wednesday (oracle)
            add_wed_jury_duty = (
                calendar_app.add_calendar_event(
                    title="Jury Duty - County Courthouse",
                    start_datetime="2025-11-26 08:00:00",
                    end_datetime="2025-11-26 17:00:00",
                    location="County Courthouse",
                    description="Mandatory jury service - cannot reschedule",
                    tag="Legal",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Event 7: Agent adds jury duty to calendar for Thursday (oracle)
            add_thu_jury_duty = (
                calendar_app.add_calendar_event(
                    title="Jury Duty - County Courthouse",
                    start_datetime="2025-11-27 08:00:00",
                    end_datetime="2025-11-27 17:00:00",
                    location="County Courthouse",
                    description="Mandatory jury service - cannot reschedule",
                    tag="Legal",
                )
                .oracle()
                .depends_on(add_wed_jury_duty, delay_seconds=1)
            )

            # Event 8: Agent sends message to neighbor Margaret requesting pickup help (oracle)
            # Note: create_and_add_message is in notification_templates.py
            neighbor_message_event = (
                messaging_app.create_and_add_message(
                    conversation_id="conv_neighbor_001",
                    sender_id="555-0100",
                    content="Hi Margaret! I have jury duty next Wednesday and Thursday (Nov 26-27) and can't do Emma's school pickup at 3:15 PM. Would you be able to pick her up both days? I'll let the school know you're coming. I really appreciate your help!",
                )
                .oracle()
                .depends_on(add_thu_jury_duty, delay_seconds=2)
            )

            # Event 9: Agent emails teacher to reschedule conference (oracle)
            teacher_email_event = (
                email_app.send_email_to_user_only(
                    sender="alex.johnson@email.com",
                    subject="Need to Reschedule Parent-Teacher Conference - Jury Duty",
                    content="Dear Ms. Williams,\n\nI've been called for jury duty on Wednesday, November 26th and will be at the courthouse all day from 8 AM to 5 PM. Unfortunately, this means I need to reschedule our parent-teacher conference scheduled for 4 PM that day.\n\nWould it be possible to meet the following week instead? I'm flexible on days and times. I apologize for the inconvenience and look forward to discussing Emma's progress.\n\nBest regards,\nAlex Johnson",
                )
                .oracle()
                .depends_on(neighbor_message_event, delay_seconds=2)
            )

            # Event 10: Agent sends courtesy message to co-parent Jordan (oracle)
            coparent_message_event = (
                messaging_app.create_and_add_message(
                    conversation_id="conv_coparent_001",
                    sender_id="555-0100",
                    content="Hey, just a heads up - I got called for jury duty Wed & Thu next week. I know you're in Chicago, so I've arranged for Margaret to do the school pickups. Everything's covered, just wanted to keep you in the loop!",
                )
                .oracle()
                .depends_on(teacher_email_event, delay_seconds=1)
            )

            # Event 11: Agent replies to jury duty summons confirming attendance (oracle)
            confirm_jury_duty_event = (
                email_app.reply_to_email(
                    email_id="jury_summons_001",
                    content="I confirm my attendance for jury duty on Wednesday, November 26, 2025 and Thursday, November 27, 2025. I will report to the County Courthouse at 8:00 AM on both days.\n\nAlex Johnson",
                )
                .oracle()
                .depends_on(coparent_message_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events: list[Event] = [
            jury_summons_event,
            check_wed_conflicts,
            check_thu_conflicts,
            proposal_event,
            acceptance_event,
            add_wed_jury_duty,
            add_thu_jury_duty,
            neighbor_message_event,
            teacher_email_event,
            coparent_message_event,
            confirm_jury_duty_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal mentioning jury duty conflicts and coordination plan
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(keyword in e.action.args.get("content", "") for keyword in ["jury duty", "jury", "summons"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["pickup", "school"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["Margaret", "neighbor"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["conference", "teacher"])
                for e in log_entries
            )

            # Check Step 2a: Agent checked calendar for Wednesday conflicts
            wed_calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                and "2025-11-26" in e.action.args.get("start_datetime", "")
                for e in log_entries
            )

            # Check Step 2b: Agent checked calendar for Thursday conflicts
            thu_calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                and "2025-11-27" in e.action.args.get("start_datetime", "")
                for e in log_entries
            )

            # Check Step 3a: Agent added Wednesday jury duty to calendar
            wed_jury_duty_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-11-26" in e.action.args.get("start_datetime", "")
                and any(keyword in e.action.args.get("title", "").lower() for keyword in ["jury", "courthouse"])
                for e in log_entries
            )

            # Check Step 3b: Agent added Thursday jury duty to calendar
            thu_jury_duty_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-11-27" in e.action.args.get("start_datetime", "")
                and any(keyword in e.action.args.get("title", "").lower() for keyword in ["jury", "courthouse"])
                for e in log_entries
            )

            # Check Step 3c: Agent sent message to neighbor Margaret requesting pickup help
            neighbor_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "create_and_add_message"
                and any(keyword in e.action.args.get("content", "") for keyword in ["jury duty", "jury"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["pickup", "pick her up", "pick up"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["Margaret", "neighbor"])
                for e in log_entries
            )

            # Check Step 3d: Agent emailed teacher to reschedule conference
            teacher_email_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email_to_user_only"
                and any(keyword in e.action.args.get("content", "") for keyword in ["jury duty", "jury"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["reschedule", "rescheduling"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["conference", "meeting"])
                for e in log_entries
            )

            # Check Step 3e: Agent informed co-parent Jordan
            coparent_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "create_and_add_message"
                and e.action.args.get("conversation_id", "") == "conv_coparent_001"
                and any(keyword in e.action.args.get("content", "") for keyword in ["jury duty", "jury"])
                for e in log_entries
            )

            # Check Step 3f: Agent confirmed attendance with the court (strict check - must reply to specific email)
            court_confirmation_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "jury_summons_001"
                and any(keyword in e.action.args.get("content", "") for keyword in ["confirm", "attendance", "report"])
                for e in log_entries
            )

            # Overall success requires:
            # - Agent proposed comprehensive coordination plan (strict)
            # - Agent detected both Wednesday and Thursday conflicts (strict)
            # - Agent added jury duty to calendar for both days (strict)
            # - Agent coordinated with neighbor for pickup coverage (strict)
            # - Agent rescheduled teacher conference (strict)
            # - Agent informed co-parent (flexible - courtesy)
            # - Agent confirmed with court (strict - legal requirement)
            success = (
                proposal_found
                and wed_calendar_check_found
                and thu_calendar_check_found
                and wed_jury_duty_added
                and thu_jury_duty_added
                and neighbor_message_sent
                and teacher_email_sent
                and court_confirmation_sent
            )
            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
