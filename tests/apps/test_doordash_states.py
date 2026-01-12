"""Tests for the DoorDash Stateful App navigation flow.

Key principles:
- Unit tests use _make_event + handle_state_transition for single transitions
- Integration tests use StateAwareEnvironmentWrapper for multi-step flows
- All tests verify BOTH functionality AND state transitions
"""
from __future__ import annotations

from typing import Any

import pytest
from are.simulation.types import Action, CompletedEvent, EventMetadata, EventType

from pas.apps.doordash.app import StatefulDoordashApp
from pas.apps.doordash.states import (
    CartView,
    CheckoutView,
    MenuItemDetail,
    OrderDetail,
    OrderListView,
    RestaurantDetail,
    RestaurantList,
)
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp
from pas.environment import StateAwareEnvironmentWrapper


def _restaurant_list_state(app: StatefulDoordashApp) -> RestaurantList:
    """Get current state as RestaurantList with assertion."""
    state = app.current_state
    assert isinstance(state, RestaurantList)
    return state


def _restaurant_detail_state(app: StatefulDoordashApp) -> RestaurantDetail:
    """Get current state as RestaurantDetail with assertion."""
    state = app.current_state
    assert isinstance(state, RestaurantDetail)
    return state


def _menu_item_detail_state(app: StatefulDoordashApp) -> MenuItemDetail:
    """Get current state as MenuItemDetail with assertion."""
    state = app.current_state
    assert isinstance(state, MenuItemDetail)
    return state


def _cart_view_state(app: StatefulDoordashApp) -> CartView:
    """Get current state as CartView with assertion."""
    state = app.current_state
    assert isinstance(state, CartView)
    return state


def _checkout_view_state(app: StatefulDoordashApp) -> CheckoutView:
    """Get current state as CheckoutView with assertion."""
    state = app.current_state
    assert isinstance(state, CheckoutView)
    return state


def _order_list_view_state(app: StatefulDoordashApp) -> OrderListView:
    """Get current state as OrderListView with assertion."""
    state = app.current_state
    assert isinstance(state, OrderListView)
    return state


def _order_detail_state(app: StatefulDoordashApp) -> OrderDetail:
    """Get current state as OrderDetail with assertion."""
    state = app.current_state
    assert isinstance(state, OrderDetail)
    return state


def _make_event(
    app: StatefulDoordashApp,
    func: callable,
    result: Any | None = None,
    **kwargs: Any,
) -> CompletedEvent:
    """Create a mock event for state transition tests."""
    action = Action(
        function=func,
        args={"self": app, **kwargs},
        app=app,
    )
    metadata = EventMetadata()
    metadata.return_value = result
    return CompletedEvent(
        event_id="test-event",
        event_type=EventType.USER,
        action=action,
        metadata=metadata,
        event_time=0,
    )


@pytest.fixture
def doordash_app() -> StatefulDoordashApp:
    """Create a DoorDash app with test data."""
    app = StatefulDoordashApp(name="doordash")

    # Create test restaurants with menu items
    restaurant1_id = app.create_restaurant_with_menu(
        name="Pizza Place",
        cuisine="Italian",
        rating=4.5,
        delivery_time=30,
        menu_items_data=[
            {"name": "Margherita Pizza", "price": 12.99, "description": "Classic pizza", "category": "Pizza"},
            {"name": "Pepperoni Pizza", "price": 14.99, "description": "Pepperoni pizza", "category": "Pizza"},
            {"name": "Caesar Salad", "price": 8.99, "description": "Fresh salad", "category": "Salad"},
        ],
    )

    restaurant2_id = app.create_restaurant_with_menu(
        name="Burger Joint",
        cuisine="American",
        rating=4.2,
        delivery_time=25,
        menu_items_data=[
            {"name": "Classic Burger", "price": 9.99, "description": "Beef burger", "category": "Burgers"},
            {"name": "Cheese Burger", "price": 10.99, "description": "Cheese burger", "category": "Burgers"},
        ],
    )

    # Store IDs for convenience
    app._restaurant1_id = restaurant1_id
    app._restaurant2_id = restaurant2_id

    # Get menu item IDs
    restaurant1 = app.restaurants[restaurant1_id]
    restaurant2 = app.restaurants[restaurant2_id]
    app._item1_id = restaurant1.menu_items[0]
    app._item2_id = restaurant1.menu_items[1]
    app._item3_id = restaurant2.menu_items[0]

    return app


