"""State definitions for the stateful DoorDash app."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from are.simulation.types import OperationType, disable_events

from pas.apps.core import AppState
from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from pas.apps.doordash.app import StatefulDoordashApp


class RestaurantList(AppState):
    """Home state for browsing and searching restaurants."""

    def on_enter(self) -> None:
        """Called when entering restaurant list state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving restaurant list state."""
        pass

    @user_tool()
    @pas_event_registered()
    def list_restaurants(self) -> list[dict[str, Any]]:
        """List all nearby restaurants.

        Returns:
            List of restaurant dictionaries with id, name, cuisine, rating, and delivery time.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).list_restaurants()

    @user_tool()
    @pas_event_registered()
    def search_restaurants(self, query: str) -> list[dict[str, Any]]:
        """Search restaurants by keyword.

        Args:
            query: Search term to match against restaurant name or cuisine type.

        Returns:
            List of matching restaurant dictionaries.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).search_restaurants(query)

    @user_tool()
    @pas_event_registered()
    def open_restaurant(self, restaurant_id: str) -> dict[str, Any]:
        """Open a restaurant detail page.

        Args:
            restaurant_id: Unique identifier of the restaurant to view.

        Returns:
            Restaurant details including menu items list.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).get_restaurant(restaurant_id)

    @user_tool()
    @pas_event_registered()
    def view_cart(self) -> dict[str, Any]:
        """Navigate to cart view to see current items.

        Returns:
            Current cart contents with items and total price.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).get_cart()

    @user_tool()
    @pas_event_registered()
    def view_orders(self) -> dict[str, Any]:
        """Navigate to order history.

        Returns:
            Dictionary containing orders list and pagination info.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).list_orders()


