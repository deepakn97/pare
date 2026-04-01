"""Tests for the enhanced stateful Cab app navigation flow."""
from __future__ import annotations

from typing import Any

import pytest
from are.simulation.apps.cab import Ride
from are.simulation.types import Action, CompletedEvent, EventMetadata, EventType

from pare.apps.cab.app import StatefulCabApp
from pare.apps.cab.states import (
    CabHome,
    CabQuotationDetail,
    CabRideDetail,
    CabServiceOptions,
)
from pare.apps.proactive_aui import PAREAgentUserInterface
from pare.apps.system import HomeScreenSystemApp
from pare.environment import StateAwareEnvironmentWrapper


def _home_state(app: StatefulCabApp) -> CabHome:
    state = app.current_state
    assert isinstance(state, CabHome)
    return state


def _service_options_state(app: StatefulCabApp) -> CabServiceOptions:
    state = app.current_state
    assert isinstance(state, CabServiceOptions)
    return state


def _quotation_detail_state(app: StatefulCabApp) -> CabQuotationDetail:
    state = app.current_state
    assert isinstance(state, CabQuotationDetail)
    return state


def _ride_detail_state(app: StatefulCabApp) -> CabRideDetail:
    state = app.current_state
    assert isinstance(state, CabRideDetail)
    return state


@pytest.fixture
def env_with_cab() -> StateAwareEnvironmentWrapper:
    """Create environment with cab app registered and opened."""
    env = StateAwareEnvironmentWrapper()
    system_app = HomeScreenSystemApp(name="HomeScreen")
    aui_app = PAREAgentUserInterface()
    cab_app = StatefulCabApp(name="cab")
    env.register_apps([system_app, aui_app, cab_app])
    env._open_app("cab")
    return env


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

    return CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=metadata,
        event_time=0,
        event_id="cab-test-event",
    )


@pytest.fixture
def cab_app() -> StatefulCabApp:
    """Create a CabApp wrapped with StatefulCabApp."""
    return StatefulCabApp(name="cab")



# Basic startup
def test_app_starts_in_home_state(cab_app: StatefulCabApp) -> None:
    """App should start in CabHome with empty navigation stack."""
    assert isinstance(cab_app.current_state, CabHome)
    assert cab_app.navigation_stack == []



# list_rides handler (unit test)
def test_list_rides_transition(cab_app: StatefulCabApp) -> None:
    """Handler: list_rides event transitions to CabServiceOptions."""
    # Call handler with mock event
    event = _make_event(
        cab_app,
        cab_app.list_rides,
        start_location="A",
        end_location="B",
    )
    cab_app.handle_state_transition(event)

    # Verify transition
    assert isinstance(cab_app.current_state, CabServiceOptions)
    assert cab_app.current_state.start_location == "A"
    assert cab_app.current_state.end_location == "B"


# get_quotation handler (unit test)
def test_get_quotation_transition(cab_app: StatefulCabApp) -> None:
    """Handler: get_quotation event transitions to CabQuotationDetail."""
    # Set starting state
    cab_app.set_current_state(CabServiceOptions("A", "B"))

    # Create mock ride result
    ride = cab_app.get_quotation("A", "B", "Default")

    # Verify tool output
    assert isinstance(ride, Ride)
    assert ride.start_location == "A"
    assert ride.end_location == "B"
    assert ride.service_type == "Default"

    # Call handler with mock event
    event = _make_event(cab_app, cab_app.get_quotation, result=ride)
    cab_app.handle_state_transition(event)

    # Verify transition
    assert isinstance(cab_app.current_state, CabQuotationDetail)
    assert cab_app.current_state.ride is ride



# order_ride handler (unit test)
def test_order_ride_transition(cab_app: StatefulCabApp) -> None:
    """Handler: order_ride event transitions to CabRideDetail."""
    # Create a quotation first
    quotation = cab_app.get_quotation("A", "B", "Default")

    # Set starting state
    cab_app.set_current_state(CabQuotationDetail(quotation))

    # Create mock ride result (booked ride)
    ride = cab_app.order_ride("A", "B", "Default")

    # Verify tool output - ride should be booked
    assert isinstance(ride, Ride)
    assert ride.status == "BOOKED"
    assert ride.start_location == "A"
    assert ride.end_location == "B"

    # Call handler with mock event
    event = _make_event(cab_app, cab_app.order_ride, result=ride)
    cab_app.handle_state_transition(event)

    # Verify transition
    assert isinstance(cab_app.current_state, CabRideDetail)
    assert cab_app.current_state.ride is ride



# open_current_ride handler (unit test)
def test_open_current_ride_transition(cab_app: StatefulCabApp) -> None:
    """Handler: open_current_ride event transitions to CabRideDetail."""
    # First create a ride so there's a current ride
    ordered_ride = cab_app.order_ride("A", "B", "Default")

    # Reset to home state (order_ride would have transitioned us)
    cab_app.load_root_state()
    assert isinstance(cab_app.current_state, CabHome)

    # Get the current ride via the state's method
    current_ride = cab_app.current_state.open_current_ride()

    # Verify tool output - should return the ride we ordered
    assert isinstance(current_ride, Ride)
    assert current_ride.ride_id == ordered_ride.ride_id
    assert current_ride.status == "BOOKED"

    # Call handler with mock event using state's method
    event = _make_event(cab_app, cab_app.current_state.open_current_ride, result=current_ride)
    cab_app.handle_state_transition(event)

    # Verify transition
    assert isinstance(cab_app.current_state, CabRideDetail)
    assert cab_app.current_state.ride is current_ride


