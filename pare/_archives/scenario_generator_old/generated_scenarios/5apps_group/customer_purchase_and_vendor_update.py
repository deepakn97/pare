from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("customer_purchase_and_vendor_update")
class CustomerPurchaseAndVendorUpdate(Scenario):
    """Simulates a customer purchase workflow where agent uses shopping, contacts, email, and system apps.

    The agent:
      1. Checks the time and searches for a product.
      2. Proposes to the user to buy a discounted item.
      3. On approval, adds the item to the cart and checks out.
      4. Sends an order confirmation email.
      5. Updates vendor details in contacts.
      6. Waits for any feedback using system notifications.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all required apps and populate minimal initial state."""
        aui = AgentUserInterface()
        contacts = ContactsApp()
        email = EmailClientApp()
        shopping = ShoppingApp()
        system = SystemApp(name="system")

        # Populate contacts with vendor details
        contacts.add_new_contact(
            first_name="Evelyn",
            last_name="Stone",
            gender=Gender.Female,
            status=Status.Employed,
            job="Vendor Manager",
            email="evelyn@techstore.com",
            phone="+1-555-345-9087",
            city_living="New York",
            country="USA",
            description="Preferred vendor contact for gadget orders.",
        )

        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Lee",
            gender=Gender.Male,
            status=Status.Employed,
            job="Customer",
            email="customer.jordan@example.com",
            phone="+1-555-997-4412",
            city_living="Boston",
            country="USA",
        )

        # Add user context
        contacts.get_current_user_details()

        # Prepare shopping catalog with multiple products
        shopping.list_all_products(offset=0, limit=10)
        # also query all discount codes so the agent can use them
        shopping.get_all_discount_codes()

        # Ensure all apps are part of the scenario
        self.apps = [aui, contacts, email, shopping, system]

    def build_events_flow(self) -> None:
        """Defines the workflow events including user-agent proactive interaction."""
        aui = self.get_typed_app(AgentUserInterface)
        email_app = self.get_typed_app(EmailClientApp)
        contacts_app = self.get_typed_app(ContactsApp)
        shop = self.get_typed_app(ShoppingApp)
        sysapp = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 1: User requests assistance buying a new gadget
            user_initiate = aui.send_message_to_agent(
                content="I need to purchase a pair of wireless headphones today. Can you help me order them?"
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent checks the system time (useful for context like 'today delivery')
            current_time_event = sysapp.get_current_time().depends_on(user_initiate, delay_seconds=1)

            # Step 3: Agent searches for the headphones in the store
            search_product_event = shop.search_product(product_name="Wireless Headphones").depends_on(
                current_time_event, delay_seconds=1
            )

            # Step 4: Agent lists possible discount codes
            list_discount_event = shop.get_all_discount_codes().depends_on(search_product_event, delay_seconds=1)

            # Step 5: Agent composes a proactive message proposing the purchase
            propose_action = aui.send_message_to_user(
                content=(
                    "I found Wireless Headphones available with a 10% discount code 'SAVE10'. "
                    "Would you like me to add them to the cart and complete your purchase?"
                )
            ).depends_on(list_discount_event, delay_seconds=1)

            # Step 6: User approves purchase with an instruction
            user_confirms = aui.send_message_to_agent(
                content="Yes, please apply the discount and complete the order."
            ).depends_on(propose_action, delay_seconds=2)

            # Step 7: Agent adds the item to the cart as oracle action
            add_to_cart_event = (
                shop.add_to_cart(item_id="product_wireless_headphones", quantity=1)
                .oracle()
                .depends_on(user_confirms, delay_seconds=1)
            )

            # Step 8: Agent performs checkout with discount code as oracle
            checkout_event = (
                shop.checkout(discount_code="SAVE10").oracle().depends_on(add_to_cart_event, delay_seconds=2)
            )

            # Step 9: Agent sends an order confirmation email to the user as oracle action
            send_email_receipt = (
                email_app.send_email(
                    recipients=["customer.jordan@example.com"],
                    subject="Order Confirmation - Wireless Headphones",
                    content="Thank you for your purchase! Your wireless headphones will be delivered soon.",
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=1)
            )

            # Step 10: Agent updates vendor contact info as oracle action
            update_vendor = (
                contacts_app.edit_contact(
                    contact_id="Evelyn_Stone_ID", updates={"description": "Contacted for headsets on current order."}
                )
                .oracle()
                .depends_on(send_email_receipt, delay_seconds=1)
            )

            # Step 11: Agent waits in standby mode for any notification
            standby_event = sysapp.wait_for_notification(timeout=5).depends_on(update_vendor, delay_seconds=1)

        self.events = [
            user_initiate,
            current_time_event,
            search_product_event,
            list_discount_event,
            propose_action,
            user_confirms,
            add_to_cart_event,
            checkout_event,
            send_email_receipt,
            update_vendor,
            standby_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent completed the full workflow successfully."""
        try:
            events = env.event_log.list_view()

            # Validate that agent made proposals to user and user approved contextually
            user_proposed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "discount" in e.action.args.get("content", "").lower()
                and "purchase" in e.action.args.get("content", "").lower()
                for e in events
            )

            user_approved = any(
                e.event_type == EventType.USER
                and "please apply the discount" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Verify critical workflow actions
            ordered = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "ShoppingApp"
                and e.action.function_name == "checkout"
                and "SAVE10" in str(e.action.args.get("discount_code", ""))
                for e in events
            )

            email_sent = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "EmailClientApp"
                and e.action.function_name == "send_email"
                and "Order Confirmation" in e.action.args.get("subject", "")
                for e in events
            )

            vendor_updated = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "ContactsApp"
                and e.action.function_name == "edit_contact"
                and "headsets" in str(e.action.args.get("updates", {})).lower()
                for e in events
            )

            # Success if all main components of the workflow executed
            success = all([user_proposed, user_approved, ordered, email_sent, vendor_updated])
            return ScenarioValidationResult(success=success)
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
