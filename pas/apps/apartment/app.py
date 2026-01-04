"""Stateful Apartment app combining ARE ApartmentListingApp with PAS navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from are.simulation.apps.apartment_listing import ApartmentListingApp

from pas.apps.apartment.states import (
    ApartmentDetail,
    ApartmentFavorites,
    ApartmentHome,
    ApartmentSearch,
)
from pas.apps.core import StatefulApp

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent


class StatefulApartmentApp(StatefulApp, ApartmentListingApp):
    """Apartment app with navigation-aware PAS behavior."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apartment app and load the root navigation state."""
        super().__init__(*args, **kwargs)
        self.load_root_state()

    def create_root_state(self) -> ApartmentHome:
        """Return the root navigation state for the apartment app."""
        return ApartmentHome()

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Update navigation state after an apartment operation completes."""
        current_state = self.current_state
        fname = event.function_name()

        if current_state is None or fname is None:  # defensive, Email-style
            return

        action = event.action
        args: dict[str, Any] = action.args if action and hasattr(action, "args") else {}

        if isinstance(current_state, ApartmentHome):
            self._handle_home_transition(fname, args)
            return

        if isinstance(current_state, ApartmentDetail):
            self._handle_detail_transition(fname, args)
            return

        if isinstance(current_state, ApartmentSearch):
            self._handle_search_transition(fname, args)
            return

        if isinstance(current_state, ApartmentFavorites):
            self._handle_saved_transition(fname, args)

    def _handle_home_transition(self, fname: str, args: dict[str, Any]) -> None:
        if fname == "view_apartment":
            apt_id = args.get("apartment_id")
            if apt_id:
                self.set_current_state(ApartmentDetail(apartment_id=apt_id))
            return

        if fname == "open_search":
            self.set_current_state(ApartmentSearch())
            return

        if fname == "open_favorites":
            self.set_current_state(ApartmentFavorites())
            return

    def _handle_detail_transition(self, fname: str, args: dict[str, Any]) -> None:
        if fname == "go_back":
            self.load_root_state()
            return

    def _handle_search_transition(self, fname: str, args: dict[str, Any]) -> None:
        if fname == "view_apartment":
            apt_id = args.get("apartment_id")
            if apt_id:
                self.set_current_state(ApartmentDetail(apartment_id=apt_id))
            return
        if fname == "go_back":
            self.load_root_state()
            return

    def _handle_saved_transition(self, fname: str, args: dict[str, Any]) -> None:
        if fname == "view_apartment":
            apt_id = args.get("apartment_id")
            if apt_id:
                self.set_current_state(ApartmentDetail(apartment_id=apt_id))
            return

        if fname == "go_back":
            self.load_root_state()
            return
