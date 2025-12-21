"""Stateful cab app combining Meta-ARE cab backend with PAS navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from are.simulation.apps.cab import CabApp

from pas.apps.cab.states import (
    CabHome,
    CabQuotationDetail,
    CabRideDetail,
    CabServiceOptions,
)
from pas.apps.core import StatefulApp

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent


class StatefulCabApp(StatefulApp, CabApp):
    """Cab client with navigation-aware user tool exposure."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialise the cab app and load the default home screen."""
        super().__init__(*args, **kwargs)
        self.load_root_state()

    def create_root_state(self) -> CabHome:
        """Return the root navigation state for the cab app."""
        return CabHome()

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Update navigation state after a cab operation completes."""
        fname = event.function_name()
        if fname is None:
            return

        event_args: dict[str, Any] = {}
        action = getattr(event, "action", None)
        if action is not None and hasattr(action, "args"):
            event_args = cast("dict[str, Any]", getattr(action, "args", {}))

        match fname:
            case "list_rides":
                self._handle_list_rides(event_args)
            case "get_quotation" | "view_quotation":
                self._handle_get_quotation(event)
            case "order_ride" | "confirm_order":
                self._handle_order_ride(event)
            case "user_cancel_ride" | "end_ride":
                self._handle_finish()

    def _handle_list_rides(self, event_args: dict[str, Any]) -> None:
        """Navigate to service options after listing rides."""
        start = event_args.get("start_location")
        end = event_args.get("end_location")
        ride_time = event_args.get("ride_time")

        if start and end:
            self.set_current_state(CabServiceOptions(start, end, ride_time))

    def _handle_get_quotation(self, event: CompletedEvent) -> None:
        """Navigate to quotation detail after getting a quotation."""
        ride_obj = getattr(event, "result", None)
        if ride_obj:
            self.set_current_state(CabQuotationDetail(ride_obj))

    def _handle_order_ride(self, event: CompletedEvent) -> None:
        """Navigate to ride detail after ordering a ride."""
        ride_obj = getattr(event, "result", None)

        if ride_obj:
            # Try to find the ride in history by matching ride_id
            ride_index = None
            if hasattr(ride_obj, "ride_id"):
                for idx, ride in enumerate(self.ride_history):
                    if hasattr(ride, "ride_id") and ride.ride_id == ride_obj.ride_id:
                        ride_index = idx
                        break

            if ride_index is None and self.ride_history:
                ride_index = len(self.ride_history) - 1

            if ride_index is not None:
                self.set_current_state(CabRideDetail(ride_index))

    def _handle_finish(self) -> None:
        """Return to home screen after canceling or ending a ride."""
        self.load_root_state()
