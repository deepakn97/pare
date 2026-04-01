"""Stateful food delivery application package."""

from __future__ import annotations

from pas.apps.food_delivery.app import StatefulFoodDeliveryApp
from pas.apps.food_delivery.states import (
    CartView,
    CheckoutView,
    MenuItemDetail,
    OrderDetail,
    OrderListView,
    RestaurantDetail,
    RestaurantList,
)

__all__ = [
    "CartView",
    "CheckoutView",
    "MenuItemDetail",
    "OrderDetail",
    "OrderListView",
    "RestaurantDetail",
    "RestaurantList",
    "StatefulFoodDeliveryApp",
]
