"""Stateful DoorDash app with PAS navigation."""

from __future__ import annotations

import contextlib
import logging
import textwrap
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from are.simulation.tool_utils import OperationType, app_tool, data_tool
from are.simulation.types import EventType
from are.simulation.utils import get_state_dict, uuid_hex
from are.simulation.utils.type_utils import type_check

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent

from pas.apps.core import StatefulApp
from pas.apps.doordash.states import (
    CartView,
    CheckoutView,
    MenuItemDetail,
    OrderDetail,
    OrderListView,
    RestaurantDetail,
    RestaurantList,
)
from pas.apps.tool_decorators import pas_event_registered

logger = logging.getLogger(__name__)


@dataclass
class MenuItem:
    """Menu item model.

    Represents a purchasable item belonging to a restaurant.
    """

    item_id: str
    name: str
    price: float
    restaurant_id: str
    description: str = ""
    category: str = ""
    available: bool = True
    customizations: dict[str, list[str]] = field(default_factory=dict)

    def __str__(self) -> str:
        return textwrap.dedent(
            f"""
            ID: {self.item_id}
            Name: {self.name}
            Price: ${self.price:.2f}
            Restaurant: {self.restaurant_id}
            Description: {self.description}
            Category: {self.category}
            Available: {self.available}
            """
        )

    def get_state(self) -> dict[str, Any]:
        """Serialize menu item state."""
        return get_state_dict(
            self,
            ["item_id", "name", "price", "restaurant_id", "description", "category", "available", "customizations"],
        )

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Restore menu item from serialized state."""
        self.item_id = state_dict["item_id"]
        self.name = state_dict["name"]
        self.price = state_dict["price"]
        self.restaurant_id = state_dict["restaurant_id"]
        self.description = state_dict.get("description", "")
        self.category = state_dict.get("category", "")
        self.available = state_dict.get("available", True)
        self.customizations = state_dict.get("customizations", {})


@dataclass
class Restaurant:
    """Restaurant model with menu references."""

    restaurant_id: str
    name: str
    cuisine: str
    rating: float = 0.0
    delivery_time: int = 30
    menu_items: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return textwrap.dedent(
            f"""
            ID: {self.restaurant_id}
            Name: {self.name}
            Cuisine: {self.cuisine}
            Rating: {self.rating}/5.0
            Delivery Time: {self.delivery_time} min
            Menu Items: {len(self.menu_items)}
            """
        )

    def get_state(self) -> dict[str, Any]:
        """Serialize restaurant state."""
        return get_state_dict(self, ["restaurant_id", "name", "cuisine", "rating", "delivery_time", "menu_items"])

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Restore restaurant from serialized state."""
        self.restaurant_id = state_dict["restaurant_id"]
        self.name = state_dict["name"]
        self.cuisine = state_dict["cuisine"]
        self.rating = state_dict.get("rating", 0.0)
        self.delivery_time = state_dict.get("delivery_time", 30)
        self.menu_items = state_dict.get("menu_items", [])


@dataclass
class CartItem:
    """Item stored in the active shopping cart."""

    item_id: str
    name: str
    quantity: int
    price: float
    customizations: dict[str, str] = field(default_factory=dict)


