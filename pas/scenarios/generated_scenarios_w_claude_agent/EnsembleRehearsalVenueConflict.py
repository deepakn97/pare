"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
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


@register_scenario("ensemble_rehearsal_venue_conflict")
class EnsembleRehearsalVenueConflict(PASScenario):
    """The user directs a community chamber music ensemble preparing for a public concert in four weeks. They receive an email on Monday from their regular rehearsal venue (a church) stating that emergency roof repairs require building closure for the next three consecutive Thursdays, canceling the ensemble's reserved practice space during their critical final rehearsal period. The user's calendar shows Thursday evening rehearsals with twelve musician contacts listed as attendees, including a professional cellist who is only available on Thursdays due to their teaching schedule at a conservatory an hour away. A messaging thread reveals that the ensemble is learning a challenging contemporary piece requiring full group rehearsals, and the violist mentioned last week that several members still need the corrected second movement parts that the composer just sent as PDF attachments via email.

    The proactive agent correlates the venue cancellation with the calendar's blocked Thursday rehearsals and recognizes that finding alternate space accommodating twelve musicians with adequate acoustics, available parking, and piano access on short notice presents a severe logistical challenge. Cross-referencing contacts, the agent identifies a high school band director in the user's contact list whose notes mention "has access to school auditorium after hours" and a retired member who previously hosted chamber groups in their large living room for sectional rehearsals. The agent also detects the unreleased sheet music corrections in the email attachments that must be distributed to all performers before the next rehearsal to avoid wasting limited practice time on outdated parts.

    The agent proactively offers to message the band director and retired member simultaneously asking about emergency rehearsal space availability for three Thursdays with specific requirements (piano, music stands, twelve chairs), send a group message to all ensemble members explaining the venue crisis and asking if anyone else can host, forward the composer's corrected sheet music PDFs to all twelve musicians with a request they print parts before the next session, draft an email to the church asking if weekend access might be possible as a backup option, and create calendar alternatives for Saturday afternoon rehearsals if no Thursday solution emerges while noting the professional cellist's constraint. The user accepts this comprehensive coordination, recognizing the agent connected venue logistics, performer availability constraints, music preparation requirements, and time-critical concert preparation timelines into a multi-option contingency plan that preserves rehearsal continuity..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for ensemble rehearsal venue conflict scenario."""
        # Initialize required apps
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.contacts = StatefulContactsApp(name="Contacts")
        self.messaging = StatefulMessagingApp(name="Messages")

        # Populate contacts - Twelve ensemble musicians plus church contact and composer
        # Professional cellist with Thursday constraint
        self.contacts.add_contact(
            Contact(
                first_name="Michael",
                last_name="Chen",
                contact_id="contact-michael-chen",
                email="m.chen@conservatory.edu",
                phone="555-0101",
                job="Cello Faculty",
                description="Professional cellist, only available Thursdays due to conservatory teaching schedule",
            )
        )

        # High school band director with venue access
        self.contacts.add_contact(
            Contact(
                first_name="Lisa",
                last_name="Martinez",
                contact_id="contact-lisa-martinez",
                email="lmartinez@highschool.edu",
                phone="555-0102",
                job="High School Band Director",
                description="Has access to school auditorium after hours",
            )
        )

        # Retired member who has hosted before
        self.contacts.add_contact(
            Contact(
                first_name="Robert",
                last_name="Williams",
                contact_id="contact-robert-williams",
                email="robert.w@email.com",
                phone="555-0103",
                job="Retired Music Teacher",
                description="Previously hosted chamber groups in large living room for sectional rehearsals",
            )
        )

        # Violist who mentioned sheet music issue
        self.contacts.add_contact(
            Contact(
                first_name="Emma",
                last_name="Davis",
                contact_id="contact-emma-davis",
                email="emma.davis@email.com",
                phone="555-0104",
                job="Violist",
            )
        )

        # Other ensemble members
        self.contacts.add_contact(
            Contact(
                first_name="James",
                last_name="Anderson",
                contact_id="contact-james-anderson",
                email="j.anderson@email.com",
                phone="555-0105",
                job="Violinist",
            )
        )

        self.contacts.add_contact(
            Contact(
                first_name="Sarah",
                last_name="Thompson",
                contact_id="contact-sarah-thompson",
                email="sarah.t@email.com",
                phone="555-0106",
                job="Violinist",
            )
        )

        self.contacts.add_contact(
            Contact(
                first_name="David",
                last_name="Brown",
                contact_id="contact-david-brown",
                email="d.brown@email.com",
                phone="555-0107",
                job="Flutist",
            )
        )

        self.contacts.add_contact(
            Contact(
                first_name="Jennifer",
                last_name="Wilson",
                contact_id="contact-jennifer-wilson",
                email="jen.wilson@email.com",
                phone="555-0108",
                job="Clarinetist",
            )
        )

        self.contacts.add_contact(
            Contact(
                first_name="Thomas",
                last_name="Moore",
                contact_id="contact-thomas-moore",
                email="tom.moore@email.com",
                phone="555-0109",
                job="Pianist",
            )
        )

        self.contacts.add_contact(
            Contact(
                first_name="Rebecca",
                last_name="Taylor",
                contact_id="contact-rebecca-taylor",
                email="rebecca.t@email.com",
                phone="555-0110",
                job="Oboist",
            )
        )

        self.contacts.add_contact(
            Contact(
                first_name="Daniel",
                last_name="Garcia",
                contact_id="contact-daniel-garcia",
                email="dan.garcia@email.com",
                phone="555-0111",
                job="French Horn Player",
            )
        )

        self.contacts.add_contact(
            Contact(
                first_name="Amy",
                last_name="Lee",
                contact_id="contact-amy-lee",
                email="amy.lee@email.com",
                phone="555-0112",
                job="Bassoonist",
            )
        )

        # Church venue contact
        self.contacts.add_contact(
            Contact(
                first_name="Patricia",
                last_name="Johnson",
                contact_id="contact-patricia-johnson",
                email="facilities@stmarkschurch.org",
                phone="555-0200",
                job="Church Facilities Manager",
            )
        )

        # Composer contact
        self.contacts.add_contact(
            Contact(
                first_name="Alexandra",
                last_name="Petrova",
                contact_id="contact-alexandra-petrova",
                email="a.petrova@composer.com",
                phone="555-0300",
                job="Composer",
            )
        )

        # Populate calendar - Three Thursday evening rehearsals blocked
        # Concert is in four weeks (December 16, 2025), so rehearsals are Nov 21, 28, and Dec 5
        all_musicians = [
            "Michael Chen",
            "Lisa Martinez",
            "Robert Williams",
            "Emma Davis",
            "James Anderson",
            "Sarah Thompson",
            "David Brown",
            "Jennifer Wilson",
            "Thomas Moore",
            "Rebecca Taylor",
            "Daniel Garcia",
            "Amy Lee",
        ]

        self.calendar.add_calendar_event(
            title="Ensemble Rehearsal",
            start_datetime="2025-11-21 19:00:00",
            end_datetime="2025-11-21 21:30:00",
            location="St. Mark's Church Fellowship Hall",
            attendees=all_musicians,
            tag="rehearsal",
            description="Full ensemble rehearsal for December concert",
        )

        self.calendar.add_calendar_event(
            title="Ensemble Rehearsal",
            start_datetime="2025-11-28 19:00:00",
            end_datetime="2025-11-28 21:30:00",
            location="St. Mark's Church Fellowship Hall",
            attendees=all_musicians,
            tag="rehearsal",
            description="Full ensemble rehearsal for December concert",
        )

        self.calendar.add_calendar_event(
            title="Ensemble Rehearsal",
            start_datetime="2025-12-05 19:00:00",
            end_datetime="2025-12-05 21:30:00",
            location="St. Mark's Church Fellowship Hall",
            attendees=all_musicians,
            tag="rehearsal",
            description="Full ensemble rehearsal for December concert - final before concert",
        )

        # Concert event (four weeks out)
        self.calendar.add_calendar_event(
            title="Community Chamber Ensemble Concert",
            start_datetime="2025-12-16 19:30:00",
            end_datetime="2025-12-16 21:00:00",
            location="Downtown Recital Hall",
            attendees=all_musicians,
            tag="performance",
            description="Public concert performance",
        )

        # Populate messaging - Existing conversation with ensemble members about sheet music
        # Create messaging user IDs for ensemble members
        self.messaging.add_users([
            "Michael Chen",
            "Lisa Martinez",
            "Robert Williams",
            "Emma Davis",
            "James Anderson",
            "Sarah Thompson",
            "David Brown",
            "Jennifer Wilson",
            "Thomas Moore",
            "Rebecca Taylor",
            "Daniel Garcia",
            "Amy Lee",
        ])

        # Get user IDs for the group conversation
        emma_id = self.messaging.name_to_id["Emma Davis"]
        user_id = self.messaging.current_user_id

        # Create group conversation about the contemporary piece
        ensemble_group_conversation = ConversationV2(
            conversation_id="conv-ensemble-group",
            participant_ids=[user_id]
            + [
                self.messaging.name_to_id[name]
                for name in [
                    "Michael Chen",
                    "Lisa Martinez",
                    "Robert Williams",
                    "Emma Davis",
                    "James Anderson",
                    "Sarah Thompson",
                    "David Brown",
                    "Jennifer Wilson",
                    "Thomas Moore",
                    "Rebecca Taylor",
                    "Daniel Garcia",
                    "Amy Lee",
                ]
            ],
            title="Chamber Ensemble - Rehearsals",
            last_updated=datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp(),
        )

        # Add historical messages - violist mentioning sheet music corrections needed
        ensemble_group_conversation.messages.append(
            MessageV2(
                sender_id=user_id,
                content="Reminder: rehearsal this Thursday 7pm at St. Mark's Church. We'll focus on the contemporary piece second movement.",
                timestamp=datetime(2025, 11, 14, 10, 0, 0, tzinfo=UTC).timestamp(),
            )
        )

        ensemble_group_conversation.messages.append(
            MessageV2(
                sender_id=emma_id,
                content="Quick question - several of us still have the old second movement parts. Did the composer send the corrected version yet? Would be good to have those before Thursday's rehearsal.",
                timestamp=datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp(),
            )
        )

        self.messaging.add_conversation(ensemble_group_conversation)

        # Populate email - Baseline contains email from composer with sheet music corrections (arrived a few days ago)
        # The venue cancellation email will arrive as an environment event in build_events_flow
        self.email.send_email_to_user_only(
            sender="a.petrova@composer.com",
            subject="Corrected Parts - Second Movement",
            content="Dear Ensemble,\n\nAttached are the corrected parts for the second movement. I've fixed the articulation markings and clarified the tempo changes. Please distribute these to all performers and have them print the new parts before your next rehearsal.\n\nBest regards,\nAlexandra Petrova",
        )

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

        with EventRegisterer.capture_mode():
            # Environment Event 1: Church facilities manager sends venue cancellation email
            venue_cancel_email = email_app.send_email_to_user_with_id(
                email_id="email-venue-cancel",
                sender="facilities@stmarkschurch.org",
                subject="URGENT: St. Mark's Church Building Closure - Nov 21, 28, Dec 5",
                content="Dear Ensemble Director,\n\nI regret to inform you that St. Mark's Church will be closed for emergency roof repairs starting Thursday, November 21st, and continuing through the following two Thursday evenings (November 28th and December 5th). This includes all facilities, including the Fellowship Hall where your ensemble rehearses.\n\nWe apologize for the short notice and any inconvenience this causes. If you need assistance finding alternate space or have questions, please contact me.\n\nSincerely,\nPatricia Johnson\nFacilities Manager",
            ).delayed(30)

            # Oracle Event 1: Agent sends comprehensive proposal to user
            # Agent correlates venue cancellation with calendar rehearsals, identifies contacts with venue access,
            # notes sheet music distribution need, and professional cellist's Thursday constraint
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed the church venue for your ensemble rehearsals is unavailable for the next three critical Thursdays before your December 16th concert. I can help coordinate:\n\n1. Message Lisa Martinez (band director with school auditorium access) and Robert Williams (previously hosted sectionals) about emergency rehearsal space for 12 musicians with piano\n2. Send group message to all ensemble members explaining the crisis and asking for alternate venue options\n3. Distribute Alexandra Petrova's corrected second movement parts to all 12 musicians (addressing Emma's concern from the group chat)\n4. Draft email to the church asking about weekend rehearsal access as backup\n5. Note: Michael Chen (cellist) is only available Thursdays due to conservatory teaching\n\nShould I proceed with this coordination plan?"
                )
                .oracle()
                .depends_on(venue_cancel_email, delay_seconds=3)
            )

            # Oracle Event 2: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please proceed with all of those. The Thursday constraint for Michael is critical - we really need him for this piece."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent messages Lisa Martinez about auditorium availability
            lisa_id = messaging_app.name_to_id["Lisa Martinez"]
            message_lisa_event = (
                messaging_app.send_message(
                    user_id=lisa_id,
                    content="Hi Lisa, I'm coordinating emergency rehearsal space for our chamber ensemble. The church venue is unavailable for the next three Thursdays (Nov 21, 28, Dec 5, 7-9:30pm). Could your school auditorium accommodate 12 musicians with piano access for those evenings?",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent messages Robert Williams about home venue
            robert_id = messaging_app.name_to_id["Robert Williams"]
            message_robert_event = (
                messaging_app.send_message(
                    user_id=robert_id,
                    content="Hi Robert, our church rehearsal space is unavailable for the next three Thursdays. Could your home accommodate the full 12-person ensemble (as you've done for sectionals), or would you be available for one or two of those dates?",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent sends group message to all ensemble members
            ensemble_conv_id = "conv-ensemble-group"
            group_message_event = (
                messaging_app.create_and_add_message(
                    conversation_id=ensemble_conv_id,
                    sender_id=messaging_app.current_user_id,
                    content="URGENT: St. Mark's Church is closed for repairs the next three Thursday rehearsals (Nov 21, 28, Dec 5). I'm reaching out to Lisa and Robert about alternate venues. If anyone else can host 12 musicians with piano access for 2.5-hour rehearsals on any of those evenings, please let me know ASAP. Also, corrected second movement parts from Alexandra are being forwarded to everyone - please print before our next session.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent replies to composer's email, forwarding to all musicians
            # (Simulated as sending email notification about distribution)
            forward_parts_event = (
                email_app.reply_to_email(
                    email_id="email-venue-cancel",
                    folder_name="INBOX",
                    content="Thank you for the corrected parts. I'm forwarding these to all 12 ensemble members with a request to print before our next rehearsal (venue currently being rearranged due to church closure).",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent drafts email to church about weekend backup
            church_backup_email = (
                email_app.send_email(
                    recipients=["facilities@stmarkschurch.org"],
                    subject="Re: Building Closure - Weekend Rehearsal Possibility?",
                    content="Dear Patricia,\n\nThank you for letting us know about the Thursday closures. We're exploring alternate venues, but I wanted to ask: would Saturday afternoon access (2-4:30pm) be possible on Nov 23, 30, or Dec 7 as backup options if we cannot secure Thursday space? We need piano access for 12 musicians.\n\nThank you for any assistance you can provide during this challenging time.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=4)
            )

            # Oracle Event 8: Agent confirms completion to user
            completion_event = (
                aui.send_message_to_user(
                    content="Coordination complete:\n• Messaged Lisa (school auditorium) and Robert (home venue) about Thursday availability\n• Sent group message to all 12 ensemble members explaining the venue crisis and requesting alternate options\n• Forwarded Alexandra's corrected parts with print request\n• Drafted church email asking about Saturday backup slots (Nov 23, 30, Dec 7, 2-4:30pm)\n\nAll communications note the importance of maintaining Thursday rehearsals due to Michael Chen's conservatory schedule. Awaiting responses from potential venue hosts."
                )
                .oracle()
                .depends_on(
                    [
                        message_lisa_event,
                        message_robert_event,
                        group_message_event,
                        forward_parts_event,
                        church_backup_email,
                    ],
                    delay_seconds=2,
                )
            )

        # Register ALL events here in self.events
        self.events: list[Event] = [
            venue_cancel_email,
            proposal_event,
            acceptance_event,
            message_lisa_event,
            message_robert_event,
            group_message_event,
            forward_parts_event,
            church_backup_email,
            completion_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent comprehensive proposal mentioning venue crisis, musicians, and coordination plan
            # STRICT: Proposal must reference key elements (venue cancellation, Thursday rehearsals, musician contacts)
            # FLEXIBLE: Exact wording and order of items can vary
            proposal_found = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower() for keyword in ["venue", "church", "rehearsal"]
                )
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["thursday"])
                and any(name in e.action.args.get("content", "") for name in ["Lisa Martinez", "Robert Williams"])
                for e in log_entries
            )

            # Check Step 2: Agent messaged Lisa Martinez (band director) about auditorium availability
            # STRICT: Must message Lisa with request for rehearsal space on specific Thursdays
            # FLEXIBLE: Exact message wording can vary as long as it requests space
            lisa_messaged = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.messaging.name_to_id.get("Lisa Martinez")
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["rehearsal", "space", "auditorium"]
                )
                for e in log_entries
            )

            # Check Step 3: Agent messaged Robert Williams (retired member) about home venue
            # STRICT: Must message Robert with request for hosting ensemble
            # FLEXIBLE: Exact message wording can vary
            robert_messaged = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.messaging.name_to_id.get("Robert Williams")
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["rehearsal", "thursday", "ensemble"]
                )
                for e in log_entries
            )

            # Check Step 4: Agent sent group message to ensemble explaining venue crisis
            # STRICT: Must send message to ensemble group conversation mentioning venue closure
            # FLEXIBLE: Exact wording and formatting can vary
            group_message_sent = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "create_and_add_message"
                and e.action.args.get("conversation_id") == "conv-ensemble-group"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["church", "venue", "closed", "repair"]
                )
                for e in log_entries
            )

            # Check Step 5: Agent handled sheet music distribution (forwarded or replied to composer email)
            # STRICT: Must interact with email system to distribute corrected parts
            # FLEXIBLE: Can use reply_to_email or send_email, exact content wording flexible
            sheet_music_distributed = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["reply_to_email", "send_email"]
                and any(
                    keyword in str(e.action.args.get("content", "")).lower()
                    for keyword in ["parts", "corrected", "print", "movement"]
                )
                for e in log_entries
            )

            # Check Step 6: Agent drafted email to church about weekend backup options
            # STRICT: Must send email to church facilities manager asking about alternative access
            # FLEXIBLE: Exact days and wording can vary
            church_backup_email = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "facilities@stmarkschurch.org" in e.action.args.get("recipients", [])
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["saturday", "weekend", "backup", "alternative"]
                )
                for e in log_entries
            )

            # Check Step 7: Agent acknowledged Michael Chen's Thursday constraint
            # STRICT: Proposal or completion message must mention the cellist's Thursday-only availability
            # FLEXIBLE: Can appear in proposal or completion message, exact wording flexible
            thursday_constraint_noted = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(name in e.action.args.get("content", "") for name in ["Michael Chen", "Michael", "cellist"])
                and "thursday" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # All strict checks must pass for success
            # STRICT SUCCESS CRITERIA:
            # - Proposal references venue crisis and key contacts (proposal_found)
            # - Messages sent to both Lisa and Robert about venues (lisa_messaged, robert_messaged)
            # - Group message sent to ensemble (group_message_sent)
            # - Sheet music distribution handled (sheet_music_distributed)
            # - Church backup email sent (church_backup_email)
            # - Thursday constraint acknowledged (thursday_constraint_noted)

            success = (
                proposal_found
                and lisa_messaged
                and robert_messaged
                and group_message_sent
                and sheet_music_distributed
                and church_backup_email
                and thursday_constraint_noted
            )

            if not success:
                # Build rationale explaining which checks failed
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("no comprehensive proposal mentioning venue crisis and key contacts")
                if not lisa_messaged:
                    failed_checks.append("no message to Lisa Martinez about auditorium availability")
                if not robert_messaged:
                    failed_checks.append("no message to Robert Williams about home venue")
                if not group_message_sent:
                    failed_checks.append("no group message to ensemble about venue closure")
                if not sheet_music_distributed:
                    failed_checks.append("no email action to distribute corrected sheet music parts")
                if not church_backup_email:
                    failed_checks.append("no email to church about weekend backup options")
                if not thursday_constraint_noted:
                    failed_checks.append("no mention of Michael Chen's Thursday-only constraint")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
