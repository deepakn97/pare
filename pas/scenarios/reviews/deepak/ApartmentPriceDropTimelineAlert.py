"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact
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


@register_scenario("apartment_price_drop_timeline_alert")
class ApartmentPriceDropTimelineAlert(PASScenario):
    """Agent detects price reduction on saved apartment and proactively alerts user based on calendar move-in timeline.

    The user has saved three apartments to favorites: "Riverside Lofts - Unit 3B" ($2,800/month), "Harbor View Residences - Unit 5B" ($2,600/month), and "Sunset Plaza Apartments - Unit 12A" ($3,200/month). The user's calendar contains an event titled "Current Lease Ends - Must Move Out" on December 15, 2025, indicating an urgent move-in deadline. An email arrives from "ApartmentFinder Alerts" with subject "Price Drop Alert: Sunset Plaza Apartments" stating that Unit 12A has reduced its monthly rent from $3,200 to $2,750 (14% decrease), and this promotional rate is available only for move-ins before December 20, 2025. The agent must:
    1. Parse the price drop notification email and identify the specific apartment (Sunset Plaza Unit 12A) using the property name and unit mentioned in the email
    2. Search the user's saved apartments to confirm this is one the user has been actively considering and retrieve the original saved price for comparison
    3. Query the calendar to find the user's lease-end date and move-in deadline
    4. Verify that the promotional move-in deadline (Dec 20) aligns with the user's calendar constraint (Dec 15 lease end)
    5. Calculate the savings opportunity (original $3,200 vs. new $2,750 = $450/month savings)
    6. Propose to the user: highlight the time-sensitive price reduction on a saved apartment that fits their move-in timeline
    7. After user expresses interest, compose and send an email reply to the listing agent (email address provided in the price drop notification) expressing interest in viewing the unit and confirming availability for move-in by mid-December

    This scenario exercises financial opportunity detection, temporal constraint reasoning across calendar and external deadlines, cross-app information synthesis (email trigger → saved apartments lookup → calendar deadline checking), proactive value-based recommendations, and multi-step task orchestration that uses all three domain apps with natural identifiers (apartment name/unit, not opaque IDs).
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario-specific apps
        self.apartment = StatefulApartmentApp(name="Apartment")
        self.email = StatefulEmailApp(name="Emails", user_email="user@example.com")
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Populate Apartment App with three saved apartments
        # Note: Sunset Plaza Unit 12A is the one that will have a price drop
        apt1_id = self.apartment.add_new_apartment(
            name="Riverside Lofts - Unit 3B",
            location="Downtown",
            zip_code="90001",
            price=2800.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1200,
            property_type="Apartment",
            furnished_status="Unfurnished",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Pool", "Gym", "Parking"],
        )
        self.apartment.save_apartment(apt1_id)

        apt2_id = self.apartment.add_new_apartment(
            name="Harbor View Residences - Unit 5B",
            location="Waterfront District",
            zip_code="90002",
            price=2600.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=950,
            property_type="Apartment",
            furnished_status="Semi-furnished",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Pool", "Concierge"],
        )
        self.apartment.save_apartment(apt2_id)

        apt3_id = self.apartment.add_new_apartment(
            name="Sunset Plaza Apartments - Unit 12A",
            location="West End",
            zip_code="90003",
            price=3200.0,
            number_of_bedrooms=3,
            number_of_bathrooms=2,
            square_footage=1500,
            property_type="Apartment",
            furnished_status="Unfurnished",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Pool", "Gym", "Parking", "Balcony"],
        )
        self.apartment.save_apartment(apt3_id)

        # Populate Calendar with lease-end event on December 15, 2025
        lease_end_event = CalendarEvent(
            title="Current Lease Ends - Must Move Out",
            start_datetime=datetime(2025, 12, 15, 10, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 12, 15, 12, 0, 0, tzinfo=UTC).timestamp(),
            description="Final day of current lease. Need to vacate apartment by end of day.",
            location="Current Apartment",
            tag="important",
        )
        self.calendar.set_calendar_event(lease_end_event)

        # Populate Email App with a contact for the listing agent
        # This will be used when the agent sends a reply after the user accepts the proposal
        listing_agent_contact = Contact(
            first_name="Sarah",
            last_name="Martinez",
            email="sarah.martinez@sunsetplaza.com",
            phone="555-0123",
        )
        # Note: We don't add this to a contacts app here since we only have email/calendar/apartment apps
        # The email address will be included in the price drop notification email

        # Register all apps
        self.apps = [
            self.agent_ui,
            self.system_app,
            self.apartment,
            self.email,
            self.calendar,
        ]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # Environment Event: Price drop notification email arrives
            price_drop_email = email_app.send_email_to_user_with_id(
                email_id="price-drop-email-001",
                sender="alerts@apartmentfinder.com",
                subject="Price Drop Alert: Sunset Plaza Apartments",
                content="Great news! One of your saved apartments has dropped in price.\n\nSunset Plaza Apartments - Unit 12A has reduced its monthly rent from $3,200 to $2,750 (14% decrease, saving you $450/month). This promotional rate is available only for move-ins before December 20, 2025.\n\nInterested in scheduling a viewing? Contact listing agent Sarah Martinez at sarah.martinez@sunsetplaza.com or call 555-0123.\n\nDon't miss this limited-time opportunity!",
            ).delayed(5)

            # Agent oracle: Check saved apartments to confirm this apartment and retrieve baseline price
            # Motivation: Price drop email mentions "Sunset Plaza Apartments - Unit 12A"; agent needs to verify it's saved and get original price
            list_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(price_drop_email, delay_seconds=2)
            )

            # Agent oracle: Query calendar to find lease-end deadline
            # Motivation: Email mentions "move-ins before December 20"; agent needs to check if user's move-in timeline aligns
            calendar_check_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-12-01 00:00:00",
                    end_datetime="2025-12-31 23:59:59",
                )
                .oracle()
                .depends_on(price_drop_email, delay_seconds=2)
            )

            # Agent oracle: Send proposal to user highlighting the opportunity
            # Motivation: Email notification about price drop on saved apartment, confirmed via list_saved and calendar checks
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw a price drop notification for Sunset Plaza Apartments Unit 12A, one of your saved apartments. The rent dropped from $3,200 to $2,750/month (saving $450/month), and this rate is available for move-ins before December 20. Your lease ends December 15, so the timing works perfectly. Would you like me to email the listing agent to express interest and schedule a viewing?"
                )
                .oracle()
                .depends_on([list_saved_event, calendar_check_event], delay_seconds=3)
            )

            # User oracle: Accept the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please reach out to the listing agent. I'm definitely interested in viewing it given the price drop and timing."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Agent oracle: Send reply email to listing agent
            # Motivation: User accepted proposal to contact listing agent; email provides agent's address (sarah.martinez@sunsetplaza.com)
            reply_event = (
                email_app.send_email(
                    recipients=["sarah.martinez@sunsetplaza.com"],
                    subject="Viewing Request for Sunset Plaza Apartments Unit 12A",
                    content="Hello Sarah,\n\nI'm writing to express interest in viewing Sunset Plaza Apartments Unit 12A following the recent price reduction to $2,750/month. I'm looking to move in mid-December (my current lease ends December 15), which aligns with the promotional move-in deadline of December 20.\n\nCould we schedule a viewing at your earliest convenience? I'm available most days this week and next.\n\nThank you,\nUser",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=3)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            price_drop_email,
            list_saved_event,
            calendar_check_event,
            proposal_event,
            acceptance_event,
            reply_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events (EventType.AGENT)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent checked saved apartments
            # The agent must verify that Sunset Plaza Unit 12A is saved
            list_saved_found = any(
                e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "list_saved_apartments"
                for e in agent_events
            )

            # STRICT Check 2: Agent queried calendar for lease-end deadline
            # The agent must check calendar to verify timeline alignment
            calendar_check_found = any(
                e.action.class_name == "StatefulCalendarApp" and e.action.function_name == "get_calendar_events_from_to"
                for e in agent_events
            )

            # STRICT Check 3: Agent sent proposal to user
            # The agent must proactively inform the user about the price drop opportunity
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent sent email to listing agent
            # After user acceptance, agent must email the listing agent
            # Accept either:
            # - send_email / send_batch_email (new outbound email), OR
            # - reply_to_email (replying to the price-drop alert thread) as an equivalent outcome.
            email_to_listing_agent_found = False
            for e in agent_events:
                if e.action.class_name != "StatefulEmailApp":
                    continue

                args = e.action.args if e.action.args else e.action.resolved_args

                if e.action.function_name in [
                    "send_email",
                    "send_batch_email",
                ] and "sarah.martinez@sunsetplaza.com" in str(args.get("recipients", [])):
                    email_to_listing_agent_found = True
                    break

                # Equivalent: replying directly to the price drop alert email (which contains the agent email address).
                if e.action.function_name == "reply_to_email" and "price-drop-email-001" in str(
                    args.get("email_id", "")
                ):
                    email_to_listing_agent_found = True
                    break

            # Build rationale for failure
            missing_checks = []
            if not list_saved_found:
                missing_checks.append("agent did not check saved apartments")
            if not calendar_check_found:
                missing_checks.append("agent did not query calendar for lease-end deadline")
            if not proposal_found:
                missing_checks.append("agent did not send proposal to user about price drop")
            if not email_to_listing_agent_found:
                missing_checks.append(
                    "agent did not contact the listing agent (send_email/send_batch_email to sarah.martinez@sunsetplaza.com or reply_to_email to price-drop-email-001)"
                )

            success = list_saved_found and calendar_check_found and proposal_found and email_to_listing_agent_found

            rationale = ""
            if not success:
                rationale = "Missing critical actions: " + "; ".join(missing_checks)

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
