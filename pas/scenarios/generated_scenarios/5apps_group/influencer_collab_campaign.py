from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("influencer_collab_campaign")
class InfluencerCollabCampaign(Scenario):
    """Scenario where an influencer coordinates a product collaboration campaign.

    Using multiple apps to demonstrate ecosystem interaction.

    Context:
    - The influencer (user) wants to order a sample product from an online catalog
      and propose a collaboration with a brand manager contact.
    - The agent assists by finding a product, proposing to message the brand, and acts upon user approval.
    - Uses proactive interaction: proposal → user approval → agent action.
    """

    start_time: float | None = 0
    duration: float | None = 35

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initializes all apps and preloads realistic data relevant to the influencer marketing scenario."""
        aui = AgentUserInterface()
        contacts_app = ContactsApp()
        messaging_app = MessagingApp()
        shopping_app = ShoppingApp()
        system_app = SystemApp(name="local_system")

        # Create contacts for collaboration
        contacts_app.add_new_contact(
            first_name="Jordan",
            last_name="Lee",
            gender=Gender.MALE,
            age=32,
            nationality="American",
            city_living="New York",
            country="USA",
            status=Status.EMPLOYED,
            job="Brand Manager",
            description="Manages lifestyle and clothing collaborations for LuxeFit.",
            phone="+1 202 456 0912",
            email="jordan.lee@luxefitbrands.com",
            address="65 Fashion Blvd, New York",
        )

        contacts_app.add_new_contact(
            first_name="Ava",
            last_name="Nguyen",
            gender=Gender.FEMALE,
            age=27,
            nationality="Canadian",
            city_living="Toronto",
            country="Canada",
            status=Status.EMployed,
            job="Creative Director",
            description="Oversees influencer collaborations and branding media content.",
            phone="+1 647 333 7777",
            email="ava.nguyen@lifestylehub.ca",
        )

        # Populate the shopping catalog with example items
        # (names differ from examples: we use fashion items fitting influencer theme)
        _ = shopping_app.list_all_products(offset=0, limit=5)

        self.apps = [aui, contacts_app, messaging_app, shopping_app, system_app]

    def build_events_flow(self) -> None:
        """Define the oracle and interaction flow demonstrating all app usages."""
        aui = self.get_typed_app(AgentUserInterface)
        contacts_app = self.get_typed_app(ContactsApp)
        messaging_app = self.get_typed_app(MessagingApp)
        shopping_app = self.get_typed_app(ShoppingApp)
        system_app = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User starts the task
            event_user_start = aui.send_message_to_agent(
                content="Hey Assistant, I need some help setting up a collab with LuxeFit. Can you find a product sample for me to review?"
            ).depends_on(None, delay_seconds=1)

            # System provides current time (for timeline tagging)
            event_time_check = system_app.get_current_time().depends_on(event_user_start, delay_seconds=1)

            # Agent searches for suitable fashion product
            event_prod_search = shopping_app.search_product(
                product_name="LuxeFit Sneakers", offset=0, limit=3
            ).depends_on(event_time_check, delay_seconds=1)

            # Agent adds product to cart
            event_add_cart = shopping_app.add_to_cart(item_id="LUXE123", quantity=1).depends_on(
                event_prod_search, delay_seconds=1
            )

            # Agent lists cart contents
            event_cart_list = shopping_app.list_cart().depends_on(event_add_cart, delay_seconds=1)

            # Agent gets current available discount codes
            event_disc_info = shopping_app.get_all_discount_codes().depends_on(event_cart_list, delay_seconds=1)

            # Agent proposes to user before purchase (proactive pattern #1)
            agent_propose_action = aui.send_message_to_user(
                content="I found LuxeFit Sneakers available with a 10% influencer discount. Should I place the order and inform Jordan about it?"
            ).depends_on(event_disc_info, delay_seconds=1)

            # User explicitly approves with a contextual response
            user_approval = aui.send_message_to_agent(
                content="Yes, please order them and send Jordan a message about our upcoming review collaboration."
            ).depends_on(agent_propose_action, delay_seconds=2)

            # Agent executes checkout only after approval
            oracle_checkout = (
                shopping_app.checkout(discount_code="INFL10").oracle().depends_on(user_approval, delay_seconds=1)
            )

            # Agent retrieves orders for verification post checkout
            event_orders_list = shopping_app.list_orders().depends_on(oracle_checkout, delay_seconds=1)

            # Agent then creates a conversation with Jordan to follow up collaboration
            conv_create = messaging_app.create_conversation(
                participants=["Jordan Lee"], title="LuxeFit Collab"
            ).depends_on(event_orders_list, delay_seconds=1)

            # Agent sends message to Jordan (collaboration announcement)
            oracle_message_to_brand = (
                messaging_app.send_message(
                    conversation_id=conv_create,
                    content="Hi Jordan, the LuxeFit Sneakers sample order has been placed. We're excited to start the collaboration!",
                )
                .oracle()
                .depends_on(conv_create, delay_seconds=1)
            )

            # Wait event to simulate delivery confirmation delay
            wait_notif = system_app.wait_for_notification(timeout=4).depends_on(
                oracle_message_to_brand, delay_seconds=2
            )

            # After some time, agent checks recent messages to confirm Jordan's response
            conv_list = messaging_app.list_recent_conversations(offset=0, limit=3).depends_on(
                wait_notif, delay_seconds=1
            )

            # Contact search (demonstrates Contacts API usage)
            event_contact_search = contacts_app.search_contacts(query="Jordan").depends_on(conv_list, delay_seconds=1)

            # Finally, agent notifies user of success
            final_notify_user = (
                aui.send_message_to_user(
                    content="All done! LuxeFit Sneakers ordered and message sent to Jordan for collab coordination."
                )
                .oracle()
                .depends_on(event_contact_search, delay_seconds=1)
            )

        self.events = [
            event_user_start,
            event_time_check,
            event_prod_search,
            event_add_cart,
            event_cart_list,
            event_disc_info,
            agent_propose_action,
            user_approval,
            oracle_checkout,
            event_orders_list,
            conv_create,
            oracle_message_to_brand,
            wait_notif,
            conv_list,
            event_contact_search,
            final_notify_user,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the influencer-collaboration workflow completed correctly."""
        try:
            logs = env.event_log.list_view()

            # Check that checkout was executed after user approved
            checkout_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ShoppingApp"
                and e.action.function_name == "checkout"
                for e in logs
            )

            # Verify messaging was sent to Jordan
            message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "MessagingApp"
                and e.action.function_name == "send_message"
                and "Jordan" in e.action.args["content"]
                for e in logs
            )

            # Confirm agent proposed the action to user before executing
            proactive_prompt = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Should I place the order" in e.action.args.get("content", "")
                for e in logs
            )

            return ScenarioValidationResult(success=(checkout_done and message_sent and proactive_prompt))
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
