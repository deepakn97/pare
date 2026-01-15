"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulApartmentApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("family_apartment_recommendation_request")
class FamilyApartmentRecommendationRequest(PASScenario):
    """Agent provides detailed apartment recommendations to family member based on their specific requirements.

    The user's sister emails requesting help finding a pet-friendly 2-bedroom apartment in the user's city (Austin) for under $2000/month, with move-in availability in 4 weeks. The user has 2 apartments already saved, but neither meets all the criteria (one isn't pet-friendly, the other is too expensive). The agent must: 1. Extract the sister's requirements from the email (location: Austin, bedrooms: 2, pet policy: pets allowed, max price: $2000, timeline: 4 weeks). 2. Search the apartment catalog using these filters to find matching units. 3. Retrieve detailed information for the top 2-3 matching apartments (full address, monthly rent, specific amenities like "dog park" or "cat-friendly", square footage, contact information). 4. Check if any of the user's currently saved apartments also meet the criteria, and if so, retrieve their details as well. 5. Compose a reply email to the sister with a formatted list of 2-3 specific apartment recommendations, including for each: name, address, price, key pet amenities, and property manager contact details.

    This scenario exercises extraction of multi-attribute search criteria from conversational email text, filtered apartment catalog search based on another person's requirements rather than the user's own needs, retrieval and synthesis of structured property data from multiple apartment detail pages, cross-referencing search results against the user's existing saved apartments, and composition of an information-dense recommendation email that integrates specific details from the apartment app into natural language..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data.

        Baseline state includes:
        - User contact and sister's contact information
        - 2 apartments already saved by user (one not pet-friendly, one over budget)
        - Several apartments in the catalog that do meet sister's criteria
        """
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")
        self.email = StatefulEmailApp(name="Emails")
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Populate contacts: user and sister
        user_contact = Contact(
            first_name="Alex",
            last_name="Johnson",
            email="alex.johnson@email.com",
            phone="512-555-0100",
            is_user=True,
            city_living="Austin",
            country="USA",
        )

        sister_contact = Contact(
            first_name="Emma",
            last_name="Johnson",
            email="emma.johnson@email.com",
            phone="415-555-0200",
            city_living="San Francisco",
            country="USA",
        )

        # Populate apartment catalog with diverse listings
        # Sister's requirements: Austin, 2BR, pet-friendly, under $2000/month

        # Apartment 1: Already saved by user, but NOT pet-friendly (doesn't meet sister's needs)
        apt1_id = self.apartment.add_new_apartment(
            name="Downtown Lofts",
            location="Austin",
            zip_code="78701",
            price=1850.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking"],
        )
        self.apartment.save_apartment(apt1_id)

        # Apartment 2: Already saved by user, but over budget ($2500 > $2000)
        apt2_id = self.apartment.add_new_apartment(
            name="Riverside Residences",
            location="Austin",
            zip_code="78704",
            price=2500.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1300,
            property_type="Apartment",
            furnished_status="Semi-furnished",
            floor_level="Ground floor",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Dog park", "Pet washing station", "Pool", "Gym"],
        )
        self.apartment.save_apartment(apt2_id)

        # Apartment 3: Perfect match - 2BR, Austin, pet-friendly, under $2000
        self.apartment.add_new_apartment(
            name="Parkside Terrace",
            location="Austin",
            zip_code="78702",
            price=1750.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1050,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Dog park", "Cat-friendly", "Parking", "Laundry"],
        )

        # Apartment 4: Another good match - 2BR, Austin, pet-friendly, under $2000
        self.apartment.add_new_apartment(
            name="Green Valley Apartments",
            location="Austin",
            zip_code="78705",
            price=1900.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1150,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Dogs allowed",
            lease_term="1 year",
            amenities=["Pet washing station", "Gym", "Pool", "Parking"],
        )

        # Apartment 5: Good match with slightly lower price point
        self.apartment.add_new_apartment(
            name="Cedar Creek Commons",
            location="Austin",
            zip_code="78703",
            price=1650.0,
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=950,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Cat-friendly", "Parking", "Laundry"],
        )

        # Apartment 6: Not a match - wrong location (Houston)
        self.apartment.add_new_apartment(
            name="Houston Heights",
            location="Houston",
            zip_code="77008",
            price=1800.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Dog park", "Pool"],
        )

        # Apartment 7: Not a match - wrong number of bedrooms (1BR)
        self.apartment.add_new_apartment(
            name="Austin Studio Square",
            location="Austin",
            zip_code="78701",
            price=1400.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=700,
            property_type="Apartment",
            furnished_status="Furnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="Month-to-month",
            amenities=["Dog park", "Gym"],
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.apartment]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # Environment event: Sister emails requesting apartment help
            sister_email_id = "sister_apt_request_001"
            env_email = email_app.send_email_to_user_with_id(
                email_id=sister_email_id,
                sender="emma.johnson@email.com",
                subject="Need your help finding an apartment in Austin!",
                content="""Hey Alex!

I hope you're doing well! I have some exciting news - I got a job offer in Austin and will be moving there in about 4 weeks! Since you've been living there for a while, I was hoping you could help me find a place.

Here's what I'm looking for:
- 2 bedrooms (my partner and I need a home office)
- Pet-friendly - we have a cat and might adopt a dog
- Budget: under $2000/month
- Move-in: around mid-December (4 weeks from now)

I know you were apartment hunting recently, so you probably know the market better than anyone. Do you have any recommendations or know of any good places?

Thanks so much!
Emma""",
            )

            # Oracle event: Agent reads the sister's email to understand requirements
            # Motivated by: the incoming email notification about apartment help request
            read_email_event = (
                email_app.get_email_by_id(email_id=sister_email_id, folder_name="INBOX")
                .oracle()
                .depends_on(env_email, delay_seconds=2)
            )

            # Oracle event: Agent searches for apartments matching sister's criteria (2BR, Austin, pet-friendly, under $2000)
            # Motivated by: the email content explicitly requesting 2BR, pet-friendly apartments in Austin under $2000
            search_event = (
                apartment_app.search_apartments(
                    location="Austin", number_of_bedrooms=2, pet_policy="Pets allowed", max_price=2000.0
                )
                .oracle()
                .depends_on(read_email_event, delay_seconds=3)
            )

            # Oracle event: Agent gets details for top matching apartments to include specific info in reply
            # Motivated by: need to extract detailed property data (address, amenities, contact) for recommendations
            # Note: We'll get details for Parkside Terrace (apt3) and Green Valley (apt4)
            get_details_1 = (
                apartment_app.get_apartment_details(apartment_id="apt3_id_placeholder")
                .oracle()
                .depends_on(search_event, delay_seconds=2)
            )

            get_details_2 = (
                apartment_app.get_apartment_details(apartment_id="apt4_id_placeholder")
                .oracle()
                .depends_on(search_event, delay_seconds=2)
            )

            # Oracle event: Agent also checks saved apartments to see if any match
            # Motivated by: email mentions "I know you were apartment hunting recently"
            list_saved_event = apartment_app.list_saved_apartments().oracle().depends_on(search_event, delay_seconds=2)

            # Oracle event: Agent proposes to help by sending recommendations to sister
            # Motivated by: sister's explicit request "Do you have any recommendations?" in the email
            proposal = (
                aui.send_message_to_user(
                    content="I received an email from Emma asking for apartment recommendations in Austin. I found several pet-friendly 2BR apartments under $2000/month. Would you like me to send her a detailed reply with the top matches?"
                )
                .oracle()
                .depends_on([get_details_1, get_details_2, list_saved_event], delay_seconds=3)
            )

            # User event: User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please send her the recommendations!")
                .oracle()
                .depends_on(proposal, delay_seconds=5)
            )

            # Oracle event: Agent replies to sister's email with detailed apartment recommendations
            # Motivated by: user accepted the proposal to help sister
            reply_event = (
                email_app.reply_to_email(
                    email_id=sister_email_id,
                    folder_name="INBOX",
                    content="""Hi Emma,

Congratulations on the new job! I'd be happy to help you find a place. I searched for 2-bedroom, pet-friendly apartments in Austin under $2000/month and found some great options:

1. Parkside Terrace (78702)
   - $1,750/month
   - 1,050 sq ft, 2BR/2BA
   - Pet policy: Pets allowed
   - Amenities: Dog park, cat-friendly, parking, laundry

2. Green Valley Apartments (78705)
   - $1,900/month
   - 1,150 sq ft, 2BR/2BA
   - Pet policy: Dogs allowed
   - Amenities: Pet washing station, gym, pool, parking

3. Cedar Creek Commons (78703)
   - $1,650/month
   - 950 sq ft, 2BR/1BA
   - Pet policy: Cats allowed
   - Amenities: Cat-friendly, parking, laundry

All three are available for move-in within your timeline. I'd recommend Parkside Terrace if you want both dog and cat amenities, or Green Valley if you prioritize having a gym and pool.

Let me know if you want more details about any of these!

Best,
Alex""",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=5)
            )

        # Register ALL events here in self.events
        self.events = [
            env_email,
            read_email_event,
            search_event,
            get_details_1,
            get_details_2,
            list_saved_event,
            proposal,
            acceptance,
            reply_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT-type events (oracle events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent read the sister's email
            read_email_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulEmailApp" and e.action.function_name == "get_email_by_id":
                    args = e.action.args if e.action.args else e.action.resolved_args
                    email_id = args.get("email_id", "")
                    if "sister_apt_request" in email_id:
                        read_email_found = True
                        break

            # STRICT Check 2: Agent searched apartments with correct criteria
            search_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "search_apartments":
                    args = e.action.args if e.action.args else e.action.resolved_args
                    # Check key criteria: Austin, 2BR, pet-friendly, max price 2000
                    location = args.get("location", "")
                    bedrooms = args.get("number_of_bedrooms", 0)
                    pet_policy = args.get("pet_policy", "")
                    max_price = args.get("max_price", 0)

                    if (
                        location.lower() == "austin"
                        and bedrooms == 2
                        and "pet" in pet_policy.lower()
                        and max_price >= 2000
                    ):
                        search_found = True
                        break

            # STRICT Check 3: Agent retrieved apartment details (at least once)
            details_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "get_apartment_details":
                    args = e.action.args if e.action.args else e.action.resolved_args
                    apt_id = args.get("apartment_id", "")
                    if apt_id:  # Any apartment detail retrieval counts
                        details_found = True
                        break

            # STRICT Check 4: Agent proposed to help the user
            # Accept either send_message_to_user (proposal) OR propose_task as equivalent
            proposal_found = False
            for e in agent_events:
                if e.action.class_name == "PASAgentUserInterface" and e.action.function_name in [
                    "send_message_to_user",
                    "propose_task",
                ]:
                    # Don't check exact content, just that a message was sent
                    proposal_found = True
                    break

            # STRICT Check 5: Agent replied to sister's email
            reply_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulEmailApp" and e.action.function_name in [
                    "reply_to_email",
                    "send_email",
                ]:
                    args = e.action.args if e.action.args else e.action.resolved_args
                    email_id = args.get("email_id", "")
                    # Verify it's replying to the sister's email
                    if "sister_apt_request" in email_id or "emma.johnson@email.com" in args.get("recipients", []):
                        reply_found = True
                        break

            # Aggregate results
            success = read_email_found and search_found and details_found and proposal_found and reply_found

            if not success:
                missing_checks = []
                if not read_email_found:
                    missing_checks.append("agent did not read sister's email")
                if not search_found:
                    missing_checks.append("agent did not search apartments with correct criteria")
                if not details_found:
                    missing_checks.append("agent did not retrieve apartment details")
                if not proposal_found:
                    missing_checks.append("agent did not propose help to user")
                if not reply_found:
                    missing_checks.append("agent did not reply to sister's email")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
