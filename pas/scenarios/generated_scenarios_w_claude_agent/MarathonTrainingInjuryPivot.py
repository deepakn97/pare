"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.email_client import Email
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


@register_scenario("marathon_training_injury_pivot")
class MarathonTrainingInjuryPivot(PASScenario):
    """The user receives an email confirmation for a half-marathon race scheduled five weeks away, including bib pickup details and a training plan attachment. Their calendar shows they've been blocking early morning running sessions three times per week leading up to the event. Two weeks before race day, the user sends a message to their running group explaining they twisted their ankle during a trail run and their physical therapist advised two weeks of no-impact activity. The contacts app contains their physical therapist with notes about approved cross-training activities, a cycling buddy who has mentioned group rides on weekends, and the race organizer's contact information with a note that registration is transferable to other runners.

    The proactive agent detects the injury disclosure in the messaging thread and correlates it with the upcoming race commitment visible in the email confirmation and calendar training blocks. It recognizes that the two-week recovery window leaves only three weeks before race day, which medical guidance suggests is insufficient for returning to peak running performance safely. The agent cross-references the physical therapist's contact notes about approved alternatives like cycling and swimming, then identifies the cycling buddy as a potential substitute training partner who could help maintain cardiovascular fitness during recovery.

    The agent proactively offers to draft a message to the running group explaining the situation and asking if anyone wants to take over the race registration, compose an email to the race organizer inquiring about the transfer process and deadlines, send a message to the cycling buddy asking about joining weekend rides during the recovery period, and replace the calendar's running blocks with low-impact cross-training sessions aligned with the physical therapist's guidelines. The user accepts the pivot strategy, appreciating that the agent understood the medical constraints, salvaged the training investment through alternative activities, and coordinated the race transfer to avoid wasting the registration fee..
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
        self.contacts = StatefulContactsApp(name="Contacts")
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.messaging = StatefulMessagingApp(name="Messages")

        # Populate contacts with key people
        # Physical therapist with approved cross-training activities
        pt_contact = Contact(
            first_name="Dr. Sarah",
            last_name="Mitchell",
            phone="555-0101",
            email="smitchell@ptrehab.com",
            job="Physical Therapist",
            description="PT at Sports Rehab Center. Approved cross-training: cycling, swimming, elliptical. No running for 2 weeks after ankle sprain.",
        )
        self.contacts.add_contact(pt_contact)

        # Cycling buddy for alternative training
        cycling_buddy = Contact(
            first_name="Marcus",
            last_name="Chen",
            phone="555-0102",
            email="mchen@email.com",
            description="Cycling enthusiast. Leads group rides on Saturday mornings at 7am and Sunday afternoons at 2pm. Mentioned rides are 20-30 miles, moderate pace.",
        )
        self.cycling_buddy_id = self.contacts.add_contact(cycling_buddy)

        # Race organizer for transfer logistics
        race_organizer = Contact(
            first_name="Jennifer",
            last_name="Patterson",
            phone="555-0103",
            email="jpatterson@bayrunrace.org",
            job="Race Director",
            description="Bay Area Half Marathon director. Registration is transferable to another runner until 1 week before race day. No refunds but transfers allowed.",
        )
        self.contacts.add_contact(race_organizer)

        # Running group members
        running_group_members = [
            Contact(
                first_name="Alex",
                last_name="Rodriguez",
                phone="555-0104",
                email="arodriguez@email.com",
            ),
            Contact(
                first_name="Emily",
                last_name="Wong",
                phone="555-0105",
                email="ewong@email.com",
            ),
        ]
        for member in running_group_members:
            self.contacts.add_contact(member)

        # Populate email with race confirmation received 5 weeks before race (3 weeks ago from start_time)
        # Race is scheduled for 5 weeks from when email was sent = 2 weeks from start_time
        race_date = datetime(2025, 12, 2, 8, 0, 0, tzinfo=UTC)
        email_received_time = datetime(2025, 10, 28, 14, 30, 0, tzinfo=UTC).timestamp()

        race_confirmation_email = Email(
            sender="registration@bayrunrace.org",
            recipients=[self.email.user_email],
            subject="Bay Area Half Marathon - Registration Confirmed",
            content="""Dear Runner,

Congratulations! Your registration for the Bay Area Half Marathon is confirmed.

Event Details:
- Date: Tuesday, December 2, 2025
- Time: 8:00 AM Start
- Location: Golden Gate Park, San Francisco
- Distance: 13.1 miles

Important Information:
- Bib Number: 2847
- Bib Pickup: December 1, 2025, 10am-6pm at race expo
- Parking: Available at Park Presidio lot, arrive early
- Registration Transfer: Allowed until November 25 (1 week before race). Contact us at jpatterson@bayrunrace.org

Attached is your 5-week training plan to help you prepare for race day.

Good luck with your training!

