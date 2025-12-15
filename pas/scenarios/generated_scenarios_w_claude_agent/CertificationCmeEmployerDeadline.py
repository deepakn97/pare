"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
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


@register_scenario("certification_cme_employer_deadline")
class CertificationCmeEmployerDeadline(PASScenario):
    """The user receives an email from their professional licensing board on March 1st warning that their nursing license expires April 30th and requires 24 continuing medical education (CME) credits for renewal, with documentation uploaded by April 15th to allow processing time. Their calendar shows they completed a 12-credit hospital training course in January (marked "CME - Emergency Protocols") and a 6-credit online seminar in February. The user's contacts contain their hospital HR director with notes stating the employer reimburses CME courses and requires staff to maintain active licenses as a condition of employment. A messaging thread with a colleague from last week discusses an upcoming 8-credit weekend workshop on April 8-9 that still has open registration, with the colleague saying "we should both sign up since it counts toward renewal".

    The proactive agent correlates the licensing board's deadline with the calendar entries showing the user has accumulated only 18 of the required 24 credits, leaving a 6-credit gap with just six weeks until the documentation deadline. It recognizes from the messaging thread that the colleague identified a workshop opportunity that would exceed the requirement (18 + 8 = 26 credits), but the agent must verify registration availability, coordinate with the employer for reimbursement approval before paying out-of-pocket, and ensure the workshop provider can issue completion certificates in time for the April 15th submission deadline. The agent understands that professional license expiration would jeopardize the user's employment based on HR policy notes, elevating this from a personal deadline to a career-critical obligation requiring immediate action.

    The agent proactively offers to send a message to the colleague confirming interest in the workshop and asking for the registration link, draft an email to the HR director requesting pre-approval for the workshop reimbursement with the licensing deadline as justification, compose a reply to the licensing board requesting confirmation that the workshop provider is an accredited CME source, create a calendar event for the April 8-9 workshop with a pre-deadline reminder to obtain the completion certificate, and prepare a summary document of completed CME activities for upload by April 15th. The user accepts this professional compliance coordination, recognizing the agent connected regulatory requirements, employer policies, peer collaboration opportunities, and documentation deadlines into a structured plan that ensures license renewal, maintains employment eligibility, and secures financial reimbursement for required professional development..
    """

    start_time = datetime(2025, 3, 1, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for professional certification renewal scenario."""
        # Initialize apps
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.contacts = StatefulContactsApp(name="Contacts")
        self.messaging = StatefulMessagingApp(name="Messages")
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Populate contacts
        # Hospital HR Director
        self.contacts.add_contact(
            Contact(
                first_name="Margaret",
                last_name="Thompson",
                contact_id="contact-hr-director",
                email="m.thompson@stmaryshospital.org",
                phone="555-123-4567",
                job="HR Director",
                description="Manages employee benefits and reimbursement. Hospital policy requires all nursing staff to maintain active licenses as a condition of employment. HR reimburses CME courses.",
            )
        )

        # Colleague from messaging thread
        self.contacts.add_contact(
            Contact(
                first_name="Sarah",
                last_name="Johnson",
                contact_id="contact-colleague-sarah",
                email="s.johnson@stmaryshospital.org",
                phone="555-234-5678",
                job="Registered Nurse",
                description="Colleague from emergency department, also needs CME credits for license renewal.",
            )
        )

        # Licensing Board contact
        self.contacts.add_contact(
            Contact(
                first_name="State",
                last_name="Nursing Board",
                contact_id="contact-nursing-board",
                email="renewals@statenursingboard.gov",
                phone="555-345-6789",
                description="State professional licensing authority for nursing credentials.",
            )
        )

        # Populate calendar with completed CME activities
        # 12-credit hospital training in January
        self.calendar.add_calendar_event(
            title="CME - Emergency Protocols",
            start_datetime="2025-01-15 08:00:00",
            end_datetime="2025-01-17 17:00:00",
            description="12-credit hospital training course on advanced emergency protocols. Completed.",
            tag="CME",
            location="St. Mary's Hospital Education Center",
        )

        # 6-credit online seminar in February
        self.calendar.add_calendar_event(
            title="CME - Patient Safety Seminar",
            start_datetime="2025-02-22 09:00:00",
            end_datetime="2025-02-22 15:00:00",
            description="6-credit online seminar on patient safety standards. Completed.",
            tag="CME",
            location="Online",
        )

        # Populate messaging with colleague conversation about workshop
        # Add colleague to messaging name/id mapping
        self.messaging.add_users(["Sarah Johnson"])
        sarah_id = self.messaging.get_user_id("Sarah Johnson")

        # Create conversation and add messages
        conversation = ConversationV2(
            participant_ids=[sarah_id, self.messaging.current_user_id],
            title="Sarah Johnson",
        )

        # Message 1: Sarah mentions the workshop (from last week)
        conversation.messages.append(
            MessageV2(
                sender_id=sarah_id,
                content="Hey! Did you see that Advanced Cardiac Care workshop coming up April 8-9? It's 8 credits and counts toward license renewal. Registration is still open!",
                timestamp=datetime(2025, 2, 22, 14, 30, 0, tzinfo=UTC).timestamp(),
            )
        )

        # Message 2: User responds with interest
        conversation.messages.append(
            MessageV2(
                sender_id=self.messaging.current_user_id,
                content="That sounds perfect! I need to check my schedule and see if I can get approval. How much is registration?",
                timestamp=datetime(2025, 2, 22, 15, 15, 0, tzinfo=UTC).timestamp(),
            )
        )

        # Message 3: Sarah provides more details
        conversation.messages.append(
            MessageV2(
                sender_id=sarah_id,
                content="It's $450 but HR should reimburse it. The workshop is at the Regional Medical Center. We should both sign up since it counts toward renewal and the deadline is coming up soon!",
                timestamp=datetime(2025, 2, 22, 16, 45, 0, tzinfo=UTC).timestamp(),
            )
        )

        conversation.last_updated = datetime(2025, 2, 22, 16, 45, 0, tzinfo=UTC).timestamp()
        self.messaging.add_conversation(conversation)

        # Register all apps
        self.apps = [
            self.email,
            self.calendar,
            self.contacts,
            self.messaging,
            self.agent_ui,
            self.system_app,
        ]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Licensing board email arrives warning about renewal deadline
            email_event = email_app.send_email_to_user_with_id(
                email_id="email-license-renewal-warning",
                sender="renewals@statenursingboard.gov",
                subject="URGENT: Nursing License Renewal Deadline - Action Required",
                content="Dear Healthcare Professional,\n\nThis is an important reminder that your nursing license (License #RN-458392) expires on April 30, 2025.\n\nRenewal Requirements:\n- 24 continuing medical education (CME) credits required\n- Documentation must be uploaded to the online portal by April 15, 2025 (to allow processing time)\n- Current license will expire if renewal is not completed by April 30, 2025\n\nPlease log into your account at www.statenursingboard.gov to:\n1. Upload proof of CME completion (certificates or transcripts)\n2. Complete the renewal application\n3. Pay the renewal fee ($150)\n\nFailure to renew will result in license expiration and inability to practice nursing in this state.\n\nFor questions about CME credit requirements or accredited providers, contact our office.\n\nState Board of Nursing\nLicensing Division",
            ).delayed(10)

            # Oracle Event 2: Agent detects the critical deadline and proposes comprehensive action plan
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed an urgent email from the State Nursing Board about your license renewal due April 30th. Based on your calendar, you've completed 18 of the required 24 CME credits (12 from Emergency Protocols in January + 6 from Patient Safety in February), leaving a 6-credit gap.\n\nI see Sarah mentioned an 8-credit Advanced Cardiac Care workshop on April 8-9 in your messages. This would exceed your requirement and the $450 cost should be reimbursable per your HR policy.\n\nWould you like me to:\n1. Message Sarah to confirm the workshop registration details\n2. Draft an email to Margaret Thompson (HR) requesting pre-approval for reimbursement\n3. Add the April 8-9 workshop to your calendar\n4. Prepare a summary of your completed CME credits for the April 15th documentation deadline\n\nThis is career-critical since your hospital requires active licenses for employment."
                )
                .oracle()
                .depends_on(email_event, delay_seconds=3)
            )

            # Oracle Event 3: User accepts the comprehensive coordination plan
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please coordinate all of that. I didn't realize I was cutting it so close on the deadline!"
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent searches calendar for CME-tagged events to verify credit count
            calendar_search_event = (
                calendar_app.get_calendar_events_by_tag(tag="CME")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent retrieves colleague contact for messaging
            sarah_lookup_event = (
                contacts_app.search_contacts(query="Sarah Johnson")
                .oracle()
                .depends_on(calendar_search_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent sends message to Sarah about workshop registration
            sarah_message_event = (
                messaging_app.send_message(
                    user_id="contact-colleague-sarah",
                    content="Hi Sarah! I'm definitely interested in that Advanced Cardiac Care workshop on April 8-9. Could you send me the registration link? I need to get this sorted out for my license renewal deadline. Thanks!",
                )
                .oracle()
                .depends_on(sarah_lookup_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent retrieves HR director contact for reimbursement request
            hr_lookup_event = (
                contacts_app.get_contact(contact_id="contact-hr-director")
                .oracle()
                .depends_on(sarah_message_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent drafts email to HR requesting workshop reimbursement pre-approval
            hr_email_event = (
                email_app.send_email(
                    recipients=["m.thompson@stmaryshospital.org"],
                    subject="Pre-Approval Request: CME Workshop for License Renewal",
                    content="Dear Margaret,\n\nI am requesting pre-approval for reimbursement of a continuing medical education workshop to fulfill my nursing license renewal requirements.\n\nWorkshop Details:\n- Title: Advanced Cardiac Care Workshop\n- Dates: April 8-9, 2025\n- Location: Regional Medical Center\n- Cost: $450\n- CME Credits: 8 credits\n\nRenewal Context:\nMy nursing license expires April 30, 2025, and requires 24 CME credits. I have completed 18 credits to date and need this 8-credit workshop to meet the requirement. Documentation must be submitted by April 15th.\n\nAs you know, hospital policy requires active licenses for employment, making timely renewal critical. This workshop is accredited and will ensure compliance with both state board and hospital requirements.\n\nPlease confirm pre-approval so I can register promptly.\n\nThank you,\n[User]",
                )
                .oracle()
                .depends_on(hr_lookup_event, delay_seconds=2)
            )

            # Oracle Event 9: Agent adds workshop to calendar with documentation reminder
            workshop_calendar_event = (
                calendar_app.add_calendar_event(
                    title="Advanced Cardiac Care Workshop (8 CME credits)",
                    start_datetime="2025-04-08 08:00:00",
                    end_datetime="2025-04-09 17:00:00",
                    description="8-credit CME workshop for license renewal. IMPORTANT: Obtain completion certificate immediately for April 15th documentation deadline.",
                    tag="CME",
                    location="Regional Medical Center",
                    attendees=["Sarah Johnson"],
                )
                .oracle()
                .depends_on(hr_email_event, delay_seconds=1)
            )

            # Oracle Event 10: Agent adds reminder event for documentation deadline
            deadline_reminder_event = (
                calendar_app.add_calendar_event(
                    title="DEADLINE: Upload CME Documentation to State Board",
                    start_datetime="2025-04-14 09:00:00",
                    end_datetime="2025-04-14 10:00:00",
                    description="Final day to upload all CME certificates to State Nursing Board portal before April 15th deadline. Need: Emergency Protocols cert (12 credits), Patient Safety cert (6 credits), Cardiac Care cert (8 credits). Total: 26 credits.",
                    tag="Deadline",
                    location="Online Portal",
                )
                .oracle()
                .depends_on(workshop_calendar_event, delay_seconds=1)
            )

            # Oracle Event 11: Agent confirms completion of all coordination tasks
            completion_event = (
                aui.send_message_to_user(
                    content="I've completed the license renewal coordination:\n\n✓ Messaged Sarah to confirm workshop registration details\n✓ Sent pre-approval request to Margaret Thompson (HR) for the $450 workshop\n✓ Added the April 8-9 workshop to your calendar (8 CME credits)\n✓ Created a reminder for April 14th to upload all documentation\n\nYour CME credit timeline:\n- Completed: 18 credits (Emergency Protocols: 12, Patient Safety: 6)\n- Pending: 8 credits (Cardiac Care workshop)\n- Total after workshop: 26 credits (exceeds the 24 required)\n\nNext steps: Wait for Sarah's registration link and HR pre-approval, then register for the workshop. You'll be compliant before the April 30th license expiration."
                )
                .oracle()
                .depends_on(deadline_reminder_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events: list[Event] = [
            email_event,
            proposal_event,
            acceptance_event,
            calendar_search_event,
            sarah_lookup_event,
            sarah_message_event,
            hr_lookup_event,
            hr_email_event,
            workshop_calendar_event,
            deadline_reminder_event,
            completion_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal mentioning the license renewal, credit gap, and comprehensive coordination plan
            proposal_found = any(
                e.event_type in [EventType.AGENT, EventType.ENV]
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "") for keyword in ["license", "renewal", "Nursing Board"]
                )
                and any(keyword in e.action.args.get("content", "") for keyword in ["18", "24", "6-credit", "gap"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["Sarah", "workshop"])
                for e in log_entries
            )

            # Check Step 2a: Agent detected CME credits by searching calendar for CME-tagged events
            calendar_search_found = any(
                e.event_type in [EventType.AGENT, EventType.ENV]
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name in ["get_calendar_events_by_tag", "get_calendar_events"]
                for e in log_entries
            )

            # Check Step 2b: Agent looked up colleague contact (Sarah Johnson) for messaging
            sarah_lookup_found = any(
                e.event_type in [EventType.AGENT, EventType.ENV]
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                and any(name in e.action.args.get("query", "") for name in ["Sarah", "Johnson"])
                for e in log_entries
            )

            # Check Step 2c: Agent retrieved HR director contact for reimbursement request
            hr_lookup_found = any(
                e.event_type in [EventType.AGENT, EventType.ENV]
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name in ["get_contact", "search_contacts"]
                and (
                    e.action.args.get("contact_id") == "contact-hr-director"
                    or any(name in e.action.args.get("query", "") for name in ["Margaret", "Thompson", "HR"])
                )
                for e in log_entries
            )

            # Check Step 3a: Agent sent message to Sarah about workshop registration (STRICT on recipient and workshop mention)
            sarah_message_found = any(
                e.event_type in [EventType.AGENT, EventType.ENV]
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == "contact-colleague-sarah"
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["workshop", "Advanced Cardiac", "April 8"]
                )
                for e in log_entries
            )

            # Check Step 3b: Agent sent email to HR requesting workshop reimbursement pre-approval (STRICT on recipient and key details)
            hr_email_found = any(
                e.event_type in [EventType.AGENT, EventType.ENV]
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "m.thompson@stmaryshospital.org" in e.action.args.get("recipients", [])
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["workshop", "reimbursement", "pre-approval"]
                )
                and any(keyword in e.action.args.get("content", "") for keyword in ["April", "license", "renewal"])
                for e in log_entries
            )

            # Check Step 3c: Agent added workshop to calendar (STRICT on dates and CME credit mention, FLEXIBLE on exact title)
            workshop_calendar_found = any(
                e.event_type in [EventType.AGENT, EventType.ENV]
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("start_datetime") == "2025-04-08 08:00:00"
                and e.action.args.get("end_datetime") == "2025-04-09 17:00:00"
                and any(keyword in e.action.args.get("title", "") for keyword in ["Cardiac", "workshop", "CME", "8"])
                for e in log_entries
            )

            # Check Step 3d: Agent created documentation deadline reminder (STRICT on date and purpose, FLEXIBLE on exact wording)
            deadline_reminder_found = any(
                e.event_type in [EventType.AGENT, EventType.ENV]
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-04-14" in e.action.args.get("start_datetime", "")
                and any(
                    keyword in e.action.args.get("title", "")
                    for keyword in ["CME", "documentation", "upload", "deadline"]
                )
                for e in log_entries
            )

            # Check Step 3e: Agent sent completion confirmation summarizing all actions (FLEXIBLE on exact formatting)
            completion_confirmation_found = any(
                e.event_type in [EventType.AGENT, EventType.ENV]
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(keyword in e.action.args.get("content", "") for keyword in ["completed", "coordination"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["18", "26", "credits"])
                for e in log_entries
            )

            # Determine success and construct rationale if failed
            success = (
                proposal_found
                and calendar_search_found
                and sarah_lookup_found
                and hr_lookup_found
                and sarah_message_found
                and hr_email_found
                and workshop_calendar_found
                and deadline_reminder_found
                and completion_confirmation_found
            )

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal mentioning license renewal and credit gap")
                if not calendar_search_found:
                    missing_checks.append("calendar search for CME events")
                if not sarah_lookup_found:
                    missing_checks.append("contact lookup for Sarah Johnson")
                if not hr_lookup_found:
                    missing_checks.append("contact lookup for HR director")
                if not sarah_message_found:
                    missing_checks.append("message to Sarah about workshop registration")
                if not hr_email_found:
                    missing_checks.append("email to HR requesting reimbursement pre-approval")
                if not workshop_calendar_found:
                    missing_checks.append("calendar event for April 8-9 workshop")
                if not deadline_reminder_found:
                    missing_checks.append("calendar reminder for April 14 documentation deadline")
                if not completion_confirmation_found:
                    missing_checks.append("completion confirmation with credit summary")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
