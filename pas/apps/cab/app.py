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
        self.load_root_state()  # start in CabHome()

    def create_root_state(self) -> CabHome:
        """Return a fresh home state."""
        return CabHome()

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Update navigation based on completed cab operations."""
        action = getattr(event, "action", None)
        if action is None:
            return

        func_name = event.function_name()
        if not func_name:
           return

        event_args = {}
        action = getattr(event, "action", None)
        if action and hasattr(action, "args"):
            event_args = action.args or {}

        match func_name:

            case "list_rides":
                start = event_args.get("start_location")
                end = event_args.get("end_location")
                ride_time = event_args.get("ride_time")
                if start and end:
                    self.set_current_state(
                        CabServiceOptions(start, end, ride_time)
                    )

  
            case "get_quotation":
                ride_obj = getattr(event, "result", None)
                if ride_obj:
                    self.set_current_state(
                        CabQuotationDetail(ride_obj)
                    )


            case "confirm_order":
                return


            case "order_ride":
                ride_obj = getattr(event, "result", None) or self.on_going_ride

                if ride_obj and ride_obj.ride_id:
                    self.set_current_state(
                        CabRideDetail(ride_obj.ride_id)
                    ) 

            case "user_cancel_ride" | "cancel_ride" | "end_ride":
                self.load_root_state()


            case _:
                pass
