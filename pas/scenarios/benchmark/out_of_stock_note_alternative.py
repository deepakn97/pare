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


@register_scenario("out_of_stock_note_alternative")
class OutOfStockNoteAlternative(PASScenario):
    """Agent replaces an out-of-stock cart item using alternative product suggestions from a shopping note.

    The user has a note in the "Personal" folder titled "Kitchen Shopping List" that contains a friend's product recommendations, including: "If the Espresso Deluxe Machine is sold out, try the Barista Pro 3000 instead - Sarah says it's even better." The user receives a shopping notification that an item in their cart (Espresso Deluxe Machine) is now out of stock and has been removed. The agent must:
    1. Detect the out-of-stock notification and identify the removed product name
    2. Search the Notes app for references to that product
    3. Extract the recommended alternative (Barista Pro 3000) from the note content
    4. Search the shopping catalog to find the alternative product
    5. Add the alternative product to the cart with the same quantity
    6. Complete checkout after user approval
    7. Update the note with a record of the purchase date and chosen alternative

    This scenario exercises cross-app information retrieval (shopping notification → notes → shopping catalog), natural language parsing of recommendation text, product substitution reasoning, and collaborative note maintenance for shopping coordination..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Create a note in the Personal folder with product alternative recommendations
        # This note contains the friend's suggestion: if Espresso Deluxe Machine is sold out,
        # try Barista Pro 3000 instead
        note_content = """Kitchen Shopping List

Items to buy:
- Coffee maker (high priority!)
- New mugs
- Coffee grinder

Coffee Maker Notes from Sarah:
If the Espresso Deluxe Machine is sold out, try the Barista Pro 3000 instead - Sarah says it's even better. She's been using hers for 6 months and loves it!

Other items:
- Espresso beans (dark roast)
- Milk frother
"""
        self.note.create_note_with_time(
            folder="Personal",
            title="Kitchen Shopping List",
            content=note_content,
            pinned=False,
            created_at="2025-11-17 10:30:00",
            updated_at="2025-11-17 10:30:00",
        )

        # Initialize Shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add the Espresso Deluxe Machine product (will be out of stock)
        espresso_deluxe_pid = self.shopping.add_product(name="Espresso Deluxe Machine")
        self.espresso_deluxe_item_id = self.shopping.add_item_to_product(
            product_id=espresso_deluxe_pid,
            price=299.99,
            options={"color": "silver", "capacity": "1.5L"},
            available=True,  # Initially available, will be marked unavailable in events flow
        )

        # Add the Barista Pro 3000 product (the alternative)
        barista_pro_pid = self.shopping.add_product(name="Barista Pro 3000")
        self.barista_pro_item_id = self.shopping.add_item_to_product(
            product_id=barista_pro_pid, price=349.99, options={"color": "black", "capacity": "2.0L"}, available=True
        )

        # Add some other products to make the catalog realistic
        mug_pid = self.shopping.add_product(name="Premium Coffee Mugs Set")
        self.shopping.add_item_to_product(
            product_id=mug_pid, price=24.99, options={"set_size": "4 pieces", "material": "ceramic"}, available=True
        )

        grinder_pid = self.shopping.add_product(name="Burr Coffee Grinder")
        self.shopping.add_item_to_product(
            product_id=grinder_pid,
            price=89.99,
            options={"type": "burr", "settings": "15 grind settings"},
            available=True,
        )

        # Pre-populate the cart with the Espresso Deluxe Machine (which will be removed due to out-of-stock)
        # NOTE: This represents the user having already added the item to cart before the scenario starts
        self.shopping.add_to_cart(item_id=self.espresso_deluxe_item_id, quantity=1)

        # Register all apps here in self.apps
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
            # Environment event 1: Mark the Espresso Deluxe Machine as unavailable and notify user
            # This is the triggering event - the product becomes out of stock
            out_of_stock_event = shopping_app.update_item(
                item_id=self.espresso_deluxe_item_id, new_availability=False
            ).delayed(10)

            # Oracle event 1: Agent searches notes for the out-of-stock product name
            # Motivation: Agent received out-of-stock notification mentioning "Espresso Deluxe Machine" and needs to check if user has notes about alternatives
            search_notes_event = (
                note_app.search_notes(query="Espresso Deluxe").oracle().depends_on(out_of_stock_event, delay_seconds=2)
            )

            # Oracle event 2: Agent retrieves the specific note containing the alternative recommendation
            # Motivation: Search results showed the "Kitchen Shopping List" note; agent needs to read full content to extract the alternative product name
            get_note_event = (
                note_app.get_note_by_id(note_id=next(iter(note_app.folders["Personal"].notes.keys())))
                .oracle()
                .depends_on(search_notes_event, delay_seconds=1)
            )

            # Oracle event 3: Agent searches shopping catalog for the alternative product mentioned in the note
            # Motivation: Note content explicitly suggests "Barista Pro 3000" as the alternative; agent must find this product in the catalog
            search_alternative_event = (
                shopping_app.search_product(product_name="Barista Pro 3000")
                .oracle()
                .depends_on(get_note_event, delay_seconds=2)
            )

            # Oracle event 4: Agent proposes replacing the out-of-stock item with the alternative
            # Motivation: Agent found matching alternative in catalog and can now propose the substitution to user, citing the note recommendation
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed the Espresso Deluxe Machine in your cart is now out of stock. Your Kitchen Shopping List note suggests trying the Barista Pro 3000 instead (recommended by Sarah). The Barista Pro 3000 is available for $349.99. Would you like me to add it to your cart and proceed with checkout?"
                )
                .oracle()
                .depends_on(search_alternative_event, delay_seconds=2)
            )

            # Oracle event 5: User accepts the proposal
            # Motivation: User agrees with the substitution plan
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please add the Barista Pro 3000 and checkout. And update the notes with your purchase update."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle event 6: Agent adds the alternative product to cart
            # Motivation: User accepted the proposal; agent now executes the substitution by adding Barista Pro 3000 to cart
            add_to_cart_event = (
                shopping_app.add_to_cart(item_id=self.barista_pro_item_id, quantity=1)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle event 7: Agent completes checkout
            # Motivation: Cart now contains the alternative product; user requested checkout in acceptance message
            checkout_event = shopping_app.checkout().oracle().depends_on(add_to_cart_event, delay_seconds=1)

            # Oracle event 8: Agent updates the note with purchase record
            # Motivation: Scenario docstring specifies updating the note with purchase date and chosen alternative for future reference
            update_note_event = (
                note_app.update_note(
                    note_id=next(iter(note_app.folders["Personal"].notes.keys())),
                    content="""Kitchen Shopping List