@pytest.fixture
def env_with_doordash() -> StateAwareEnvironmentWrapper:
    """Create environment with DoorDash app registered and opened."""
    env = StateAwareEnvironmentWrapper()
    system_app = HomeScreenSystemApp(name="HomeScreen")
    aui_app = PASAgentUserInterface()
    doordash_app = StatefulDoordashApp(name="doordash")

    # Add test data
    restaurant1_id = doordash_app.create_restaurant_with_menu(
        name="Pizza Place",
        cuisine="Italian",
        rating=4.5,
        delivery_time=30,
        menu_items_data=[
            {"name": "Margherita Pizza", "price": 12.99, "description": "Classic pizza", "category": "Pizza"},
            {"name": "Pepperoni Pizza", "price": 14.99, "description": "Pepperoni pizza", "category": "Pizza"},
        ],
    )

    doordash_app._restaurant1_id = restaurant1_id
    restaurant1 = doordash_app.restaurants[restaurant1_id]
    doordash_app._item1_id = restaurant1.menu_items[0]
    doordash_app._item2_id = restaurant1.menu_items[1]

    env.register_apps([system_app, aui_app, doordash_app])
    env._open_app("doordash")
    return env



def test_app_starts_in_restaurant_list_state(doordash_app: StatefulDoordashApp) -> None:
    """App should start in RestaurantList with empty navigation stack."""
    assert isinstance(doordash_app.current_state, RestaurantList)
    assert doordash_app.navigation_stack == []


def test_open_restaurant_transition(doordash_app: StatefulDoordashApp) -> None:
    """Handler: open_restaurant from RestaurantList transitions to RestaurantDetail."""
    state = _restaurant_list_state(doordash_app)
    restaurant_id = doordash_app._restaurant1_id

    result = state.open_restaurant(restaurant_id)
    event = _make_event(doordash_app, state.open_restaurant, result=result, restaurant_id=restaurant_id)
    doordash_app.handle_state_transition(event)

    assert isinstance(doordash_app.current_state, RestaurantDetail)
    assert doordash_app.current_state.restaurant_id == restaurant_id


def test_open_menu_item_transition(doordash_app: StatefulDoordashApp) -> None:
    """Handler: open_menu_item from RestaurantDetail transitions to MenuItemDetail."""
    restaurant_id = doordash_app._restaurant1_id
    item_id = doordash_app._item1_id
    doordash_app.set_current_state(RestaurantDetail(restaurant_id))

    state = _restaurant_detail_state(doordash_app)
    result = state.open_menu_item(item_id)
    event = _make_event(doordash_app, state.open_menu_item, result=result, item_id=item_id)
    doordash_app.handle_state_transition(event)

    assert isinstance(doordash_app.current_state, MenuItemDetail)
    assert doordash_app.current_state.item_id == item_id
    assert doordash_app.current_state.restaurant_id == restaurant_id


def test_add_cart_transition(doordash_app: StatefulDoordashApp) -> None:
    """Handler: add_cart from MenuItemDetail transitions to CartView."""
    restaurant_id = doordash_app._restaurant1_id
    item_id = doordash_app._item1_id
    doordash_app.set_current_state(MenuItemDetail(item_id, restaurant_id))

    state = _menu_item_detail_state(doordash_app)
    result = state.add_cart(item_id, quantity=1)
    event = _make_event(doordash_app, state.add_cart, result=result, item_id=item_id, quantity=1)
    doordash_app.handle_state_transition(event)

    assert isinstance(doordash_app.current_state, CartView)


