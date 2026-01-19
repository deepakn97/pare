"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

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


@register_scenario("bulk_order_space_constraint_alert")
class BulkOrderSpaceConstraint(PASScenario):
    """Agent alerts user that saved apartments lack sufficient space for bulk furniture order.

    The user has multiple apartments saved to favorites with varying square footages (mix of studios, 1BR, and 2BR units). The user receives a shopping notification confirming a "bulk order" of large furniture items (couch, king bed, dining table, bookshelf) has shipped. Separately, a delivery-planning email explicitly warns that large items may not fit in smaller units and suggests reviewing saved apartments' square footage before delivery. The agent must: 1) detect the shipment notification and recognize the total volume/size implications of multiple large furniture pieces, 2) read the delivery email and extract the space-constraint warning, 3) retrieve the user's saved apartments to check their square footage specifications, 4) identify which saved apartments have insufficient space (e.g., studios or small 1BR units under 500 sq ft) to reasonably accommodate all the furniture items, 5) propose removing undersized apartments from the saved list or highlighting only apartments with adequate space (e.g., 2BR units over 800 sq ft), and 6) alert the user to finalize their apartment choice from spatially compatible options before the furniture arrives.

    This scenario exercises spatial reasoning across domains (furniture dimensions → apartment floor plans), constraint-based filtering within apartment search, proactive incompatibility detection, and multi-item shopping order analysis to infer space requirements..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Initialize email app (used for an environment cue; no reply required)
        self.email = StatefulEmailApp(name="Emails")

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Populate apartment app with baseline data
        # Create apartments with varying square footages
        # Small studio - insufficient space (350 sq ft)
        self.apt_id_studio = self.apartment.add_new_apartment(
            name="Cozy Studio Downtown",
            location="Downtown",
            zip_code="93101",
            price=1200.0,
            number_of_bedrooms=0,
            number_of_bathrooms=1,
            square_footage=350,
            property_type="Studio",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Gym", "Parking"],
        )
        self.apartment.save_apartment(self.apt_id_studio)

        # Small 1BR - insufficient space (480 sq ft)
        self.apt_id_1br_small = self.apartment.add_new_apartment(
            name="Compact 1BR Near Campus",
            location="Isla Vista",
            zip_code="93117",
            price=1500.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=480,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Pool", "Laundry"],
        )
        self.apartment.save_apartment(self.apt_id_1br_small)

        # Medium 1BR - borderline space (650 sq ft)
        apt_id_1br_medium = self.apartment.add_new_apartment(
            name="Modern 1BR Midtown",
            location="Midtown",
            zip_code="93103",
            price=1800.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=650,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking"],
        )
        self.apartment.save_apartment(apt_id_1br_medium)

        # Large 2BR - adequate space (900 sq ft)
        apt_id_2br_large = self.apartment.add_new_apartment(
            name="Spacious 2BR with Balcony",
            location="Mesa",
            zip_code="93109",
            price=2400.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=900,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking", "Balcony"],
        )
        self.apartment.save_apartment(apt_id_2br_large)

        # Extra large 2BR - adequate space (1100 sq ft)
        apt_id_2br_xlarge = self.apartment.add_new_apartment(
            name="Luxury 2BR Ocean View",
            location="Waterfront",
            zip_code="93109",
            price=3200.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Condo",
            furnished_status="Unfurnished",
            floor_level="Penthouse",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking", "Balcony", "Ocean View"],
        )
        self.apartment.save_apartment(apt_id_2br_xlarge)

        # Populate shopping app with large furniture products
        # Store item IDs for use in build_events_flow()

        # Product 1: Large Sectional Couch
        product_id_couch = self.shopping.add_product(name="Large Sectional Couch")
        self.item_id_couch = self.shopping.add_item_to_product(
            product_id=product_id_couch,
            price=1299.99,
            options={"color": "Gray", "size": "L-shaped", "dimensions": "120x90 inches"},
            available=True,
        )

        # Product 2: King Size Bed Frame
        product_id_bed = self.shopping.add_product(name="King Size Bed Frame")
        self.item_id_bed = self.shopping.add_item_to_product(
            product_id=product_id_bed,
            price=899.99,
            options={"material": "Wood", "size": "King", "dimensions": "80x76 inches"},
            available=True,
        )

        # Product 3: Large Dining Table Set
        product_id_table = self.shopping.add_product(name="Large Dining Table Set")
        self.item_id_table = self.shopping.add_item_to_product(
            product_id=product_id_table,
            price=699.99,
            options={"material": "Oak", "seats": "6-person", "dimensions": "72x42 inches"},
            available=True,
        )

        # Product 4: Large Bookshelf
        product_id_bookshelf = self.shopping.add_product(name="Large Bookshelf")
        self.item_id_bookshelf = self.shopping.add_item_to_product(
            product_id=product_id_bookshelf,
            price=349.99,
            options={"material": "Wood", "shelves": "5-tier", "dimensions": "72x36 inches"},
            available=True,
        )

        # Create a bulk order by adding all items to cart and checking out
        self.shopping.add_to_cart(item_id=self.item_id_couch, quantity=1)
        self.shopping.add_to_cart(item_id=self.item_id_bed, quantity=1)
        self.shopping.add_to_cart(item_id=self.item_id_table, quantity=1)
        self.shopping.add_to_cart(item_id=self.item_id_bookshelf, quantity=1)

        # Checkout to create the order
        self.bulk_order_id = self.shopping.checkout()

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.apartment, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment event: Bulk furniture order status update
            # User receives notification that their bulk furniture order is shipped
            # This is the exogenous trigger that motivates agent action
            env_event = shopping_app.update_order_status(order_id=self.bulk_order_id, status="shipped").delayed(
                1
            )  # Notification arrives 1 second after scenario starts

            # Environment event: Delivery-planning email warns about space constraints for large items
            # This explicitly motivates checking saved apartments' square footage before delivery.
            delivery_email_id = "bulk_furniture_delivery_planning_001"
            delivery_email_event = email_app.send_email_to_user_with_id(
                email_id=delivery_email_id,
                sender="delivery@furnishco.example",
                subject="Delivery planning for your furniture shipment",
                content=(
                    "Hi,\n\n"
                    "Your furniture order has shipped. Because these items are large (sectional couch, king bed, dining table, bookshelf), "
                    "please make sure your destination space can accommodate them.\n\n"
                    "If you're still choosing an apartment, we recommend reviewing your saved apartments' square footage and removing very small units "
                    "(e.g., studios or small 1BRs) that won't fit your delivery.\n\n"
                    "Thanks,\n"
                    "FurnishCo Delivery Team"
                ),
            ).delayed(3)

            # Oracle event: Agent reads the delivery email to ground the space-constraint check
            # Motivated by: delivery_email_event arrived with explicit warning to review saved apartments' square footage.
            agent_read_delivery_email = (
                email_app.get_email_by_id(email_id=delivery_email_id, folder_name="INBOX")
                .oracle()
                .depends_on(delivery_email_event, delay_seconds=2)
            )

            # Oracle event: Agent lists orders to discover the bulk furniture order
            # Motivated by: the update_order_status notification showing a shipped order
            agent_list_orders = shopping_app.list_orders().oracle().depends_on(env_event, delay_seconds=10)

            # Oracle event: Agent retrieves the order details to see all furniture items and their dimensions
            # Motivated by: discovering the order from list_orders
            agent_get_order_details = (
                shopping_app.get_order_details(order_id=self.bulk_order_id)
                .oracle()
                .depends_on(agent_list_orders, delay_seconds=5)
            )

            # Oracle event: Agent lists saved apartments to analyze space constraints
            # Motivated by: delivery email explicitly suggests reviewing saved apartments' square footage, and order details
            # confirm multiple large items are being delivered.
            agent_list_saved_apts = (
                apartment_app.list_saved_apartments()
                .oracle()
                .depends_on([agent_get_order_details, agent_read_delivery_email], delay_seconds=10)
            )

            # Oracle event: Agent proposes removing undersized apartments from saved list
            # Motivated by: comparing furniture dimensions to apartment square footages
            agent_proposal = (
                aui.send_message_to_user(
                    content="Your bulk furniture order (sectional couch, king bed, dining table, bookshelf) has shipped. I reviewed your saved apartments and found that two units (350 sq ft studio and 480 sq ft 1BR) are too small to comfortably fit these large pieces. Would you like me to remove these from your saved list so you can focus on apartments with adequate space?"
                )
                .oracle()
                .depends_on(agent_list_saved_apts, delay_seconds=15)
            )

            # User event: User accepts the proposal
            user_acceptance = (
                aui.accept_proposal(content="Yes, please remove the smaller apartments.")
                .oracle()
                .depends_on(agent_proposal, delay_seconds=30)
            )

            # Oracle event: Agent removes the studio apartment from saved list
            # Motivated by: user acceptance + knowledge of which apartments are undersized from the list_saved_apartments results
            agent_remove_studio = (
                apartment_app.remove_saved_apartment(apartment_id=self.apt_id_studio)
                .oracle()
                .depends_on(user_acceptance, delay_seconds=5)
            )

            # Oracle event: Agent removes the small 1BR apartment from saved list
            # Motivated by: same - user acceptance + knowledge from list_saved_apartments results
            agent_remove_1br_small = (
                apartment_app.remove_saved_apartment(apartment_id=self.apt_id_1br_small)
                .oracle()
                .depends_on(user_acceptance, delay_seconds=2)
            )

            # Oracle event: Agent sends summary message to user
            # Motivated by: completion of apartment removal actions
            agent_summary = (
                aui.send_message_to_user(
                    content="Done! I removed the two small apartments. Your saved list now has three spacious options that will comfortably fit your furniture."
                )
                .oracle()
                .depends_on([agent_remove_studio, agent_remove_1br_small], delay_seconds=10)
            )

        # Register ALL events here in self.events
        self.events = [
            env_event,
            delivery_email_event,
            agent_read_delivery_email,
            agent_list_orders,
            agent_get_order_details,
            agent_list_saved_apts,
            agent_proposal,
            user_acceptance,
            agent_remove_studio,
            agent_remove_1br_small,
            agent_summary,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent retrieved order details to discover bulk furniture items
            # Must use list_orders or get_order_details to understand what was shipped
            agent_checked_order = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name in ["list_orders", "get_order_details"]
                for e in log_entries
            )

            # STRICT Check 2: Agent retrieved saved apartments to analyze space
            # Must call list_saved_apartments to see what apartments the user has saved
            agent_checked_apartments = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "list_saved_apartments"
                for e in log_entries
            )

            # FLEXIBLE Check 3: Agent sent proposal/message to user about space constraints
            # Content checking is flexible - just verify the agent communicated with the user
            agent_sent_proposal = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 4: Agent removed the studio apartment (350 sq ft)
            # Must remove the specific undersized apartment
            studio_removed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "remove_saved_apartment"
                and e.action.args.get("apartment_id") == self.apt_id_studio
                for e in log_entries
            )

            # STRICT Check 5: Agent removed the small 1BR apartment (480 sq ft)
            # Must remove the specific undersized apartment
            small_1br_removed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "remove_saved_apartment"
                and e.action.args.get("apartment_id") == self.apt_id_1br_small
                for e in log_entries
            )

            # Determine success and build rationale
            all_checks = {
                "agent_checked_order": agent_checked_order,
                "agent_checked_apartments": agent_checked_apartments,
                "agent_sent_proposal": agent_sent_proposal,
                "studio_removed": studio_removed,
                "small_1br_removed": small_1br_removed,
            }

            success = all(all_checks.values())

            if not success:
                failed_checks = [name for name, passed in all_checks.items() if not passed]
                rationale = f"Validation failed. Missing required agent actions: {', '.join(failed_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