class RestaurantDetail(AppState):
    """State for viewing a specific restaurant and its menu.

    Users can browse the restaurant's menu items, view restaurant information,
    and select items to view in detail.

    Attributes:
        restaurant_id: ID of the restaurant being viewed.
    """

    def __init__(self, restaurant_id: str) -> None:
        """Initialize restaurant detail state.

        Args:
            restaurant_id: Unique identifier of the restaurant.
        """
        super().__init__()
        self.restaurant_id = restaurant_id

    def on_enter(self) -> None:
        """Called when entering restaurant detail state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving restaurant detail state."""
        pass

    @user_tool()
    @pas_event_registered()
    def get_restaurant(self, restaurant_id: str) -> dict[str, Any]:
        """Fetch restaurant information.

        Args:
            restaurant_id: Unique identifier of the restaurant.

        Returns:
            Restaurant details including name, cuisine, rating, and delivery time.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).get_restaurant(restaurant_id)

    @user_tool()
    @pas_event_registered()
    def list_menu(self, restaurant_id: str) -> list[dict[str, Any]]:
        """List menu categories and items.

        Args:
            restaurant_id: Unique identifier of the restaurant.

        Returns:
            List of menu items with name, price, category, and availability.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).list_menu(restaurant_id)

    @user_tool()
    @pas_event_registered()
    def open_menu_item(self, item_id: str) -> dict[str, Any]:
        """Open detail page for a menu item.

        Args:
            item_id: Unique identifier of the menu item to view.

        Returns:
            Complete menu item details including description and customization options.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).get_item(item_id)

    @user_tool()
    @pas_event_registered()
    def search_menu_item(self, query: str) -> list[dict[str, Any]]:
        """Search menu items by name or description within this restaurant.

        Args:
            query: Search term to match against menu item name or description.

        Returns:
            List of matching menu items with details.
        """
        with disable_events():
            app = cast("StatefulDoordashApp", self.app)
            return app.search_menu_item(query, restaurant_id=self.restaurant_id)


class MenuItemDetail(AppState):
    """State for viewing a specific menu item with customization options.

    Users can view item details, select customizations, and add the item
    to their cart.

    Attributes:
        item_id: ID of the menu item being viewed.
        restaurant_id: ID of the parent restaurant.
    """

    def __init__(self, item_id: str, restaurant_id: str) -> None:
        """Initialize menu item detail state.

        Args:
            item_id: Unique identifier of the menu item.
            restaurant_id: Unique identifier of the parent restaurant.
        """
        super().__init__()
        self.item_id = item_id
        self.restaurant_id = restaurant_id

    def on_enter(self) -> None:
        """Called when entering menu item detail state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving menu item detail state."""
        pass

    @user_tool()
    @pas_event_registered()
    def get_item(self, item_id: str) -> dict[str, Any]:
        """Fetch menu item details.

        Args:
            item_id: Unique identifier of the menu item.

        Returns:
            Item details including price, description, and available customizations.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).get_item(item_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def add_cart(self, item_id: str, quantity: int, customizations: dict[str, str] | None = None) -> str:
        """Add item to shopping cart.

        Args:
            item_id: Unique identifier of the menu item.
            quantity: Number of items to add.
            customizations: Selected customization options (e.g., {"size": "Large", "spice": "Medium"}).

        Returns:
            Success message confirming item was added to cart.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).add_to_cart(item_id, quantity, customizations)


class CartView(AppState):
    """State for viewing and managing the shopping cart.

    Users can view all items in their cart, update quantities, remove items,
    and proceed to checkout.
    """

    def on_enter(self) -> None:
        """Called when entering cart view state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving cart view state."""
        pass

    @user_tool()
    @pas_event_registered()
    def get_cart(self) -> dict[str, Any]:
        """Get the user's current cart contents.

        Returns:
            Dictionary containing items list and total price.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).get_cart()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def update_cart(self, item_id: str, quantity: int) -> str:
        """Modify item quantity in cart.

        Args:
            item_id: Unique identifier of the cart item.
            quantity: New quantity (use 0 to remove item).

        Returns:
            Success message confirming quantity was updated.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).update_cart(item_id, quantity)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def remove_from_cart(self, item_id: str) -> str:
        """Remove an item from cart.

        Args:
            item_id: Unique identifier of the cart item to remove.

        Returns:
            Success message confirming item was removed.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).remove_from_cart(item_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def clear_cart(self) -> str:
        """Clear all items from the cart.

        Returns:
            Success message confirming cart was cleared.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).clear_cart()

    @user_tool()
    @pas_event_registered()
    def checkout(self) -> dict[str, Any]:
        """Navigate to checkout view.

        Returns:
            Checkout information including cart summary and current delivery/payment settings.
        """
        with disable_events():
            app = cast("StatefulDoordashApp", self.app)
            return {
                "cart": app.get_cart(),
                "delivery_address": app.delivery_address,
                "payment_method": app.payment_method,
            }


class CheckoutView(AppState):
    """State for checkout and order placement.

    Users can set their delivery address, select payment method, and
    finalize their order.
    """

    def on_enter(self) -> None:
        """Called when entering checkout state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving checkout state."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def set_address(self, address: str) -> str:
        """Set or update delivery address.

        Args:
            address: Full delivery address string.

        Returns:
            Confirmation message with the address.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).set_delivery_address(address)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def set_payment(self, method: str) -> str:
        """Set or update payment method.

        Args:
            method: Payment method identifier (e.g., "credit_card", "paypal", "cash").

        Returns:
            Confirmation message with the payment method.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).set_payment_method(method)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def submit_order(self) -> str:
        """Submit order and navigate to order detail.

        Returns:
            Order ID of the newly created order.

        Note:
            This will empty the cart and create a new order with status "placed".
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).place_order()


class OrderListView(AppState):
    """State for viewing order history.

    Users can view all their past orders and select one to view details.
    """

    def on_enter(self) -> None:
        """Called when entering order list state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving order list state."""
        pass

    @user_tool()
    @pas_event_registered()
    def list_orders(self) -> dict[str, Any]:
        """List all past orders.

        Returns:
            Dictionary containing orders list and pagination info.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).list_orders()

    @user_tool()
    @pas_event_registered()
    def open_order(self, order_id: str) -> dict[str, Any]:
        """Open detail page for a specific order.

        Args:
            order_id: Unique identifier of the order to view.

        Returns:
            Complete order details including all items and delivery information.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).get_order(order_id)


class OrderDetail(AppState):
    """State for viewing a specific order's details.

    Users can view complete order information, track delivery status,
    cancel active orders, or reorder previous items.

    Attributes:
        order_id: ID of the order being viewed.
    """

    def __init__(self, order_id: str) -> None:
        """Initialize order detail state.

        Args:
            order_id: Unique identifier of the order.
        """
        super().__init__()
        self.order_id = order_id

    def on_enter(self) -> None:
        """Called when entering order detail state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving order detail state."""
        pass

    @user_tool()
    @pas_event_registered()
    def get_order(self, order_id: str) -> dict[str, Any]:
        """Fetch full order details.

        Args:
            order_id: Unique identifier of the order.

        Returns:
            Complete order information including items, status, delivery address,
            payment method, and timestamps.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).get_order(order_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def cancel_order(self, order_id: str) -> str:
        """Cancel an ongoing order.

        Args:
            order_id: Unique identifier of the order to cancel.

        Returns:
            Confirmation message that order was cancelled.

        Note:
            Only orders with status "placed", "preparing", or "delivering" can be cancelled.
            Delivered or already cancelled orders cannot be cancelled.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).cancel_order(order_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def reorder_order(self, order_id: str) -> str:
        """Reorder all items from this order.

        Args:
            order_id: Unique identifier of the order to reorder from.

        Returns:
            Success message indicating items were added to cart.

        Note:
            This adds all items from the specified order to the current cart.
            Navigate to cart to review and checkout.
        """
        with disable_events():
            return cast("StatefulDoordashApp", self.app).reorder(order_id)
