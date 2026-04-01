"""Navigation state implementations for the stateful shopping app.

This module defines the navigation-aware states used by
`StatefulShoppingApp`, providing product browsing, variant inspection,
cart interaction, and order history viewing.

Output format conventions:
    - READ operations → dict | list | object
    - WRITE operations → str | dict
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from are.simulation.types import OperationType

from pare.apps.core import AppState
from pare.apps.tool_decorators import pare_event_registered, user_tool

if TYPE_CHECKING:
    from pare.apps.shopping.app import StatefulShoppingApp


# ShoppingHome
class ShoppingHome(AppState):
    """Root navigation state providing product catalog access."""

    def __init__(self) -> None:
        """Initialise the home state."""
        super().__init__()

    def on_enter(self) -> None:
        """No-op hook for entering the home screen."""
        return None

    def on_exit(self) -> None:
        """No-op hook for exiting the home screen."""
        return None

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def list_products(self, offset: int = 0, limit: int = 10) -> dict[str, Any]:
        """List all available products.

        Args:
            offset: Pagination offset.
            limit: Maximum number of products to return.

        Returns:
            dict[str, Any]: Backend payload containing products and metadata.
        """
        app = cast("StatefulShoppingApp", self.app)
        return app.list_all_products(offset=offset, limit=limit)

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def view_product(self, product_id: str) -> dict[str, Any]:
        """Retrieve product details and navigate to ProductDetail.

        Args:
            product_id: Identifier for the product to open.

        Returns:
            dict[str, Any]: Detailed product information.
        """
        app = cast("StatefulShoppingApp", self.app)
        return app.get_product_details(product_id=product_id)

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def view_cart(self) -> dict[str, Any]:
        """Open the cart screen.

        Returns:
            dict[str, Any]: Cart contents.
        """
        app = cast("StatefulShoppingApp", self.app)
        return app.get_cart()

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def list_orders(self) -> list[dict[str, Any]]:
        """List all previous orders.

        Returns:
            list[dict[str, Any]]: Summaries of past orders.
        """
        app = cast("StatefulShoppingApp", self.app)
        return app.list_orders()


# ProductDetail
class ProductDetail(AppState):
    """Detail view for a specific product."""

    def __init__(self, product_id: str) -> None:
        """Bind this state to a product identifier.

        Args:
            product_id: Product ID for which details are displayed.
        """
        super().__init__()
        self.product_id = product_id

    def on_enter(self) -> None:
        """No-op entry hook."""
        return None

    def on_exit(self) -> None:
        """No-op exit hook."""
        return None

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def view_variant(self, item_id: str) -> dict[str, Any]:
        """Open a specific variant for this product.

        Args:
            item_id: Variant (item) identifier.

        Returns:
            dict[str, Any]: Variant detail payload.
        """
        app = cast("StatefulShoppingApp", self.app)
        return app._get_item(item_id=item_id)


# VariantDetail
class VariantDetail(AppState):
    """Detail view for a single product variant."""

    def __init__(self, item_id: str) -> None:
        """Initialise the state with an item identifier.

        Args:
            item_id: The variant being displayed.
        """
        super().__init__()
        self.item_id = item_id

    def on_enter(self) -> None:
        """No-op entry hook."""
        return None

    def on_exit(self) -> None:
        """No-op exit hook."""
        return None

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def add_to_cart(self, quantity: int = 1) -> str | dict[str, Any]:
        """Add this variant to the cart.

        Args:
            quantity: Number of units to add.

        Returns:
            str | dict[str, Any]: Backend confirmation or cart update result.
        """
        app = cast("StatefulShoppingApp", self.app)
        return app.add_to_cart(item_id=self.item_id, quantity=quantity)


# CartView
class CartView(AppState):
    """Navigation state showing cart contents."""

    def __init__(self) -> None:
        """Initialise the cart view."""
        super().__init__()

    def on_enter(self) -> None:
        """No-op entry hook."""
        return None

    def on_exit(self) -> None:
        """No-op exit hook."""
        return None

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def remove_item(self, item_id: str, quantity: int = 1) -> str | dict[str, Any]:
        """Remove an item or reduce its quantity.

        Args:
            item_id: Identifier of the variant to remove.
            quantity: Quantity to remove.

        Returns:
            str | dict[str, Any]: Backend removal result.
        """
        app = cast("StatefulShoppingApp", self.app)
        return app.remove_from_cart(item_id=item_id, quantity=quantity)

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def checkout(self, discount_code: str | None = None) -> str | dict[str, Any]:
        """Checkout the cart and create an order.

        Args:
            discount_code: Optional discount code.

        Returns:
            str | dict[str, Any]: Order confirmation.
        """
        app = cast("StatefulShoppingApp", self.app)
        return app.checkout(discount_code=discount_code)


# OrderListView
class OrderListView(AppState):
    """State listing all completed orders."""

    def __init__(self) -> None:
        """Initialise the order list view."""
        super().__init__()

    def on_enter(self) -> None:
        """No-op entry hook."""
        return None

    def on_exit(self) -> None:
        """No-op exit hook."""
        return None

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def view_order(self, order_id: str) -> dict[str, Any]:
        """Open details for a specific order.

        Args:
            order_id: Order identifier.

        Returns:
            dict[str, Any]: Order detail payload.
        """
        app = cast("StatefulShoppingApp", self.app)
        return app.get_order_details(order_id=order_id)


# OrderDetailView
class OrderDetailView(AppState):
    """Detailed view for a single order."""

    def __init__(self, order_id: str) -> None:
        """Bind state to a specific order.

        Args:
            order_id: Identifier of the order to display.
        """
        super().__init__()
        self.order_id = order_id

    def on_enter(self) -> None:
        """No-op entry hook."""
        return None

    def on_exit(self) -> None:
        """No-op exit hook."""
        return None

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def view_order(self) -> dict[str, Any]:
        """Retrieve backend data for the current order.

        Returns:
            dict[str, Any]: Order detail payload.
        """
        app = cast("StatefulShoppingApp", self.app)
        return app.get_order_details(order_id=self.order_id)