def test_submit_order_transition(doordash_app: StatefulDoordashApp) -> None:
    """Handler: submit_order from CheckoutView transitions to OrderDetail."""
    item_id = doordash_app._item1_id
    doordash_app.add_to_cart(item_id, quantity=1)
    doordash_app.delivery_address = "123 Main St"
    doordash_app.payment_method = "credit_card"
    doordash_app.set_current_state(CheckoutView())

    state = _checkout_view_state(doordash_app)
    result = state.submit_order()
    event = _make_event(doordash_app, state.submit_order, result=result)
    doordash_app.handle_state_transition(event)

    assert isinstance(doordash_app.current_state, OrderDetail)
    assert doordash_app.current_state.order_id == result



class TestDoordashEnvironmentIntegration:
    """Integration tests that exercise the full environment flow."""

    def test_full_order_flow(self, env_with_doordash: StateAwareEnvironmentWrapper) -> None:
        """Integration: RestaurantList -> RestaurantDetail -> MenuItemDetail -> CartView -> CheckoutView -> OrderDetail."""
        env = env_with_doordash
        app = env.get_app_with_class(StatefulDoordashApp)

        assert isinstance(app.current_state, RestaurantList)
        assert len(app.navigation_stack) == 0

        # Navigate through the full flow
        restaurant_id = app._restaurant1_id
        _restaurant_list_state(app).open_restaurant(restaurant_id)
        assert isinstance(app.current_state, RestaurantDetail)
        assert len(app.navigation_stack) == 1

        item_id = app._item1_id
        _restaurant_detail_state(app).open_menu_item(item_id)
        assert isinstance(app.current_state, MenuItemDetail)
        assert len(app.navigation_stack) == 2

        _menu_item_detail_state(app).add_cart(item_id, quantity=1)
        assert isinstance(app.current_state, CartView)
        assert len(app.navigation_stack) == 3

        _cart_view_state(app).checkout()
        assert isinstance(app.current_state, CheckoutView)
        assert len(app.navigation_stack) == 4

        _checkout_view_state(app).set_address("123 Main St")
        _checkout_view_state(app).set_payment("credit_card")
        order_id = _checkout_view_state(app).submit_order()
        assert isinstance(app.current_state, OrderDetail)
        assert app.current_state.order_id == order_id
        assert len(app.navigation_stack) == 5

    def test_view_orders_flow(self, env_with_doordash: StateAwareEnvironmentWrapper) -> None:
        """Integration: RestaurantList -> OrderListView -> OrderDetail."""
        env = env_with_doordash
        app = env.get_app_with_class(StatefulDoordashApp)

        # Create an order first
        restaurant_id = app._restaurant1_id
        item_id = app._item1_id
        order_id = app.create_order_with_time(
            restaurant_id=restaurant_id,
            items=[{"item_id": item_id, "name": "Test Item", "price": 10.0, "quantity": 1}],
            delivery_address="123 Main St",
            payment_method="credit_card",
            order_date="2024-01-01 12:00:00",
        )

        _restaurant_list_state(app).view_orders()
        assert isinstance(app.current_state, OrderListView)
        assert len(app.navigation_stack) == 1

        _order_list_view_state(app).open_order(order_id)
        assert isinstance(app.current_state, OrderDetail)
        assert app.current_state.order_id == order_id
        assert len(app.navigation_stack) == 2

    def test_reorder_flow(self, env_with_doordash: StateAwareEnvironmentWrapper) -> None:
        """Integration: OrderDetail -> reorder -> CartView -> CheckoutView."""
        env = env_with_doordash
        app = env.get_app_with_class(StatefulDoordashApp)

        # Create an order first
        restaurant_id = app._restaurant1_id
        item_id = app._item1_id
        order_id = app.create_order_with_time(
            restaurant_id=restaurant_id,
            items=[{"item_id": item_id, "name": "Test Item", "price": 10.0, "quantity": 1}],
            delivery_address="123 Main St",
            payment_method="credit_card",
            order_date="2024-01-01 12:00:00",
        )

        app.set_current_state(OrderDetail(order_id))
        _order_detail_state(app).reorder_order(order_id)
        assert isinstance(app.current_state, CartView)
        assert len(app.cart) > 0

        _cart_view_state(app).checkout()
        assert isinstance(app.current_state, CheckoutView)

    def test_go_back_navigation(self, env_with_doordash: StateAwareEnvironmentWrapper) -> None:
        """Integration: Test go_back navigation through states."""
        env = env_with_doordash
        app = env.get_app_with_class(StatefulDoordashApp)

        restaurant_id = app._restaurant1_id
        item_id = app._item1_id
        _restaurant_list_state(app).open_restaurant(restaurant_id)
        _restaurant_detail_state(app).open_menu_item(item_id)
        assert isinstance(app.current_state, MenuItemDetail)
        assert len(app.navigation_stack) == 2

        app.go_back()
        assert isinstance(app.current_state, RestaurantDetail)
        assert len(app.navigation_stack) == 1

        app.go_back()
        assert isinstance(app.current_state, RestaurantList)
        assert len(app.navigation_stack) == 0

    def test_cart_management(self, env_with_doordash: StateAwareEnvironmentWrapper) -> None:
        """Integration: Test cart operations."""
        env = env_with_doordash
        app = env.get_app_with_class(StatefulDoordashApp)

        item_id = app._item1_id
        app.add_to_cart(item_id, quantity=2)

        _restaurant_list_state(app).view_cart()
        assert isinstance(app.current_state, CartView)

        cart_state = _cart_view_state(app)
        cart = cart_state.get_cart()
        assert len(cart["items"]) == 1
        assert cart["items"][0]["quantity"] == 2

        cart_state.update_cart(item_id, quantity=3)
        cart = cart_state.get_cart()
        assert cart["items"][0]["quantity"] == 3

        cart_state.remove_from_cart(item_id)
        cart = cart_state.get_cart()
        assert len(cart["items"]) == 0
        assert cart["total"] == 0

    def test_multiple_items_cart_flow(self, env_with_doordash: StateAwareEnvironmentWrapper) -> None:
        """Integration: Add multiple items to cart, update quantities, then checkout."""
        env = env_with_doordash
        app = env.get_app_with_class(StatefulDoordashApp)

        restaurant_id = app._restaurant1_id
        item1_id = app._item1_id
        item2_id = app._item2_id

        _restaurant_list_state(app).open_restaurant(restaurant_id)
        _restaurant_detail_state(app).open_menu_item(item1_id)
        _menu_item_detail_state(app).add_cart(item1_id, quantity=2)
        assert isinstance(app.current_state, CartView)

        app.go_back()
        app.go_back()
        _restaurant_detail_state(app).open_menu_item(item2_id)
        _menu_item_detail_state(app).add_cart(item2_id, quantity=1)
        assert isinstance(app.current_state, CartView)

        cart = _cart_view_state(app).get_cart()
        assert len(cart["items"]) == 2

        _cart_view_state(app).update_cart(item1_id, quantity=3)
        _cart_view_state(app).remove_from_cart(item2_id)
        cart = _cart_view_state(app).get_cart()
        assert len(cart["items"]) == 1

        _cart_view_state(app).checkout()
        assert isinstance(app.current_state, CheckoutView)

        _checkout_view_state(app).set_address("789 Pine St")
        _checkout_view_state(app).set_payment("debit_card")
        order_id = _checkout_view_state(app).submit_order()
        assert isinstance(app.current_state, OrderDetail)
        assert len(app.cart) == 0



