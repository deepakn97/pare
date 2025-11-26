"""Stateful Apartment app combining ARE ApartmentListingApp with PAS navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from are.simulation.apps.apartment_listing import ApartmentListingApp

from pas.apps.apartment.states import (
    ApartmentDetail,
    ApartmentHome,
    ApartmentSaved,
    ApartmentSearch,
)
from pas.apps.core import StatefulApp
from pas.apps.tool_decorators import user_tool

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

    # Navigation tools
    @user_tool()
    def open_search(self) -> str:
        """Navigate to the search screen.

        Returns:
            str: Indicator string used by tests.
        """
        return "open_search"

    @user_tool()
    def open_saved(self) -> str:
        """Navigate to the saved apartments screen.

        Returns:
            str: Indicator string used by tests.
        """
        return "open_saved"

    @user_tool()
    def go_back(self) -> str:
        """Navigate back to the home screen.

        Returns:
            str: Indicator string used by tests.
        """
        return "go_back"

    # Internal dispatch helpers
    def _run_backend_if_needed(self, fname: str, args: dict[str, Any]) -> None:
        """Execute backend operations that tests do not auto-run.

        Args:
            fname: Function name of the backend call.
            args: Backend arguments passed via the CompletedEvent.
        """
        backend_funcs = {
            "update_apartment",
            "delete_apartment",
            "save_apartment",
            "remove_saved_apartment",
        }

        if fname not in backend_funcs:
            return

        action_func = getattr(self, fname, None)
        if callable(action_func):
            clean_args = {k: v for k, v in args.items() if k != "self"}
            action_func(**clean_args)

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

        if fname == "delete_apartment":
            self.load_root_state()
            return

        if fname in {"save_apartment", "remove_saved_apartment"}:
            return

        if fname == "go_back":
            self.load_root_state()
            return

    # Dispatch
    def _dispatch(self, fname: str, args: dict[str, Any]) -> None:
        """Dispatch backend operations and navigation handling.

        Args:
            fname: Name of the executed function.
            args: Arguments passed to the function.
        """
        self._run_backend_if_needed(fname, args)
        self._navigate(fname, args)

    # Main entry
    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Handle state transition after a simulated ARE backend event.

        Args:
            event: Completed event with function name and arguments.
        """
        action = getattr(event, "action", None)
        if action is None:
            return

        fname = event.function_name()
        if not fname:
            return

        args = action.args or {}
        self._dispatch(fname, args)
