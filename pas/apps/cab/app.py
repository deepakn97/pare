"""Stateful cab app combining Meta-ARE cab backend with PAS navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from are.simulation.apps.cab import CabApp

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent

from pas.apps.cab.states import (
    CabHome,
    CabQuotationDetail,
    CabRideDetail,
    CabServiceOptions,
)
from pas.apps.core import StatefulApp


class StatefulCabApp(StatefulApp, CabApp):
    """Cab client with navigation-aware user tool exposure."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialise the cab app and load the default home screen."""
        super().__init__(*args, **kwargs)
        self.load_root_state()  # Start in CabHome()

    def create_root_state(self) -> CabHome:
        """Return a fresh home state.

        Returns:
            CabHome: The initial root state for the cab app navigation.
        """
        return CabHome()

    def _handle_list_rides(self, args: dict[str, Any]) -> None:
        start = args.get("start_location")
        end = args.get("end_location")
        ride_time = args.get("ride_time")

        if start and end:
            self.set_current_state(CabServiceOptions(start, end, ride_time))

    def _handle_get_quotation(self, event: CompletedEvent) -> None:
        ride_obj = getattr(event, "result", None)
        if ride_obj:
            self.set_current_state(CabQuotationDetail(ride_obj))

    def _handle_order_ride(self, event: CompletedEvent) -> None:
        ride_obj = getattr(event, "result", None) or self.on_going_ride

        if ride_obj:
            # Find the ride index in ride_history
            try:
                ride_index = self.ride_history.index(ride_obj)
            except ValueError:
                # If not found, it's likely the most recent ride
                ride_index = len(self.ride_history) - 1
            self.set_current_state(CabRideDetail(ride_index))

    def _handle_finish(self) -> None:
        self.load_root_state()

    def _dispatch(self, fname: str, event: CompletedEvent, args: dict[str, Any]) -> None:
        """Small dispatcher to remove match-case complexity."""
        if fname == "list_rides":
            self._handle_list_rides(args)
        elif fname == "get_quotation":
            self._handle_get_quotation(event)
        elif fname == "order_ride":
            self._handle_order_ride(event)
        elif fname in {"user_cancel_ride", "cancel_ride", "end_ride"}:
            self._handle_finish()
        # confirm_order and others → no-op

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Update navigation state after a cab operation completes.

        Args:
            event: The completed event emitted by the cab backend. Contains the
                executed function name, arguments, and result of the cab action.

        Returns:
            None
        """
        action = getattr(event, "action", None)
        if action is None:
            return

        fname = event.function_name()
        if not fname:
            return

        event_args = action.args or {}
        self._dispatch(fname, event, event_args)
