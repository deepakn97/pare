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
from pare.apps.shopping import StatefulShoppingApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("move_in_required_items_cart_prep")
class MoveInRequiredItemsCartPrep(PAREScenario):
    """Agent populates shopping cart with required move-in items extracted from apartment lease confirmation email.

    The user receives a lease approval confirmation email from "Riverside Towers Leasing Office" for apartment unit 402B. The email contains a section titled "Required Items for Move-In" listing: door mats (for unit entrance), smoke detector batteries (tenant responsibility), and window blinds (not provided by landlord). The user's shopping cart is currently empty. The agent must:
    1. Detect and read the lease confirmation email
    2. Extract the list of required move-in items from the email body
    3. Search the shopping catalog for matching products (door mat, batteries for smoke detectors, window blinds)
    4. Add appropriate items to the cart with reasonable quantities
    5. Notify the user that move-in requirements have been prepared in their cart
    6. Upon user acceptance, confirm the cart is ready for review or checkout

    This scenario exercises extracting structured information from unstructured email text, translating natural language requirements into product searches, autonomous cart population based on external obligations, and preparing actionable shopping lists from apartment-domain events.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        # Initialize core apps
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize shopping app and populate with products
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add door mat product
        door_mat_pid = self.shopping.add_product(name="Welcome Door Mat")
        self.door_mat_item_id = self.shopping.add_item_to_product(
            product_id=door_mat_pid, price=24.99, options={"color": "brown", "size": "24x36 inches"}, available=True
        )

        # Add smoke detector batteries
        batteries_pid = self.shopping.add_product(name="9V Batteries for Smoke Detectors")
        self.batteries_item_id = self.shopping.add_item_to_product(
            product_id=batteries_pid, price=12.99, options={"pack_size": "4-pack", "type": "alkaline"}, available=True
        )

        # Add window blinds
        blinds_pid = self.shopping.add_product(name="Cordless Window Blinds")
        self.blinds_item_id = self.shopping.add_item_to_product(
            product_id=blinds_pid, price=45.99, options={"color": "white", "width": "36 inches"}, available=True
        )

        # Cart is empty by default (no seeding needed)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        # Use stored item IDs from initialization
        # These represent item IDs that the agent would discover through search/list operations
        doormat_item_id = self.door_mat_item_id
        batteries_item_id = self.batteries_item_id
        blinds_item_id = self.blinds_item_id

        with EventRegisterer.capture_mode():
            # Environment Event 1: Lease confirmation email arrives with required items list
            lease_email_event = email_app.send_email_to_user_with_id(
                email_id="lease_confirmation_001",
                sender="leasing@riversidetowers.com",
                subject="Lease Approved - Unit 402B Move-In Requirements",
                content="""Dear Tenant,

Congratulations! Your lease application for Unit 402B at Riverside Towers has been approved. Your move-in date is scheduled for December 1st, 2025.

Required Items for Move-In:
To ensure a smooth move-in process, please note that the following items are the tenant's responsibility and must be provided:

1. Door mats - Required for unit entrance (not provided by landlord)
2. Smoke detector batteries - Tenant responsibility to maintain (9V batteries recommended)
3. Window blinds - Not provided by landlord, must be installed by tenant

Please ensure all items are ready by your move-in date. If you have any questions, feel free to contact our leasing office.

