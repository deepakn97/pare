"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.note import StatefulNotesApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("discount_shopping_from_shared_note")
class DiscountShoppingFromSharedNote(PASScenario):
    """Agent completes a shared shopping list using available discount codes from a collaborative note.

    The user has a note in the "Personal" folder titled "Black Friday Deals - Share with roommate" that contains a list of discount codes for various products (e.g., "WINTER25 - 25% off winter jackets", "TECH15 - 15% off electronics"). The user receives a shopping notification about an abandoned cart reminder for a winter jacket. Shortly after, the user receives another notification indicating that several items from their wishlist are now on sale. The agent must:
    1. Detect the shopping notifications and identify the products mentioned
    2. Search the Notes app for relevant discount codes by product category
    3. Verify which discount codes apply to the cart items using shopping app tools
    4. Apply the best available discount code to maximize savings
    5. Complete the checkout with the applied discount
    6. Update the shared note with a record of which codes were used and the savings achieved

    This scenario exercises cross-app information retrieval (notes -> shopping), discount code validation, cart management, strategic decision-making for maximizing value, and collaborative note updating to track shared resources..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Initialize Shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Populate Notes app with discount code note in Personal folder
        # This note contains discount codes shared with roommate
        discount_note_content = """Black Friday Deals - Discount Codes:

WINTER25 - 25% off winter jackets
TECH15 - 15% off electronics
HOME10 - 10% off home decor
FASHION20 - 20% off clothing

These codes expire end of November. Let me know which ones you use!"""

        self.discount_note_id = self.note.create_note_with_time(
            folder="Personal",
            title="Black Friday Deals - Share with roommate",
            content=discount_note_content,
            pinned=False,
            created_at="2025-11-15 10:00:00",
            updated_at="2025-11-15 10:00:00",
        )

        # Populate Shopping app with products and variants
        # Add winter jacket product
        jacket_product_id = self.shopping.add_product(name="Premium Winter Jacket")
        self.jacket_item_id = self.shopping.add_item_to_product(
            product_id=jacket_product_id, price=120.00, options={"color": "navy", "size": "medium"}, available=True
        )

        # Add electronics product (wireless headphones)
        headphones_product_id = self.shopping.add_product(name="Wireless Noise-Cancelling Headphones")
        headphones_item_id = self.shopping.add_item_to_product(
            product_id=headphones_product_id, price=200.00, options={"color": "black"}, available=True
        )

        # Add home decor product
        lamp_product_id = self.shopping.add_product(name="Modern LED Desk Lamp")
        lamp_item_id = self.shopping.add_item_to_product(
            product_id=lamp_product_id, price=50.00, options={"color": "white"}, available=True
        )

        # Add discount codes for the items
        self.shopping.add_discount_code(self.jacket_item_id, {"WINTER25": 25.0})
        self.shopping.add_discount_code(headphones_item_id, {"TECH15": 15.0})
        self.shopping.add_discount_code(lamp_item_id, {"HOME10": 10.0})

        # Pre-populate cart with winter jacket (abandoned cart scenario)
        self.shopping.add_to_cart(item_id=self.jacket_item_id, quantity=1)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Cart reminder notification triggers the scenario
            cart_reminder_event = shopping_app.update_item(item_id=self.jacket_item_id, new_price=120.00).delayed(10)

            # Oracle Event 1: Agent observes the cart contents to understand what's in the abandoned cart
            # Motivation: The cart reminder notification prompts the agent to check what items need attention
            check_cart_event = shopping_app.list_cart().oracle().depends_on(cart_reminder_event, delay_seconds=2)

            # Oracle Event 2: Agent searches notes for discount codes related to the cart item (winter jacket)
            # Motivation: The cart contains a winter jacket, so the agent searches for "winter" discount codes in notes
            search_discount_event = (
                note_app.search_notes(query="winter").oracle().depends_on(check_cart_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent retrieves the specific note by ID to get all discount codes
            # Motivation: The search revealed a discount codes note; now fetch the full content to extract codes
            get_note_event = (
                note_app.get_note_by_id(note_id=self.discount_note_id)
                .oracle()
                .depends_on(search_discount_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent checks which discount codes are available for cart items
            # Motivation: The note contains "WINTER25"; verify if this code applies to the jacket in the cart
            check_discount_event = (
                shopping_app.get_discount_code_info(discount_code="WINTER25")
                .oracle()
                .depends_on(get_note_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent sends proposal to user citing the cart reminder and available discount
            # Motivation: Cart reminder notification + discovered WINTER25 discount code from shared note
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you have a Premium Winter Jacket in your cart. I found a WINTER25 discount code in your shared note that gives 25% off, saving you $30. Would you like me to complete the checkout with this discount?"
                )
                .oracle()
                .depends_on([cart_reminder_event, check_discount_event], delay_seconds=2)
            )

            # Oracle Event 6: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please apply the discount and checkout.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent completes checkout with the discount code
            # Motivation: User accepted the proposal to use WINTER25 discount for checkout
            checkout_event = (
                shopping_app.checkout(discount_code="WINTER25").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            cart_reminder_event,
            check_cart_event,
            search_discount_event,
            get_note_event,
            check_discount_event,
            proposal_event,
            acceptance_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT event types (oracle events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent must check the cart to identify what needs attention
            # Accept list_cart() as the primary method
            check_cart_found = any(
                e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "list_cart"
                for e in agent_events
            )

            # STRICT Check 2: Agent must search notes for discount codes
            # Accept search_notes() or get_note_by_id() as valid ways to access note information
            search_notes_found = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["search_notes", "get_note_by_id"]
                for e in agent_events
            )

            # STRICT Check 3: Agent must verify the discount code applicability
            # Accept get_discount_code_info() as the verification method
            verify_discount_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_discount_code_info"
                and e.action.args.get("discount_code") == "WINTER25"
                for e in agent_events
            )

            # STRICT Check 4: Agent must send a proposal to the user
            # Check for send_message_to_user() call (content is flexible)
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 5: Agent must complete the checkout with the discount code
            # Accept checkout() with discount_code="WINTER25"
            checkout_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "WINTER25"
                for e in agent_events
            )

            # Collect all strict checks
            all_checks_passed = (
                check_cart_found and search_notes_found and verify_discount_found and proposal_found and checkout_found
            )

            # Build rationale for failures
            if not all_checks_passed:
                missing_checks = []
                if not check_cart_found:
                    missing_checks.append("agent did not check cart contents")
                if not search_notes_found:
                    missing_checks.append("agent did not search notes for discount codes")
                if not verify_discount_found:
                    missing_checks.append("agent did not verify WINTER25 discount code applicability")
                if not proposal_found:
                    missing_checks.append("agent did not send proposal to user")
                if not checkout_found:
                    missing_checks.append("agent did not complete checkout with WINTER25 discount")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
