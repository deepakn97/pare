"""Scenario for filtering apartment search based on furniture delivery constraints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulEmailApp,
)
from pare.apps.apartment import StatefulApartmentApp
from pare.apps.shopping import StatefulShoppingApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("furniture_delivery_apartment_search")
class FurnitureDeliveryApartmentSearch(PAREScenario):
    """Agent helps user resolve conflict between furniture delivery date and apartment availability.

    Story:
    1. User has ordered furniture (sofa + coffee table) - delivery scheduled for Dec 15
    2. User has saved 4 apartments with different availability dates:
       - Downtown Loft: Available Dec 10 (compatible)
       - Midtown Heights: Available Dec 1 (compatible)
       - Westside Garden: Available Dec 20 (incompatible - after delivery)
       - Uptown Plaza: Available Jan 5 (incompatible - after delivery)
    3. Delivery email arrives confirming Dec 15 delivery date
    4. Agent notices the conflict and presents OPTIONS to user:
       - Option A: Focus on compatible apartments (remove Dec 20+ ones from saved)
       - Option B: Contact store to reschedule delivery for later date
    5. User chooses to focus on compatible apartments
    6. Agent removes incompatible apartments from saved list

    This scenario exercises cross-app constraint detection (shopping -> apartment),
    temporal reasoning, and user choice presentation.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You have furniture ordered with delivery scheduled for December 15.
You're also searching for apartments and have several saved.

ACCEPT proposals that:
- Present you with OPTIONS (e.g., reschedule delivery vs remove incompatible apartments from saved list)
- Clearly explain which apartments are compatible/incompatible and why
- Let you make the choice about how to resolve the conflict

REJECT proposals that:
- Simply say they'll remove apartments without giving you options
- Don't explain the conflict or reasoning
- Take action without presenting alternatives first

