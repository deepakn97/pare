"""Tests for the stateful shopping app navigation flow."""

from __future__ import annotations
from typing import TYPE_CHECKING, Callable, Any

import pytest
from are.simulation.types import Action, CompletedEvent, EventMetadata, EventType

from pas.apps.shopping.app import StatefulShoppingApp
from pas.apps.shopping.states import (
    ShoppingHome,
    ProductDetail,
    VariantDetail,
    CartView,
    OrderListView,
    OrderDetailView,
)

if TYPE_CHECKING:
    from collections.abc import Generator



# Utility: Create CompletedEvent to drive state transitions
def make_event(
    app: StatefulShoppingApp,
    func: Callable[..., object],
    **kwargs: Any
) -> CompletedEvent:
    action = Action(function=func, args={"self": app, **kwargs}, app=app)
    return CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=EventMetadata(),
        event_time=0,
        event_id="test-shopping-event",
    )



# Fixture: Create a shopping app with product + variants
@pytest.fixture()
def shopping_app() -> Generator[StatefulShoppingApp, None, None]:
    app = StatefulShoppingApp(name="shopping")

    # A product with two variants
    pid = app.add_product("Laptop")
    iid1 = app.add_item_to_product(pid, price=1000.0)
    iid2 = app.add_item_to_product(pid, price=1500.0)

    # stash ids for convenience
    app._pid = pid
    app._iid1 = iid1
    app._iid2 = iid2

    yield app



# Helpers matching Contacts tests style
def _home(app: StatefulShoppingApp) -> ShoppingHome:
    state = app.current_state
    assert isinstance(state, ShoppingHome)
    return state


def _product_detail(app: StatefulShoppingApp) -> ProductDetail:
    state = app.current_state
    assert isinstance(state, ProductDetail)
    return state


def _variant_detail(app: StatefulShoppingApp) -> VariantDetail:
    state = app.current_state
    assert isinstance(state, VariantDetail)
    return state


def _cart_view(app: StatefulShoppingApp) -> CartView:
    state = app.current_state
    assert isinstance(state, CartView)
    return state


# 1. Initial State
def test_app_starts_in_home(shopping_app: StatefulShoppingApp) -> None:
    """App should start in ShoppingHome with an empty navigation stack."""
    assert isinstance(shopping_app.current_state, ShoppingHome)
    assert shopping_app.navigation_stack == []



# 2. Product Navigation
def test_open_product_moves_to_detail(shopping_app: StatefulShoppingApp) -> None:
    """view_product → get_product_details should push ProductDetail."""
    pid = shopping_app._pid

    # Trigger user tool
    _home(shopping_app).view_product(pid)

    # CompletedEvent
    evt = make_event(shopping_app, shopping_app.get_product_details, product_id=pid)
    shopping_app.handle_state_transition(evt)

    assert isinstance(shopping_app.current_state, ProductDetail)
    assert shopping_app.current_state.product_id == pid
    assert len(shopping_app.navigation_stack) == 1
    assert isinstance(shopping_app.navigation_stack[0], ShoppingHome)


# 3. Variant Navigation
def test_open_variant_moves_to_variant_detail(shopping_app: StatefulShoppingApp) -> None:
    """view_variant → get_item should move from ProductDetail to VariantDetail."""

    pid = shopping_app._pid
    iid = shopping_app._iid1

    # Step 1: product detail
    _home(shopping_app).view_product(pid)
    evt1 = make_event(shopping_app, shopping_app.get_product_details, product_id=pid)
    shopping_app.handle_state_transition(evt1)

    # Step 2: variant detail
    _product_detail(shopping_app).view_variant(iid)
    evt2 = make_event(shopping_app, shopping_app.get_item, item_id=iid)
    shopping_app.handle_state_transition(evt2)

    assert isinstance(shopping_app.current_state, VariantDetail)
    assert shopping_app.current_state.item_id == iid
    assert len(shopping_app.navigation_stack) == 2
    assert isinstance(shopping_app.navigation_stack[0], ShoppingHome)
    assert isinstance(shopping_app.navigation_stack[1], ProductDetail)



