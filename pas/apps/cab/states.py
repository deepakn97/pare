from __future__ import annotations

from typing import TYPE_CHECKING, cast

from are.simulation.types import OperationType, disable_events

from pas.apps.core import AppState
from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from pas.apps.cab.app import StatefulCabApp


# Home Screen
class CabHome(AppState):
    """Home view for cab operations such as listing rides, quotations, orders, and history."""

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_rides(
        self,
        start_location: str,
        end_location: str,
        ride_time: str | None = None,
    ):
        """Retrieve available ride options for the given start and end locations.

        Args:
            start_location (str): Pickup location for the ride.
            end_location (str): Drop-off location for the ride.
            ride_time (str | None, optional): Desired ride time. If None, the backend
                computes availability from the current simulated time.

        Returns:
            list[dict[str, object]]: A list of ride option dictionaries containing
            service type, ETA, pricing information, and backend-provided metadata.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.list_rides(
                start_location=start_location,
                end_location=end_location,
                ride_time=ride_time,
            )

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def get_quotation(
        self,
        start_location: str,
        end_location: str,
        service_type: str,
        ride_time: str | None = None,
    ):
        """Request a fare quotation for the selected route and service type.

        Args:
            start_location (str): Pickup location for the quotation.
            end_location (str): Destination location for the quotation.
            service_type (str): Service category (e.g., Standard, Premium).
            ride_time (str | None, optional): Desired ride time. Defaults to None.

        Returns:
            CabRideQuotation: A quotation object containing estimated fare, ride
            duration, and backend metadata for the requested service type.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.get_quotation(
                start_location=start_location,
                end_location=end_location,
                service_type=service_type,
                ride_time=ride_time,
            )

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def order_ride(
        self,
        start_location: str,
        end_location: str,
        service_type: str,
        ride_time: str | None = None,
    ):
        """Create a new ride order for a selected service type.

        Args:
            start_location (str): Starting point of the ride.
            end_location (str): Destination point of the ride.
            service_type (str): Ride service type selected by the user.
            ride_time (str | None, optional): Scheduled time for the ride.

        Returns:
            CabRide: A Ride object containing ride ID, cost, timestamps, and metadata
            produced by the backend upon ride creation.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.order_ride(
                start_location=start_location,
                end_location=end_location,
                service_type=service_type,
                ride_time=ride_time,
            )

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def get_ride_history(self, offset: int = 0, limit: int = 10):
        """Fetch past ride history records for the user.

        Args:
            offset (int): Pagination offset for ride history retrieval.
            limit (int): Maximum number of ride records to return.

        Returns:
            list[dict[str, object]]: A list of ride history entries containing ride ID,
            timestamps, cost information, and status metadata.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.get_ride_history(offset=offset, limit=limit)


# Ride Detail Screen
class CabRideDetail(AppState):
    """Detail view showing live ride status and operations for a specific ride."""

    def __init__(self, ride_id: str):
        super().__init__()
        self.ride_id = ride_id

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def get_current_ride_status(self):
        """Retrieve the live status of the current ride.

        Returns:
            dict[str, object]: A dictionary containing live ride progress, driver
            information, estimated arrival time, and backend updates.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.get_current_ride_status()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def get_ride(self):
        """Fetch a full ride record for the ride represented by this detail screen.

        Returns:
            CabRide: A ride object containing route details, timestamps, pricing,
            and completion metadata.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.get_ride(self.ride_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def user_cancel_ride(self):
        """Cancel the currently active ride.

        Returns:
            dict[str, object]: Backend confirmation response indicating whether the
            cancellation request succeeded.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.user_cancel_ride()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def end_ride(self):
        """Mark the current ride as completed.

        Returns:
            dict[str, object]: Backend response indicating final ride completion
            status and summary metadata.
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.end_ride()


# Service Type Selection Screen
class CabServiceOptions(AppState):
    """Screen that displays available ride service categories for a selected route."""

    def __init__(
        self,
        start_location: str,
        end_location: str,
        ride_time: str | None = None,
    ):
        super().__init__()
        self.start_location = start_location
        self.end_location = end_location
        self.ride_time = ride_time

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    @user_tool()
    @pas_event_registered()
    def list_service_types(self) -> list[str]:
        """List all available ride service categories.

        Returns:
            list[str]: Sorted list of service type names supported by the cab backend.
        """
        app = cast("StatefulCabApp", self.app)
        return sorted(app.d_service_config.keys())

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def view_quotation(self, service_type: str):
        """Retrieve a quotation for a specific service type on the selected route.

        Args:
            service_type (str): Ride service category selected by the user.

        Returns:
            CabRideQuotation: A quotation object including estimated fare and
            service details for the chosen ride type.
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
    """Screen displaying quotation details before placing a ride order."""

    def __init__(self, ride_obj: Any) -> None:
        super().__init__()
        self.ride = ride_obj

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def show_quotation(self):
        """Return the full quotation object for user inspection.

        Returns:
            CabRideQuotation: Complete quotation metadata including cost estimate,
            ETA, and service information.
        """
        return self.ride

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def confirm_order(self):
        """Confirm the quotation and create a final ride order.

        Returns:
            CabRide: A newly created ride object containing ride ID, route details,
            pricing metadata, timestamps, and driver assignment (if available).
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.order_ride(
                start_location=self.ride.start_location,
                end_location=self.ride.end_location,
                service_type=self.ride.service_type,
                ride_time=self.ride.ride_time,
            )