Best regards,
Riverside Towers Leasing Office""",
            ).delayed(10)

            # Oracle Event 1: Agent reads the lease confirmation email to extract requirements
            # Motivated by: the environment event delivered a new email notification
            read_email_event = (
                email_app.get_email_by_id(email_id="lease_confirmation_001", folder_name="INBOX")
                .oracle()
                .depends_on(lease_email_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent searches for door mat product
            # Motivated by: the email content lists "door mats" as a required item
            search_doormat_event = (
                shopping_app.search_product(product_name="door mat", offset=0, limit=10)
                .oracle()
                .depends_on(read_email_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent searches for smoke detector batteries
            # Motivated by: the email content lists "smoke detector batteries" as a required item
            search_batteries_event = (
                shopping_app.search_product(product_name="batteries smoke detector", offset=0, limit=10)
                .oracle()
                .depends_on(read_email_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent searches for window blinds
            # Motivated by: the email content lists "window blinds" as a required item
            search_blinds_event = (
                shopping_app.search_product(product_name="window blinds", offset=0, limit=10)
                .oracle()
                .depends_on(read_email_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent lists all products to see what's available
            # Motivated by: after searching, need to see the full product catalog to identify products and their item IDs for cart operations
            list_products_event = (
                shopping_app.list_all_products(offset=0, limit=10)
                .oracle()
                .depends_on([search_doormat_event, search_batteries_event, search_blinds_event], delay_seconds=1)
            )

            # Oracle Event 6: Agent sends proposal to user BEFORE modifying the cart
            # Motivated by: lease email requirements (read_email_event) + product discovery (list_products_event)
            proposal_event = (
                aui.send_message_to_user(
                    content="I reviewed your lease approval for Unit 402B and found three required move-in items: a door mat, smoke detector batteries, and window blinds. I found matching products in your shopping catalog. Would you like me to add these items to your cart so it's ready for checkout?"
                )
                .oracle()
                .depends_on([read_email_event, list_products_event], delay_seconds=2)
            )

            # Oracle Event 7: User accepts the proposal
            # Motivated by: user wants the agent to proceed with adding the required items to the cart
            acceptance_event = (
                aui.accept_proposal(content="Yes, that sounds great. Please confirm the cart is ready.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 8: Agent adds door mat to cart (after user approval)
            # Motivated by: user accepted proposal + discovered item_id from list_products_event
            add_doormat_event = (
                shopping_app.add_to_cart(item_id=doormat_item_id, quantity=1)
                .oracle()
                .depends_on([acceptance_event, list_products_event], delay_seconds=2)
            )

            # Oracle Event 9: Agent adds batteries to cart (after user approval)
            # Motivated by: user accepted proposal + discovered item_id from list_products_event
            add_batteries_event = (
                shopping_app.add_to_cart(item_id=batteries_item_id, quantity=1)
                .oracle()
                .depends_on([acceptance_event, list_products_event], delay_seconds=2)
            )

            # Oracle Event 10: Agent adds window blinds to cart (after user approval)
            # Motivated by: user accepted proposal + discovered item_id from list_products_event
            add_blinds_event = (
                shopping_app.add_to_cart(item_id=blinds_item_id, quantity=1)
                .oracle()
                .depends_on([acceptance_event, list_products_event], delay_seconds=2)
            )

            # Oracle Event 11: Agent confirms cart is ready by listing cart contents
            # Motivated by: user requested confirmation; agent verifies all items are in cart after adding them
            confirm_cart_event = (
                shopping_app.list_cart()
                .oracle()
                .depends_on([add_doormat_event, add_batteries_event, add_blinds_event], delay_seconds=1)
            )

            # Oracle Event 12: Agent sends final confirmation message
            # Motivated by: list_cart confirmed all three items present; fulfilling user's request for confirmation
            final_message_event = (
                aui.send_message_to_user(
                    content="Your cart is ready with all three required move-in items (door mat, batteries, and window blinds). Total items: 3. You can review and checkout whenever you're ready."
                )
                .oracle()
                .depends_on(confirm_cart_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            lease_email_event,
            read_email_event,
            search_doormat_event,
            search_batteries_event,
            search_blinds_event,
            list_products_event,
            proposal_event,
            acceptance_event,
            add_doormat_event,
            add_batteries_event,
            add_blinds_event,
            confirm_cart_event,
            final_message_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events (EventType.AGENT)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent read the lease confirmation email
            read_email_found = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                and e.action.args.get("email_id") == "lease_confirmation_001"
                for e in agent_events
            )

            # STRICT Check 2: Agent added all three required items to cart
            expected_item_ids = {self.door_mat_item_id, self.batteries_item_id, self.blinds_item_id}
            added_item_ids = {
                e.action.args.get("item_id")
                for e in agent_events
                if e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id")
            }
            all_items_added = len(added_item_ids) == 3 and added_item_ids == expected_item_ids

            # STRICT Check 3: Agent sent a proposal to user
            proposal_sent = any(
                e.action.class_name == "PAREAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Determine success based on STRICT checks only
            success = read_email_found and all_items_added and proposal_sent

            # Build rationale if validation fails
            if not success:
                missing_checks = []
                if not read_email_found:
                    missing_checks.append("agent did not read lease confirmation email")
                if not all_items_added:
                    missing_checks.append(
                        f"agent did not add all three required items to cart (found {len(added_item_ids)}/3, expected {expected_item_ids})"
                    )
                if not proposal_sent:
                    missing_checks.append("agent did not send proposal to user")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