# cancel_ride handler (unit test)
def test_cancel_ride_transition(cab_app: StatefulCabApp) -> None:
    """Handler: cancel_ride event transitions to CabHome."""
    # Create a ride and set starting state
    ride = cab_app.order_ride("A", "B", "Default")
    state = CabRideDetail(ride)
    cab_app.set_current_state(state)

    # Call cancel_ride and verify tool output
    result = state.cancel_ride()
    assert "cancelled" in result.lower()  # Should return cancellation message

    # Call handler with mock event using state's cancel_ride method
    event = _make_event(cab_app, state.cancel_ride)
    cab_app.handle_state_transition(event)

    # Verify transition to home and stack cleared
    assert isinstance(cab_app.current_state, CabHome)
    assert cab_app.navigation_stack == []


# Self-loop tests (no state transition)
def test_get_ride_history_no_transition(cab_app: StatefulCabApp) -> None:
    """Handler: get_ride_history should not change state."""
    assert isinstance(cab_app.current_state, CabHome)

    # Call tool and verify output
    result = cab_app.current_state.get_ride_history()
    assert isinstance(result, dict)

    event = _make_event(cab_app, cab_app.current_state.get_ride_history, result=result)
    cab_app.handle_state_transition(event)

    # Should remain in CabHome
    assert isinstance(cab_app.current_state, CabHome)


def test_list_service_types_no_transition(cab_app: StatefulCabApp) -> None:
    """Handler: list_service_types should not change state."""
    state = CabServiceOptions("A", "B")
    cab_app.set_current_state(state)

    # Call tool and verify output
    result = state.list_service_types()
    assert isinstance(result, list)
    assert len(result) > 0  # Should have at least one service type
    assert "Default" in result

    event = _make_event(cab_app, state.list_service_types, result=result)
    cab_app.handle_state_transition(event)

    # Should remain in CabServiceOptions
    assert isinstance(cab_app.current_state, CabServiceOptions)


def test_show_quotation_no_transition(cab_app: StatefulCabApp) -> None:
    """Handler: show_quotation should not change state."""
    ride = cab_app.get_quotation("A", "B", "Default")
    state = CabQuotationDetail(ride)
    cab_app.set_current_state(state)

    # Call tool and verify output
    result = state.show_quotation()
    assert isinstance(result, Ride)
    assert result is ride  # Should return the same ride object

    event = _make_event(cab_app, state.show_quotation, result=result)
    cab_app.handle_state_transition(event)

    # Should remain in CabQuotationDetail
    assert isinstance(cab_app.current_state, CabQuotationDetail)


# =============================================================================
# Integration Tests (multi-step trajectories via environment)
# =============================================================================


