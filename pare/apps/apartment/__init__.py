"""Stateful Apartment app module exports."""

from __future__ import annotations

from pare.apps.apartment.app import StatefulApartmentApp
from pare.apps.apartment.states import (
    ApartmentDetail,
    ApartmentFavorites,
    ApartmentHome,
    ApartmentSearch,
)

__all__ = [
    "ApartmentDetail",
    "ApartmentFavorites",
    "ApartmentHome",
    "ApartmentSearch",
    "StatefulApartmentApp",
]