# 4. Cart Behavior
def test_add_to_cart_opens_cart_view(shopping_app: StatefulShoppingApp) -> None:
    """Adding to cart should open CartView."""

    pid = shopping_app._pid
    iid = shopping_app._iid1

    # Navigate to variant
    _home(shopping_app).view_product(pid)
    shopping_app.handle_state_transition(
        make_event(shopping_app, shopping_app.get_product_details, product_id=pid)
    )
    _product_detail(shopping_app).view_variant(iid)
    shopping_app.handle_state_transition(
        make_event(shopping_app, shopping_app.get_item, item_id=iid)
    )

    # Add to cart from VariantDetail
    _variant_detail(shopping_app).add_to_cart(quantity=1)
    evt = make_event(shopping_app, shopping_app.add_to_cart, item_id=iid, quantity=1)
    shopping_app.handle_state_transition(evt)

    assert isinstance(shopping_app.current_state, CartView)
    assert iid in shopping_app.cart


def test_remove_from_cart_stays_in_cart(shopping_app: StatefulShoppingApp) -> None:
    """Removing an item keeps user in CartView."""

    iid = shopping_app._iid1
    shopping_app.add_to_cart(iid, quantity=2)

    # Enter CartView via root + tool for consistency
    _home(shopping_app).view_cart()
    shopping_app.handle_state_transition(
        make_event(shopping_app, shopping_app.get_cart)
    )

    _cart_view(shopping_app).remove_item(iid, quantity=1)
    evt = make_event(shopping_app, shopping_app.remove_from_cart, item_id=iid, quantity=1)
    shopping_app.handle_state_transition(evt)

    assert isinstance(shopping_app.current_state, CartView)
    assert shopping_app.cart[iid].quantity == 1


# 5. Orders
def test_checkout_creates_order_and_opens_detail(shopping_app: StatefulShoppingApp) -> None:
    """Checkout should create an order and push OrderDetailView."""

    iid = shopping_app._iid1
    shopping_app.add_to_cart(iid, 1)

    # Navigate to cart
    _home(shopping_app).view_cart()
    shopping_app.handle_state_transition(make_event(shopping_app, shopping_app.get_cart))

    # Checkout: user tool
    order_id = _cart_view(shopping_app).checkout()

    evt = make_event(shopping_app, shopping_app.checkout, discount_code="")
    evt._return_value = order_id  # same pattern as contacts tests for edit_contact
    shopping_app.handle_state_transition(evt)

    assert isinstance(shopping_app.current_state, OrderDetailView)
    assert shopping_app.current_state.order_id == order_id


def test_list_orders_opens_order_list(shopping_app: StatefulShoppingApp) -> None:
    """Order list should open OrderListView."""
    _home(shopping_app).list_orders()

    evt = make_event(shopping_app, shopping_app.list_orders)
    shopping_app.handle_state_transition(evt)

    assert isinstance(shopping_app.current_state, OrderListView)


def test_view_order_from_list_opens_detail(shopping_app: StatefulShoppingApp) -> None:
    """view_order → get_order_details should open OrderDetailView."""
    iid = shopping_app._iid1
    shopping_app.add_to_cart(iid, 1)
    order_id = shopping_app.checkout()

    # Go to list view
    _home(shopping_app).list_orders()
    shopping_app.handle_state_transition(make_event(shopping_app, shopping_app.list_orders))

    # View order
    _list_view = shopping_app.current_state
    assert isinstance(_list_view, OrderListView)

    _list_view.view_order(order_id)
    evt = make_event(shopping_app, shopping_app.get_order_details, order_id=order_id)
    shopping_app.handle_state_transition(evt)

    assert isinstance(shopping_app.current_state, OrderDetailView)
    assert shopping_app.current_state.order_id == order_id



# 6. Navigation Stack
def test_navigation_stack_product_then_variant(shopping_app: StatefulShoppingApp) -> None:
    """Stack should accumulate Home → ProductDetail → VariantDetail."""

    pid = shopping_app._pid
    iid = shopping_app._iid1

    # Product detail
    _home(shopping_app).view_product(pid)
    shopping_app.handle_state_transition(
        make_event(shopping_app, shopping_app.get_product_details, product_id=pid)
    )

    # Variant detail
    _product_detail(shopping_app).view_variant(iid)
    shopping_app.handle_state_transition(
        make_event(shopping_app, shopping_app.get_item, item_id=iid)
    )

    assert len(shopping_app.navigation_stack) == 2
    assert isinstance(shopping_app.navigation_stack[0], ShoppingHome)
    assert isinstance(shopping_app.navigation_stack[1], ProductDetail)
