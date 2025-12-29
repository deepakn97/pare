"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.apartment_listing import Apartment
from are.simulation.apps.shopping import CartItem, Item, Order, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.apartment import StatefulApartmentApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("furniture_delivery_apartment_search")
class FurnitureDeliveryApartmentSearch(PASScenario):
    """Agent assists user by filtering apartment search based on furniture delivery constraints.

    The user has furniture items already purchased (existing order). A delivery-scheduling email arrives informing the user that their furniture order delivery is scheduled for December 15. The agent must: 1) recognize this delivery notification as creating a constraint on apartment move-in timing, 2) read the delivery email to confirm the delivery date, 3) notice that the user has saved apartments in their favorites, 4) retrieve the saved apartments and identify their availability dates (encoded in the listing names), 5) propose filtering or removing saved apartments that become available after the delivery date (e.g., apartments available Dec 20 or later), and 6) assist the user in narrowing their apartment search to options compatible with the furniture delivery schedule.

    This scenario exercises reverse temporal reasoning (shopping commitment → apartment search constraints), cross-app dependency discovery, proactive constraint propagation, and multi-step coordination between e-commerce order tracking and apartment search workflows.

    ---.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Initialize Email app (delivery schedule details are surfaced via an incoming email).
        self.email = StatefulEmailApp(name="Emails")

        # Seed furniture products in the shopping app catalog
        # Product 1: Sectional Sofa
        product_id_1 = "prod_sofa_001"
        item_id_1 = "item_sofa_beige_001"
        self.shopping.products[product_id_1] = Product(
            name="Modern Sectional Sofa",
            product_id=product_id_1,
            variants={
                item_id_1: Item(
                    item_id=item_id_1, price=1299.99, available=True, options={"color": "Beige", "material": "Fabric"}
                )
            },
        )

        # Product 2: Coffee Table
        product_id_2 = "prod_table_002"
        item_id_2 = "item_table_oak_002"
        self.shopping.products[product_id_2] = Product(
            name="Oak Coffee Table",
            product_id=product_id_2,
            variants={
                item_id_2: Item(
                    item_id=item_id_2,
                    price=349.99,
                    available=True,
                    options={"color": "Natural Oak", "shape": "Rectangular"},
                )
            },
        )

        # Seed an existing order placed before start_time
        # Order placed 5 days ago (Nov 13), delivery scheduled for Dec 15, 2-4 PM
        order_id = "order_furniture_12345"
        order_date_timestamp = datetime(2025, 11, 13, 14, 30, 0, tzinfo=UTC)

        self.shopping.orders[order_id] = Order(
            order_id=order_id,
            order_status="processed",
            order_date=order_date_timestamp,
            order_total=1649.98,
            order_items={
                item_id_1: CartItem(
                    item_id=item_id_1,
                    quantity=1,
                    price=1299.99,
                    available=True,
                    options={"color": "Beige", "material": "Fabric"},
                ),
                item_id_2: CartItem(
                    item_id=item_id_2,
                    quantity=1,
                    price=349.99,
                    available=True,
                    options={"color": "Natural Oak", "shape": "Rectangular"},
                ),
            },
        )

        # Initialize Apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Seed apartment listings with different lease start dates
        # Apartment 1: Available Dec 10 (compatible with Dec 15 delivery)
        apt_id_1 = "apt_downtown_001"
        self.apartment.apartments[apt_id_1] = Apartment(
            apartment_id=apt_id_1,
            name="Downtown Loft (Available Dec 10)",
            location="Downtown",
            zip_code="90001",
            price=2200.0,
            bedrooms=2,
            bathrooms=2,
            property_type="Loft",
            square_footage=950,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Parking", "Gym", "Pool"],
            saved=True,
        )
        self.apartment.saved_apartments.append(apt_id_1)

        # Apartment 2: Available Dec 1 (compatible with Dec 15 delivery)
        apt_id_2 = "apt_midtown_002"
        self.apartment.apartments[apt_id_2] = Apartment(
            apartment_id=apt_id_2,
            name="Midtown Heights (Available Dec 1)",
            location="Midtown",
            zip_code="90002",
            price=1950.0,
            bedrooms=1,
            bathrooms=1,
            property_type="Apartment",
            square_footage=800,
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Parking", "Laundry"],
            saved=True,
        )
        self.apartment.saved_apartments.append(apt_id_2)

        # Apartment 3: Available Dec 20 (INCOMPATIBLE - lease starts after delivery)
        apt_id_3 = "apt_westside_003"
        self.apartment.apartments[apt_id_3] = Apartment(
            apartment_id=apt_id_3,
            name="Westside Garden (Available Dec 20)",
            location="Westside",
            zip_code="90003",
            price=2100.0,
            bedrooms=2,
            bathrooms=1,
            property_type="Apartment",
            square_footage=900,
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Garden", "Parking"],
            saved=True,
        )
        self.apartment.saved_apartments.append(apt_id_3)

        # Apartment 4: Available Jan 5 (INCOMPATIBLE - lease starts after delivery)
        apt_id_4 = "apt_uptown_004"
        self.apartment.apartments[apt_id_4] = Apartment(
            apartment_id=apt_id_4,
            name="Uptown Plaza (Available Jan 5)",
            location="Uptown",
            zip_code="90004",
            price=2300.0,
            bedrooms=2,
            bathrooms=2,
            property_type="Condo",
            square_footage=1100,
            furnished_status="Semi-furnished",
            floor_level="Penthouse",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Concierge"],
            saved=True,
        )
        self.apartment.saved_apartments.append(apt_id_4)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.apartment, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment event: Shopping order status update (delivery scheduled notification)
            # This is the exogenous trigger that creates the apartment search constraint
            env_event_1 = shopping_app.update_order_status(order_id="order_furniture_12345", status="shipped").delayed(
                10
            )

            # Environment event: Delivery-scheduling email arrives with the delivery date.
            # NOTE: Meta-ARE Shopping orders do NOT include delivery schedule fields, so this must come from observable text.
            env_event_2 = email_app.send_email_to_user_with_id(
                email_id="email-furniture-delivery-12345",
                sender="Acme Furniture",
                subject="Delivery scheduled for your sofa + coffee table",
                content=(
                    "Order: order_furniture_12345\n"
                    "Items: Modern Sectional Sofa; Oak Coffee Table\n\n"
                    "Delivery scheduled: Monday, December 15 (time window will be sent closer to delivery).\n"
                ),
            ).depends_on([env_event_1], delay_seconds=2)

            # Agent reads the delivery email to learn the delivery date.
            oracle_event_0 = (
                email_app.get_email_by_id(email_id="email-furniture-delivery-12345", folder_name="INBOX")
                .oracle()
                .depends_on([env_event_2], delay_seconds=3)
            )

            # Agent lists orders to confirm which order is in-flight (but NOT to infer delivery schedule).
            oracle_event_1 = shopping_app.list_orders().oracle().depends_on([env_event_1], delay_seconds=5)

            # Agent retrieves order details to understand the delivery timing constraint
            oracle_event_2 = (
                shopping_app.get_order_details(order_id="order_furniture_12345")
                .oracle()
                .depends_on(oracle_event_1, delay_seconds=3)
            )

            # Agent checks the user's saved apartments to see if any conflict with the delivery
            oracle_event_3 = (
                apartment_app.list_saved_apartments()
                .oracle()
                .depends_on([oracle_event_2, oracle_event_0], delay_seconds=3)
            )

            # Agent sends proposal to user about filtering apartments based on delivery constraint
            oracle_event_4 = (
                aui.send_message_to_user(
                    content="Your furniture delivery email says your sofa + coffee table order (order_furniture_12345) is scheduled for delivery on December 15. In your saved apartments, two listings appear to become available after that date (Westside Garden — Available Dec 20; Uptown Plaza — Available Jan 5). Would you like me to remove those incompatible apartments from your saved list so you focus on options that can receive the delivery?"
                )
                .oracle()
                .depends_on(oracle_event_3, delay_seconds=5)
            )

            # User accepts the agent's proposal
            user_event_1 = (
                aui.accept_proposal(
                    content="Yes, please remove those apartments that won't work with my delivery date."
                )
                .oracle()
                .depends_on(oracle_event_4, delay_seconds=10)
            )

            # Agent removes the first incompatible apartment (Westside Garden - Dec 20 availability)
            oracle_event_5 = (
                apartment_app.remove_saved_apartment(apartment_id="apt_westside_003")
                .oracle()
                .depends_on(user_event_1, delay_seconds=3)
            )

            # Agent removes the second incompatible apartment (Uptown Plaza - Jan 5 availability)
            oracle_event_6 = (
                apartment_app.remove_saved_apartment(apartment_id="apt_uptown_004")
                .oracle()
                .depends_on(oracle_event_5, delay_seconds=2)
            )

            # Agent confirms completion
            oracle_event_7 = (
                aui.send_message_to_user(
                    content="Done! I've removed Westside Garden and Uptown Plaza from your saved apartments. Your remaining saved options (Downtown Loft and Midtown Heights) both have lease start dates before December 15th, so you'll be able to receive your furniture delivery."
                )
                .oracle()
                .depends_on(oracle_event_6, delay_seconds=3)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            env_event_1,
            env_event_2,
            oracle_event_0,
            oracle_event_1,
            oracle_event_2,
            oracle_event_3,
            oracle_event_4,
            user_event_1,
            oracle_event_5,
            oracle_event_6,
            oracle_event_7,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events (oracle events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal to user
            # Must be a message from PASAgentUserInterface
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 1b: Agent read the delivery email before proposing constraints
            read_delivery_email_found = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                and e.action.args.get("email_id") == "email-furniture-delivery-12345"
                for e in agent_events
            )

            # STRICT Check 2: Agent removed apartment apt_westside_003
            # Must be a remove_saved_apartment call with the correct apartment_id
            westside_removed = any(
                e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "remove_saved_apartment"
                and e.action.args.get("apartment_id") == "apt_westside_003"
                for e in agent_events
            )

            # STRICT Check 3: Agent removed apartment apt_uptown_004
            # Must be a remove_saved_apartment call with the correct apartment_id
            uptown_removed = any(
                e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "remove_saved_apartment"
                and e.action.args.get("apartment_id") == "apt_uptown_004"
                for e in agent_events
            )

            # Check all strict conditions
            success = proposal_found and read_delivery_email_found and westside_removed and uptown_removed

            if not success:
                # Build rationale for failure
                missing = []
                if not proposal_found:
                    missing.append("no proposal message to user found")
                if not read_delivery_email_found:
                    missing.append("delivery email not read")
                if not westside_removed:
                    missing.append("apartment apt_westside_003 not removed")
                if not uptown_removed:
                    missing.append("apartment apt_uptown_004 not removed")

                rationale = "; ".join(missing)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