Items to buy:
- Coffee maker (high priority!)
- New mugs
- Coffee grinder

Coffee Maker Notes from Sarah:
If the Espresso Deluxe Machine is sold out, try the Barista Pro 3000 instead - Sarah says it's even better. She's been using hers for 6 months and loves it!

PURCHASE UPDATE (2025-11-18):
✓ Purchased Barista Pro 3000 as alternative to out-of-stock Espresso Deluxe Machine

Other items:
- Espresso beans (dark roast)
- Milk frother
""",
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            out_of_stock_event,
            search_notes_event,
            get_note_event,
            search_alternative_event,
            proposal_event,
            acceptance_event,
            add_to_cart_event,
            checkout_event,
            update_note_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events (oracle events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent searched notes for the out-of-stock product
            # The agent must use search_notes to find references to the Espresso Deluxe Machine
            search_notes_found = any(
                e.action.class_name == "StatefulNotesApp" and e.action.function_name == "search_notes"
                for e in agent_events
            )

            # STRICT Check 2: Agent retrieved the note content
            # The agent must read the full note to extract the alternative recommendation
            # Accepts either get_note_by_id OR get_note_by_title as equivalent methods
            get_note_found = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["get_note_by_id", "get_note_by_title"]
                for e in agent_events
            )

            # STRICT Check 3: Agent proposed the substitution to user
            # The agent must send a message to the user proposing the alternative
            # We do NOT check exact message content, only that the agent communicated with the user
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent added the alternative product to cart
            # The agent must call add_to_cart to add the Barista Pro 3000
            add_to_cart_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == self.barista_pro_item_id
                for e in agent_events
            )

            # STRICT Check 5: Agent completed checkout
            # The agent must call checkout to finalize the purchase
            checkout_found = any(
                e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "checkout"
                for e in agent_events
            )

            # STRICT Check 6: Agent updated the note with purchase record
            # The agent must call update_note to record the purchase
            # We check that update_note was called, but do NOT assert on exact content
            update_note_found = any(
                e.action.class_name == "StatefulNotesApp" and e.action.function_name == "update_note"
                for e in agent_events
            )

            # Combine all checks
            all_checks_passed = (
                search_notes_found
                and get_note_found
                and proposal_found
                and add_to_cart_found
                and checkout_found
                and update_note_found
            )

            if not all_checks_passed:
                # Build a detailed rationale of what failed
                failures = []
                if not search_notes_found:
                    failures.append("agent did not search notes for out-of-stock product")
                if not get_note_found:
                    failures.append("agent did not retrieve note content")
                if not proposal_found:
                    failures.append("agent did not propose substitution to user")
                if not add_to_cart_found:
                    failures.append("agent did not add alternative product to cart")
                if not checkout_found:
                    failures.append("agent did not complete checkout")
                if not update_note_found:
                    failures.append("agent did not update note with purchase record")

                rationale = "; ".join(failures)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
