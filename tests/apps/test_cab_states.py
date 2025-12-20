"""Tests for the enhanced stateful Cab app navigation flow."""

from typing import Any
import pytest

from are.simulation.types import Action, CompletedEvent, EventMetadata, EventType
from are.simulation.apps.cab import Ride

from pas.apps.cab.app import StatefulCabApp
from pas.apps.cab.states import (
    CabHome,
    CabRideDetail,
    CabServiceOptions,
    CabQuotationDetail,
)


def _make_event(
    app: StatefulCabApp,
    func: callable,
    result: Any | None = None,
    **kwargs: Any,
) -> CompletedEvent:
    """Utility to build a minimal CompletedEvent for state transition tests."""
    action = Action(function=func, args={"self": app, **kwargs}, app=app)

    metadata = EventMetadata()
    metadata.return_value = result

    event = CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=metadata,
        event_time=0,
        event_id="cab-test-event",
    )

    # Some handlers read event.result directly
    event.result = result
    return event


@pytest.fixture
def cab_app() -> StatefulCabApp:
    """Create a CabApp wrapped with StatefulCabApp."""
    return StatefulCabApp(name="cab")



# Basic startup
def test_app_starts_in_home_state(cab_app: StatefulCabApp) -> None:
    """App should start in CabHome with empty navigation stack."""
    assert isinstance(cab_app.current_state, CabHome)
    assert cab_app.navigation_stack == []



# list_rides
def test_list_rides_transitions_to_service_options(cab_app: StatefulCabApp) -> None:
    """list_rides should transition to CabServiceOptions."""

    cab_app.current_state.list_rides(
        start_location="A",
        end_location="B",
        ride_time=None,
    )

    event = _make_event(
        cab_app,
        cab_app.list_rides,
        start_location="A",
        end_location="B",
        ride_time=None,
    )

    cab_app.handle_state_transition(event)

    assert isinstance(cab_app.current_state, CabServiceOptions)
    assert cab_app.current_state.start_location == "A"
    assert cab_app.current_state.end_location == "B"


# get_quotation
def test_get_quotation_transitions_to_quotation_detail(
    cab_app: StatefulCabApp,
) -> None:
    """get_quotation should transition to CabQuotationDetail."""

    ride = cab_app.current_state.get_quotation(
        start_location="A",
        end_location="B",
        service_type="Default",
        ride_time=None,
    )

    assert isinstance(ride, Ride)
    assert ride.status is None  # quotation == unbooked Ride

    event = _make_event(
        cab_app,
        cab_app.get_quotation,
        result=ride,
        start_location="A",
        end_location="B",
        service_type="Default",
        ride_time=None,
    )

    cab_app.handle_state_transition(event)

    assert isinstance(cab_app.current_state, CabQuotationDetail)
    assert cab_app.current_state.ride is ride
    assert cab_app.current_state.ride.service_type == "Default"



# order_ride
def test_order_ride_transitions_to_detail(cab_app: StatefulCabApp) -> None:
    """Ordering a ride should transition to CabRideDetail."""

    ride = cab_app.current_state.order_ride(
        start_location="A",
        end_location="B",
        service_type="Default",
    )

    assert ride in cab_app.ride_history

    event = _make_event(
        cab_app,
        cab_app.order_ride,
        result=ride,
        start_location="A",
        end_location="B",
        service_type="Default",
    )

    cab_app.handle_state_transition(event)

    assert isinstance(cab_app.current_state, CabRideDetail)

    # CabRideDetail uses ride_history index
    idx = cab_app.ride_history.index(ride)
    assert cab_app.current_state.ride_index == idx

    # Navigation stack should contain previous state
    assert len(cab_app.navigation_stack) == 1



# cancel ride
def test_cancel_ride_transitions_back_home(cab_app: StatefulCabApp) -> None:
    """Canceling a ride should return to CabHome."""

    ride = cab_app.current_state.order_ride("A", "B", "Default")

    order_event = _make_event(
        cab_app,
        cab_app.order_ride,
        result=ride,
        start_location="A",
        end_location="B",
        service_type="Default",
    )
    cab_app.handle_state_transition(order_event)

    assert isinstance(cab_app.current_state, CabRideDetail)

    # Cancel ride
    cab_app.current_state.user_cancel_ride()

    cancel_event = _make_event(cab_app, cab_app.user_cancel_ride)
    cab_app.handle_state_transition(cancel_event)

    assert isinstance(cab_app.current_state, CabHome)
    assert cab_app.navigation_stack == []

def test_confirm_order_transitions_to_ride_detail(cab_app: StatefulCabApp) -> None:
    ride = cab_app.current_state.get_quotation("A", "B", "Default")

    quote_event = _make_event(
        cab_app,
        cab_app.get_quotation,
        result=ride,
        start_location="A",
        end_location="B",
        service_type="Default",
    )
    cab_app.handle_state_transition(quote_event)

    assert isinstance(cab_app.current_state, CabQuotationDetail)

    ordered_ride = cab_app.current_state.confirm_order()

    order_event = _make_event(
        cab_app,
        cab_app.order_ride,
        result=ordered_ride,
    )
    cab_app.handle_state_transition(order_event)

    assert isinstance(cab_app.current_state, CabRideDetail)