class TestCabEnvironmentIntegration:
    """Integration tests that exercise the full environment flow.

    These tests use the environment pattern where:
    1. Tool calls automatically log events via @pare_event_registered
    2. Events automatically trigger state transitions via StateAwareEnvironmentWrapper.add_to_log
    3. No manual event handling is needed - just call tools and verify state
    """

    def test_full_booking_flow(self, env_with_cab: StateAwareEnvironmentWrapper) -> None:
        """Integration: Home -> list_rides -> Options -> get_quotation -> Quote -> order_ride -> RideDetail."""
        env = env_with_cab
        app = env.get_app_with_class(StatefulCabApp)

        # Start at CabHome
        assert isinstance(app.current_state, CabHome)
        assert len(app.navigation_stack) == 0

        # Step 1: list_rides -> CabServiceOptions
        _home_state(app).list_rides("A", "B")
        assert isinstance(app.current_state, CabServiceOptions)
        assert len(app.navigation_stack) == 1

        # Step 2: get_quotation -> CabQuotationDetail
        _service_options_state(app).get_quotation("Default")
        assert isinstance(app.current_state, CabQuotationDetail)
        assert len(app.navigation_stack) == 2

        # Step 3: order_ride -> CabRideDetail
        _quotation_detail_state(app).order_ride()
        assert isinstance(app.current_state, CabRideDetail)
        assert len(app.navigation_stack) == 3

    def test_open_current_ride_then_cancel(self, env_with_cab: StateAwareEnvironmentWrapper) -> None:
        """Integration: Home -> open_current_ride -> RideDetail -> cancel_ride -> Home."""
        env = env_with_cab
        app = env.get_app_with_class(StatefulCabApp)

        # First create a ride (using internal method, not through environment)
        app.order_ride("A", "B", "Default")
        app.load_root_state()
        assert isinstance(app.current_state, CabHome)

        # Step 1: open_current_ride -> CabRideDetail
        _home_state(app).open_current_ride()
        assert isinstance(app.current_state, CabRideDetail)
        assert len(app.navigation_stack) == 1

        # Step 2: cancel_ride -> CabHome (clears stack)
        _ride_detail_state(app).cancel_ride()
        assert isinstance(app.current_state, CabHome)
        assert len(app.navigation_stack) == 0

    def test_go_back_from_service_options(self, env_with_cab: StateAwareEnvironmentWrapper) -> None:
        """Integration: Home -> list_rides -> Options -> go_back -> Home.

        Tests that go_back doesn't double-pop (the bug documented in Fix go_back Double-Pop Bug.md).
        """
        env = env_with_cab
        app = env.get_app_with_class(StatefulCabApp)

        # Step 1: list_rides -> CabServiceOptions
        _home_state(app).list_rides("A", "B")
        assert isinstance(app.current_state, CabServiceOptions)
        assert len(app.navigation_stack) == 1

        # Step 2: go_back -> CabHome
        app.go_back()
        assert isinstance(app.current_state, CabHome)
        assert len(app.navigation_stack) == 0

    def test_go_back_from_quotation_detail(self, env_with_cab: StateAwareEnvironmentWrapper) -> None:
        """Integration: Home -> Options -> QuoteDetail -> go_back -> Options (not Home).

        Verifies no double-pop: should return to Options, not skip to Home.
        """
        env = env_with_cab
        app = env.get_app_with_class(StatefulCabApp)

        # Step 1: list_rides -> CabServiceOptions
        _home_state(app).list_rides("A", "B")
        assert isinstance(app.current_state, CabServiceOptions)

        # Step 2: get_quotation -> CabQuotationDetail
        _service_options_state(app).get_quotation("Default")
        assert isinstance(app.current_state, CabQuotationDetail)
        assert len(app.navigation_stack) == 2

        # Step 3: go_back -> CabServiceOptions (NOT CabHome)
        app.go_back()
        assert isinstance(app.current_state, CabServiceOptions)
        assert len(app.navigation_stack) == 1

    def test_go_back_from_ride_detail(self, env_with_cab: StateAwareEnvironmentWrapper) -> None:
        """Integration: Full booking flow -> go_back -> QuoteDetail (not further).

        Verifies no double-pop from deep navigation stack.
        """
        env = env_with_cab
        app = env.get_app_with_class(StatefulCabApp)

        # Full booking flow: Home -> Options -> QuoteDetail -> RideDetail
        _home_state(app).list_rides("A", "B")
        _service_options_state(app).get_quotation("Default")
        _quotation_detail_state(app).order_ride()

        assert isinstance(app.current_state, CabRideDetail)
        assert len(app.navigation_stack) == 3

        # go_back -> CabQuotationDetail (NOT CabServiceOptions)
        app.go_back()
        assert isinstance(app.current_state, CabQuotationDetail)
        assert len(app.navigation_stack) == 2


# =============================================================================
# State Initialization Tests
# =============================================================================


def test_cab_service_options_initialization() -> None:
    """CabServiceOptions stores context correctly."""
    state = CabServiceOptions("Start", "End", "2024-01-01 10:00:00")

    assert state.start_location == "Start"
    assert state.end_location == "End"
    assert state.ride_time == "2024-01-01 10:00:00"


def test_cab_quotation_detail_initialization(cab_app: StatefulCabApp) -> None:
    """CabQuotationDetail stores ride object correctly."""
    ride = cab_app.get_quotation("A", "B", "Default")
    state = CabQuotationDetail(ride)

    assert state.ride is ride


def test_cab_ride_detail_initialization(cab_app: StatefulCabApp) -> None:
    """CabRideDetail stores ride object correctly."""
    ride = cab_app.order_ride("A", "B", "Default")
    state = CabRideDetail(ride)

    assert state.ride is ride


# =============================================================================
# Edge Case Tests
# =============================================================================


def test_go_back_with_empty_stack(cab_app: StatefulCabApp) -> None:
    """go_back with empty stack should not crash and stay in current state."""
    assert isinstance(cab_app.current_state, CabHome)
    assert len(cab_app.navigation_stack) == 0

    # go_back should handle empty stack gracefully
    cab_app.go_back()

    # Should remain in CabHome
    assert isinstance(cab_app.current_state, CabHome)
    assert len(cab_app.navigation_stack) == 0


def test_cancel_ride_clears_navigation_stack(env_with_cab: StateAwareEnvironmentWrapper) -> None:
    """cancel_ride should clear entire navigation stack."""
    env = env_with_cab
    app = env.get_app_with_class(StatefulCabApp)

    # Build up a navigation stack
    _home_state(app).list_rides("A", "B")
    _service_options_state(app).get_quotation("Default")
    _quotation_detail_state(app).order_ride()

    assert len(app.navigation_stack) == 3

    # cancel_ride should clear stack and return to home
    _ride_detail_state(app).cancel_ride()

    assert isinstance(app.current_state, CabHome)
    assert len(app.navigation_stack) == 0
