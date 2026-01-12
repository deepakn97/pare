# Stateful DoorDash App

`pas.apps.doordash.app.StatefulDoordashApp` is a stateful DoorDash application that manages restaurant browsing, cart management, checkout, and order history with PAS navigation.
It launches in `RestaurantList` and transitions between restaurant browsing, menu viewing, cart management, checkout, and order tracking flows based on completed operations.

---

## Navigation States

---

### RestaurantList

Home screen for browsing and searching restaurants, viewing cart, and accessing order history.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_restaurants()` | `StatefulDoordashApp.list_restaurants()` | `list[dict[str, Any]]` restaurant summaries | Remains in `RestaurantList` |
| `search_restaurants(query: str)` | `StatefulDoordashApp.search_restaurants(query)` | `list[dict[str, Any]]` matching restaurants | Remains in `RestaurantList` |
| `open_restaurant(restaurant_id: str)` | `StatefulDoordashApp.get_restaurant(restaurant_id)` | `dict[str, Any]` restaurant details | → `RestaurantDetail(restaurant_id)` |
| `view_cart()` | `StatefulDoordashApp.get_cart()` | `dict[str, Any]` cart contents | → `CartView` |
| `view_orders()` | `StatefulDoordashApp.list_orders()` | `dict[str, Any]` orders list with pagination | → `OrderListView` |

---

### RestaurantDetail

Screen for viewing a specific restaurant and its menu items.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_restaurant(restaurant_id: str)` | `StatefulDoordashApp.get_restaurant(restaurant_id)` | `dict[str, Any]` restaurant details | Remains in `RestaurantDetail` |
| `list_menu(restaurant_id: str)` | `StatefulDoordashApp.list_menu(restaurant_id)` | `list[dict[str, Any]]` menu items | Remains in `RestaurantDetail` |
| `search_menu_item(query: str)` | `StatefulDoordashApp.search_menu_item(query, restaurant_id)` | `list[dict[str, Any]]` matching menu items | Remains in `RestaurantDetail` |
| `open_menu_item(item_id: str)` | `StatefulDoordashApp.get_item(item_id)` | `dict[str, Any]` menu item details | → `MenuItemDetail(item_id, restaurant_id)` |
| `go_back()` | — | Navigation indicator string | → Previous state (via navigation stack) |

---

### MenuItemDetail

Screen for viewing a specific menu item with customization options.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_item(item_id: str)` | `StatefulDoordashApp.get_item(item_id)` | `dict[str, Any]` menu item details | Remains in `MenuItemDetail` |
| `add_cart(item_id: str, quantity: int, customizations: dict[str, str] \| None = None)` | `StatefulDoordashApp.add_to_cart(item_id, quantity, customizations)` | `str` confirmation message | → `CartView` |
| `go_back()` | — | Navigation indicator string | → Previous state (via navigation stack) |

---

### CartView

Screen for viewing and managing the shopping cart.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_cart()` | `StatefulDoordashApp.get_cart()` | `dict[str, Any]` cart contents with items and total | Remains in `CartView` |
| `update_cart(item_id: str, quantity: int)` | `StatefulDoordashApp.update_cart(item_id, quantity)` | `str` confirmation message | Remains in `CartView` |
| `remove_from_cart(item_id: str)` | `StatefulDoordashApp.remove_from_cart(item_id)` | `str` confirmation message | Remains in `CartView` |
| `clear_cart()` | `StatefulDoordashApp.clear_cart()` | `str` confirmation message | Remains in `CartView` |
| `checkout()` | Reads cart, delivery address, and payment method | `dict[str, Any]` checkout info | → `CheckoutView` |
| `go_back()` | — | Navigation indicator string | → Previous state (via navigation stack) |

---

### CheckoutView

Screen for checkout and order placement.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `set_address(address: str)` | `StatefulDoordashApp.set_delivery_address(address)` | `str` confirmation message | Remains in `CheckoutView` |
| `set_payment(method: str)` | `StatefulDoordashApp.set_payment_method(method)` | `str` confirmation message | Remains in `CheckoutView` |
| `submit_order()` | `StatefulDoordashApp.place_order()` | `str` order ID | → `OrderDetail(order_id)` |
| `go_back()` | — | Navigation indicator string | → Previous state (via navigation stack) |

---

### OrderListView

Screen for viewing order history.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_orders()` | `StatefulDoordashApp.list_orders()` | `dict[str, Any]` orders list with pagination | Remains in `OrderListView` |
| `open_order(order_id: str)` | `StatefulDoordashApp.get_order(order_id)` | `dict[str, Any]` order details | → `OrderDetail(order_id)` |
| `go_back()` | — | Navigation indicator string | → Previous state (via navigation stack) |

---

### OrderDetail

Screen for viewing a specific order's details.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_order(order_id: str)` | `StatefulDoordashApp.get_order(order_id)` | `dict[str, Any]` complete order details | Remains in `OrderDetail` |
| `cancel_order(order_id: str)` | `StatefulDoordashApp.cancel_order(order_id)` | `str` confirmation message | Remains in `OrderDetail` |
| `reorder_order(order_id: str)` | `StatefulDoordashApp.reorder(order_id)` | `str` confirmation message | → `CartView` |
| `go_back()` | — | Navigation indicator string | → Previous state (via navigation stack) |

---

## Summary Table

| State | Context | Transitions Out | Self-Loops |
|-------|---------|-----------------|------------|
| **RestaurantList** | — | `open_restaurant` → RestaurantDetail, `view_cart` → CartView, `view_orders` → OrderListView | `list_restaurants`, `search_restaurants` |
| **RestaurantDetail** | restaurant_id | `open_menu_item` → MenuItemDetail, `go_back` → previous state | `get_restaurant`, `list_menu`, `search_menu_item` |
| **MenuItemDetail** | item_id, restaurant_id | `add_cart` → CartView, `go_back` → previous state | `get_item` |
| **CartView** | — | `checkout` → CheckoutView, `go_back` → previous state | `get_cart`, `update_cart`, `remove_from_cart`, `clear_cart` |
| **CheckoutView** | — | `submit_order` → OrderDetail, `go_back` → previous state | `set_address`, `set_payment` |
| **OrderListView** | — | `open_order` → OrderDetail, `go_back` → previous state | `list_orders` |
| **OrderDetail** | order_id | `reorder_order` → CartView, `go_back` → previous state | `get_order`, `cancel_order` |

---

## Navigation Helpers

- Navigation transitions are handled in `StatefulDoordashApp.handle_state_transition` based on the completed tool name.
- States store context parameters (e.g., `restaurant_id`, `item_id`, `order_id`) for navigation.
- Cart can only contain items from a single restaurant at a time.
- After order submission, the cart is automatically cleared.
- `go_back()` is inherited from `StatefulApp` and uses the navigation stack to return to the previous state.
- Order cancellation can only be performed on orders with status "placed", "preparing", or "delivering" (not "delivered" or "cancelled").
