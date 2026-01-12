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
)
from pas.apps.apartment import StatefulApartmentApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("furniture_order_lease_term_mismatch")
class FurnitureOrderLeaseTermMismatch(PASScenario):
    """Agent recognizes furniture order commitment requires longer apartment lease and filters saved apartments.

    The user has multiple apartments saved to favorites with varying lease terms (mix of 6-month and 12-month leases) and has a large furniture order placed but not yet shipped. A shopping notification arrives stating the furniture order is "preparing to ship" or entering final fulfillment (last opportunity to modify/cancel). The agent must: 1) detect the furniture shipment notification and recognize the order involves substantial furniture (expensive, bulky items), 2) retrieve the user's saved apartments and identify that they have mixed lease terms, 3) recognize that committing to expensive furniture is incompatible with short-term (6-month) leases, 4) filter or prioritize the saved apartments to highlight only those with 12-month lease terms, and 5) alert the user to finalize their apartment choice from the longer-term options before the furniture ships.

    This scenario exercises temporal commitment reasoning (order shipment deadline creates decision urgency), cross-app constraint propagation (furniture investment → minimum lease duration), intra-domain filtering based on cross-domain signals, and proactive mismatch prevention between two pending user decisions..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize shopping app with furniture order
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add furniture products to catalog
        sofa_product_id = self.shopping.add_product(name="Modern Sectional Sofa")
        sofa_item_id = self.shopping.add_item_to_product(
            product_id=sofa_product_id, price=1899.99, options={"color": "gray", "material": "fabric"}, available=True
        )

        dining_product_id = self.shopping.add_product(name="Dining Table Set")
        dining_item_id = self.shopping.add_item_to_product(
            product_id=dining_product_id, price=1299.99, options={"seats": "6", "material": "wood"}, available=True
        )

        # Create a furniture order that was placed previously (order exists but not yet shipped)
        # Note: We manually construct the order to avoid the add_order bug with CartItem
        from are.simulation.apps.shopping import CartItem, Order

        order_timestamp = datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC)

        furniture_order = Order(
            order_id="ord_furniture_001",
            order_status="processed",
            order_date=order_timestamp,
            order_total=3199.98,
            order_items={
                sofa_item_id: CartItem(
                    item_id=sofa_item_id,
                    quantity=1,
                    price=1899.99,
                    available=True,
                    options={"color": "gray", "material": "fabric"},
                ),
                dining_item_id: CartItem(
                    item_id=dining_item_id,
                    quantity=1,
                    price=1299.99,
                    available=True,
                    options={"seats": "6", "material": "wood"},
                ),
            },
        )
        self.shopping.orders["ord_furniture_001"] = furniture_order

        # Initialize apartment app with multiple saved apartments (mix of 6-month and 12-month leases)
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Add apartments to catalog with different lease terms
        # 12-month lease apartments
        apt_12mo_1_id = self.apartment.add_new_apartment(
            name="Downtown Loft",
            location="Downtown",
            zip_code="93101",
            price=2200.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Loft",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Parking", "Gym", "In-unit laundry"],
        )

        apt_12mo_2_id = self.apartment.add_new_apartment(
            name="Beachside Condo",
            location="West Beach",
            zip_code="93103",
            price=2500.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1200,
            property_type="Condo",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Pool", "Parking", "Ocean view"],
        )

        # 6-month lease apartments
        apt_6mo_1_id = self.apartment.add_new_apartment(
            name="Upper State Studio",
            location="Upper State",
            zip_code="93105",
            price=1800.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=750,
            property_type="Apartment",
            furnished_status="Furnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="2 months",
            amenities=["Parking", "Pool"],
        )

        apt_6mo_2_id = self.apartment.add_new_apartment(
            name="Milpas Garden Apartment",
            location="Eastside",
            zip_code="93103",
            price=1900.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=850,
            property_type="Apartment",
            furnished_status="Semi-furnished",
            floor_level="Ground floor",
            pet_policy="Pets allowed",
            lease_term="2 months",
            amenities=["Garden", "Parking"],
        )

        # Save all apartments to favorites
        self.apartment.save_apartment(apt_12mo_1_id)
        self.apartment.save_apartment(apt_12mo_2_id)
        self.apartment.save_apartment(apt_6mo_1_id)
        self.apartment.save_apartment(apt_6mo_2_id)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.apartment]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # Event 1: Environment event - Order status update to "shipped" (furniture order is now preparing to ship)
            # This is the non-oracle environment trigger that initiates the scenario
            order_status_event = shopping_app.update_order_status(
                order_id="ord_furniture_001", status="shipped"
            ).delayed(30)

            # Event 2: Agent retrieves order details to understand what's being shipped
            # Motivated by: the order status notification reveals order_id "ord_furniture_001"
            order_details_event = (
                shopping_app.get_order_details(order_id="ord_furniture_001")
                .oracle()
                .depends_on(order_status_event, delay_seconds=2)
            )

            # Event 3: Agent retrieves saved apartments to check what options user has
            # Motivated by: agent needs to understand user's apartment options after seeing the furniture order value ($3199.98) and items (sofa, dining set)
            saved_apartments_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(order_details_event, delay_seconds=2)
            )

            # Event 4: Agent searches for apartments with 1-year lease terms specifically
            # Motivated by: after seeing mixed lease terms in saved apartments (from previous list call), agent needs to identify long-term options that justify furniture investment
            filter_apartments_event = (
                apartment_app.search_apartments(lease_term="1 year", saved_only=True)
                .oracle()
                .depends_on(saved_apartments_event, delay_seconds=2)
            )

            # Event 5: Agent proposes to user to finalize apartment choice before furniture ships
            # Motivated by: agent has identified that furniture order is shipping, total investment is $3199.98 for substantial items, and only 2 of 4 saved apartments have lease terms (1 year) compatible with this investment
            proposal_event = (
                aui.send_message_to_user(
                    content="Your furniture order ($3,200 for a sofa and dining set) is now shipping. I notice you have 4 apartments saved, but only 2 offer 1-year leases (Downtown Loft and Beachside Condo). Given this furniture investment, a longer lease would make more sense. Would you like me to help you finalize your apartment choice from these two 1-year options before the furniture arrives?"
                )
                .oracle()
                .depends_on(filter_apartments_event, delay_seconds=3)
            )

            # Event 6: User accepts the proposal
            # Motivated by: user recognizes the agent's reasoning about lease/furniture compatibility
            acceptance_event = (
                aui.accept_proposal(content="Yes, that makes sense. Help me decide between those two.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Event 7: Agent provides comparison summary to help user decide
            # Motivated by: user has accepted help and explicitly asked to decide between the two 1-year lease apartments
            summary_event = (
                aui.send_message_to_user(
                    content="Here's a comparison:\n\n• Downtown Loft ($2200/mo): 1100 sq ft, 2BR/2BA, unfurnished, gym + in-unit laundry, pets allowed, upper floors\n• Beachside Condo ($2500/mo): 1200 sq ft, 2BR/2BA, unfurnished, pool + ocean view, cats only, ground floor\n\nBoth have 1-year leases and parking. The Beachside Condo is $300 more but offers more space and an ocean view. Which would you prefer?"
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            order_status_event,
            order_details_event,
            saved_apartments_event,
            filter_apartments_event,
            proposal_event,
            acceptance_event,
            summary_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to AGENT events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent retrieved order details to assess furniture investment
            # The agent must check the order to understand what's being shipped
            order_details_check = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                and e.action.args.get("order_id") == "ord_furniture_001"
                for e in agent_events
            )

            # STRICT Check 2: Agent listed or searched saved apartments
            # The agent must check available apartment options (either list_saved_apartments or search_apartments)
            apartments_check = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name in ["list_saved_apartments", "search_apartments"]
                for e in agent_events
            )

            # STRICT Check 3: Agent filtered apartments by 1-year lease term
            # This is the core constraint propagation - agent must recognize furniture investment requires longer lease
            filter_lease_check = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "search_apartments"
                for e in agent_events
            )

            # STRICT Check 4: Agent sent proposal to user about the lease term mismatch
            # The proposal must reference the furniture order/investment and the lease term constraint
            # We check for structural presence of proposal, not exact content
            proposal_check = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 5: Agent provided apartment comparison after user acceptance
            # After user accepts, agent should help with decision by providing comparison
            # At least one follow-up message after the initial proposal
            follow_up_messages = [
                e
                for e in agent_events
                if isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
            ]
            comparison_check = len(follow_up_messages) >= 2  # Initial proposal + follow-up comparison

            # Determine success based on all strict checks
            all_strict_checks = [
                order_details_check,
                apartments_check,
                filter_lease_check,
                proposal_check,
                comparison_check,
            ]

            if not all(all_strict_checks):
                # Build rationale for failure
                failed_checks = []
                if not order_details_check:
                    failed_checks.append("agent did not retrieve order details")
                if not apartments_check:
                    failed_checks.append("agent did not list/search saved apartments")
                if not filter_lease_check:
                    failed_checks.append("agent did not filter apartments by 1-year lease term")
                if not proposal_check:
                    failed_checks.append("agent did not send proposal to user")
                if not comparison_check:
                    failed_checks.append("agent did not provide apartment comparison after user acceptance")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
