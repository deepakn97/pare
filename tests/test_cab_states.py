"""Tests for the enhanced stateful Cab app navigation flow."""

from typing import Any
import pytest

from are.simulation.types import Action, CompletedEvent, EventMetadata, EventType
from are.simulation.apps.cab import CabApp

from pas.apps.cab.app import StatefulCabApp
from pas.apps.cab.states import (
    CabHome,
    CabRideDetail,
    CabServiceOptions,
    CabQuotationDetail,
)


def _make_event(app: StatefulCabApp, func: callable, **kwargs: Any) -> CompletedEvent:
    """Utility to build a minimal CompletedEvent for state transition tests."""
    action = Action(function=func, args={"self": app, **kwargs}, app=app)
    return CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=EventMetadata(),
        event_time=0,
        event_id="cab-test-event",
    )


@pytest.fixture
def cab_app() -> StatefulCabApp:
    """Create a CabApp wrapped with StatefulCabApp."""
    return StatefulCabApp(name="cab")



def test_app_starts_in_home_state(cab_app: StatefulCabApp) -> None:
    """App should start in CabHome with empty navigation stack."""
    assert isinstance(cab_app.current_state, CabHome)
    assert cab_app.navigation_stack == []


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



def test_get_quotation_transitions_to_quotation_detail(cab_app: StatefulCabApp) -> None:
    """get_quotation should transition to CabQuotationDetail."""

    # Trigger quotation
    ride_obj = cab_app.current_state.get_quotation(
        start_location="A",
        end_location="B",
        service_type="Default",
        ride_time=None,
    )

    event = _make_event(
        cab_app,
        cab_app.get_quotation,
        start_location="A",
        end_location="B",
        service_type="Default",
        ride_time=None,
    )

    # Inject the returned Ride into event.result for consistency
    event.result = ride_obj

    cab_app.handle_state_transition(event)

    assert isinstance(cab_app.current_state, CabQuotationDetail)
    assert cab_app.current_state.ride.service_type == "Default"



def test_order_ride_transitions_to_detail(cab_app: StatefulCabApp) -> None:
    """Ordering a ride should transition to CabRideDetail."""

    cab_app.current_state.order_ride(
        start_location="A",
        end_location="B",
        service_type="Default",
    )

    event = _make_event(
        cab_app,
        cab_app.order_ride,
        start_location="A",
        end_location="B",
        service_type="Default",
    )

    cab_app.handle_state_transition(event)

    assert isinstance(cab_app.current_state, CabRideDetail)
    assert len(cab_app.navigation_stack) == 1


def test_cancel_ride_transitions_back_home(cab_app: StatefulCabApp) -> None:
    """Canceling a ride should return to CabHome."""

    # Order a ride
    cab_app.current_state.order_ride("A", "B", "Default")
    event = _make_event(
        cab_app, cab_app.order_ride, start_location="A", end_location="B", service_type="Default"
    )
    cab_app.handle_state_transition(event)

    assert isinstance(cab_app.current_state, CabRideDetail)

    # Cancel the ride
    cab_app.current_state.user_cancel_ride()
    event = _make_event(cab_app, cab_app.user_cancel_ride)

    cab_app.handle_state_transition(event)

    assert isinstance(cab_app.current_state, CabHome)
    assert len(cab_app.navigation_stack) == 0
