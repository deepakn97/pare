from typing import TYPE_CHECKING, cast
from are.simulation.types import OperationType, disable_events
from pas.apps.core import AppState
from pas.apps.tool_decorators import user_tool, pas_event_registered

if TYPE_CHECKING:
    from pas.apps.cab.app import StatefulCabApp


# Home Screen
class CabHome(AppState):
    """Home view for cab operations: listing rides, quotations, orders, and history."""

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_rides(self, start_location: str, end_location: str,
                   ride_time: str | None = None):
        """
        Retrieve available ride options for the given start and end locations.

        :param start_location: Pickup location for the ride.
        :type start_location: str
        :param end_location: Drop-off location for the ride.
        :type end_location: str
        :param ride_time: Optional desired time for the ride. If None, the backend
            computes availability from current time.
        :type ride_time: str | None

        :return: A list of ride option dictionaries containing service type, ETA,
            pricing information, and metadata provided by the cab backend.
        :rtype: list[dict[str, object]]
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
    def get_quotation(self, start_location: str, end_location: str,
                      service_type: str, ride_time: str | None = None):
        """
        Request a fare quotation for the selected route and service type.

        :param start_location: Pickup location for the quotation.
        :type start_location: str
        :param end_location: Destination location for the quotation.
        :type end_location: str
        :param service_type: Service category (e.g. Standard, Premium).
        :type service_type: str
        :param ride_time: Optional desired ride time. Defaults to None.
        :type ride_time: str | None

        :return: A quotation object including estimated price, duration, and service
            metadata for the requested ride.
        :rtype: CabRideQuotation
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
    def order_ride(self, start_location: str, end_location: str,
                   service_type: str, ride_time: str | None = None):
        """
        Create a new ride order for a selected service type.

        :param start_location: Starting point of the ride.
        :type start_location: str
        :param end_location: Destination point of the ride.
        :type end_location: str
        :param service_type: Service type chosen by the user.
        :type service_type: str
        :param ride_time: Optional scheduled time for the ride.
        :type ride_time: str | None

        :return: A Ride object containing ride ID, cost, and metadata produced
            by the backend upon order creation.
        :rtype: CabRide
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
        """
        Fetch past ride history records for the user.

        :param offset: Pagination offset for ride history.
        :type offset: int
        :param limit: Maximum number of ride records to return.
        :type limit: int

        :return: A list of ride history entries, each containing ID, cost,
            timestamp, and status metadata.
        :rtype: list[dict[str, object]]
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.get_ride_history(offset=offset, limit=limit)


# Ride Detail Screen
class CabRideDetail(AppState):
    """Detail view showing status and operations for a specific ride."""

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
        """
        Retrieve live status updates for the currently active ride.

        :return: A dictionary containing current ride progress, driver info,
            estimated arrival time, and other live backend data.
        :rtype: dict[str, object]
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.get_current_ride_status()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def get_ride(self):
        """
        Fetch a full ride record for the ride represented by this detail screen.

        :return: A ride object containing ride ID, start/end info, timestamps,
            pricing, and completion metadata.
        :rtype: CabRide
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.get_ride(self.ride_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def user_cancel_ride(self):
        """
        Cancel the currently active ride.

        :return: Confirmation response from the backend indicating whether the
            cancellation request was successful.
        :rtype: dict[str, object]
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.user_cancel_ride()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def end_ride(self):
        """
        Mark the current ride as completed.

        :return: Backend response indicating final completion status and summary.
        :rtype: dict[str, object]
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.end_ride()



# Service Type Selection Screen
class CabServiceOptions(AppState):
    """Screen that displays available service categories for the selected route."""

    def __init__(self, start_location: str, end_location: str,
                 ride_time: str | None = None):
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
        """
        Return a sorted list of all available service category names.

        :return: List of service type names supported by the backend configuration.
        :rtype: list[str]
        """
        app = cast("StatefulCabApp", self.app)
        return sorted(app.d_service_config.keys())

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def view_quotation(self, service_type: str):
        """
        Retrieve a quotation for a specific service type on the selected route.

        :param service_type: Category of ride service selected by the user.
        :type service_type: str

        :return: A quotation object containing estimated price and details for
            the requested service type.
        :rtype: CabRideQuotation
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
    """Screen displaying quotation details before confirming purchase."""

    def __init__(self, ride_obj):
        super().__init__()
        self.ride = ride_obj

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def show_quotation(self):
        """
        Return the full quotation object for user inspection.

        :return: Quotation details including cost breakdown, ETA, and service info.
        :rtype: CabRideQuotation
        """
        return self.ride

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def confirm_order(self):
        """
        Confirm the quotation and create a final ride order.

        :return: A newly created Ride object containing ride ID, start/end metadata,
            pricing, timestamps, and driver assignment if available.
        :rtype: CabRide
        """
        app = cast("StatefulCabApp", self.app)
        with disable_events():
            return app.order_ride(
                start_location=self.ride.start_location,
                end_location=self.ride.end_location,
                service_type=self.ride.service_type,
                ride_time=self.ride.ride_time,
            )