def test_add_item_from_different_restaurant_error(doordash_app: StatefulDoordashApp) -> None:
    """Test that adding items from different restaurants to cart raises error."""
    item1_id = doordash_app._item1_id  # From restaurant 1
    item3_id = doordash_app._item3_id  # From restaurant 2

    doordash_app.add_to_cart(item1_id, quantity=1)

    with pytest.raises(ValueError, match="different restaurant"):
        doordash_app.add_to_cart(item3_id, quantity=1)


def test_place_order_with_empty_cart_error(doordash_app: StatefulDoordashApp) -> None:
    """Test that placing order with empty cart raises error."""
    doordash_app.delivery_address = "123 Main St"
    doordash_app.payment_method = "credit_card"

    with pytest.raises(ValueError, match="Cart is empty"):
        doordash_app.place_order()


def test_place_order_without_address_error(doordash_app: StatefulDoordashApp) -> None:
    """Test that placing order without address raises error."""
    item_id = doordash_app._item1_id
    doordash_app.add_to_cart(item_id, quantity=1)
    doordash_app.payment_method = "credit_card"

    with pytest.raises(ValueError, match="Delivery address not set"):
        doordash_app.place_order()


def test_place_order_without_payment_error(doordash_app: StatefulDoordashApp) -> None:
    """Test that placing order without payment method raises error."""
    item_id = doordash_app._item1_id
    doordash_app.add_to_cart(item_id, quantity=1)
    doordash_app.delivery_address = "123 Main St"

    with pytest.raises(ValueError, match="Payment method not set"):
        doordash_app.place_order()