@dataclass
class Order:
    """Placed order snapshot."""

    order_id: str
    restaurant_id: str
    restaurant_name: str
    order_status: str
    order_date: datetime | float
    order_total: float
    delivery_address: str
    payment_method: str
    order_items: dict[str, CartItem] = field(default_factory=dict)

    def __str__(self) -> str:
        order_date_str = (
            datetime.fromtimestamp(self.order_date, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(self.order_date, (int, float))
            else str(self.order_date)
        )
        return textwrap.dedent(
            f"""
            Order ID: {self.order_id}
            Restaurant: {self.restaurant_name}
            Status: {self.order_status}
            Total: ${self.order_total:.2f}
            Address: {self.delivery_address}
            Payment: {self.payment_method}
            Date: {order_date_str}
            Items: {len(self.order_items)}
            """
        )

    def get_state(self) -> dict[str, Any]:
        """Serialize order state."""
        return {
            "order_id": self.order_id,
            "restaurant_id": self.restaurant_id,
            "restaurant_name": self.restaurant_name,
            "order_status": self.order_status,
            "order_date": self.order_date.isoformat() if isinstance(self.order_date, datetime) else self.order_date,
            "order_total": self.order_total,
            "delivery_address": self.delivery_address,
            "payment_method": self.payment_method,
            "order_items": {
                k: {
                    "item_id": v.item_id,
                    "name": v.name,
                    "quantity": v.quantity,
                    "price": v.price,
                    "customizations": v.customizations,
                }
                for k, v in self.order_items.items()
            },
        }

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Restore order from serialized state."""
        self.order_id = state_dict["order_id"]
        self.restaurant_id = state_dict["restaurant_id"]
        self.restaurant_name = state_dict["restaurant_name"]
        self.order_status = state_dict["order_status"]
        self.order_total = state_dict["order_total"]
        self.delivery_address = state_dict["delivery_address"]
        self.payment_method = state_dict["payment_method"]

        if isinstance(state_dict["order_date"], str):
            try:
                self.order_date = datetime.fromisoformat(state_dict["order_date"])
            except ValueError:
                # Try to convert string to float (timestamp)
                try:
                    self.order_date = float(state_dict["order_date"])
                except (ValueError, TypeError):
                    # Fallback to current timestamp if conversion fails
                    self.order_date = datetime.now(UTC).timestamp()
        else:
            self.order_date = state_dict["order_date"]

        self.order_items = {}
        for item_id, item_data in state_dict.get("order_items", {}).items():
            self.order_items[item_id] = CartItem(**item_data)


@dataclass
class StatefulDoordashApp(StatefulApp):
    """A DoorDash application that manages restaurant browsing, cart management, checkout, and order history with state-aware transitions.

    Key Features:
    - Restaurant Management: Browse, search, and view restaurant details
    - Menu Management: View and search menu items with customization options
    - Cart Management: Add, update, remove items with quantity control
    - Order Management: Place orders, track status, view history, cancel and reorder
    - Checkout Flow: Set delivery address and payment method
    - State Management: Save and load application state

    Notes:
    - Cart can only contain items from a single restaurant at a time
    - Order IDs are automatically generated when placing orders
    - All monetary values are in USD
    """

    name: str | None = None
    restaurants: dict[str, Restaurant] = field(default_factory=dict)
    menu_items: dict[str, MenuItem] = field(default_factory=dict)
    cart: dict[str, CartItem] = field(default_factory=dict)
    orders: dict[str, Order] = field(default_factory=dict)
    delivery_address: str = ""
    payment_method: str = ""

    def __post_init__(self) -> None:
        """Initialize the DoorDash app."""
        super().__init__(self.name or "doordash")
        self.load_root_state()

    def create_root_state(self) -> RestaurantList:
        """Create the root navigation state."""
        return RestaurantList()

    def reset(self) -> None:
        """Reset the app to empty state."""
        super().reset()
        self.restaurants.clear()
        self.menu_items.clear()
        self.cart.clear()
        self.orders.clear()
        self.delivery_address = ""
        self.payment_method = ""

    def _get_restaurant_by_id(self, restaurant_id: str) -> Restaurant:
        """Get restaurant by ID with validation."""
        if restaurant_id not in self.restaurants:
            raise KeyError(f"Restaurant {restaurant_id} not found")
        return self.restaurants[restaurant_id]

    def _get_menu_item_by_id(self, item_id: str) -> MenuItem:
        """Get menu item by ID with validation."""
        if item_id not in self.menu_items:
            raise KeyError(f"Menu item {item_id} not found")
        return self.menu_items[item_id]

    def _validate_cart_restaurant_consistency(self) -> str | None:
        """Validate that all cart items are from the same restaurant."""
        if not self.cart:
            return None

        restaurant_ids = set()
        for item_id in self.cart:
            menu_item = self.menu_items.get(item_id)
            if not menu_item:
                raise ValueError(f"Cart contains invalid item: {item_id}")
            restaurant_ids.add(menu_item.restaurant_id)

        if len(restaurant_ids) > 1:
            raise ValueError("Cart contains items from multiple restaurants")

        return restaurant_ids.pop() if restaurant_ids else None

    @type_check
    @data_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def create_restaurant_with_menu(
        self,
        name: str,
        cuisine: str,
        rating: float = 0.0,
        delivery_time: int = 30,
        menu_items_data: list[dict[str, Any]] | None = None,
    ) -> str:
        """Create a restaurant with initial menu items."""
        if not isinstance(rating, (int, float)):
            raise TypeError(f"Rating must be a number, got {type(rating)}.")
        if rating < 0.0 or rating > 5.0:
            raise ValueError("Rating must be between 0.0 and 5.0")
        if not isinstance(delivery_time, int):
            raise TypeError(f"Delivery time must be an integer, got {type(delivery_time)}.")
        if delivery_time < 0:
            raise ValueError("Delivery time must be non-negative")

        restaurant_id = uuid_hex(self.rng)
        restaurant = Restaurant(
            restaurant_id=restaurant_id,
            name=name,
            cuisine=cuisine,
            rating=rating,
            delivery_time=delivery_time,
            menu_items=[],
        )

        if menu_items_data:
            for item_data in menu_items_data:
                item_id = uuid_hex(self.rng)
                menu_item = MenuItem(
                    item_id=item_id,
                    restaurant_id=restaurant_id,
                    name=item_data.get("name", ""),
                    price=item_data.get("price", 0.0),
                    description=item_data.get("description", ""),
                    category=item_data.get("category", ""),
                    available=item_data.get("available", True),
                    customizations=item_data.get("customizations", {}),
                )
                self.menu_items[item_id] = menu_item
                restaurant.menu_items.append(item_id)

        self.restaurants[restaurant_id] = restaurant
        return restaurant_id

    @type_check
    @data_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def create_order_with_time(
        self,
        restaurant_id: str,
        items: list[dict[str, Any]],
        delivery_address: str,
        payment_method: str,
        order_date: str,
        order_status: str = "placed",
    ) -> str:
        """Create an order with specific timestamp."""
        try:
            order_timestamp = datetime.strptime(order_date, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()
        except ValueError as e:
            raise ValueError("Invalid datetime format. Use YYYY-MM-DD HH:MM:SS") from e

        restaurant = self._get_restaurant_by_id(restaurant_id)

        order_id = uuid_hex(self.rng)
        order_items = {}
        total = 0.0

        for item_data in items:
            item_id = item_data.get("item_id", uuid_hex(self.rng))
            cart_item = CartItem(
                item_id=item_id,
                name=item_data.get("name", ""),
                quantity=item_data.get("quantity", 1),
                price=item_data.get("price", 0.0),
                customizations=item_data.get("customizations", {}),
            )
            order_items[item_id] = cart_item
            total += cart_item.price * cart_item.quantity

        order = Order(
            order_id=order_id,
            restaurant_id=restaurant_id,
            restaurant_name=restaurant.name,
            order_status=order_status,
            order_date=order_timestamp,
            order_total=total,
            delivery_address=delivery_address,
            payment_method=payment_method,
            order_items=order_items,
        )

        self.orders[order_id] = order
        return order_id

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def list_restaurants(self) -> list[dict[str, Any]]:
        """List all available restaurants."""
        return [
            {
                "restaurant_id": r.restaurant_id,
                "name": r.name,
                "cuisine": r.cuisine,
                "rating": r.rating,
                "delivery_time": r.delivery_time,
            }
            for r in self.restaurants.values()
        ]

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def search_restaurants(self, query: str) -> list[dict[str, Any]]:
        """Search restaurants by name or cuisine."""
        if not isinstance(query, str):
            raise TypeError(f"Query must be a string, got {type(query)}.")
        if len(query.strip()) == 0:
            raise ValueError("Query must be non-empty.")

        query_lower = query.lower()
        return [
            {
                "restaurant_id": r.restaurant_id,
                "name": r.name,
                "cuisine": r.cuisine,
                "rating": r.rating,
                "delivery_time": r.delivery_time,
            }
            for r in self.restaurants.values()
            if query_lower in r.name.lower() or query_lower in r.cuisine.lower()
        ]

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def get_restaurant(self, restaurant_id: str) -> dict[str, Any]:
        """Get details of a specific restaurant."""
        if not isinstance(restaurant_id, str):
            raise TypeError(f"Restaurant ID must be a string, got {type(restaurant_id)}.")
        if len(restaurant_id) == 0:
            raise ValueError("Restaurant ID must be non-empty.")

        restaurant = self._get_restaurant_by_id(restaurant_id)

        return {
            "restaurant_id": restaurant.restaurant_id,
            "name": restaurant.name,
            "cuisine": restaurant.cuisine,
            "rating": restaurant.rating,
            "delivery_time": restaurant.delivery_time,
            "menu_items": restaurant.menu_items,
        }

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def list_menu(self, restaurant_id: str) -> list[dict[str, Any]]:
        """List menu items for a specific restaurant."""
        if not isinstance(restaurant_id, str):
            raise TypeError(f"Restaurant ID must be a string, got {type(restaurant_id)}.")
        if len(restaurant_id) == 0:
            raise ValueError("Restaurant ID must be non-empty.")

        restaurant = self._get_restaurant_by_id(restaurant_id)

        return [
            {
                "item_id": self.menu_items[item_id].item_id,
                "name": self.menu_items[item_id].name,
                "price": self.menu_items[item_id].price,
                "category": self.menu_items[item_id].category,
                "available": self.menu_items[item_id].available,
            }
            for item_id in restaurant.menu_items
            if item_id in self.menu_items
        ]

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def search_menu_item(self, query: str, restaurant_id: str | None = None) -> list[dict[str, Any]]:
        """Search menu items by name or description."""
        if not isinstance(query, str):
            raise TypeError(f"Query must be a string, got {type(query)}.")
        if len(query.strip()) == 0:
            raise ValueError("Query must be non-empty.")

        query_lower = query.lower()
        items_to_search = []

        if restaurant_id is not None:
            restaurant = self._get_restaurant_by_id(restaurant_id)
            items_to_search = [
                self.menu_items[item_id] for item_id in restaurant.menu_items if item_id in self.menu_items
            ]
        else:
            items_to_search = list(self.menu_items.values())

        return [
            {
                "item_id": item.item_id,
                "name": item.name,
                "price": item.price,
                "description": item.description,
                "category": item.category,
                "restaurant_id": item.restaurant_id,
                "available": item.available,
            }
            for item in items_to_search
            if query_lower in item.name.lower() or query_lower in item.description.lower()
        ]

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def get_item(self, item_id: str) -> dict[str, Any]:
        """Get detailed information about a menu item."""
        if not isinstance(item_id, str):
            raise TypeError(f"Item ID must be a string, got {type(item_id)}.")
        if len(item_id) == 0:
            raise ValueError("Item ID must be non-empty.")

        item = self._get_menu_item_by_id(item_id)

        return {
            "item_id": item.item_id,
            "name": item.name,
            "price": item.price,
            "description": item.description,
            "category": item.category,
            "available": item.available,
            "customizations": item.customizations,
            "restaurant_id": item.restaurant_id,
        }

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def add_to_cart(self, item_id: str, quantity: int = 1, customizations: dict[str, str] | None = None) -> str:
        """Add an item to the shopping cart."""
        if not isinstance(item_id, str):
            raise TypeError(f"Item ID must be a string, got {type(item_id)}.")
        if len(item_id) == 0:
            raise ValueError("Item ID must be non-empty.")
        if not isinstance(quantity, int):
            raise TypeError(f"Quantity must be an integer, got {type(quantity)}.")
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        item = self._get_menu_item_by_id(item_id)

        if not item.available:
            raise ValueError(f"Item {item.name} is not available")

        if self.cart:
            current_restaurant = self._validate_cart_restaurant_consistency()
            if current_restaurant and current_restaurant != item.restaurant_id:
                raise ValueError(
                    f"Cannot add item from different restaurant. Cart contains items from restaurant {current_restaurant}"
                )

        if item_id in self.cart:
            self.cart[item_id].quantity += quantity
        else:
            self.cart[item_id] = CartItem(
                item_id=item_id,
                name=item.name,
                quantity=quantity,
                price=item.price,
                customizations=customizations or {},
            )
        return f"Added {quantity}x {item.name} to cart"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def update_cart(self, item_id: str, quantity: int) -> str:
        """Update the quantity of an item in the cart."""
        if not isinstance(item_id, str):
            raise TypeError(f"Item ID must be a string, got {type(item_id)}.")
        if len(item_id) == 0:
            raise ValueError("Item ID must be non-empty.")
        if not isinstance(quantity, int):
            raise TypeError(f"Quantity must be an integer, got {type(quantity)}.")

        if item_id not in self.cart:
            raise KeyError(f"Item {item_id} not in cart")

        if quantity == 0:
            name = self.cart[item_id].name
            del self.cart[item_id]
            return f"Removed {name} from cart"
        elif quantity > 0:
            self.cart[item_id].quantity = quantity
            return f"Updated quantity to {quantity}"
        else:
            raise ValueError("Quantity cannot be negative")

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def remove_from_cart(self, item_id: str) -> str:
        """Remove an item from the cart."""
        if not isinstance(item_id, str):
            raise TypeError(f"Item ID must be a string, got {type(item_id)}.")
        if len(item_id) == 0:
            raise ValueError("Item ID must be non-empty.")

        if item_id not in self.cart:
            raise KeyError(f"Item {item_id} not in cart")

        name = self.cart[item_id].name
        del self.cart[item_id]
        return f"Removed {name} from cart"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def clear_cart(self) -> str:
        """Clear all items from the cart."""
        count = len(self.cart)
        self.cart.clear()
        return f"Removed {count} items from cart"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def get_cart(self) -> dict[str, Any]:
        """Get current cart contents and total."""
        total = sum(item.price * item.quantity for item in self.cart.values())
        return {
            "items": [
                {
                    "item_id": item.item_id,
                    "name": item.name,
                    "quantity": item.quantity,
                    "price": item.price,
                    "customizations": item.customizations,
                }
                for item in self.cart.values()
            ],
            "total": total,
        }

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def set_delivery_address(self, address: str) -> str:
        """Set the delivery address for the order."""
        if not isinstance(address, str):
            raise TypeError(f"Address must be a string, got {type(address)}.")
        if len(address.strip()) == 0:
            raise ValueError("Address must be non-empty.")

        self.delivery_address = address
        return f"Delivery address set to: {address}"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def set_payment_method(self, method: str) -> str:
        """Set the payment method for the order."""
        if not isinstance(method, str):
            raise TypeError(f"Payment method must be a string, got {type(method)}.")
        if len(method.strip()) == 0:
            raise ValueError("Payment method must be non-empty.")

        self.payment_method = method
        return f"Payment method set to: {method}"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def place_order(self) -> str:
        """Place an order with current cart contents."""
        if not self.cart:
            raise ValueError("Cart is empty")
        if not self.delivery_address or not self.delivery_address.strip():
            raise ValueError("Delivery address not set")
        if not self.payment_method or not self.payment_method.strip():
            raise ValueError("Payment method not set")

        restaurant_id = self._validate_cart_restaurant_consistency()
        if restaurant_id is None:
            raise ValueError("Cannot determine restaurant for order")
        restaurant = self.restaurants.get(restaurant_id)
        if restaurant is None:
            raise KeyError(f"Restaurant {restaurant_id} no longer exists")

        unavailable_items = []
        for item_id, cart_item in self.cart.items():
            menu_item = self.menu_items.get(item_id)
            if menu_item is None:
                unavailable_items.append(f"{cart_item.name} (removed from menu)")
            elif not menu_item.available:
                unavailable_items.append(f"{cart_item.name} (no longer available)")

        if unavailable_items:
            raise ValueError(f"Cannot place order. The following items are unavailable: {', '.join(unavailable_items)}")

        order_id = uuid_hex(self.rng)
        total = sum(item.price * item.quantity for item in self.cart.values())

        order = Order(
            order_id=order_id,
            restaurant_id=restaurant_id,
            restaurant_name=restaurant.name,
            order_status="placed",
            order_date=self.time_manager.time(),
            order_total=total,
            delivery_address=self.delivery_address,
            payment_method=self.payment_method,
            order_items=deepcopy(self.cart),
        )

        self.orders[order_id] = order
        self.cart.clear()
        return order_id

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def list_orders(self, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        """List orders with pagination."""
        if not isinstance(limit, int):
            raise TypeError(f"Limit must be an integer, got {type(limit)}.")
        if not isinstance(offset, int):
            raise TypeError(f"Offset must be an integer, got {type(offset)}.")
        if limit <= 0:
            raise ValueError("Limit must be positive")
        if offset < 0:
            raise ValueError("Offset must be non-negative")

        sorted_orders = sorted(
            self.orders.values(),
            key=lambda o: o.order_date if isinstance(o.order_date, (int, float)) else 0,
            reverse=True,
        )

        total = len(sorted_orders)
        end = min(offset + limit, total)
        paginated_orders = sorted_orders[offset:end]

        return {
            "orders": [
                {
                    "order_id": order.order_id,
                    "restaurant_name": order.restaurant_name,
                    "total": order.order_total,
                    "status": order.order_status,
                    "created_at": order.order_date,
                }
                for order in paginated_orders
            ],
            "total_orders": total,
            "offset": offset,
            "limit": limit,
        }

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def get_order(self, order_id: str) -> dict[str, Any]:
        """Get complete details of a specific order."""
        if not isinstance(order_id, str):
            raise TypeError(f"Order ID must be a string, got {type(order_id)}.")
        if len(order_id) == 0:
            raise ValueError("Order ID must be non-empty.")

        order = self.orders.get(order_id)
        if order is None:
            raise KeyError(f"Order {order_id} not found")

        return {
            "order_id": order.order_id,
            "restaurant_name": order.restaurant_name,
            "items": [
                {
                    "name": item.name,
                    "quantity": item.quantity,
                    "price": item.price,
                    "customizations": item.customizations,
                }
                for item in order.order_items.values()
            ],
            "total": order.order_total,
            "status": order.order_status,
            "delivery_address": order.delivery_address,
            "payment_method": order.payment_method,
            "created_at": order.order_date,
        }

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def cancel_order(self, order_id: str) -> str:
        """Cancel an active order."""
        if not isinstance(order_id, str):
            raise TypeError(f"Order ID must be a string, got {type(order_id)}.")
        if len(order_id) == 0:
            raise ValueError("Order ID must be non-empty.")

        order = self.orders.get(order_id)
        if order is None:
            raise KeyError(f"Order {order_id} not found")

        if order.order_status in ["delivered", "cancelled"]:
            raise ValueError(f"Cannot cancel order with status: {order.order_status}")

        order.order_status = "cancelled"
        return f"Order {order_id} cancelled"

    def _process_reorder_items(self, order: Order) -> tuple[list[str], list[str]]:
        """Process items from an order for reordering.

        Returns:
            Tuple of (added_items, unavailable_items) lists.
        """
        added_items = []
        unavailable_items = []
        for item_id, cart_item in order.order_items.items():
            menu_item = self.menu_items.get(item_id)

            if menu_item is None:
                unavailable_items.append(f"{cart_item.name} (no longer on menu)")
                continue

            if not menu_item.available:
                unavailable_items.append(f"{cart_item.name} (currently unavailable)")
                continue

            self.cart[item_id] = CartItem(
                item_id=cart_item.item_id,
                name=cart_item.name,
                quantity=cart_item.quantity,
                price=menu_item.price,
                customizations=cart_item.customizations,
            )
            added_items.append(cart_item.name)
        return added_items, unavailable_items

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def reorder(self, order_id: str) -> str:
        """Reorder a previous order into the cart."""
        if not isinstance(order_id, str):
            raise TypeError(f"Order ID must be a string, got {type(order_id)}.")
        if len(order_id) == 0:
            raise ValueError("Order ID must be non-empty.")

        order = self.orders.get(order_id)
        if order is None:
            raise KeyError(f"Order {order_id} not found")
        if self.cart:
            current_restaurant = self._validate_cart_restaurant_consistency()
            if current_restaurant and current_restaurant != order.restaurant_id:
                raise ValueError("Cart contains items from a different restaurant. Please clear your cart first.")

        added_items, unavailable_items = self._process_reorder_items(order)

        if not added_items:
            if unavailable_items:
                return f"Could not add any items. Unavailable: {', '.join(unavailable_items)}"
            return "No items were added to cart"

        result = f"Added {len(added_items)} items to cart"
        if unavailable_items:
            result += f". Unavailable: {', '.join(unavailable_items)}"

        return result

    def get_state(self) -> dict[str, Any]:
        """Serialize complete app state."""
        return {
            "restaurants": {k: v.get_state() for k, v in self.restaurants.items()},
            "menu_items": {k: v.get_state() for k, v in self.menu_items.items()},
            "cart": {
                k: {
                    "item_id": v.item_id,
                    "name": v.name,
                    "quantity": v.quantity,
                    "price": v.price,
                    "customizations": v.customizations,
                }
                for k, v in self.cart.items()
            },
            "orders": {k: v.get_state() for k, v in self.orders.items()},
            "delivery_address": self.delivery_address,
            "payment_method": self.payment_method,
        }

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Restore app state from serialized data."""
        self.restaurants.clear()
        self.menu_items.clear()
        self.cart.clear()
        self.orders.clear()

        for r_id, r_data in state_dict.get("restaurants", {}).items():
            restaurant = Restaurant(
                restaurant_id=r_data["restaurant_id"],
                name=r_data["name"],
                cuisine=r_data["cuisine"],
            )
            restaurant.load_state(r_data)
            self.restaurants[r_id] = restaurant

        for item_id, item_data in state_dict.get("menu_items", {}).items():
            item = MenuItem(
                item_id=item_data["item_id"],
                name=item_data["name"],
                price=item_data["price"],
                restaurant_id=item_data["restaurant_id"],
            )
            item.load_state(item_data)
            self.menu_items[item_id] = item

        for item_id, item_data in state_dict.get("cart", {}).items():
            self.cart[item_id] = CartItem(**item_data)

        for order_id, order_data in state_dict.get("orders", {}).items():
            order_date = order_data["order_date"]
            if isinstance(order_date, str):
                with contextlib.suppress(ValueError):
                    order_date = datetime.fromisoformat(order_date)

            order = Order(
                order_id=order_data["order_id"],
                restaurant_id=order_data["restaurant_id"],
                restaurant_name=order_data["restaurant_name"],
                order_status=order_data["order_status"],
                order_date=order_date,
                order_total=order_data["order_total"],
                delivery_address=order_data["delivery_address"],
                payment_method=order_data["payment_method"],
            )
            order.load_state(order_data)
            self.orders[order_id] = order

        self.delivery_address = state_dict.get("delivery_address", "")
        self.payment_method = state_dict.get("payment_method", "")

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Handle navigation state transitions based on user actions."""
        current_state = self.current_state
        fname = event.function_name()

        if current_state is None or fname is None:
            return

        action = event.action
        event_args = action.resolved_args or action.args
        metadata_value = event.metadata.return_value if event.metadata else None

        if isinstance(current_state, RestaurantList):
            self._handle_restaurant_list_transition(fname, event_args, metadata_value)
        elif isinstance(current_state, RestaurantDetail):
            self._handle_restaurant_detail_transition(fname, event_args, metadata_value)
        elif isinstance(current_state, MenuItemDetail):
            self._handle_menu_item_detail_transition(fname, event_args, metadata_value)
        elif isinstance(current_state, CartView):
            self._handle_cart_view_transition(fname, event_args, metadata_value)
        elif isinstance(current_state, CheckoutView):
            self._handle_checkout_view_transition(fname, event_args, metadata_value)
        elif isinstance(current_state, OrderListView):
            self._handle_order_list_view_transition(fname, event_args, metadata_value)
        elif isinstance(current_state, OrderDetail):
            self._handle_order_detail_transition(fname, event_args, metadata_value)

    def _handle_restaurant_list_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from restaurant list state."""
        if fname == "open_restaurant":
            restaurant_id = args.get("restaurant_id")
            if restaurant_id:
                self.set_current_state(RestaurantDetail(restaurant_id=str(restaurant_id)))
        elif fname == "view_cart":
            self.set_current_state(CartView())
        elif fname == "view_orders":
            self.set_current_state(OrderListView())

    def _handle_restaurant_detail_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from restaurant detail state."""
        if fname == "open_menu_item":
            item_id = args.get("item_id")
            if item_id and isinstance(self.current_state, RestaurantDetail):
                restaurant_id = self.current_state.restaurant_id
                self.set_current_state(MenuItemDetail(item_id=str(item_id), restaurant_id=restaurant_id))

    def _handle_menu_item_detail_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from menu item detail state."""
        if fname == "add_cart":
            self.set_current_state(CartView())

    def _handle_cart_view_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from cart view state."""
        if fname == "checkout":
            self.set_current_state(CheckoutView())

    def _handle_checkout_view_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from checkout state."""
        if fname == "submit_order":
            order_id = metadata if isinstance(metadata, str) else None
            if order_id:
                self.set_current_state(OrderDetail(order_id=order_id))

    def _handle_order_list_view_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from order list state."""
        if fname == "open_order":
            order_id = args.get("order_id")
            if order_id:
                self.set_current_state(OrderDetail(order_id=str(order_id)))

    def _handle_order_detail_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from order detail state."""
        if fname == "reorder_order":
            self.set_current_state(CartView())
