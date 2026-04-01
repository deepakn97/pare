"""Scenario for creating contact from delivery notification about package left with neighbor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulShoppingApp,
)
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario

# Neighbor's contact information from delivery notification
NEIGHBOR_NAME = "Alex Thompson"
NEIGHBOR_PHONE = "555-876-5432"


@register_scenario("order_recipient_contact_creation")
class OrderRecipientContactCreation(PAREScenario):
    """Agent creates contact for neighbor who received user's package.

    Story:
    1. User has an existing order for Bluetooth Speaker (status: shipped)
    2. Email arrives from carrier saying package was delivered but left with
       neighbor Alex Thompson (since no one was home)
    3. Alex Thompson is not in user's contacts
    4. Agent proposes creating a contact for Alex so user can coordinate pickup
    5. User accepts
    6. Agent creates contact with neighbor's info

    This scenario exercises delivery-notification parsing, contact existence
    verification, and cross-app coordination (email -> contacts) for managing
    relationships with helpful neighbors.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You ordered a Bluetooth Speaker that was supposed to be delivered to your home.

ACCEPT proposals that:
- Offer to create a contact for the neighbor who received your package
- Include the neighbor's name and phone number

REJECT proposals that:
- Don't explain why you'd want to save this person as a contact
- Don't provide the neighbor's contact information"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize contacts app (has default user John Doe at 123 Main St)
        self.contacts = StatefulContactsApp(name="Contacts")

        # Get user's address to derive neighbor's address (same street)
        user_details = self.contacts.get_current_user_details()
        # User is at "123 Main St, Anytown, USA", neighbor is at "125 Main St, Anytown, USA"
        self.neighbor_address = "125 Main St, Anytown, USA"

        # Add a couple existing contacts (not Alex Thompson)
        self.contacts.add_new_contact(
            first_name="Jordan",
            last_name="Lee",
            phone="555-020-1234",
            email="jordan.lee@email.com",
        )
        self.contacts.add_new_contact(
            first_name="Morgan",
            last_name="Chen",
            phone="555-020-2345",
            email="morgan.chen@email.com",
        )

        # Initialize shopping app with order
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add product and create order
        product_id = self.shopping.add_product(name="Bluetooth Speaker - Silver")
        item_id = self.shopping.add_item_to_product(
            product_id=product_id,
            price=79.99,
            options={"color": "Silver", "connectivity": "Bluetooth 5.0"},
            available=True,
        )

        # Create order (placed a few days ago, status: shipped)
        order_date = datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp()
        self.shopping.add_order(
            order_id="order_7234",
            order_status="shipped",
            order_date=order_date,
            order_total=79.99,
            item_id=item_id,
            quantity=1,
        )

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        self.apps = [self.agent_ui, self.system_app, self.contacts, self.shopping, self.email]

    def build_events_flow(self) -> None:
        """Build event flow for neighbor contact creation."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # ENV: Email notification about delivery left with neighbor
            delivery_email_event = email_app.send_email_to_user_with_id(
                email_id="email_delivery_neighbor",
                sender="notifications@expressdelivery.com",
                subject="Your Order #7234 Has Been Delivered",
                content=(
                    "Dear Customer,\n\n"
                    "Your order #7234 (Bluetooth Speaker - Silver) has been delivered!\n\n"
                    "Delivery Details:\n"
                    "- Status: Delivered\n"
                    "- Note: No one was home. Package was left with your neighbor.\n\n"
                    "Neighbor Information:\n"
                    f"- Name: {NEIGHBOR_NAME}\n"
                    f"- Address: {self.neighbor_address}\n"
                    f"- Phone: {NEIGHBOR_PHONE}\n\n"
                    "Please contact your neighbor to arrange pickup.\n\n"
                    "Thank you for shopping with us!\n"
                    "Express Delivery Team"
                ),
            ).delayed(10)

            # Oracle: Agent searches contacts to verify neighbor is not saved
            search_contacts_event = (
                contacts_app.search_contacts(query="Alex Thompson")
                .oracle()
                .depends_on(delivery_email_event, delay_seconds=2)
            )

            # Oracle: Agent proposes creating contact for the neighbor
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        f"Your Bluetooth Speaker was delivered but left with your neighbor "
                        f"{NEIGHBOR_NAME} at {self.neighbor_address}. They're not in your contacts yet. "
                        f"Would you like me to save their information (phone: {NEIGHBOR_PHONE}) "
                        "so you can contact them to pick up your package?"
                    )
                )
                .oracle()
                .depends_on(search_contacts_event, delay_seconds=2)
            )

            # Oracle: User accepts
            acceptance_event = (
                aui.accept_proposal(content="Yes, please save their contact info.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle: Agent creates contact for neighbor
            create_contact_event = (
                contacts_app.add_new_contact(
                    first_name="Alex",
                    last_name="Thompson",
                    phone=NEIGHBOR_PHONE,
                    address=self.neighbor_address,
                    description="Neighbor who received my package (order #7234)",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

        self.events = [
            delivery_email_event,
            search_contacts_event,
            proposal_event,
            acceptance_event,
            create_contact_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate essential outcomes.

        Checks:
        1. Agent sent proposal to user
        2. Agent created contact with correct name and phone
        """
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Proposal sent to user
            proposal_found = any(
                e.action.class_name == "PAREAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check 2: Contact created with correct name (Alex) and phone
            contact_created = any(
                e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "add_new_contact"
                and e.action.args.get("first_name") == "Alex"
                and e.action.args.get("phone") == NEIGHBOR_PHONE
                for e in agent_events
            )

            success = proposal_found and contact_created

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user")
                if not contact_created:
                    missing.append(f"contact created for Alex with phone {NEIGHBOR_PHONE}")
                return ScenarioValidationResult(
                    success=False,
                    rationale=f"Missing: {', '.join(missing)}",
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