Bay Area Half Marathon Team
www.bayrunrace.org""",
            timestamp=email_received_time,
            is_read=True,
        )
        self.email.add_email(race_confirmation_email)

        # Populate calendar with running training blocks for the past 3 weeks and next 2 weeks
        # Start from 3 weeks before start_time (October 28) through 2 weeks after (December 2)
        # Training sessions: Mon/Wed/Fri at 6:00 AM, 1 hour duration
        base_date = datetime(2025, 10, 28, 6, 0, 0, tzinfo=UTC)
        training_days = [0, 2, 4]  # Monday, Wednesday, Friday

        # Generate training blocks for 5 weeks total
        for week in range(5):
            for day_offset in training_days:
                event_start = base_date + timedelta(days=week * 7 + day_offset)
                event_end = event_start + timedelta(hours=1)

                training_event = CalendarEvent(
                    title="Morning Run Training",
                    start_datetime=event_start.timestamp(),
                    end_datetime=event_end.timestamp(),
                    tag="fitness",
                    description="Half marathon training session - gradually building distance and endurance",
                    location="Golden Gate Park running trails",
                )
                self.calendar.add_event(training_event)

        # Populate messaging with running group conversation
        # Add users to messaging app
        alex_id = running_group_members[0].contact_id
        emily_id = running_group_members[1].contact_id
        self.messaging.add_users(["Alex Rodriguez", "Emily Wong"])
        self.messaging.name_to_id["Alex Rodriguez"] = alex_id
        self.messaging.name_to_id["Emily Wong"] = emily_id
        self.messaging.id_to_name[alex_id] = "Alex Rodriguez"
        self.messaging.id_to_name[emily_id] = "Emily Wong"

        # Create running group conversation with baseline history
        running_group_conversation = ConversationV2(
            participant_ids=[self.messaging.current_user_id, alex_id, emily_id],
            title="Bay Area Runners Group",
        )
        self.running_group_conv_id = running_group_conversation.conversation_id

        # Add earlier messages from 1 week ago discussing training progress
        earlier_time_1 = datetime(2025, 11, 11, 19, 30, 0, tzinfo=UTC).timestamp()
        running_group_conversation.messages.append(
            MessageV2(
                sender_id=alex_id,
                content="How's everyone's training going? I just finished my longest run yet - 10 miles!",
                timestamp=earlier_time_1,
            )
        )

        earlier_time_2 = datetime(2025, 11, 11, 19, 45, 0, tzinfo=UTC).timestamp()
        running_group_conversation.messages.append(
            MessageV2(
                sender_id=emily_id,
                content="Nice work Alex! I'm feeling good too. The race is in just 2 weeks, exciting!",
                timestamp=earlier_time_2,
            )
        )

        running_group_conversation.update_last_updated(earlier_time_2)
        self.messaging.add_conversation(running_group_conversation)

        # Register all apps
        self.apps = [
            self.agent_ui,
            self.system_app,
            self.contacts,
            self.email,
            self.calendar,
            self.messaging,
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
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: User sends injury disclosure message to running group
            injury_message_event = messaging_app.create_and_add_message(
                conversation_id=self.running_group_conv_id,
                sender_id=self.messaging.current_user_id,
                content="Bad news everyone - I twisted my ankle pretty badly on a trail run yesterday. Saw my PT this morning and she says no running for at least 2 weeks. Really bummed since the race is only 2 weeks away.",
            ).delayed(20)

            # Oracle Event 1: Agent detects injury and correlates with race commitment
            # Agent checks calendar for upcoming training sessions
            check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 00:00:00",
                    end_datetime="2025-12-02 23:59:59",
                )
                .oracle()
                .depends_on(injury_message_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent searches for PT contact to verify recovery guidance
            search_pt_event = (
                contacts_app.search_contacts(query="Physical Therapist")
                .oracle()
                .depends_on(check_calendar_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent proposes comprehensive pivot strategy
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your ankle injury message to the running group. With only 2 weeks until the Bay Area Half Marathon on December 2nd and your PT's 2-week no-running restriction, you won't have adequate training time to safely complete the race. I found several ways to help:\n\n1. Draft a message to your running group asking if anyone wants to take over your race registration (it's transferable until November 25)\n2. Email Jennifer Patterson at bayrunrace.org to initiate the transfer process\n3. Contact Marcus Chen about joining his weekend cycling group rides during recovery (your PT approved cycling)\n4. Update your calendar training blocks to low-impact cross-training activities\n\nWould you like me to proceed with this plan?"
                )
                .oracle()
                .depends_on(search_pt_event, delay_seconds=3)
            )

            # Oracle Event 4: User accepts the pivot strategy
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, that makes sense. Please go ahead with all of those actions - thanks for thinking this through."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent sends message to running group about race transfer
            running_group_message_event = (
                messaging_app.send_message(
                    user_id=self.running_group_conv_id,
                    content="Hey team, following up on my injury update - I've decided it's best not to rush back for the race. My registration is transferable to another runner until November 25th. If anyone is interested in taking my spot (bib #2847), let me know! Would hate for the registration to go to waste.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent emails race organizer about transfer process
            race_organizer_email_event = (
                email_app.send_email(
                    recipients=["jpatterson@bayrunrace.org"],
                    subject="Registration Transfer Request - Bay Area Half Marathon",
                    content="Hi Jennifer,\n\nI'm registered for the Bay Area Half Marathon on December 2nd (bib #2847) but unfortunately suffered an ankle injury that prevents me from participating. I understand the registration is transferable to another runner until November 25th.\n\nCould you please provide the process and any forms needed to transfer my registration? I'm coordinating with my running group to find someone who would like to take my spot.\n\nThank you,\n[User]",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent messages cycling buddy about joining rides
            cycling_buddy_message_event = (
                messaging_app.send_message(
                    user_id=self.cycling_buddy_id,
                    content="Hey Marcus! I twisted my ankle and can't run for a couple weeks, but my PT cleared me for cycling. I remember you mentioned leading group rides on weekends - would it be okay if I joined you? Looking to maintain cardio fitness during recovery.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent updates calendar - search for remaining training events to modify
            get_training_events = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-19 00:00:00",
                    end_datetime="2025-12-02 00:00:00",
                )
                .oracle()
                .depends_on(cycling_buddy_message_event, delay_seconds=2)
            )

            # Oracle Event 9: Agent sends confirmation summary to user
            summary_event = (
                aui.send_message_to_user(
                    content="I've completed all the actions:\n\n✓ Messaged your running group about the race transfer opportunity\n✓ Emailed Jennifer Patterson to start the transfer process\n✓ Contacted Marcus Chen about joining his cycling rides\n✓ Identified your upcoming training sessions for cross-training updates\n\nYou should hear back from the race organizer about next steps, and Marcus will likely respond about the cycling schedule. Focus on recovery - you're making the smart choice for long-term health!"
                )
                .oracle()
                .depends_on(get_training_events, delay_seconds=3)
            )

        # TODO: Register ALL events here in self.events
        self.events: list[Event] = [
            injury_message_event,
            check_calendar_event,
            search_pt_event,
            proposal_event,
            acceptance_event,
            running_group_message_event,
            race_organizer_email_event,
            cycling_buddy_message_event,
            get_training_events,
            summary_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user about injury and pivot strategy
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["injury", "ankle", "race"])
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["December 2", "registration", "transfer"]
                )
                and "Marcus" in e.action.args.get("content", "")
                and "Jennifer Patterson" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Check Step 2a: Agent checked calendar for training sessions (detection action)
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                and "2025-11-18" in e.action.args.get("start_datetime", "")
                and "2025-12-02" in e.action.args.get("end_datetime", "")
                for e in log_entries
            )

            # Check Step 2b: Agent searched for PT contact (detection action)
            pt_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                and "Physical Therapist" in e.action.args.get("query", "")
                for e in log_entries
            )

            # Check Step 3a: Agent sent message to running group about race transfer
            running_group_message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["transfer", "registration"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["2847", "bib", "November 25"])
                for e in log_entries
            )

            # Check Step 3b: Agent emailed race organizer about transfer process
            race_email_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "jpatterson@bayrunrace.org" in e.action.args.get("recipients", [])
                and any(keyword in e.action.args.get("subject", "").lower() for keyword in ["transfer", "registration"])
                and "2847" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Check Step 3c: Agent messaged cycling buddy about joining rides
            cycling_message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.cycling_buddy_id
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["cycling", "ride"])
                and any(
                    keyword in e.action.args.get("content", "").lower() for keyword in ["ankle", "injury", "recovery"]
                )
                for e in log_entries
            )

            # Check Step 3d: Agent queried training events for cross-training updates
            training_events_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                and "2025-11-19" in e.action.args.get("start_datetime", "")
                for e in log_entries
            )

            # Check Step 3e: Agent sent completion summary to user
            summary_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(keyword in e.action.args.get("content", "") for keyword in ["completed", "✓", "Messaged"])
                and "Jennifer Patterson" in e.action.args.get("content", "")
                and "Marcus" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Strict checks (required for success): proposal, calendar check, PT search, and race email
            strict_checks = proposal_found and calendar_check_found and pt_search_found and race_email_found

            # Flexible checks (nice-to-have): running group message, cycling message, training check, summary
            flexible_count = sum([
                running_group_message_found,
                cycling_message_found,
                training_events_check_found,
                summary_found,
            ])

            # Success requires all strict checks plus at least 3 out of 4 flexible checks
            success = strict_checks and flexible_count >= 3

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
