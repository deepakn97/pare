from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulApartmentApp,
    StatefulEmailApp,
)
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("sublet_inquiry_response_triage")
class SubletInquiryResponseTriage(PAREScenario):
    """Agent responds to multiple apartment sublet inquiries by extracting listing details and personalizing replies. The user has listed their downtown 1-bedroom apartment for sublet on a housing platform and receives three inquiry emails within an hour from prospective subletters. Jessica Martinez asks about the pet policy and available move-in dates. Ryan Thompson requests details about parking and in-unit laundry. Sarah Kim asks about lease flexibility and expresses urgent need due to a job relocation. The agent must: 1. Identify which saved apartment in the user's apartment app matches the sublet listing being discussed (based on location and features mentioned in inquiries). 2. Extract relevant apartment attributes from the apartment app to answer each inquiry's specific questions. 3. Compose three personalized email replies addressing each prospective subletter's questions with accurate details from the listing. 4. Flag Sarah's inquiry as high-priority due to urgency and strong interest signals, suggesting the user schedule a showing with her first. 5. Confirm all three replies were sent with correct information matching the actual apartment listing.

    This scenario exercises reverse apartment workflow where the user is the lister rather than the searcher, one-to-many email triage and personalization, cross-app data extraction to populate outbound communications (apartment app → email content rather than email → apartment search), interest qualification based on inquiry content and urgency signals, and prioritization recommendations for follow-up actions when handling multiple inbound requests simultaneously..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data.

        The user has listed their downtown 1-bedroom apartment for sublet. The apartment
        listing exists in the apartment app as a saved listing. No emails exist at start_time;
        all inquiry emails will arrive as environment events in build_events_flow().
        """
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Add the user's apartment that they are subletting
        # This apartment will be referenced when responding to inquiries
        self.sublet_apartment_id = self.apartment.add_new_apartment(
            name="Downtown Loft Sublet",
            location="Downtown",
            zip_code="90210",
            price=2200.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=750,
            property_type="Apartment",
            furnished_status="Furnished",
            floor_level="3rd Floor",
            pet_policy="No pets allowed",
            lease_term="6-month sublet (Dec 2025 - May 2026)",
            amenities=["In-unit laundry", "Parking included", "Gym access", "Central AC"],
        )

        # Mark this apartment as saved (indicates user's own listing)
        self.apartment.save_apartment(apartment_id=self.sublet_apartment_id)

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment event 1: First inquiry from Jessica Martinez about pet policy and move-in dates
            email1_event = email_app.send_email_to_user_with_id(
                email_id="email-jessica-inquiry",
                sender="jessica.martinez@email.com",
                subject="Inquiry about your Downtown Loft Sublet",
                content="Hi! I'm interested in your downtown apartment listing. I have a few questions:\n\n1. What is your pet policy? I have a small cat.\n2. What are the available move-in dates?\n\nLooking forward to hearing from you!\n\nBest,\nJessica Martinez",
            ).delayed(30)

            # Environment event 2: Second inquiry from Ryan Thompson about parking and laundry
            email2_event = email_app.send_email_to_user_with_id(
                email_id="email-ryan-inquiry",
                sender="ryan.thompson@email.com",
                subject="Questions about Downtown apartment",
                content="Hello,\n\nI saw your sublet listing and have some questions:\n\n- Is parking included?\n- Is there in-unit laundry or shared laundry facilities?\n\nThanks,\nRyan Thompson",
            ).delayed(15)

            # Environment event 3: Third inquiry from Sarah Kim expressing urgency
            email3_event = email_app.send_email_to_user_with_id(
                email_id="email-sarah-inquiry",
                sender="sarah.kim@email.com",
                subject="URGENT: Need apartment for job relocation",
                content="Hi there,\n\nI'm relocating to the area for a new job starting in early December and urgently need housing. Your downtown listing looks perfect!\n\nCan you tell me:\n1. Is there any flexibility on the lease dates?\n2. When is the earliest I could move in?\n\nI'm very interested and can move quickly on this. Would it be possible to schedule a showing this week?\n\nThank you!\nSarah Kim",
            ).delayed(10)

            # Oracle event 1: Agent lists saved apartments to find the user's sublet listing
            list_saved_event = apartment_app.list_saved_apartments().oracle().depends_on(email3_event, delay_seconds=3)

            # Oracle event 2: Agent gets apartment details to extract information for replies
            get_details_event = (
                apartment_app.get_apartment_details(apartment_id=self.sublet_apartment_id)
                .oracle()
                .depends_on(list_saved_event, delay_seconds=2)
            )

            # Oracle event 3: Agent lists emails to review all inquiries
            list_emails_event = (
                email_app.list_emails(folder_name="INBOX", offset=0, limit=10)
                .oracle()
                .depends_on(get_details_event, delay_seconds=2)
            )

            # Oracle event 4: Agent sends proposal to user
            proposal_event = (
                aui.send_message_to_user(
                    content="You've received three inquiries about your Downtown Loft Sublet. I can help respond to each with accurate details from your listing:\n\n1. Jessica Martinez - asking about pet policy and move-in dates\n2. Ryan Thompson - asking about parking and laundry\n3. Sarah Kim - urgent need for December move-in, requesting showing (HIGH PRIORITY)\n\nWould you like me to draft personalized replies to all three inquiries?"
                )
                .oracle()
                .depends_on(list_emails_event, delay_seconds=3)
            )

            # Oracle event 5: User accepts proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please draft replies to all three. Prioritize Sarah's since she mentioned urgency."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle event 6: Agent gets Jessica's email to read full content
            get_jessica_email_event = (
                email_app.get_email_by_id(email_id="email-jessica-inquiry", folder_name="INBOX")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle event 7: Agent replies to Jessica Martinez
            reply_jessica_event = (
                email_app.reply_to_email(
                    email_id="email-jessica-inquiry",
                    folder_name="INBOX",
                    content="Hi Jessica,\n\nThank you for your interest in the Downtown Loft Sublet!\n\nRegarding your questions:\n1. Pet policy: Unfortunately, no pets are allowed in this unit.\n2. Move-in dates: The sublet is available from December 2025 through May 2026.\n\nPlease let me know if you have any other questions!\n\nBest regards",
                )
                .oracle()
                .depends_on(get_jessica_email_event, delay_seconds=3)
            )

            # Oracle event 8: Agent gets Ryan's email to read full content
            get_ryan_email_event = (
                email_app.get_email_by_id(email_id="email-ryan-inquiry", folder_name="INBOX")
                .oracle()
                .depends_on(reply_jessica_event, delay_seconds=1)
            )

            # Oracle event 9: Agent replies to Ryan Thompson
            reply_ryan_event = (
                email_app.reply_to_email(
                    email_id="email-ryan-inquiry",
                    folder_name="INBOX",
                    content="Hello Ryan,\n\nThanks for reaching out about the downtown apartment!\n\nTo answer your questions:\n- Parking: Yes, parking is included with the unit.\n- Laundry: There is in-unit laundry available.\n\nFeel free to contact me if you'd like more information or to schedule a viewing.\n\nBest",
                )
                .oracle()
                .depends_on(get_ryan_email_event, delay_seconds=3)
            )

            # Oracle event 10: Agent gets Sarah's email to read full content
            get_sarah_email_event = (
                email_app.get_email_by_id(email_id="email-sarah-inquiry", folder_name="INBOX")
                .oracle()
                .depends_on(reply_ryan_event, delay_seconds=1)
            )

            # Oracle event 11: Agent replies to Sarah Kim (high priority)
            reply_sarah_event = (
                email_app.reply_to_email(
                    email_id="email-sarah-inquiry",
                    folder_name="INBOX",
                    content="Hi Sarah,\n\nThank you for your interest! I understand the urgency of your situation.\n\nRegarding your questions:\n1. Lease flexibility: The sublet runs from December 2025 to May 2026. Some flexibility on exact dates may be possible.\n2. Earliest move-in: Early December works perfectly with the lease timeline.\n\nGiven your urgent timeline, I'd be happy to arrange a showing this week. What days work best for you?\n\nLooking forward to hearing from you!\n\nBest regards",
                )
                .oracle()
                .depends_on(get_sarah_email_event, delay_seconds=3)
            )

        # Register ALL events here in self.events
        self.events = [
            email1_event,
            email2_event,
            email3_event,
            list_saved_event,
            get_details_event,
            list_emails_event,
            proposal_event,
            acceptance_event,
            get_jessica_email_event,
            reply_jessica_event,
            get_ryan_email_event,
            reply_ryan_event,
            get_sarah_email_event,
            reply_sarah_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent initial proposal to user mentioning all three inquirers
            # and the Downtown Loft Sublet
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent accessed apartment app to get listing details
            apartment_details_accessed = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name in ["get_apartment_details", "list_saved_apartments", "search_apartments"]
                for e in log_entries
            )

            # STRICT Check 3: Agent replied to Jessica with information about pet policy
            # (must mention "no pets" or similar negative pet policy)
            jessica_reply_sent = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email-jessica-inquiry"
                and any(
                    phrase in e.action.args.get("content", "").lower()
                    for phrase in ["no pets", "not allowed", "pets are not", "no pet"]
                )
                for e in log_entries
            )

            # STRICT Check 4: Agent replied to Ryan with information about parking and laundry
            # (must confirm both parking and in-unit laundry are available/included)
            ryan_reply_sent = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email-ryan-inquiry"
                and any(
                    parking_keyword in e.action.args.get("content", "").lower()
                    for parking_keyword in ["parking", "parking included", "parking is"]
                )
                and any(
                    laundry_keyword in e.action.args.get("content", "").lower()
                    for laundry_keyword in ["in-unit laundry", "laundry", "in unit"]
                )
                for e in log_entries
            )

            # STRICT Check 5: Agent replied to Sarah mentioning urgency/priority
            # and December timeline
            sarah_reply_sent = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email-sarah-inquiry"
                and any(keyword in e.action.args.get("content", "") for keyword in ["December", "Dec"])
                for e in log_entries
            )

            # Combine all checks
            all_replies_sent = jessica_reply_sent and ryan_reply_sent and sarah_reply_sent

            success = proposal_found and apartment_details_accessed and all_replies_sent

            # Build rationale if failed
            if not success:
                missing = []
                if not proposal_found:
                    missing.append("initial proposal mentioning all three inquirers")
                if not apartment_details_accessed:
                    missing.append("apartment details access")
                if not all_replies_sent:
                    missing.append("sending all three personalized replies with correct info")

                rationale = f"Missing critical checks: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
