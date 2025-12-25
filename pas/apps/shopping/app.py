"""Stateful shopping app combining Meta-ARE shopping backend with PAS navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from are.simulation.apps.shopping import ShoppingApp

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

    def __init__(self, name: str = "Shopping", **kwargs: object) -> None:
        """Initialise shopping app with root state."""
        StatefulApp.__init__(self, name)
        # IMPORTANT: Meta-ARE's `ShoppingApp` is a dataclass whose `__post_init__`
        # calls `App.__init__(self.name)`. If we don't pass `name` here, that
        # post-init will see `name=None` and overwrite `self.name` to the class
        # name (e.g., "StatefulShoppingApp"), which breaks `Scenario.get_typed_app`
        # lookups that match on both type *and* app.name.
        ShoppingApp.__init__(self, name=name, **kwargs)
        self.load_root_state()

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
