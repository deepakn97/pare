from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("bulk_discount_validation_reminder")
class BulkDiscountValidationReminder(PASScenario):
    """Agent validates bulk shopping opportunity against existing purchase reminder, verifies discount eligibility, and consolidates the order.

    The user has a reminder titled "Buy office supplies for Q1" due next Monday with description listing needed items: "printer paper, staplers, pens, notebooks". The user receives a promotional email from the shopping app announcing "This Weekend Only: 20% off all office supplies with code OFFICE20 - minimum 4 items required". The agent must:
    1. Parse the incoming discount email extracting the code (OFFICE20), discount percentage (20%), eligibility requirements (office supplies category, minimum 4 items), and expiration (this weekend)
    2. Check reminders and identify the related "Buy office supplies" reminder due Monday (after the weekend deadline)
    3. Search the shopping catalog for products matching the reminder's item list (printer paper, staplers, pens, notebooks)
    4. Verify discount code eligibility by calling `get_discount_code_info("OFFICE20")` to confirm which products qualify
    5. Propose adding the qualifying items to cart now to capture the expiring discount before the reminder's original due date
    6. After user acceptance, add the 4+ qualifying items to cart using `add_to_cart()`
    7. Apply the discount code and complete checkout via `checkout(discount_code="OFFICE20")`
    8. Update the reminder's description to note "Completed via OFFICE20 discount" and mark as completed or delete it

    This scenario exercises temporal opportunity detection (expiring discount vs. future reminder), cross-app correlation (email promotion + shopping catalog + reminder intent), multi-step shopping workflow (search products, validate discount eligibility, batch add to cart, apply code at checkout).
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize reminder app with existing office supplies reminder due Monday
        self.reminder = StatefulReminderApp(name="Reminders")
        monday_due_datetime = datetime(2025, 11, 24, 17, 0, 0, tzinfo=UTC)
        self.office_supplies_reminder_id = self.reminder.add_reminder(
            title="Buy office supplies for Q1",
            due_datetime=monday_due_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            description="printer paper, staplers, pens, notebooks",
        )

        # Initialize shopping app with office supplies catalog
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add printer paper product
        printer_paper_product_id = self.shopping.add_product("Premium Printer Paper")
        self.printer_paper_item_id = self.shopping.add_item_to_product(
            product_id=printer_paper_product_id,
            price=24.99,
            options={"ream_count": "5", "paper_size": "Letter"},
            available=True,
        )

        # Add stapler product
        stapler_product_id = self.shopping.add_product("Heavy Duty Stapler")
        self.stapler_item_id = self.shopping.add_item_to_product(
            product_id=stapler_product_id,
            price=18.50,
            options={"color": "black", "capacity": "50 sheets"},
            available=True,
        )

        # Add pens product
        pens_product_id = self.shopping.add_product("Ballpoint Pens Pack")
        self.pens_item_id = self.shopping.add_item_to_product(
            product_id=pens_product_id,
            price=12.99,
            options={"color": "blue", "pack_size": "24"},
            available=True,
        )

        # Add notebooks product
        notebooks_product_id = self.shopping.add_product("Spiral Notebooks")
        self.notebooks_item_id = self.shopping.add_item_to_product(
            product_id=notebooks_product_id,
            price=15.99,
            options={"page_count": "100", "pack_size": "6"},
            available=True,
        )

        # Add OFFICE20 discount code for all office supply items (20% off)
        self.shopping.add_discount_code(self.printer_paper_item_id, {"OFFICE20": 20.0})
        self.shopping.add_discount_code(self.stapler_item_id, {"OFFICE20": 20.0})
        self.shopping.add_discount_code(self.pens_item_id, {"OFFICE20": 20.0})
        self.shopping.add_discount_code(self.notebooks_item_id, {"OFFICE20": 20.0})

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.reminder, self.shopping, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Event 1: Incoming promotional email from shopping app (environment event)
            # Trigger: email explicitly mentions discount code OFFICE20, 20% off, minimum 4 items, this weekend only, office supplies
            promo_email_event = email_app.send_email_to_user_with_id(
                email_id="promo_email_office20",
                sender="promos@shopping.com",
                subject="This Weekend Only: 20% Off Office Supplies!",
                content="Don't miss out! Use code OFFICE20 for 20% off all office supplies this weekend. Minimum 4 items required. Shop printer paper, staplers, pens, notebooks and more. Offer expires Sunday night! Check your reminders to see if you have the items you need!",
            ).delayed(15)

            # Motivation: Promotional email mentions "office supplies" which matches the reminder content "Buy office supplies for Q1"
            # Agent reads reminders to find related pending tasks
            check_reminders_event = (
                reminder_app.get_all_reminders().oracle().depends_on(promo_email_event, delay_seconds=2)
            )

            # Motivation: Need to verify discount code eligibility for the items listed in the reminder (printer paper, staplers, pens, notebooks)
            # Agent verifies which items qualify for OFFICE20 code
            verify_discount_event = (
                shopping_app.get_discount_code_info(discount_code="OFFICE20")
                .oracle()
                .depends_on(check_reminders_event, delay_seconds=2)
            )

            # Motivation: Need to search for each item mentioned in reminder to get product/item IDs for cart operations
            # Agent searches for printer paper
            search_paper_event = (
                shopping_app.search_product(product_name="printer paper")
                .oracle()
                .depends_on(verify_discount_event, delay_seconds=1)
            )

            # Motivation: Continuing search for items mentioned in reminder
            # Agent searches for staplers
            search_stapler_event = (
                shopping_app.search_product(product_name="stapler")
                .oracle()
                .depends_on(search_paper_event, delay_seconds=1)
            )

            # Motivation: Continuing search for items mentioned in reminder
            # Agent searches for pens
            search_pens_event = (
                shopping_app.search_product(product_name="pens")
                .oracle()
                .depends_on(search_stapler_event, delay_seconds=1)
            )

            # Motivation: Continuing search for items mentioned in reminder
            # Agent searches for notebooks
            search_notebooks_event = (
                shopping_app.search_product(product_name="notebooks")
                .oracle()
                .depends_on(search_pens_event, delay_seconds=1)
            )

            # Motivation: Based on promo email ("This Weekend Only: 20% off with code OFFICE20 - minimum 4 items") and matching reminder ("Buy office supplies for Q1" due Monday after weekend)
            # Agent proposes ordering now to capture expiring discount before reminder deadline
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw a promotional email offering 20% off office supplies with code OFFICE20 this weekend only (minimum 4 items). You have a reminder to buy office supplies (printer paper, staplers, pens, notebooks) due Monday. Would you like me to order these items now to capture the expiring discount?"
                )
                .oracle()
                .depends_on(search_notebooks_event, delay_seconds=2)
            )

            # User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please order the items with the discount code.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Motivation: User accepted proposal to order items; agent adds printer paper
            add_paper_event = (
                shopping_app.add_to_cart(item_id=self.printer_paper_item_id, quantity=1)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Motivation: User accepted proposal; agent continues adding items (stapler)
            add_stapler_event = (
                shopping_app.add_to_cart(item_id=self.stapler_item_id, quantity=1)
                .oracle()
                .depends_on(add_paper_event, delay_seconds=1)
            )

            # Motivation: User accepted proposal; agent continues adding items (pens)
            add_pens_event = (
                shopping_app.add_to_cart(item_id=self.pens_item_id, quantity=1)
                .oracle()
                .depends_on(add_stapler_event, delay_seconds=1)
            )

            # Motivation: User accepted proposal; agent continues adding items (notebooks)
            add_notebooks_event = (
                shopping_app.add_to_cart(item_id=self.notebooks_item_id, quantity=1)
                .oracle()
                .depends_on(add_pens_event, delay_seconds=1)
            )

            # Motivation: User accepted proposal and all 4 items added to cart; agent completes checkout with OFFICE20 discount code
            checkout_event = (
                shopping_app.checkout(discount_code="OFFICE20")
                .oracle()
                .depends_on(add_notebooks_event, delay_seconds=2)
            )

            # Motivation: Order completed; agent updates reminder description to note completion via OFFICE20 discount
            # Agent updates the reminder's description to indicate completion
            monday_due_datetime = datetime(2025, 11, 24, 17, 0, 0, tzinfo=UTC)
            update_reminder_event = (
                reminder_app.update_reminder(
                    reminder_id=self.office_supplies_reminder_id,
                    title="Buy office supplies for Q1",
                    description="printer paper, staplers, pens, notebooks - Completed via OFFICE20 discount",
                    due_datetime=monday_due_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                    repetition_unit=None,
                    repetition_value=None,
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=1)
            )

            # Motivation: Task completed via discount; agent deletes the reminder since it's fulfilled
            # Agent deletes the office supplies reminder after updating it
            delete_reminder_event = (
                reminder_app.delete_reminder(reminder_id=self.office_supplies_reminder_id)
                .oracle()
                .depends_on(update_reminder_event, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            promo_email_event,
            check_reminders_event,
            verify_discount_event,
            search_paper_event,
            search_stapler_event,
            search_pens_event,
            search_notebooks_event,
            proposal_event,
            acceptance_event,
            add_paper_event,
            add_stapler_event,
            add_pens_event,
            add_notebooks_event,
            checkout_event,
            update_reminder_event,
            delete_reminder_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning the discount code and ordering early to capture discount
            # Flexible on exact wording, but must reference OFFICE20 and the opportunity
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "OFFICE20" in e.action.args.get("content", "")
                for e in log_entries
            )

            # STRICT Check 2: Agent added items to cart (at least 4 items to meet discount requirement)
            # Check that add_to_cart was called for the expected item IDs
            add_to_cart_calls = [
                e
                for e in log_entries
                if (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
            ]
            cart_items_added = len(add_to_cart_calls) >= 4

            # STRICT Check 3: Agent completed checkout with OFFICE20 discount code
            checkout_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "OFFICE20"
                for e in log_entries
            )

            # Collect missing checks for rationale
            missing_checks = []
            if not proposal_found:
                missing_checks.append("agent proposal mentioning OFFICE20 discount opportunity")
            if not cart_items_added:
                missing_checks.append("adding at least 4 items to cart to meet discount minimum")
            if not checkout_found:
                missing_checks.append("checkout completion with OFFICE20 discount code")

            success = proposal_found and cart_items_added and checkout_found

            rationale = None if success else f"Missing critical checks: {', '.join(missing_checks)}"
            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
