"""Stateful Apartment app combining ARE ApartmentListingApp with PAS navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from are.simulation.apps.apartment_listing import ApartmentListingApp

from pas.apps.apartment.states import (
    ApartmentDetail,
    ApartmentHome,
    ApartmentSaved,
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
        """Create and return the root state for this app.

        Returns:
            ApartmentHome: Initial navigation state.
        """
        return ApartmentHome()

    def open_search(self) -> str:
        """Navigate to search page."""
        return "open_search"

    def open_saved(self) -> str:
        """Navigate to saved page."""
        return "open_saved"

    def go_back(self) -> str:
        """Go back to home."""
        return "go_back"

    def _navigate(self, fname: str, args: dict[str, Any]) -> None:
        """Update navigation state based on the completed action.

        Args:
            fname: Function name for routing.
            args: Arguments of the action.
        """
        if fname in {"get_apartment_details", "view_apartment"}:
            apt_id = args.get("apartment_id")
            if apt_id:
                self.set_current_state(ApartmentDetail(apartment_id=apt_id))
            return

        if fname == "open_search":
            self.set_current_state(ApartmentSearch())
            return

        if fname == "open_saved":
            self.set_current_state(ApartmentSaved())
            return

        if fname == "update_apartment":
            apt_id = args.get("apartment_id")
            if apt_id:
                self.set_current_state(ApartmentDetail(apartment_id=apt_id))
            return

        if fname in {"save_apartment", "remove_saved_apartment"}:
            # No navigation change needed
            return

        if fname == "go_back":
            self.load_root_state()
            return

        if fname == "delete_apartment":
            self.load_root_state()
            return

    def _execute_operation(self, fname: str, event_args: dict[str, Any]) -> None:
        """Execute the actual apartment operation.

        Args:
            fname: Function name.
            event_args: Arguments for the operation.
        """
        apartment_id = event_args.get("apartment_id")
        if not apartment_id:
            return

        if fname == "update_apartment":
            new_price = event_args.get("new_price")
            if new_price is not None:
                ApartmentListingApp.update_apartment(self, apartment_id=apartment_id, new_price=new_price)
        elif fname == "delete_apartment":
            ApartmentListingApp.delete_apartment(self, apartment_id=apartment_id)
        elif fname == "save_apartment":
            ApartmentListingApp.save_apartment(self, apartment_id=apartment_id)
        elif fname == "remove_saved_apartment":
            ApartmentListingApp.remove_saved_apartment(self, apartment_id=apartment_id)

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Handle state transition after a simulated ARE backend event.

        Args:
            event: Completed event with function name and arguments.
        """
        fname = event.function_name()
        if fname is None:
            return

        # Safely extract event args
        event_args: dict[str, Any] = {}
        action = getattr(event, "action", None)
        if action is not None and hasattr(action, "args"):
            event_args = cast("dict[str, Any]", getattr(action, "args", {}))

        # Execute the actual operation first
        self._execute_operation(fname, event_args)

        # Then handle navigation
        self._navigate(fname, event_args)
