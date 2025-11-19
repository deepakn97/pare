from typing import TYPE_CHECKING, cast
from pas.apps.core import AppState
from pas.apps.tool_decorators import user_tool, pas_event_registered
from are.simulation.types import OperationType

if TYPE_CHECKING:
    from pas.apps.cab.app import StatefulCabApp


# Home Screen
class CabHome(AppState):
    """Home view for cab operations: list rides, get quotations, place orders."""

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_rides(self, start_location: str, end_location: str,
                   ride_time: str | None = None):
        """List available rides matching user criteria."""
        app = cast("StatefulCabApp", self.app)
        return app.list_rides(
            start_location=start_location,
            end_location=end_location,
            ride_time=ride_time,
        )

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def get_quotation(self, start_location: str, end_location: str,
                      service_type: str, ride_time: str | None = None):
        """Request a quotation for a selected service type."""
        app = cast("StatefulCabApp", self.app)
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
        """Create a new ride order."""
        app = cast("StatefulCabApp", self.app)
        return app.order_ride(
            start_location=start_location,
            end_location=end_location,
            service_type=service_type,
            ride_time=ride_time,
        )

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def get_ride_history(self, offset: int = 0, limit: int = 10):
        """Fetch past ride records."""
        app = cast("StatefulCabApp", self.app)
        return app.get_ride_history(offset=offset, limit=limit)


# Ride Detail
class CabRideDetail(AppState):
    """Detail view for an ongoing or selected ride."""

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
        """Retrieve live status of the current ride."""
        app = cast("StatefulCabApp", self.app)
        return app.get_current_ride_status()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def get_ride(self):
        """Fetch ride information for this ride ID."""
        app = cast("StatefulCabApp", self.app)
        return app.get_ride(self.ride_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def user_cancel_ride(self):
        """Cancel the ongoing ride."""
        app = cast("StatefulCabApp", self.app)
        return app.user_cancel_ride()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def end_ride(self):
        """Mark the ride as completed."""
        app = cast("StatefulCabApp", self.app)
        return app.end_ride()


# Service Type Selection
class CabServiceOptions(AppState):
    """Service selection screen showing available ride categories."""

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
        """Return available service categories (sorted for stable UI)."""
        app = cast("StatefulCabApp", self.app)
        return sorted(app.d_service_config.keys())

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def view_quotation(self, service_type: str):
        """Get quotation for the selected service type."""
        app = cast("StatefulCabApp", self.app)
        return app.get_quotation(
            start_location=self.start_location,
            end_location=self.end_location,
            service_type=service_type,
            ride_time=self.ride_time,
        )


# Quotation Detail
class CabQuotationDetail(AppState):
    """Display quotation details before confirming the ride."""

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
        """Return quotation details."""
        return self.ride

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def confirm_order(self):
        """
        Confirm the quotation and create an actual ride.
        NOTE: this triggers one single order_ride event.
        """
        app = cast("StatefulCabApp", self.app)
        return app.order_ride(
            start_location=self.ride.start_location,
            end_location=self.ride.end_location,
            service_type=self.ride.service_type,
            ride_time=self.ride.ride_time,   
        )
