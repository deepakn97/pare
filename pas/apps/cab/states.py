from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from are.simulation.types import OperationType, disable_events

from pas.apps.core import AppState
from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from are.simulation.apps.cab import Ride

    from pas.apps.cab.app import StatefulCabApp


# Home Screen
class CabHome(AppState):
    """Home view for cab operations such as listing rides, quotations, and history.

    This state provides the main interface for users to interact with the cab service,
    including listing available rides, getting quotations, ordering rides, and viewing
    ride history.
    """

    def on_enter(self) -> None:
        """Called when entering this state."""
        pass

    def on_exit(self) -> None:
        """Called when exiting this state."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_rides(
        self,
        start_location: str,
        end_location: str,
        ride_time: str | None = None,
    ) -> list[Ride]:
        """List available ride quotations for all service types.

        Args:
            start_location: The starting location for the ride.
            end_location: The destination location for the ride.
            ride_time: The time for the ride in format 'YYYY-MM-DD HH:MM:SS'. If None, the current time is used.

        Returns:
            list[Ride]: Available ride objects with quotations for all service types.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.list_rides(
                start_location=start_location,
                end_location=end_location,
                ride_time=ride_time,
            )

    # should navigate to CabRideDetail
    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def open_current_ride(self) -> Ride:
        """Get the details for the current ride.

        Returns:
            Ride: Current ride object if there is an ongoing ride.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.get_current_ride_status()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def get_ride_history(self, offset: int = 0, limit: int = 10) -> dict[str, Any]:
        """Fetch ride history.

        Args:
            offset: The number of records to skip (default: 0).
            limit: The maximum number of records to return (default: 10).

        Returns:
            dict[str, Any]: Collection of historical ride records.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.get_ride_history(offset=offset, limit=limit)


# Ride Detail Screen
class CabRideDetail(AppState):
    """Detail view for a specific ride.

    This state provides detailed information and operations for a specific ride,
    including viewing ride details, checking status, and canceling or ending the ride.
    """

    def __init__(self, ride: Ride) -> None:
        """Initialize ride detail view with a ride index.

        Args:
            ride: The ride object to display.
        """
        super().__init__()
        self.ride = ride

    def on_enter(self) -> None:
        """Called when entering this state."""
        pass

    def on_exit(self) -> None:
        """Called when exiting this state."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def cancel_ride(self) -> str:
        """Cancel the current ride.

        Returns:
            str: Cancellation confirmation message.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.user_cancel_ride()


# Service Type Selection
class CabServiceOptions(AppState):
    """Screen displaying available service types.

    This state allows users to browse available service types and view quotations
    for specific service types based on their journey details.

    Attributes:
        start_location: The starting location for the ride.
        end_location: The destination location for the ride.
        ride_time: Optional scheduled time for the ride.
    """

    def __init__(
        self,
        start_location: str,
        end_location: str,
        ride_time: str | None = None,
    ) -> None:
        """Initialize service options view.

        Args:
            start_location: The starting location for the ride.
            end_location: The destination location for the ride.
            ride_time: Optional scheduled time for the ride.
        """
        super().__init__()
        self.start_location = start_location
        self.end_location = end_location
        self.ride_time = ride_time

    def on_enter(self) -> None:
        """Called when entering this state."""
        pass

    def on_exit(self) -> None:
        """Called when exiting this state."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_service_types(self) -> list[str]:
        """List all available service types.

        Returns:
            list[str]: Sorted list of available service type names.
        """
        app = cast("StatefulCabApp", self.app)
        return sorted(app.d_service_config.keys())

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def get_quotation(self, service_type: str) -> Ride:
        """View quotation for a specific service type.

        Args:
            service_type: The type of service to get a quotation for.

        Returns:
            Ride: Quotation for the specified service type.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.get_quotation(
                start_location=self.start_location,
                end_location=self.end_location,
                service_type=service_type,
                ride_time=self.ride_time,
            )


# Quotation Detail Screen
class CabQuotationDetail(AppState):
    """Screen displaying a quotation (Ride before booking).

    This state shows the details of a quotation and allows the user to confirm
    and book the ride.

    Attributes:
        ride: The Ride object containing the quotation details.
    """

    def __init__(self, ride: Ride) -> None:
        """Initialize quotation detail view.

        Args:
            ride: The Ride object containing the quotation to display.
        """
        super().__init__()
        self.ride = ride

    def on_enter(self) -> None:
        """Called when entering this state."""
        pass

    def on_exit(self) -> None:
        """Called when exiting this state."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def show_quotation(self) -> Ride:
        """Show the quotation details.

        Returns:
            Ride: The quotation details.
        """
        return self.ride

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def order_ride(self) -> Ride:
        """Confirm and book the ride from the quotation.

        Returns:
            Ride: The confirmed and booked ride.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.order_ride(
                start_location=self.ride.start_location,
                end_location=self.ride.end_location,
                service_type=self.ride.service_type,
                ride_time=None,
            )
