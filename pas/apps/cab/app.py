"""Stateful cab app combining Meta-ARE cab backend with PAS navigation."""

from typing import Any
from are.simulation.apps.cab import CabApp
from are.simulation.types import CompletedEvent

from pas.apps.core import StatefulApp
from pas.apps.cab.states import (
    CabHome,
    CabRideDetail,
    CabServiceOptions,
    CabQuotationDetail,
)


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

        # Extract function name (calendar convention)
        function_name = event.function_name()
        if not function_name:
            return

        # Extract event args (calendar convention)
        event_args = action.args or {}

        match function_name:

            # User lists rides
            case "list_rides":
                start = event_args.get("start_location")
                end = event_args.get("end_location")
                ride_time = event_args.get("ride_time")

                if start and end:
                    self.set_current_state(
                        CabServiceOptions(start, end, ride_time)
                    )


            # User requests a quotation
            case "get_quotation":
                ride_obj = getattr(event, "result", None)
                if ride_obj:
                    self.set_current_state(
                        CabQuotationDetail(ride_obj)
                    )

            # Order confirmation does not change navigation
            case "confirm_order":
                return

            # User places order, move to ride detail
            case "order_ride":
                ride_obj = getattr(event, "result", None) or self.on_going_ride

                if ride_obj and ride_obj.ride_id:
                    self.set_current_state(
                        CabRideDetail(ride_obj.ride_id)
                    )

            # User or system ends/cancels ride → return to home
            case "user_cancel_ride" | "cancel_ride" | "end_ride":
                self.load_root_state()

            # Anything else: no navigation change
            case _:
                return
