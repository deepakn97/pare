"""Stateful shopping app combining Meta-ARE shopping backend with PAS navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from are.simulation.apps.shopping import CartItem, Order, ShoppingApp
from are.simulation.tool_utils import data_tool
from are.simulation.utils import type_check

from pas.apps.core import StatefulApp
from pas.apps.shopping.states import (
    CartView,
    OrderDetailView,
    OrderListView,
    ProductDetail,
    ShoppingHome,
    VariantDetail,
)

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent


class StatefulShoppingApp(StatefulApp, ShoppingApp):
    """Shopping app with PAS-aware navigation."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialise shopping app with root state."""
        super().__init__(*args, **kwargs)
        self.load_root_state()

    @type_check
    @data_tool()
    def add_order(
        self,
        order_id: str,
        order_status: str,
        order_date: float,
        order_total: float,
        item_id: str,
        quantity: int,
    ) -> str:
        """Add an order (used for scenario seeding).

        The upstream `are` ShoppingApp currently returns extra keys (e.g. `name`,
        `product_id`) from `_get_item()`, but its `CartItem` dataclass does not
        accept them. We defensively filter to the fields `CartItem` supports.

        Args:
            order_id: The ID of the order.
            order_status: The status of the order.
            order_date: The date of the order as a timestamp.
            order_total: The total amount of the order.
            item_id: The ID of the item to add to the order.
            quantity: The quantity of the item to add to the order.

        Returns:
            str: The ID of the created order.
        """
        item_dict = self._get_item(item_id)
        if not item_dict:
            raise ValueError("Item does not exist")

        cart_item = CartItem(
            item_id=item_dict["item_id"],
            quantity=quantity,
            price=item_dict["price"],
            available=item_dict.get("available", True),
            options=item_dict.get("options", {}),
        )
        self.orders[order_id] = Order(
            order_status=order_status,
            order_date=order_date,
            order_total=order_total,
            order_id=order_id,
            order_items={item_id: cart_item},
        )
        return order_id

    @type_check
    @data_tool()
    def add_order_multiple_items(
        self,
        order_id: str,
        order_status: str,
        order_date: float,
        order_total: float,
        items: dict[str, int],
    ) -> str:
        """Add an order with multiple items (used for scenario seeding).

        The upstream `are` ShoppingApp currently returns extra keys (e.g. `name`,
        `product_id`) from `_get_item()`, but its `CartItem` dataclass does not
        accept them. We defensively filter to the fields `CartItem` supports.

        Args:
            order_id: The ID of the order.
            order_status: The status of the order.
            order_date: The date of the order as a timestamp.
            order_total: The total amount of the order.
            items: A dictionary mapping item IDs to quantities.

        Returns:
            str: The ID of the created order.
        """
        order_items: dict[str, CartItem] = {}
        for item_id, quantity in items.items():
            item_dict = self._get_item(item_id)
            if not item_dict:
                raise ValueError(f"Item {item_id} does not exist")

            cart_item = CartItem(
                item_id=item_dict["item_id"],
                quantity=quantity,
                price=item_dict["price"],
                available=item_dict.get("available", True),
                options=item_dict.get("options", {}),
            )
            order_items[item_id] = cart_item

        self.orders[order_id] = Order(
            order_status=order_status,
            order_date=order_date,
            order_total=order_total,
            order_id=order_id,
            order_items=order_items,
        )
        return order_id

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Update navigation state based on completed operations."""
        current_state = self.current_state
        function_name = event.function_name()

        if current_state is None or function_name is None:
            return

        action = event.action
        args = action.resolved_args or action.args

        if isinstance(current_state, ShoppingHome):
            self._handle_home_transition(function_name, args, event)
            return

        if isinstance(current_state, ProductDetail):
            self._handle_product_transition(function_name, args, event)
            return

        if isinstance(current_state, VariantDetail):
            self._handle_variant_transition(function_name, args, event)
            return

        if isinstance(current_state, CartView):
            self._handle_cart_transition(function_name, args, event)
            return

        if isinstance(current_state, OrderListView):
            self._handle_order_list_transition(function_name, args, event)
            return

        if isinstance(current_state, OrderDetailView):
            self._handle_order_detail_transition(function_name, args, event)

    def _handle_home_transition(
        self,
        function_name: str,
        args: dict[str, object],
        event: CompletedEvent,
    ) -> None:
        """Handle transitions from ShoppingHome."""
        if function_name in {"view_product", "get_product", "get_product_details"}:
            pid = args.get("product_id")
            if isinstance(pid, str):
                self.set_current_state(ProductDetail(product_id=pid))
            return

        if function_name in {"get_item", "get_item_details", "_get_item"}:
            iid = args.get("item_id")
            if isinstance(iid, str):
                self.set_current_state(VariantDetail(item_id=iid))
            return

        if function_name in {"view_cart", "add_to_cart", "list_cart", "get_cart"}:
            self.set_current_state(CartView())
            return

        if function_name == "list_orders":
            self.set_current_state(OrderListView())

    def _handle_product_transition(
        self,
        function_name: str,
        args: dict[str, object],
        event: CompletedEvent,
    ) -> None:
        """Handle transitions from ProductDetail."""
        if function_name in {"view_variant", "get_item", "get_item_details", "_get_item"}:
            iid = args.get("item_id")
            if isinstance(iid, str):
                self.set_current_state(VariantDetail(item_id=iid))
            return

        if function_name == "add_to_cart":
            self.set_current_state(CartView())

    def _handle_variant_transition(
        self,
        function_name: str,
        args: dict[str, object],
        event: CompletedEvent,
    ) -> None:
        """Handle transitions from VariantDetail."""
        if function_name == "add_to_cart":
            self.set_current_state(CartView())

    def _handle_cart_transition(
        self,
        function_name: str,
        args: dict[str, object],
        event: CompletedEvent,
    ) -> None:
        """Handle transitions from CartView."""
        if function_name == "checkout":
            order_id = self._order_id_from_event(event)
            if isinstance(order_id, str):
                self.set_current_state(OrderDetailView(order_id=order_id))
            return

        if function_name in {"remove_item", "remove_from_cart"}:
            return

    def _handle_order_list_transition(
        self,
        function_name: str,
        args: dict[str, object],
        event: CompletedEvent,
    ) -> None:
        """Handle transitions from OrderListView."""
        if function_name in {"view_order", "get_order_details"}:
            oid = args.get("order_id")
            if isinstance(oid, str):
                self.set_current_state(OrderDetailView(order_id=oid))

    def _handle_order_detail_transition(
        self,
        function_name: str,
        args: dict[str, object],
        event: CompletedEvent,
    ) -> None:
        """Handle transitions from OrderDetailView."""
        return None

    @staticmethod
    def _order_id_from_event(event: CompletedEvent) -> str | None:
        """Extract order_id from event return payload."""
        if hasattr(event, "_return_value") and event._return_value:
            rv = event._return_value
            if isinstance(rv, str):
                return rv
            if isinstance(rv, dict):
                val = rv.get("order_id")
                return val if isinstance(val, str) else None

        meta = event.metadata.return_value if event.metadata else None
        if isinstance(meta, str):
            return meta
        if isinstance(meta, dict):
            val = meta.get("order_id")
            return val if isinstance(val, str) else None

        return None

    def create_root_state(self) -> ShoppingHome:
        """Return root navigation state."""
        return ShoppingHome()

    def get_item(self, item_id: str) -> dict[str, object]:
        """Wrapper for _get_item for compatibility."""
        return self._get_item(item_id)

    def get_cart(self) -> dict[str, object]:
        """Wrapper for list_cart() used by states."""
        return self.list_cart()