You prefer to remove incompatible apartments from your saved list (those available after Dec 15) so you
can focus on apartments where you can receive your furniture delivery, rather than rescheduling delivery."""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Initialize Email app (delivery schedule details are surfaced via an incoming email)
        self.email = StatefulEmailApp(name="Emails")

        # Seed furniture products using proper app methods
        # Product 1: Modern Sectional Sofa
        sofa_product_id = self.shopping.add_product(name="Modern Sectional Sofa")
        sofa_item_id = self.shopping.add_item_to_product(
            product_id=sofa_product_id,
            price=1299.99,
            options={"color": "Beige", "material": "Fabric"},
            available=True,
        )

        # Product 2: Oak Coffee Table
        table_product_id = self.shopping.add_product(name="Oak Coffee Table")
        table_item_id = self.shopping.add_item_to_product(
            product_id=table_product_id,
            price=349.99,
            options={"color": "Natural Oak", "shape": "Rectangular"},
            available=True,
        )

        # Seed existing order (placed Nov 13, delivery scheduled for Dec 15)
        order_date_timestamp = datetime(2025, 11, 13, 14, 30, 0, tzinfo=UTC).timestamp()
        self.shopping.add_order_multiple_items(
            order_id="order_furniture_12345",
            order_status="processed",
            order_date=order_date_timestamp,
            order_total=1649.98,
            items={sofa_item_id: 1, table_item_id: 1},
        )

        # Initialize Apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Apartment 1: Available Dec 10 (compatible with Dec 15 delivery)
        self.apt_id_1 = self.apartment.add_new_apartment(
            name="Downtown Loft (Available Dec 10)",
            location="Downtown",
            zip_code="90001",
            price=2200.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=950,
            property_type="Loft",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Parking", "Gym", "Pool"],
        )
        self.apartment.save_apartment(self.apt_id_1)

        # Apartment 2: Available Dec 1 (compatible with Dec 15 delivery)
        self.apt_id_2 = self.apartment.add_new_apartment(
            name="Midtown Heights (Available Dec 1)",
            location="Midtown",
            zip_code="90002",
            price=1950.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=800,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Parking", "Laundry"],
        )
        self.apartment.save_apartment(self.apt_id_2)

        # Apartment 3: Available Dec 20 (INCOMPATIBLE - after delivery)
        self.apt_id_3 = self.apartment.add_new_apartment(
            name="Westside Garden (Available Dec 20)",
            location="Westside",
            zip_code="90003",
            price=2100.0,
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=900,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Garden", "Parking"],
        )
        self.apartment.save_apartment(self.apt_id_3)

        # Apartment 4: Available Jan 5 (INCOMPATIBLE - after delivery)
        self.apt_id_4 = self.apartment.add_new_apartment(
            name="Uptown Plaza (Available Jan 5)",
            location="Uptown",
            zip_code="90004",
            price=2300.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Condo",
            furnished_status="Semi-furnished",
            floor_level="Penthouse",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Concierge"],
        )
        self.apartment.save_apartment(self.apt_id_4)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.apartment, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # ENV: Order status update
            order_status_event = shopping_app.update_order_status(
                order_id="order_furniture_12345", status="shipped"
            ).delayed(10)

            # ENV: Delivery email arrives with the delivery date
            delivery_email_event = email_app.send_email_to_user_with_id(
                email_id="email-furniture-delivery-12345",
                sender="Acme Furniture",
                subject="Delivery scheduled for your sofa + coffee table",
                content=(
                    "Order: order_furniture_12345\n"
                    "Items: Modern Sectional Sofa; Oak Coffee Table\n\n"
                    "Delivery scheduled: Monday, December 15 (time window will be sent closer to delivery).\n"
                ),
            ).depends_on([order_status_event], delay_seconds=2)

            # Oracle: Agent reads the delivery email to learn the delivery date
            read_email_event = (
                email_app.get_email_by_id(email_id="email-furniture-delivery-12345", folder_name="INBOX")
                .oracle()
                .depends_on([delivery_email_event], delay_seconds=3)
            )

            # Oracle: Agent checks the user's saved apartments
            list_apartments_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(read_email_event, delay_seconds=3)
            )

            # Oracle: Agent presents OPTIONS to user with clear explanation of what each means
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "Your furniture (Modern Sectional Sofa + Oak Coffee Table) is scheduled for delivery "
                        "on December 15. I noticed two of your saved apartments won't be available until after "
                        "that date:\n\n"
                        "- Westside Garden: Available Dec 20\n"
                        "- Uptown Plaza: Available Jan 5\n\n"
                        "You have a couple of options:\n"
                        "1. Remove those two apartments from your saved list so you can focus on Downtown Loft "
                        "(Dec 10) and Midtown Heights (Dec 1) which are available before your delivery\n"
                        "2. Contact Acme Furniture to reschedule delivery for a later date\n\n"
                        "Which would you prefer?"
                    )
                )
                .oracle()
                .depends_on(list_apartments_event, delay_seconds=5)
            )

            # Oracle: User chooses to remove incompatible apartments
            user_acceptance = (
                aui.accept_proposal(content="Let's go with option 1 - remove those two apartments from my saved list.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=10)
            )

            # Oracle: Agent removes first incompatible apartment (Westside Garden)
            remove_westside = (
                apartment_app.remove_saved_apartment(apartment_id=self.apt_id_3)
                .oracle()
                .depends_on(user_acceptance, delay_seconds=3)
            )

            # Oracle: Agent removes second incompatible apartment (Uptown Plaza)
            remove_uptown = (
                apartment_app.remove_saved_apartment(apartment_id=self.apt_id_4)
                .oracle()
                .depends_on(remove_westside, delay_seconds=2)
            )

        self.events = [
            order_status_event,
            delivery_email_event,
            read_email_event,
            list_apartments_event,
            proposal_event,
            user_acceptance,
            remove_westside,
            remove_uptown,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent proposed options and removed incompatible apartments.

        Essential outcomes checked:
        1. Agent sent proposal to user with options
        2. Agent removed both incompatible apartments (Westside Garden, Uptown Plaza)
        """
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Agent sent proposal to user
            proposal_found = any(
                e.action.class_name == "PAREAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check 2: Agent removed Westside Garden (apt_id_3)
            westside_removed = any(
                e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "remove_saved_apartment"
                and e.action.args.get("apartment_id") == self.apt_id_3
                for e in agent_events
            )

            # Check 3: Agent removed Uptown Plaza (apt_id_4)
            uptown_removed = any(
                e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "remove_saved_apartment"
                and e.action.args.get("apartment_id") == self.apt_id_4
                for e in agent_events
            )

            success = proposal_found and westside_removed and uptown_removed

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user with options")
                if not westside_removed:
                    missing.append("Westside Garden apartment not removed")
                if not uptown_removed:
                    missing.append("Uptown Plaza apartment not removed")
                return ScenarioValidationResult(
                    success=False,
                    rationale=f"Missing required actions: {', '.join(missing)}",
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
