from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("ecommerce_support_transaction_workflow")
class EcommerceSupportTransactionWorkflow(Scenario):
    """A comprehensive ecommerce support scenario integrating all available apps.

    The workflow:
    1. The agent helps the user find a suitable product to gift.
    2. The agent proposes to add it to the cart and send confirmation.
    3. The user confirms; agent completes checkout and saves receipt to a file.
    4. Agent emails the receipt and updates contact records with a buying note.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate environment with applications and base data."""
        aui = AgentUserInterface()
        system = SystemApp(name="system")
        contacts = ContactsApp()
        email_client = EmailClientApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        shopping = ShoppingApp()

        # Add a new contact (Jordan) to Contacts for future interactions
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Fischer",
            gender=Gender.MALE,
            age=30,
            nationality="Canadian",
            city_living="Toronto",
            country="Canada",
            status=Status.EMPLOYED,
            job="Designer",
            description="Frequent shopper and recipient of gift emails.",
            phone="+1-416-555-0193",
            email="jordan.fischer@example.com",
            address="789 Maple Ave, Toronto, ON",
        )

        # Create a directory for receipts
        fs.makedirs("Receipts", exist_ok=True)

        self.apps = [aui, system, contacts, email_client, fs, shopping]

    def build_events_flow(self) -> None:
        """Define the sequence of user/agent/system/shop/email/contact interactions."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        contacts = self.get_typed_app(ContactsApp)
        email_client = self.get_typed_app(EmailClientApp)
        fs = self.get_typed_app(SandboxLocalFileSystem)
        shopping = self.get_typed_app(ShoppingApp)

        # Begin the flow
        with EventRegisterer.capture_mode():
            # User initiates a request to the agent
            event0 = (
                aui.send_message_to_agent(
                    content=(
                        "Hey, I need help finding a birthday gift for Jordan Fischer. "
                        "Could you check something elegant but affordable?"
                    )
                )
                .depends_on(None, delay_seconds=1)
                .with_id("user_request")
            )

            # Agent retrieves current time to personalize the search
            event1 = system.get_current_time().depends_on(event0, delay_seconds=1)

            # Agent searches for a product
            event2 = shopping.search_product(product_name="watch").depends_on(event1, delay_seconds=1)

            # Agent proposes to add one found product to cart and send confirmation email
            event3 = aui.send_message_to_user(
                content=(
                    "I found a few elegant watches within your budget range. "
                    "Would you like me to add one to your cart and email the purchase receipt to Jordan?"
                )
            ).depends_on(event2, delay_seconds=1)

            # User provides approval with contextual response
            event4 = aui.send_message_to_agent(
                content="Yes, please go ahead and purchase one and share the receipt with Jordan."
            ).depends_on(event3, delay_seconds=1)

            # Agent adds the watch to cart (oracle truth)
            event5 = shopping.add_to_cart(item_id="watch_001", quantity=1).oracle().depends_on(event4, delay_seconds=1)

            # Agent performs checkout
            event6 = shopping.checkout(discount_code=None).oracle().depends_on(event5, delay_seconds=1)

            # Agent saves receipt to filesystem
            event7 = fs.open(path="Receipts/order_receipt.txt", mode="wb").oracle().depends_on(event6, delay_seconds=1)

            # Agent emails the receipt
            event8 = (
                email_client.send_email(
                    recipients=["jordan.fischer@example.com"],
                    subject="Gift Receipt - Happy Birthday!",
                    content="Hi Jordan, here's the receipt for your gift from the store. Wishing you a wonderful birthday!",
                    attachment_paths=["Receipts/order_receipt.txt"],
                )
                .oracle()
                .depends_on(event7, delay_seconds=1)
            )

            # Agent updates contact record with a purchase note
            event9 = (
                contacts.edit_contact(contact_id="1", updates={"description": "Received birthday gift watch, 2024."})
                .oracle()
                .depends_on(event8, delay_seconds=1)
            )

            # Agent confirms completion
            event10 = (
                aui.send_message_to_user(
                    content=(
                        "The order was completed successfully! I've shared the receipt with Jordan "
                        "and updated the contact record accordingly."
                    )
                )
                .oracle()
                .depends_on(event9, delay_seconds=1)
            )

            # Agent idles for any system notifications
            event11 = system.wait_for_notification(timeout=3).depends_on(event10, delay_seconds=1)

        self.events = [event0, event1, event2, event3, event4, event5, event6, event7, event8, event9, event10, event11]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that all critical actions were completed successfully."""
        try:
            logs = env.event_log.list_view()

            added_to_cart = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ShoppingApp"
                and e.action.function_name == "add_to_cart"
                for e in logs
            )
            email_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "EmailClientApp"
                and e.action.function_name == "send_email"
                and "jordan.fischer@example.com" in str(e.action.args.get("recipients"))
                for e in logs
            )
            contact_updated = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ContactsApp"
                and e.action.function_name == "edit_contact"
                for e in logs
            )
            confirmation_to_user = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "order was completed" in e.action.args.get("content", "")
                for e in logs
            )

            success = added_to_cart and email_sent and contact_updated and confirmation_to_user
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
