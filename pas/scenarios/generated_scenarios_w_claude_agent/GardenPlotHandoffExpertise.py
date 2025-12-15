"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
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


@register_scenario("garden_plot_handoff_expertise")
class GardenPlotHandoffExpertise(PASScenario):
    """The user directs a community chamber music ensemble preparing for a public concert in four weeks. They receive an email on Monday from their regular rehearsal venue (a church) stating that emergency roof repairs require building closure for the next three consecutive Thursdays, canceling the ensemble's reserved practice space during their critical final rehearsal period. The user's calendar shows Thursday evening rehearsals with twelve musician contacts listed as attendees, including a professional cellist who is only available on Thursdays due to their teaching schedule at a conservatory an hour away. A messaging thread reveals that the ensemble is learning a challenging contemporary piece requiring full group rehearsals, and the violist mentioned last week that several members still need the corrected second movement parts that the composer just sent as PDF attachments via email.

    The proactive agent correlates the venue cancellation with the calendar's blocked Thursday rehearsals and recognizes that finding alternate space accommodating twelve musicians with adequate acoustics, available parking, and piano access on short notice presents a severe logistical challenge. Cross-referencing contacts, the agent identifies a high school band director in the user's contact list whose notes mention "has access to school auditorium after hours" and a retired member who previously hosted chamber groups in their large living room for sectional rehearsals. The agent also detects the unreleased sheet music corrections in the email attachments that must be distributed to all performers before the next rehearsal to avoid wasting limited practice time on outdated parts.

    The agent proactively offers to message the band director and retired member simultaneously asking about emergency rehearsal space availability for three Thursdays with specific requirements (piano, music stands, twelve chairs), send a group message to all ensemble members explaining the venue crisis and asking if anyone else can host, forward the composer's corrected sheet music PDFs to all twelve musicians with a request they print parts before the next session, draft an email to the church asking if weekend access might be possible as a backup option, and create calendar alternatives for Saturday afternoon rehearsals if no Thursday solution emerges while noting the professional cellist's constraint. The user accepts this comprehensive coordination, recognizing the agent connected venue logistics, performer availability constraints, music preparation requirements, and time-critical concert preparation timelines into a multi-option contingency plan that preserves rehearsal continuity.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data for chamber music ensemble scenario."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario-specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.contacts = StatefulContactsApp(name="Contacts")
        self.messaging = StatefulMessagingApp(name="Messages")

        # Populate contacts - all twelve ensemble members plus venue coordinator and composer
        # Professional cellist (Thursday-only constraint)
        cellist_id = self.contacts.add_contact(
            Contact(
                first_name="Elena",
                last_name="Martinez",
                email="elena.martinez@conservatory.edu",
                phone="555-0101",
                job="Cellist",
                description="Professional cellist, teaches at conservatory one hour away, only available Thursdays",
            )
        )

        # High school band director (has auditorium access)
        director_id = self.contacts.add_contact(
            Contact(
                first_name="Marcus",
                last_name="Chen",
                email="mchen@highschool.edu",
                phone="555-0102",
                job="Band Director",
                description="High school band director, has access to school auditorium after hours",
            )
        )

        # Retired member (hosts sectionals)
        retired_id = self.contacts.add_contact(
            Contact(
                first_name="Dorothy",
                last_name="Williams",
                email="dorothy.williams@email.com",
                phone="555-0103",
                description="Retired violinist, previously hosted chamber groups in large living room for sectional rehearsals",
            )
        )

        # Violist (mentioned needing corrected parts)
        violist_id = self.contacts.add_contact(
            Contact(
                first_name="James",
                last_name="Thompson",
                email="james.thompson@email.com",
                phone="555-0104",
                job="Violist",
            )
        )

        # Other ensemble members
        member_ids = []
        members_data = [
            ("Sarah", "Johnson", "sarah.j@email.com", "555-0105", "Violinist"),
            ("Michael", "Brown", "mbrown@email.com", "555-0106", "Violinist"),
            ("Lisa", "Davis", "lisa.davis@email.com", "555-0107", "Violinist"),
            ("Robert", "Miller", "rmiller@email.com", "555-0108", "Cellist"),
            ("Amanda", "Garcia", "agarcia@email.com", "555-0109", "Flutist"),
            ("David", "Wilson", "dwilson@email.com", "555-0110", "Clarinetist"),
            ("Jennifer", "Moore", "jmoore@email.com", "555-0111", "Oboist"),
            ("Christopher", "Taylor", "ctaylor@email.com", "555-0112", "Pianist"),
        ]

        for first, last, email, phone, job in members_data:
            member_id = self.contacts.add_contact(
                Contact(
                    first_name=first,
                    last_name=last,
                    email=email,
                    phone=phone,
                    job=job,
                )
            )
            member_ids.append(member_id)

        # Church venue coordinator
        venue_id = self.contacts.add_contact(
            Contact(
                first_name="Father",
                last_name="O'Brien",
                email="obrien@saintmarys-church.org",
                phone="555-0113",
                job="Venue Coordinator",
                description="St. Mary's Church venue coordinator",
            )
        )

        # Composer
        composer_id = self.contacts.add_contact(
            Contact(
                first_name="Dr. Alexandra",
                last_name="Novak",
                email="anovak@composersguild.org",
                phone="555-0114",
                job="Composer",
            )
        )

        # Populate calendar with three Thursday evening rehearsals (next three weeks)
        all_attendees = [
            "Elena Martinez",
            "Marcus Chen",
            "Dorothy Williams",
            "James Thompson",
            "Sarah Johnson",
            "Michael Brown",
            "Lisa Davis",
            "Robert Miller",
            "Amanda Garcia",
            "David Wilson",
            "Jennifer Moore",
            "Christopher Taylor",
        ]

        # Thursday Nov 21, 2025 - 7:00 PM to 9:00 PM
        self.calendar.add_calendar_event(
            title="Chamber Ensemble Rehearsal",
            start_datetime="2025-11-21 19:00:00",
            end_datetime="2025-11-21 21:00:00",
            location="St. Mary's Church Hall",
            attendees=all_attendees,
            description="Full ensemble rehearsal for upcoming concert",
        )

        # Thursday Nov 28, 2025 - 7:00 PM to 9:00 PM
        self.calendar.add_calendar_event(
            title="Chamber Ensemble Rehearsal",
            start_datetime="2025-11-28 19:00:00",
            end_datetime="2025-11-28 21:00:00",
            location="St. Mary's Church Hall",
            attendees=all_attendees,
            description="Full ensemble rehearsal for upcoming concert",
        )

        # Thursday Dec 5, 2025 - 7:00 PM to 9:00 PM
        self.calendar.add_calendar_event(
            title="Chamber Ensemble Rehearsal",
            start_datetime="2025-12-05 19:00:00",
            end_datetime="2025-12-05 21:00:00",
            location="St. Mary's Church Hall",
            attendees=all_attendees,
            description="Final full ensemble rehearsal before concert",
        )

        # Concert date (four weeks from start)
        self.calendar.add_calendar_event(
            title="Chamber Ensemble Concert",
            start_datetime="2025-12-16 19:30:00",
            end_datetime="2025-12-16 21:30:00",
            location="Community Arts Center",
            attendees=all_attendees,
            description="Public concert performance",
        )

        # Populate messaging with ensemble group conversation
        # Add messaging contacts
        self.messaging.add_contacts([
            ("James Thompson", "555-0104"),
            ("Sarah Johnson", "555-0105"),
            ("Michael Brown", "555-0106"),
        ])

        # Create group conversation with violist mentioning need for corrected parts
        ensemble_group_id = self.messaging.create_group_conversation(
            user_ids=["555-0104", "555-0105", "555-0106"], title="Chamber Ensemble Group"
        )

        # Add baseline messages showing discussion about challenging piece and corrected parts
        message_time_1 = datetime(2025, 11, 12, 14, 30, 0, tzinfo=UTC).timestamp()
        self.messaging.add_message(
            conversation_id=ensemble_group_id,
            sender_id="555-0105",
            content="This contemporary piece is really challenging! The rhythms in the second movement are tricky.",
            timestamp=message_time_1,
        )

        message_time_2 = datetime(2025, 11, 13, 19, 15, 0, tzinfo=UTC).timestamp()
        self.messaging.add_message(
            conversation_id=ensemble_group_id,
            sender_id="555-0104",
            content="I heard the composer just sent corrected second movement parts. Several members still need those - the old parts have wrong articulations.",
            timestamp=message_time_2,
        )

        message_time_3 = datetime(2025, 11, 14, 10, 0, 0, tzinfo=UTC).timestamp()
        self.messaging.add_message(
            conversation_id=ensemble_group_id,
            sender_id="555-0106",
            content="Yes, we definitely need those corrections before next rehearsal!",
            timestamp=message_time_3,
        )

        # Email app starts with only old composer email (corrected parts email arrives as event)
        # No baseline emails needed - the critical venue cancellation and composer correction emails arrive during events flow

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar, self.contacts, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Email from composer with corrected sheet music PDFs arrives
            composer_email_id = "email-composer-corrected-parts"
            composer_email = email_app.send_email_to_user_with_id(
                email_id=composer_email_id,
                sender="anovak@composersguild.org",
                subject="Corrected Second Movement Parts - Contemporary Piece",
                content="Hello! I've corrected the articulation errors in the second movement. Please find the updated parts attached as PDFs. It's essential everyone has these before your next rehearsal to avoid confusion. Best, Alexandra",
            ).delayed(30)

            # Environment Event 2: Email from church venue coordinator about emergency closure
            venue_email_id = "email-venue-cancellation"
            venue_email = email_app.send_email_to_user_with_id(
                email_id=venue_email_id,
                sender="obrien@saintmarys-church.org",
                subject="URGENT: Rehearsal Space Unavailable - Emergency Roof Repairs",
                content="I'm writing to inform you that emergency roof repairs require St. Mary's Church to close for the next three consecutive Thursdays (Nov 21, 28, and Dec 5). Unfortunately, this means your scheduled evening rehearsals must be canceled. We apologize for the short notice and the inconvenience. Please let me know if you have questions. - Father O'Brien",
            ).delayed(45)

            # Oracle Event 1: Agent detects venue crisis and proposes comprehensive coordination plan
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your rehearsal venue (St. Mary's Church) is closed for all three remaining Thursday rehearsals due to emergency repairs. This is critical since your concert is in four weeks and Elena Martinez (cellist) is only available Thursdays. I can help by:\n\n1. Messaging Marcus Chen (band director with auditorium access) and Dorothy Williams (hosted sectionals before) about emergency space for three Thursdays\n2. Sending a group message to all ensemble members asking if anyone else can host\n3. Forwarding the composer's corrected sheet music PDFs to all twelve musicians\n4. Drafting an email to the church asking about weekend backup options\n5. Creating Saturday afternoon calendar alternatives if needed\n\nWould you like me to proceed with this coordination?"
                )
                .oracle()
                .depends_on(venue_email, delay_seconds=5)
            )

            # Oracle Event 2: User accepts the comprehensive coordination proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please do all of that. We need to solve this quickly.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 3: Agent sends message to band director about auditorium access
            message_director = (
                messaging_app.send_message(
                    user_id="555-0102",
                    content="Hi Marcus, our rehearsal venue has emergency closure for the next three Thursdays (Nov 21, 28, Dec 5). Could we use your school auditorium 7-9 PM those evenings? We need piano, 12 chairs, and music stands for our concert prep. Thanks!",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends message to retired member about hosting
            message_retired = (
                messaging_app.send_message(
                    user_id="555-0103",
                    content="Hi Dorothy, our church venue is closed for three Thursdays due to roof repairs (Nov 21, 28, Dec 5). Would you be able to host full ensemble rehearsals 7-9 PM like you've done for sectionals? We're 12 musicians with a piano requirement. Let me know!",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent sends group message to ensemble about venue crisis
            ensemble_group_id = "555-0104"  # Violist's phone, representing the group conversation
            group_message = (
                messaging_app.send_message(
                    user_id=ensemble_group_id,
                    content="URGENT: St. Mary's Church is closed for emergency repairs the next three Thursdays (Nov 21, 28, Dec 5). We're working on alternate venues. Can anyone host 12 musicians with a piano for evening rehearsals? Please reply ASAP!",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent drafts email to church asking about weekend backup
            church_email_reply = (
                email_app.send_email(
                    recipients=["obrien@saintmarys-church.org"],
                    subject="Re: Rehearsal Space - Weekend Availability?",
                    content="Father O'Brien, thank you for notifying us about the Thursday closures. Would the church hall be available on Saturday afternoons (2-4 PM) as a backup option for any of those three weekends? This would help us maintain our rehearsal schedule. Best regards",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=3)
            )

            # Oracle Event 7: Agent forwards composer's corrected sheet music to all musicians
            # Using a representative action - in practice would send to all 12 musicians
            forward_music = (
                email_app.send_email(
                    recipients=[
                        "elena.martinez@conservatory.edu",
                        "mchen@highschool.edu",
                        "dorothy.williams@email.com",
                        "james.thompson@email.com",
                        "sarah.j@email.com",
                        "mbrown@email.com",
                        "lisa.davis@email.com",
                        "rmiller@email.com",
                        "agarcia@email.com",
                        "dwilson@email.com",
                        "jmoore@email.com",
                        "ctaylor@email.com",
                    ],
                    subject="URGENT: Corrected Second Movement Parts - Print Before Next Rehearsal",
                    content="Everyone, the composer sent corrected second movement parts (attached). Please print these before our next rehearsal - the old parts have wrong articulations. Essential we all have the same version!",
                )
                .oracle()
                .depends_on(composer_email, delay_seconds=4)
            )

            # Oracle Event 8: Agent creates Saturday afternoon calendar alternatives for all three weeks
            alt_calendar_1 = (
                calendar_app.add_calendar_event(
                    title="[BACKUP] Chamber Ensemble Rehearsal - Saturday Option",
                    start_datetime="2025-11-23 14:00:00",
                    end_datetime="2025-11-23 16:00:00",
                    location="TBD - pending venue confirmation",
                    attendees=[
                        "Elena Martinez",
                        "Marcus Chen",
                        "Dorothy Williams",
                        "James Thompson",
                        "Sarah Johnson",
                        "Michael Brown",
                        "Lisa Davis",
                        "Robert Miller",
                        "Amanda Garcia",
                        "David Wilson",
                        "Jennifer Moore",
                        "Christopher Taylor",
                    ],
                    description="Backup rehearsal option if Thursday venues fall through. NOTE: Elena (cellist) may not be available - Thursday strongly preferred.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=5)
            )

            alt_calendar_2 = (
                calendar_app.add_calendar_event(
                    title="[BACKUP] Chamber Ensemble Rehearsal - Saturday Option",
                    start_datetime="2025-11-30 14:00:00",
                    end_datetime="2025-11-30 16:00:00",
                    location="TBD - pending venue confirmation",
                    attendees=[
                        "Elena Martinez",
                        "Marcus Chen",
                        "Dorothy Williams",
                        "James Thompson",
                        "Sarah Johnson",
                        "Michael Brown",
                        "Lisa Davis",
                        "Robert Miller",
                        "Amanda Garcia",
                        "David Wilson",
                        "Jennifer Moore",
                        "Christopher Taylor",
                    ],
                    description="Backup rehearsal option if Thursday venues fall through. NOTE: Elena (cellist) may not be available - Thursday strongly preferred.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=5)
            )

            alt_calendar_3 = (
                calendar_app.add_calendar_event(
                    title="[BACKUP] Chamber Ensemble Rehearsal - Saturday Option",
                    start_datetime="2025-12-07 14:00:00",
                    end_datetime="2025-12-07 16:00:00",
                    location="TBD - pending venue confirmation",
                    attendees=[
                        "Elena Martinez",
                        "Marcus Chen",
                        "Dorothy Williams",
                        "James Thompson",
                        "Sarah Johnson",
                        "Michael Brown",
                        "Lisa Davis",
                        "Robert Miller",
                        "Amanda Garcia",
                        "David Wilson",
                        "Jennifer Moore",
                        "Christopher Taylor",
                    ],
                    description="Backup rehearsal option if Thursday venues fall through. NOTE: Elena (cellist) may not be available - Thursday strongly preferred.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=5)
            )

            # Oracle Event 9: Agent sends confirmation summary to user
            confirmation = (
                aui.send_message_to_user(
                    content="I've completed the coordination:\n• Messaged Marcus (school auditorium) and Dorothy (previous host) about emergency space\n• Sent group message asking if other members can host\n• Forwarded corrected sheet music to all 12 musicians with print reminder\n• Emailed church about Saturday backup availability\n• Added Saturday backup rehearsals to calendar (noting Elena's Thursday-only constraint)\n\nYou should hear back from venue options soon. The corrected parts are now distributed to prevent rehearsal time waste."
                )
                .oracle()
                .depends_on(forward_music, delay_seconds=3)
            )

        # Register ALL events
        self.events: list[Event] = [
            composer_email,
            venue_email,
            proposal_event,
            acceptance_event,
            message_director,
            message_retired,
            group_message,
            church_email_reply,
            forward_music,
            alt_calendar_1,
            alt_calendar_2,
            alt_calendar_3,
            confirmation,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning venue crisis and comprehensive coordination plan
            # Must reference the venue cancellation, Thursday conflicts, and multiple coordination actions
            proposal_found = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["venue", "church", "closed", "closure", "cancel"]
                )
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["thursday"])
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["elena", "cellist"])
                for e in log_entries
            )

            # STRICT Check 2: Agent sent messages to band director about auditorium access
            # Must reference the band director and emergency space request
            message_director_found = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == "555-0102"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["auditorium", "school", "venue", "rehearsal", "space"]
                )
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["thursday", "nov 21", "nov 28", "dec 5"]
                )
                for e in log_entries
            )

            # STRICT Check 3: Agent sent messages to retired member about hosting
            # Must reference Dorothy and hosting request
            message_retired_found = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == "555-0103"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["host", "rehearsal", "ensemble", "venue", "space"]
                )
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["thursday", "nov 21", "nov 28", "dec 5"]
                )
                for e in log_entries
            )

            # STRICT Check 4: Agent sent group message to ensemble about venue crisis
            # Must ask if anyone can host and mention the emergency
            group_message_found = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["venue", "church", "closed", "closure", "urgent", "emergency"]
                )
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["thursday", "nov 21", "nov 28", "dec 5"]
                )
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["host", "space"])
                for e in log_entries
            )

            # STRICT Check 5: Agent forwarded corrected sheet music to all musicians
            # Must send email to all 12 musicians with corrected parts and print instructions
            forward_music_found = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and len(e.action.args.get("recipients", [])) >= 10  # Should include most/all 12 musicians
                and any(
                    keyword in e.action.args.get("subject", "").lower() + e.action.args.get("content", "").lower()
                    for keyword in ["corrected", "second movement", "parts", "sheet music"]
                )
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["print", "rehearsal"])
                for e in log_entries
            )

            # STRICT Check 6: Agent drafted email to church about weekend backup
            # Must ask about Saturday availability
            church_email_found = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "obrien@saintmarys-church.org" in e.action.args.get("recipients", [])
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["saturday", "weekend", "backup", "alternative"]
                )
                for e in log_entries
            )

            # STRICT Check 7: Agent created Saturday backup rehearsals in calendar
            # Must create at least 2-3 Saturday alternatives noting cellist constraint
            saturday_rehearsals_created = [
                e
                for e in log_entries
                if (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and any(keyword in e.action.args.get("start_datetime", "") for keyword in ["11-23", "11-30", "12-07"])
                and "14:00:00" in e.action.args.get("start_datetime", "")  # Saturday afternoon
                and any(
                    keyword in e.action.args.get("description", "").lower()
                    for keyword in ["elena", "cellist", "thursday", "backup"]
                )
            ]
            calendar_backups_created = len(saturday_rehearsals_created) >= 2

            # FLEXIBLE: Allow some variation in exact wording but require core logic
            # Core logic required:
            # 1. Agent must recognize venue crisis affects all three Thursday rehearsals
            # 2. Agent must coordinate with multiple potential venue hosts (director + retired member)
            # 3. Agent must distribute corrected sheet music to prevent rehearsal waste
            # 4. Agent must create contingency plans (Saturday alternatives + church weekend query)
            # 5. Agent must note the professional cellist's Thursday-only constraint

            # Calculate success
            success = (
                proposal_found
                and message_director_found
                and message_retired_found
                and group_message_found
                and forward_music_found
                and church_email_found
                and calendar_backups_created
            )

            # Build rationale if validation fails
            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent proposal mentioning venue crisis and coordination plan not found")
                if not message_director_found:
                    failed_checks.append("message to band director about auditorium access not found")
                if not message_retired_found:
                    failed_checks.append("message to retired member about hosting not found")
                if not group_message_found:
                    failed_checks.append("group message to ensemble about venue crisis not found")
                if not forward_music_found:
                    failed_checks.append("forwarded corrected sheet music email to all musicians not found")
                if not church_email_found:
                    failed_checks.append("email to church about weekend backup availability not found")
                if not calendar_backups_created:
                    failed_checks.append(
                        "Saturday backup rehearsal calendar events not created with cellist constraint note"
                    )

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
