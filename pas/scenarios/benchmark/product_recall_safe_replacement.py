"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.shopping import CartItem, Order
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.note import StatefulNotesApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("product_recall_safe_replacement")
class ProductRecallSafeReplacement(PASScenario):
    """Agent handles a product safety recall by cross-referencing purchase history with safety notes and ordering a verified alternative.

    The user receives a shopping notification that a recently ordered item (Baby Formula Pro) has been recalled due to safety concerns and the order has been cancelled. The user maintains a note in the "Personal" folder titled "Baby Product Safety Research" containing verified safe alternatives researched from parenting forums, including: "If Formula Pro is unavailable or recalled, use Organic Baby Formula Plus - pediatrician approved, no safety issues." The agent must:
    1. Detect the recall notification and identify the recalled product name
    2. Search the shopping app to confirm the cancellation and retrieve order details
    3. Search the Notes app for safety-related information about the recalled product
    4. Extract the recommended safe alternative from the note content
    5. Search the shopping catalog to locate the verified alternative product
    6. Add the alternative to the cart and complete checkout
    7. Update the safety research note with the recall date and replacement purchase confirmation

    This scenario exercises time-sensitive safety response, cross-app information retrieval (shopping notification → notes → shopping catalog), trust-based product substitution reasoning with safety constraints, and proactive documentation maintenance for critical consumer safety records.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.note = StatefulNotesApp(name="Notes")
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Populate Notes app with baseline safety research
        # Note: The recalled product (Baby Formula Pro) safety info exists before the recall
        self.note.create_note_with_time(
            folder="Personal",
            title="Baby Product Safety Research",
            content=(
                "Baby Formula Safety Notes:\n\n"
                "Baby Formula Pro - was my first choice, ordered from BabyStore.\n\n"
                "SAFE ALTERNATIVES (if Baby Formula Pro unavailable or recalled):\n"
                "- Organic Baby Formula Plus - pediatrician approved, no safety issues reported\n"
                "- Premium Infant Formula - certified organic, highly rated\n\n"
                "Last updated: 2025-11-15"
            ),
            pinned=False,
            created_at="2025-11-15 08:00:00",
            updated_at="2025-11-15 08:00:00",
        )

        # Populate Shopping app with catalog and order history
        # Add the recalled product to catalog
        recalled_product_id = self.shopping.add_product("Baby Formula Pro")
        recalled_item_id = self.shopping.add_item_to_product(
            product_id=recalled_product_id,
            price=29.99,
            options={"size": "24oz", "type": "powder"},
            available=True,  # Initially available, will be recalled via event
        )

        # Add the safe alternative product to catalog
        alternative_product_id = self.shopping.add_product("Organic Baby Formula Plus")
        alternative_item_id = self.shopping.add_item_to_product(
            product_id=alternative_product_id,
            price=34.99,
            options={"size": "24oz", "type": "powder", "organic": True},
            available=True,
        )

        # Add another alternative mentioned in notes
        other_alternative_id = self.shopping.add_product("Premium Infant Formula")
        other_alternative_item_id = self.shopping.add_item_to_product(
            product_id=other_alternative_id,
            price=32.99,
            options={"size": "24oz", "type": "powder", "organic": True},
            available=True,
        )

        # Seed a recent order for the recalled product (placed 2 days ago)
        # This order will be cancelled by the recall notification
        recall_order_date = datetime(2025, 11, 16, 10, 30, 0, tzinfo=UTC)
        recall_order_id = "order_baby_formula_001"
        self.shopping.orders[recall_order_id] = Order(
            order_id=recall_order_id,
            order_status="processed",
            order_date=recall_order_date,
            order_total=59.98,  # 2 x $29.99
            order_items={
                recalled_item_id: CartItem(
                    item_id=recalled_item_id,
                    quantity=2,
                    price=29.99,
                    available=True,
                    options={"size": "24oz", "type": "powder"},
                )
            },
        )

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
            # Environment Event 1: Product recall notification - order cancelled
            # The shopping app sends a notification that the Baby Formula Pro order has been recalled and cancelled
            recall_notification_event = shopping_app.cancel_order(order_id="order_baby_formula_001").delayed(2)

            # Oracle Event 1: Agent checks cancelled order details to understand what was recalled
            # Motivation: The cancel_order notification triggers the agent to investigate which product was affected
            check_order_event = (
                shopping_app.get_order_details(order_id="order_baby_formula_001")
                .oracle()
                .depends_on(recall_notification_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent searches notes for safety information about the recalled product
            # Motivation: Agent needs to find trusted alternative recommendations for the recalled baby formula
            search_notes_event = (
                note_app.search_notes(query="Baby Formula").oracle().depends_on(check_order_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent retrieves the specific safety research note to extract alternative
            # Motivation: The search revealed a "Baby Product Safety Research" note; agent reads it for the safe alternative
            get_note_event = (
                note_app.get_note_by_id(note_id=next(iter(note_app.folders["Personal"].notes.keys())))
                .oracle()
                .depends_on(search_notes_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent proposes ordering the safe alternative from the note
            # Motivation: Agent found the recall notification and identified "Organic Baby Formula Plus" as the pediatrician-approved alternative
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your Baby Formula Pro order was cancelled due to a product recall. I found your safety research note recommending Organic Baby Formula Plus as a pediatrician-approved alternative. Would you like me to order it to replace the recalled product?"
                )
                .oracle()
                .depends_on(get_note_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please order the safe alternative with same quantity.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent searches shopping catalog for the alternative product
            # Motivation: Agent needs to find the product_id for "Organic Baby Formula Plus" to proceed with ordering
            search_product_event = (
                shopping_app.search_product(product_name="Organic Baby Formula Plus")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent gets product details to find the correct item_id
            # Motivation: search_product returned the product; agent needs the item_id from variants to add to cart
            get_product_event = (
                shopping_app.get_product_details(product_id=list(shopping_app.products.values())[1].product_id)
                .oracle()
                .depends_on(search_product_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent adds the safe alternative to cart
            # Motivation: Agent now has the item_id and can add the verified alternative to cart
            add_to_cart_event = (
                shopping_app.add_to_cart(
                    item_id=next(iter(list(shopping_app.products.values())[1].variants.values())).item_id,
                    quantity=2,
                )
                .oracle()
                .depends_on(get_product_event, delay_seconds=2)
            )

            # Oracle Event 9: Agent completes checkout
            # Motivation: Cart now contains the safe alternative; agent proceeds to complete the order
            checkout_event = shopping_app.checkout().oracle().depends_on(add_to_cart_event, delay_seconds=2)

        # TODO: Register ALL events here in self.events
        self.events = [
            recall_notification_event,
            check_order_event,
            search_notes_event,
            get_note_event,
            proposal_event,
            acceptance_event,
            search_product_event,
            get_product_event,
            add_to_cart_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal to the user about ordering the safe alternative
            # STRICT: must send proposal via send_message_to_user
            # FLEXIBLE: exact message wording can vary
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent investigated the cancelled order to identify the recalled product
            # STRICT: must check order details to understand what was recalled
            order_check_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                and e.action.args.get("order_id") == "order_baby_formula_001"
                for e in log_entries
            )

            # Check 3: Agent searched notes for safety information about the recalled product
            # STRICT: must search notes (using search_notes or list_notes)
            # FLEXIBLE: query terms can vary (e.g., "Baby Formula", "Baby", "Formula", "safety")
            notes_search_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["search_notes", "list_notes"]
                for e in log_entries
            )

            # Check 4: Agent retrieved the specific safety research note
            # STRICT: must read note content to extract the safe alternative
            note_read_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "get_note_by_id"
                for e in log_entries
            )

            # Check 5: Agent searched for the alternative product in the shopping catalog
            # STRICT: must search for product (using search_product or list_products)
            # FLEXIBLE: product name variations acceptable (e.g., "Organic Baby Formula Plus", "Organic Baby Formula")
            product_search_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name in ["search_product", "list_products"]
                for e in log_entries
            )

            # Check 6: Agent got product details to find the correct item_id
            # STRICT: must retrieve product details before adding to cart
            product_details_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_product_details"
                for e in log_entries
            )

            # Check 7: Agent added the safe alternative to cart
            # STRICT: must add item to cart with quantity 2 (matching original order)
            add_to_cart_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("quantity") == 2
                for e in log_entries
            )

            # Check 8: Agent completed checkout
            # STRICT: must complete checkout to finalize the replacement order
            checkout_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                for e in log_entries
            )

            # Collect missing checks for rationale
            missing_checks = []
            if not proposal_found:
                missing_checks.append("agent proposal to user about ordering safe alternative")
            if not order_check_found:
                missing_checks.append("cancelled order investigation (get_order_details)")
            if not notes_search_found:
                missing_checks.append("safety notes search")
            if not note_read_found:
                missing_checks.append("safety research note retrieval (get_note_by_id)")
            if not product_search_found:
                missing_checks.append("alternative product search in catalog")
            if not product_details_found:
                missing_checks.append("product details retrieval (get_product_details)")
            if not add_to_cart_found:
                missing_checks.append("adding safe alternative to cart with quantity 2")
            if not checkout_found:
                missing_checks.append("checkout completion")

            success = (
                proposal_found
                and order_check_found
                and notes_search_found
                and note_read_found
                and product_search_found
                and product_details_found
                and add_to_cart_found
                and checkout_found
            )

            rationale = None if success else f"Missing critical checks: {', '.join(missing_checks)}"
            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
