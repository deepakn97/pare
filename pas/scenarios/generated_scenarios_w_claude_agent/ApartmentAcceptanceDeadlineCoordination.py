"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.apartment_listing import Apartment
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulApartmentApp,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("apartment_acceptance_deadline_coordination")
class ApartmentAcceptanceDeadlineCoordination(PASScenario):
    """Agent coordinates apartment application acceptance deadline with pending viewings and responses from preferred properties.

    The user has saved four apartments to favorites and submitted applications to three of them: "Harbor View Residences - Unit 5B" ($2,600/month, preferred location near work), "Riverside Lofts - Unit 3B" ($2,800/month, preferred amenities), and "Downtown Studios - Unit 8A" ($2,400/month, backup option). The user's calendar shows upcoming apartment viewing appointments: "Harbor View Tour & Second Interview" on Friday January 10, 2025 at 3:00 PM and "Riverside Lofts Final Walkthrough" on Saturday January 11, 2025 at 11:00 AM.

    An email arrives from Downtown Studios property management with subject "Application Approved - Unit 8A Available" stating the user's application is accepted, but they must sign the lease and submit first month's rent by Thursday January 9, 2025 at 5:00 PM (48 hours) or the unit will be offered to the next applicant. The agent must:
    1. Parse the acceptance email and extract the acceptance deadline (Thursday Jan 9, 5 PM)
    2. Search saved apartments to retrieve details for Downtown Studios and identify it as the backup option based on price comparison
    3. Query the calendar to find the upcoming viewing appointments for Harbor View and Riverside Lofts, noting that both occur AFTER the acceptance deadline
    4. Recognize the timing dilemma: accepting the backup apartment guarantees housing but forecloses potentially preferred options that haven't responded yet
    5. Propose to the user: (a) send urgent follow-up emails to Harbor View and Riverside property managers requesting expedited application decisions before Jan 9, (b) if no responses received by Wednesday evening, recommend accepting Downtown Studios to avoid losing guaranteed housing
    6. After user acceptance, compose and send follow-up emails to both Harbor View (harbor.leasing@harborview.com from the user's saved apartment details) and Riverside Lofts (leasing@riversidefts.com) explaining the situation and requesting application status updates by January 8
    7. Add a calendar reminder "Decision Deadline: Downtown Studios Acceptance" on January 9 at 12:00 PM to ensure the user makes a final decision with buffer time before the 5 PM deadline

    This scenario exercises time-critical decision support under uncertainty, multi-party coordination via targeted emails using contact information from apartment records, deadline-driven backward planning, preference inference from apartment attributes (price/location/amenities), and proactive risk mitigation when the user hasn't explicitly recognized the timing conflict between acceptance deadlines and pending decisions..
    """

    start_time = datetime(2025, 1, 7, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Seed four apartment listings that the user has been researching
        # Apartment 1: Harbor View Residences - Unit 5B (preferred - near work)
        apt1 = Apartment(
            name="Harbor View Residences - Unit 5B",
            location="Harbor District, 2 blocks from Financial Center",
            zip_code="93101",
            price=2600.0,
            bedrooms=2,
            bathrooms=1,
            property_type="Apartment",
            square_footage=900,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Gym", "Parking", "Rooftop deck"],
            apartment_id="harbor_view_5b",
        )
        self.apartment.apartments[apt1.apartment_id] = apt1
        self.apartment.save_apartment(apt1.apartment_id)

        # Apartment 2: Riverside Lofts - Unit 3B (preferred - great amenities)
        apt2 = Apartment(
            name="Riverside Lofts - Unit 3B",
            location="Riverside, near parks and restaurants",
            zip_code="93103",
            price=2800.0,
            bedrooms=2,
            bathrooms=2,
            property_type="Apartment",
            square_footage=1100,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Pool", "Gym", "In-unit laundry", "Balcony", "Concierge"],
            apartment_id="riverside_lofts_3b",
        )
        self.apartment.apartments[apt2.apartment_id] = apt2
        self.apartment.save_apartment(apt2.apartment_id)

        # Apartment 3: Downtown Studios - Unit 8A (backup - cheapest option)
        apt3 = Apartment(
            name="Downtown Studios - Unit 8A",
            location="Downtown, 15 min walk to transit",
            zip_code="93102",
            price=2400.0,
            bedrooms=1,
            bathrooms=1,
            property_type="Apartment",
            square_footage=750,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Parking", "On-site laundry"],
            apartment_id="downtown_studios_8a",
        )
        self.apartment.apartments[apt3.apartment_id] = apt3
        self.apartment.save_apartment(apt3.apartment_id)

        # Apartment 4: Additional listing (not applied to, just browsing)
        apt4 = Apartment(
            name="Hillside Terrace - Unit 12C",
            location="Hillside neighborhood",
            zip_code="93105",
            price=2500.0,
            bedrooms=2,
            bathrooms=1,
            property_type="Apartment",
            square_footage=950,
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Parking", "Gym"],
            apartment_id="hillside_12c",
        )
        self.apartment.apartments[apt4.apartment_id] = apt4
        self.apartment.save_apartment(apt4.apartment_id)

        # Initialize Calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Seed upcoming viewing appointments for the two preferred apartments
        # Friday January 10, 2025 at 3:00 PM: Harbor View Tour & Second Interview
        harbor_viewing = CalendarEvent(
            event_id="harbor_view_tour",
            title="Harbor View Tour & Second Interview",
            start_datetime=datetime(2025, 1, 10, 15, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 1, 10, 16, 0, 0, tzinfo=UTC).timestamp(),
            tag="Apartment Search",
            description="Second viewing with property manager at Harbor View Residences Unit 5B. Bring application documents.",
            location="Harbor View Residences - 450 Harbor Blvd",
            attendees=["User", "Harbor View Property Manager"],
        )
        self.calendar.set_calendar_event(harbor_viewing)

        # Saturday January 11, 2025 at 11:00 AM: Riverside Lofts Final Walkthrough
        riverside_viewing = CalendarEvent(
            event_id="riverside_lofts_walkthrough",
            title="Riverside Lofts Final Walkthrough",
            start_datetime=datetime(2025, 1, 11, 11, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 1, 11, 12, 0, 0, tzinfo=UTC).timestamp(),
            tag="Apartment Search",
            description="Final walkthrough before application decision at Riverside Lofts Unit 3B.",
            location="Riverside Lofts - 789 River Drive",
            attendees=["User", "Riverside Property Manager"],
        )
        self.calendar.set_calendar_event(riverside_viewing)

        # Initialize Email app (starts empty - acceptance email will arrive as an event)
        self.email = StatefulEmailApp(name="Emails")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.calendar, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps used in event flow
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Acceptance email from Downtown Studios property management
            # This is the triggering event - user receives apartment application acceptance with tight deadline
            acceptance_email_event = email_app.send_email_to_user_with_id(
                email_id="downtown_acceptance_email",
                sender="leasing@downtownstudios.com",
                subject="Application Approved - Unit 8A Available",
                content="Congratulations! Your application for Downtown Studios - Unit 8A has been approved. "
                "We're pleased to offer you this 1-bedroom apartment at $2,400/month. To secure the unit, "
                "you must sign the lease and submit first month's rent by Thursday, January 9, 2025 at 5:00 PM. "
                "If we do not receive your signed lease and payment by this deadline, the unit will be offered "
                "to the next applicant on our waitlist. Please contact us at leasing@downtownstudios.com or "
                "call 555-867-5309 to arrange lease signing. We look forward to welcoming you!",
            ).delayed(20)

            # Oracle Event 1: Agent reads the acceptance email to parse deadline
            # Motivated by: acceptance_email_event triggered a notification, agent reads to understand urgency
            read_acceptance_event = (
                email_app.get_email_by_id(
                    email_id="downtown_acceptance_email",
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(acceptance_email_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent searches saved apartments to retrieve Downtown Studios details
            # Motivated by: email mentions "Unit 8A" which agent recognizes from saved apartments
            search_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(read_acceptance_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent checks calendar for viewing appointments in the relevant timeframe
            # Motivated by: agent needs to see if user has pending viewings for other apartments after Jan 9
            check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-01-09 00:00:00",
                    end_datetime="2025-01-12 23:59:59",
                )
                .oracle()
                .depends_on(search_saved_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent sends proposal explaining the timing dilemma
            # Motivated by: acceptance email (deadline Jan 9 5 PM) + calendar shows viewings on Jan 10-11 (after deadline)
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw the acceptance email from Downtown Studios for Unit 8A ($2,400/month). "
                    "You have until Thursday, January 9 at 5:00 PM to sign the lease, but your viewing "
                    "appointments for Harbor View (Jan 10 at 3 PM) and Riverside Lofts (Jan 11 at 11 AM) "
                    "are after this deadline. Since those are your preferred options (Harbor View is closer "
                    "to work, Riverside has better amenities), would you like me to send urgent follow-up "
                    "emails to both property managers requesting expedited application decisions before "
                    "January 9? This would help you make an informed choice without losing the guaranteed "
                    "Downtown Studios option."
                )
                .oracle()
                .depends_on(check_calendar_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            # Motivated by: user trusts agent's analysis and wants to maximize options
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please send follow-up emails to both Harbor View and Riverside Lofts. "
                    "Ask them if they can provide application decisions by January 8."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent composes and sends follow-up email to Harbor View
            # Motivated by: user acceptance + need to contact Harbor View leasing per saved apartment contact info
            harbor_email_event = (
                email_app.send_email(
                    recipients=["harbor.leasing@harborview.com"],
                    subject="Application Status Request - Time-Sensitive",
                    content="Hello,\n\nI submitted an application for Harbor View Residences - Unit 5B and "
                    "have a viewing appointment scheduled for January 10. I've received an acceptance offer "
                    "from another property with a response deadline of January 9 at 5:00 PM. Harbor View "
                    "remains my preferred choice due to its proximity to my workplace.\n\nWould it be possible "
                    "to receive an application decision by January 8 to help me make an informed choice? I "
                    "understand this is short notice and appreciate any consideration.\n\nThank you,\nUser",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent composes and sends follow-up email to Riverside Lofts
            # Motivated by: user acceptance + need to contact Riverside leasing per saved apartment contact info
            riverside_email_event = (
                email_app.send_email(
                    recipients=["leasing@riversidefts.com"],
                    subject="Application Status Request - Time-Sensitive",
                    content="Hello,\n\nI submitted an application for Riverside Lofts - Unit 3B and have a "
                    "final walkthrough scheduled for January 11. I've received an acceptance offer from another "
                    "property with a response deadline of January 9 at 5:00 PM. Riverside Lofts is highly "
                    "appealing due to its amenities and pet-friendly policy.\n\nWould it be possible to receive "
                    "an application decision by January 8 to help me make an informed choice? I understand this "
                    "is short notice and appreciate any consideration.\n\nThank you,\nUser",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent adds calendar reminder for decision deadline
            # Motivated by: need to ensure user makes final decision with buffer time before 5 PM deadline
            reminder_event = (
                calendar_app.add_calendar_event(
                    title="Decision Deadline: Downtown Studios Acceptance",
                    start_datetime="2025-01-09 12:00:00",
                    end_datetime="2025-01-09 12:30:00",
                    description="Final decision needed on Downtown Studios Unit 8A lease by 5:00 PM today. "
                    "Lease signing deadline is 5:00 PM. Follow-up emails sent to Harbor View and Riverside "
                    "Lofts requesting expedited decisions.",
                    tag="Apartment Search",
                )
                .oracle()
                .depends_on([harbor_email_event, riverside_email_event], delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            acceptance_email_event,
            read_acceptance_event,
            search_saved_event,
            check_calendar_event,
            proposal_event,
            acceptance_event,
            harbor_email_event,
            riverside_email_event,
            reminder_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent read the acceptance email to extract deadline information
            email_read = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                and e.action.args.get("email_id") == "downtown_acceptance_email"
                for e in agent_events
            )

            # STRICT Check 2: Agent searched saved apartments to compare options
            apartments_searched = any(
                e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "list_saved_apartments"
                for e in agent_events
            )

            # STRICT Check 3: Agent queried calendar to find viewing appointments relative to deadline
            calendar_queried = any(
                e.action.class_name == "StatefulCalendarApp" and e.action.function_name == "get_calendar_events_from_to"
                for e in agent_events
            )

            # STRICT Check 4: Agent sent proposal to user explaining timing dilemma (flexible on exact wording)
            proposal_sent = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 5: Agent sent follow-up email to Harbor View property manager
            # Accept send_email or send_batch_email (equivalent for single-recipient outbound email)
            harbor_email_sent = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["send_email", "send_batch_email"]
                and any(
                    "harbor.leasing@harborview.com" in str(recipient).lower()
                    for recipient in (e.action.args or e.action.resolved_args or {}).get("recipients", [])
                )
                for e in agent_events
            )

            # STRICT Check 6: Agent sent follow-up email to Riverside Lofts property manager
            # Accept send_email or send_batch_email (equivalent for single-recipient outbound email)
            riverside_email_sent = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["send_email", "send_batch_email"]
                and any(
                    "leasing@riversidefts.com" in str(recipient).lower()
                    for recipient in (e.action.args or e.action.resolved_args or {}).get("recipients", [])
                )
                for e in agent_events
            )

            # STRICT Check 7: Agent added calendar reminder for decision deadline
            # Check that the event exists with correct structural properties (flexible on exact title/description)
            reminder_added = any(
                e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("start_datetime") is not None
                and "2025-01-09" in str(e.action.args.get("start_datetime"))
                for e in agent_events
            )

            # Determine success based on all strict checks
            all_strict_checks = [
                email_read,
                apartments_searched,
                calendar_queried,
                proposal_sent,
                harbor_email_sent,
                riverside_email_sent,
                reminder_added,
            ]

            if all(all_strict_checks):
                return ScenarioValidationResult(success=True)
            else:
                # Build rationale explaining which checks failed
                failed_checks = []
                if not email_read:
                    failed_checks.append("agent did not read Downtown Studios acceptance email")
                if not apartments_searched:
                    failed_checks.append("agent did not search saved apartments")
                if not calendar_queried:
                    failed_checks.append("agent did not query calendar for viewing appointments")
                if not proposal_sent:
                    failed_checks.append("agent did not send proposal to user")
                if not harbor_email_sent:
                    failed_checks.append("agent did not send follow-up email to Harbor View")
                if not riverside_email_sent:
                    failed_checks.append("agent did not send follow-up email to Riverside Lofts")
                if not reminder_added:
                    failed_checks.append("agent did not add calendar reminder for decision deadline")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
