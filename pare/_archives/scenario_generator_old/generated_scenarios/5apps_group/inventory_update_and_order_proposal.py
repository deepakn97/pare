from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.sandbox_file_system import Files
from are.simulation.apps.shopping import Shopping
from are.simulation.apps.system import SystemApp
from are.simulation.apps.virtual_file_system import VirtualFileSystem
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("inventory_update_and_order_proposal")
class InventoryUpdateAndOrderProposal(Scenario):
    """A comprehensive scenario combining shopping catalog exploration with file system operations.

    The workflow:
    1. Agent checks the system time and prepares inventory folders using VirtualFileSystem and Files.
    2. Agent searches a product catalog (Shopping) and logs data into local files.
    3. Agent proposes to the user to place an order for a popular product.
    4. User confirms.
    5. Agent adds it to the cart and checks out using a discount code.
    6. Files and VirtualFileSystem are used to move and archive order data.
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all available apps with data."""
        aui = AgentUserInterface()
        system = SystemApp(name="system")
        vfs = VirtualFileSystem(name="vfs")
        files = Files(name="files", sandbox_dir=kwargs.get("sandbox_dir"))
        shopping = Shopping(name="shopping")

        # Create directory structures in both Files and VirtualFileSystem
        vfs.mkdir(path="/reports/inventory", create_recursive=True)
        files.makedirs(path="/workspace/inventory_data", exist_ok=True)

        # Populate: simulate listing and saving catalog data to workspace (through Files app)
        files.mkdir(path="/workspace/logs", create_parents=True)
        # List all available products (we won't know the exact list, but the scenario shows the tool use)
        shopping.list_all_products(offset=0, limit=5)
        shopping.get_all_discount_codes()

        self.apps = [aui, system, vfs, files, shopping]

    def build_events_flow(self) -> None:
        """Define the interactive scenario flow with oracle actions."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        vfs = self.get_typed_app(VirtualFileSystem)
        files = self.get_typed_app(Files)
        shopping = self.get_typed_app(Shopping)

        with EventRegisterer.capture_mode():
            # User starts by asking to update local inventory data
            event0 = aui.send_message_to_agent(
                content="Hey Assistant, please update today's inventory report and suggest any top-rated product to order."
            ).depends_on(None, delay_seconds=0)

            # Agent checks current system time (helps timestamp reports)
            event1 = system.get_current_time().depends_on(event0, delay_seconds=1)

            # Agent lists product catalog to gather overview
            event2 = shopping.list_all_products(offset=0, limit=3).depends_on(event1, delay_seconds=1)

            # Agent saves a mock report file into Files workspace
            event3 = files.mkdir(path="/workspace/inventory_snapshots", create_parents=True).depends_on(
                event2, delay_seconds=1
            )

            # Agent proposes next step: placing an order
            event4 = aui.send_message_to_user(
                content="I've finished updating the inventory report. Would you like me to order the popular coffee maker from our catalog?"
            ).depends_on(event3, delay_seconds=1)

            # The user confirms the proposal with contextual permission
            event5 = aui.send_message_to_agent(
                content="Yes, please go ahead and order the coffee maker with a discount if possible."
            ).depends_on(event4, delay_seconds=2)

            # Agent searches specifically for the coffee maker
            event6 = shopping.search_product(product_name="coffee maker", offset=0, limit=1).depends_on(
                event5, delay_seconds=1
            )

            # Agent adds coffee maker to cart (oracle)
            event7 = (
                shopping.add_to_cart(item_id="coffee_maker_001", quantity=1)
                .depends_on(event6, delay_seconds=1)
                .oracle()
            )

            # Agent applies available discount information
            event8 = shopping.get_discount_code_info(discount_code="COFFEE10").depends_on(event7, delay_seconds=1)

            # Agent checks out the cart using discount code
            event9 = shopping.checkout(discount_code="COFFEE10").depends_on(event8, delay_seconds=1).oracle()

            # Archive the resulting order summary using VirtualFileSystem (oracle)
            event10 = vfs.mkdir(path="/reports/orders", create_recursive=True).depends_on(event9, delay_seconds=1)
            event11 = (
                vfs.mv(path1="/tmp/order_summary.txt", path2="/reports/orders/order_summary.txt")  # noqa: S108
                .oracle()
                .depends_on(event10, delay_seconds=1)
            )

            # Agent confirms completion with user
            event12 = (
                aui.send_message_to_user(
                    content="The coffee maker has been ordered successfully and the order summary is archived in /reports/orders."
                )
                .depends_on(event11, delay_seconds=1)
                .oracle()
            )

            # To simulate agent idle time after completion
            event13 = system.wait_for_notification(timeout=5).depends_on(event12, delay_seconds=1)

        self.events = [
            event0,
            event1,
            event2,
            event3,
            event4,
            event5,
            event6,
            event7,
            event8,
            event9,
            event10,
            event11,
            event12,
            event13,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the update and order placement were successful."""
        try:
            events = env.event_log.list_view()
            # Validation criteria:
            # 1. The checkout action was executed.
            # 2. The agent confirmed with a message to the user mentioning "ordered successfully".
            # 3. The agent archived an order file via VirtualFileSystem.
            checkout_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "Shopping"
                and e.action.function_name == "checkout"
                for e in events
            )
            confirmation_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and isinstance(e.action.args.get("content"), str)
                and "ordered successfully" in e.action.args["content"].lower()
                for e in events
            )
            archive_moved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "VirtualFileSystem"
                and e.action.function_name == "mv"
                for e in events
            )
            return ScenarioValidationResult(success=(checkout_done and confirmation_sent and archive_moved))
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