def test_cancel_delivered_order_error(doordash_app: StatefulDoordashApp) -> None:
    """Test that canceling a delivered order raises error."""
    restaurant_id = doordash_app._restaurant1_id
    item_id = doordash_app._item1_id
    order_id = doordash_app.create_order_with_time(
        restaurant_id=restaurant_id,
        items=[{"item_id": item_id, "name": "Test Item", "price": 10.0, "quantity": 1}],
        delivery_address="123 Main St",
        payment_method="credit_card",
        order_date="2024-01-01 12:00:00",
        order_status="delivered",
    )

    with pytest.raises(ValueError, match="Cannot cancel order with status"):
        doordash_app.cancel_order(order_id)


def test_save_and_load_state(doordash_app: StatefulDoordashApp) -> None:
    """Test that app state can be saved and loaded correctly."""
    item_id = doordash_app._item1_id
    doordash_app.add_to_cart(item_id, quantity=2)
    doordash_app.delivery_address = "123 Main St"
    doordash_app.payment_method = "credit_card"

    restaurant_id = doordash_app._restaurant1_id
    order_id = doordash_app.create_order_with_time(
        restaurant_id=restaurant_id,
        items=[{"item_id": item_id, "name": "Test Item", "price": 10.0, "quantity": 1}],
        delivery_address="456 Oak Ave",
        payment_method="paypal",
        order_date="2024-01-01 12:00:00",
    )

    state_dict = doordash_app.get_state()

    new_app = StatefulDoordashApp(name="doordash2")
    new_app.load_state(state_dict)

    assert len(new_app.restaurants) == len(doordash_app.restaurants)
    assert len(new_app.menu_items) == len(doordash_app.menu_items)
    assert len(new_app.cart) == len(doordash_app.cart)
    assert len(new_app.orders) == len(doordash_app.orders)
    assert new_app.delivery_address == doordash_app.delivery_address
    assert new_app.payment_method == doordash_app.payment_method
    assert new_app.cart[item_id].quantity == doordash_app.cart[item_id].quantity
    assert new_app.orders[order_id].order_status == doordash_app.orders[order_id].order_status


def test_reset_app(doordash_app: StatefulDoordashApp) -> None:
    """Test that reset clears all app state."""
    item_id = doordash_app._item1_id
    doordash_app.add_to_cart(item_id, quantity=1)
    doordash_app.delivery_address = "123 Main St"
    doordash_app.payment_method = "credit_card"

    doordash_app.reset()

    assert len(doordash_app.restaurants) == 0
    assert len(doordash_app.menu_items) == 0
    assert len(doordash_app.cart) == 0
    assert len(doordash_app.orders) == 0
    assert doordash_app.delivery_address == ""
    assert doordash_app.payment_method == ""
    assert isinstance(doordash_app.current_state, RestaurantList)
    assert len(doordash_app.navigation_stack) == 0
