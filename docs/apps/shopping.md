# Stateful Shopping App

`pare.apps.shopping.app.StatefulShoppingApp` pairs PARE navigation with the Meta-ARE `ShoppingApp`.
It starts in `ShoppingHome()` and pushes additional states for product detail, variant detail, cart, and order views.

## Navigation States

---

## ShoppingHome

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_products(offset: int = 0, limit: int = 10)` | `ShoppingApp.list_all_products(offset=offset, limit=limit)` | Dict with items and pagination metadata | Remains in `ShoppingHome` |
| `view_product(product_id: str)` | `ShoppingApp.get_product_details(product_id=product_id)` | Product detail dict | Completed event transitions to `ProductDetail(product_id)` |
| `view_cart()` | `ShoppingApp.list_cart()` | Cart payload dict | Transitions to `CartView` |
| `list_orders()` | `ShoppingApp.list_orders()` | List of order summaries | Transitions to `OrderListView` |

---

## ProductDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `view_variant(item_id: str)` | `ShoppingApp._get_item(item_id=item_id)` | Variant detail dict | Completed event transitions to `VariantDetail(item_id)` |

---

## VariantDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `add_to_cart(quantity: int = 1)` | `ShoppingApp.add_to_cart(item_id=self.item_id, quantity=quantity)` | Confirmation string or updated cart dict | Completed event transitions to `CartView` |

---

## CartView

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `remove_item(item_id: str, quantity: int = 1)` | `ShoppingApp.remove_from_cart(item_id=item_id, quantity=quantity)` | Confirmation string or updated cart dict | Remains in `CartView` |
| `checkout(discount_code: Optional[str] = None)` | `ShoppingApp.checkout(discount_code=discount_code)` | Order confirmation string or dict | Completed event transitions to `OrderDetailView(order_id)` |

---

## OrderListView

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `view_order(order_id: str)` | `ShoppingApp.get_order_details(order_id=order_id)` | Order detail dict | Completed event transitions to `OrderDetailView(order_id)` |

---

## OrderDetailView

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `view_order()` | `ShoppingApp.get_order_details(order_id=self.order_id)` | Order detail dict | Remains in `OrderDetailView` |

---

## Navigation Helpers

- `set_current_state(...)` is used for all forward transitions.
- `ShoppingHome → ProductDetail → VariantDetail → CartView → OrderDetailView` flows are triggered entirely via completed events.
- Destructive or write operations (`add_to_cart`, `checkout`) perform automatic transitions based on the returned payload.
- `create_root_state()` returns `ShoppingHome` as the initial view.
