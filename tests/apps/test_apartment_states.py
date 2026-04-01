"""Tests for the Apartment Stateful App navigation flow.

Key principles:
- Unit tests use _make_event + handle_state_transition for single transitions
- Integration tests use StateAwareEnvironmentWrapper for multi-step flows
- All tests verify BOTH functionality AND state transitions
"""
from __future__ import annotations

from typing import Any

import pytest
from are.simulation.apps.apartment_listing import Apartment
from are.simulation.types import (
    Action,
    CompletedEvent,
    EventMetadata,
    EventType,
)

from pare.apps.apartment.app import StatefulApartmentApp
from pare.apps.apartment.states import (
    ApartmentDetail,
    ApartmentFavorites,
    ApartmentHome,
    ApartmentSearch,
)
from pare.apps.proactive_aui import PAREAgentUserInterface
from pare.apps.system import HomeScreenSystemApp
from pare.environment import StateAwareEnvironmentWrapper

# =============================================================================
# State Helpers
# =============================================================================


def _home_state(app: StatefulApartmentApp) -> ApartmentHome:
    """Get current state as ApartmentHome with assertion."""
    state = app.current_state
    assert isinstance(state, ApartmentHome)
    return state


def _detail_state(app: StatefulApartmentApp) -> ApartmentDetail:
    """Get current state as ApartmentDetail with assertion."""
    state = app.current_state
    assert isinstance(state, ApartmentDetail)
    return state


def _search_state(app: StatefulApartmentApp) -> ApartmentSearch:
    """Get current state as ApartmentSearch with assertion."""
    state = app.current_state
    assert isinstance(state, ApartmentSearch)
    return state


def _favorites_state(app: StatefulApartmentApp) -> ApartmentFavorites:
    """Get current state as ApartmentFavorites with assertion."""
    state = app.current_state
    assert isinstance(state, ApartmentFavorites)
    return state

# =============================================================================
# Helper Functions
# =============================================================================


def _make_event(
    app: StatefulApartmentApp,
    func: callable,
    result: Any = None,
    **kwargs: Any,
) -> CompletedEvent:
    """Create a mock event for state transition tests."""
    action = Action(
        function=func,
        args={"self": app, **kwargs},
        app=app,
    )
    metadata = EventMetadata()
    metadata.return_value = result
    return CompletedEvent(
        event_id="test-event",
        event_type=EventType.USER,
        action=action,
        metadata=metadata,
        event_time=0,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def apt_app() -> StatefulApartmentApp:
    """Create an apartment app with test data."""
    app = StatefulApartmentApp(name="apartment")

    # Preload test data (prices MUST be float)
    app.add_new_apartment(
        name="Apt1",
        location="SB",
        zip_code="93106",
        price=2000.0,
        number_of_bedrooms=2,
        number_of_bathrooms=1,
        square_footage=900,
    )
    app.add_new_apartment(
        name="Apt2",
        location="LA",
        zip_code="90001",
        price=2500.0,
        number_of_bedrooms=3,
        number_of_bathrooms=2,
        square_footage=1200,
    )
    return app


@pytest.fixture
def env_with_apartment() -> StateAwareEnvironmentWrapper:
    """Create environment with apartment app registered and opened."""
    env = StateAwareEnvironmentWrapper()
    system_app = HomeScreenSystemApp(name="HomeScreen")
    aui_app = PAREAgentUserInterface()
    apt_app = StatefulApartmentApp(name="apartment")

    # Add test data
    apt_app.add_new_apartment(
        name="Apt1",
        location="SB",
        zip_code="93106",
        price=2000.0,
        number_of_bedrooms=2,
        number_of_bathrooms=1,
        square_footage=900,
    )
    apt_app.add_new_apartment(
        name="Apt2",
        location="LA",
        zip_code="90001",
        price=2500.0,
        number_of_bedrooms=3,
        number_of_bathrooms=2,
        square_footage=1200,
    )

    env.register_apps([system_app, aui_app, apt_app])
    env._open_app("apartment")
    return env


# =============================================================================
# Basic Unit Tests
# =============================================================================


def test_starts_in_home(apt_app: StatefulApartmentApp) -> None:
    """App should start in ApartmentHome with empty navigation stack."""
    assert isinstance(apt_app.current_state, ApartmentHome)
    assert apt_app.navigation_stack == []


def test_home_to_detail(apt_app: StatefulApartmentApp) -> None:
    """Handler: view_apartment from Home transitions to ApartmentDetail."""
    apt_id = list(apt_app.apartments.keys())[0]
    home_state = _home_state(apt_app)

    # Call tool and verify output
    result = home_state.view_apartment(apartment_id=apt_id)
    assert isinstance(result, Apartment)
    assert result.name == "Apt1"  # Verify apartment details returned

    # Call handler with mock event
    event = _make_event(apt_app, home_state.view_apartment, result=result, apartment_id=apt_id)
    apt_app.handle_state_transition(event)

    # Verify transition
    assert isinstance(apt_app.current_state, ApartmentDetail)
    assert apt_app.current_state.apartment_id == apt_id


def test_open_search(apt_app: StatefulApartmentApp) -> None:
    """Handler: open_search from Home transitions to ApartmentSearch."""
    home_state = _home_state(apt_app)

    # Call tool and verify output
    result = home_state.open_search()
    assert isinstance(result, str)

    # Call handler with mock event
    event = _make_event(apt_app, home_state.open_search, result=result)
    apt_app.handle_state_transition(event)

    # Verify transition
    assert isinstance(apt_app.current_state, ApartmentSearch)


def test_open_favorites_transition(apt_app: StatefulApartmentApp) -> None:
    """Handler: open_favorites from Home transitions to ApartmentFavorites."""
    home_state = _home_state(apt_app)

    # Call tool and verify output
    result = home_state.open_favorites()
    assert isinstance(result, dict)  # Returns dict of saved apartments (empty initially)

    # Call handler with mock event
    event = _make_event(apt_app, home_state.open_favorites, result=result)
    apt_app.handle_state_transition(event)

    # Verify transition
    assert isinstance(apt_app.current_state, ApartmentFavorites)


def test_search_to_detail(apt_app: StatefulApartmentApp) -> None:
    """Handler: view_apartment from Search transitions to ApartmentDetail."""
    apt_id = list(apt_app.apartments.keys())[1]

    # Navigate to search first
    apt_app.set_current_state(ApartmentSearch())
    search_state = _search_state(apt_app)

    # Call tool and verify output
    result = search_state.view_apartment(apartment_id=apt_id)
    assert isinstance(result, Apartment)
    assert result.name == "Apt2"

    # Call handler with mock event
    event = _make_event(apt_app, search_state.view_apartment, result=result, apartment_id=apt_id)
    apt_app.handle_state_transition(event)

    # Verify transition
    assert isinstance(apt_app.current_state, ApartmentDetail)
    assert apt_app.current_state.apartment_id == apt_id


def test_favorites_to_detail(apt_app: StatefulApartmentApp) -> None:
    """Handler: view_apartment from Favorites transitions to ApartmentDetail."""
    apt_id = list(apt_app.apartments.keys())[0]

    # Save the apartment first
    apt_app.save_apartment(apartment_id=apt_id)

    # Navigate to favorites
    apt_app.set_current_state(ApartmentFavorites())
    favorites_state = _favorites_state(apt_app)

    # Call tool and verify output
    result = favorites_state.view_apartment(apartment_id=apt_id)
    assert isinstance(result, Apartment)
    assert result.name == "Apt1"

    # Call handler with mock event
    event = _make_event(apt_app, favorites_state.view_apartment, result=result, apartment_id=apt_id)
    apt_app.handle_state_transition(event)

    # Verify transition
    assert isinstance(apt_app.current_state, ApartmentDetail)
    assert apt_app.current_state.apartment_id == apt_id


# =============================================================================
# Self-Loop Unit Tests
# =============================================================================


def test_list_apartments_no_transition(apt_app: StatefulApartmentApp) -> None:
    """Handler: list_apartments should not change state."""
    home_state = _home_state(apt_app)

    # Call tool and verify output
    result = home_state.list_apartments()
    assert isinstance(result, dict)
    assert len(result) == 2  # Two apartments in fixture

    # Call handler with mock event
    event = _make_event(apt_app, home_state.list_apartments, result=result)
    apt_app.handle_state_transition(event)

    # Should remain in ApartmentHome
    assert isinstance(apt_app.current_state, ApartmentHome)


def test_search_no_transition(apt_app: StatefulApartmentApp) -> None:
    """Handler: search should not change state."""
    apt_app.set_current_state(ApartmentSearch())
    search_state = _search_state(apt_app)

    # Call tool and verify output
    result = search_state.search(location="SB")
    assert isinstance(result, dict)

    # Call handler with mock event
    event = _make_event(apt_app, search_state.search, result=result, location="SB")
    apt_app.handle_state_transition(event)

    # Should remain in ApartmentSearch
    assert isinstance(apt_app.current_state, ApartmentSearch)


def test_save_apartment_no_transition(apt_app: StatefulApartmentApp) -> None:
    """Handler: save should not change state, apartment should be saved."""
    apt_id = list(apt_app.apartments.keys())[0]
    apt_app.set_current_state(ApartmentDetail(apartment_id=apt_id))
    detail_state = _detail_state(apt_app)

    # Verify not saved initially
    assert apt_id not in apt_app.saved_apartments

    # Call tool
    detail_state.save()

    # Verify saved
    assert apt_id in apt_app.saved_apartments

    # Call handler with mock event
    event = _make_event(apt_app, detail_state.save)
    apt_app.handle_state_transition(event)

    # Should remain in ApartmentDetail
    assert isinstance(apt_app.current_state, ApartmentDetail)
    assert apt_app.current_state.apartment_id == apt_id


def test_unsave_apartment_no_transition(apt_app: StatefulApartmentApp) -> None:
    """Handler: unsave should not change state, apartment should be unsaved."""
    apt_id = list(apt_app.apartments.keys())[0]

    # Save first
    apt_app.save_apartment(apartment_id=apt_id)
    assert apt_id in apt_app.saved_apartments

    apt_app.set_current_state(ApartmentDetail(apartment_id=apt_id))
    detail_state = _detail_state(apt_app)

    # Call tool
    detail_state.unsave()

    # Verify unsaved
    assert apt_id not in apt_app.saved_apartments

    # Call handler with mock event
    event = _make_event(apt_app, detail_state.unsave)
    apt_app.handle_state_transition(event)

    # Should remain in ApartmentDetail
    assert isinstance(apt_app.current_state, ApartmentDetail)


# =============================================================================
# Integration Tests
# =============================================================================


class TestApartmentIntegration:
    """Integration tests using StateAwareEnvironmentWrapper."""

    def test_search_and_view_flow(self, env_with_apartment: StateAwareEnvironmentWrapper) -> None:
        """Integration: Home -> open_search -> Search -> view_apartment -> Detail."""
        app = env_with_apartment.get_app_with_class(StatefulApartmentApp)
        apt_id = list(app.apartments.keys())[0]

        # Start at Home
        assert isinstance(app.current_state, ApartmentHome)
        assert len(app.navigation_stack) == 0

        # Step 1: open_search -> ApartmentSearch
        _home_state(app).open_search()
        assert isinstance(app.current_state, ApartmentSearch)
        assert len(app.navigation_stack) == 1

        # Step 2: view_apartment -> ApartmentDetail
        _search_state(app).view_apartment(apartment_id=apt_id)
        assert isinstance(app.current_state, ApartmentDetail)
        assert app.current_state.apartment_id == apt_id
        assert len(app.navigation_stack) == 2

    def test_favorites_flow(self, env_with_apartment: StateAwareEnvironmentWrapper) -> None:
        """Integration: Home -> view -> Detail -> save -> go_back -> Home -> open_favorites -> Favorites."""
        app = env_with_apartment.get_app_with_class(StatefulApartmentApp)
        apt_id = list(app.apartments.keys())[0]

        # Start at Home
        assert isinstance(app.current_state, ApartmentHome)

        # Step 1: view_apartment -> Detail
        _home_state(app).view_apartment(apartment_id=apt_id)
        assert isinstance(app.current_state, ApartmentDetail)

        # Step 2: save apartment (self-loop)
        _detail_state(app).save()
        assert isinstance(app.current_state, ApartmentDetail)
        assert apt_id in app.saved_apartments

        # Step 3: go_back -> Home
        app.go_back()
        assert isinstance(app.current_state, ApartmentHome)

        # Step 4: open_favorites -> Favorites
        _home_state(app).open_favorites()
        assert isinstance(app.current_state, ApartmentFavorites)

    def test_go_back_from_search(self, env_with_apartment: StateAwareEnvironmentWrapper) -> None:
        """Integration: Home -> open_search -> Search -> go_back -> Home."""
        app = env_with_apartment.get_app_with_class(StatefulApartmentApp)

        # Step 1: open_search -> Search
        _home_state(app).open_search()
        assert isinstance(app.current_state, ApartmentSearch)
        assert len(app.navigation_stack) == 1

        # Step 2: go_back -> Home
        app.go_back()
        assert isinstance(app.current_state, ApartmentHome)
        assert len(app.navigation_stack) == 0

    def test_go_back_from_favorites(self, env_with_apartment: StateAwareEnvironmentWrapper) -> None:
        """Integration: Home -> open_favorites -> Favorites -> go_back -> Home."""
        app = env_with_apartment.get_app_with_class(StatefulApartmentApp)

        # Step 1: open_favorites -> Favorites
        _home_state(app).open_favorites()
        assert isinstance(app.current_state, ApartmentFavorites)
        assert len(app.navigation_stack) == 1

        # Step 2: go_back -> Home
        app.go_back()
        assert isinstance(app.current_state, ApartmentHome)
        assert len(app.navigation_stack) == 0

    def test_go_back_from_detail(self, env_with_apartment: StateAwareEnvironmentWrapper) -> None:
        """Integration: Home -> view_apartment -> Detail -> go_back -> Home."""
        app = env_with_apartment.get_app_with_class(StatefulApartmentApp)
        apt_id = list(app.apartments.keys())[0]

        # Step 1: view_apartment -> Detail
        _home_state(app).view_apartment(apartment_id=apt_id)
        assert isinstance(app.current_state, ApartmentDetail)
        assert len(app.navigation_stack) == 1

        # Step 2: go_back -> Home
        app.go_back()
        assert isinstance(app.current_state, ApartmentHome)
        assert len(app.navigation_stack) == 0

    def test_go_back_chain(self, env_with_apartment: StateAwareEnvironmentWrapper) -> None:
        """Integration: Home -> Search -> Detail -> go_back -> Search -> go_back -> Home."""
        app = env_with_apartment.get_app_with_class(StatefulApartmentApp)
        apt_id = list(app.apartments.keys())[0]

        # Build up navigation stack: Home -> Search -> Detail
        _home_state(app).open_search()
        _search_state(app).view_apartment(apartment_id=apt_id)

        assert isinstance(app.current_state, ApartmentDetail)
        assert len(app.navigation_stack) == 2

        # go_back -> Search
        app.go_back()
        assert isinstance(app.current_state, ApartmentSearch)
        assert len(app.navigation_stack) == 1

        # go_back -> Home
        app.go_back()
        assert isinstance(app.current_state, ApartmentHome)
        assert len(app.navigation_stack) == 0


# =============================================================================
# State Initialization Tests
# =============================================================================


def test_apartment_detail_initialization() -> None:
    """ApartmentDetail stores apartment_id correctly."""
    apt_id = "test-apt-123"
    state = ApartmentDetail(apartment_id=apt_id)

    assert state.apartment_id == apt_id


# =============================================================================
# Edge Case Tests
# =============================================================================


def test_go_back_with_empty_stack(apt_app: StatefulApartmentApp) -> None:
    """go_back with empty stack should not crash and stay in current state."""
    assert isinstance(apt_app.current_state, ApartmentHome)
    assert len(apt_app.navigation_stack) == 0

    # go_back should handle empty stack gracefully
    apt_app.go_back()

    # Should remain in ApartmentHome
    assert isinstance(apt_app.current_state, ApartmentHome)
    assert len(apt_app.navigation_stack) == 0


def test_save_already_saved_apartment(apt_app: StatefulApartmentApp) -> None:
    """Saving an already saved apartment should not cause issues."""
    apt_id = list(apt_app.apartments.keys())[0]

    # Save once
    apt_app.save_apartment(apartment_id=apt_id)
    assert apt_id in apt_app.saved_apartments

    # Save again through state
    apt_app.set_current_state(ApartmentDetail(apartment_id=apt_id))
    detail_state = _detail_state(apt_app)
    detail_state.save()

    # Should still be saved (no error, idempotent)
    assert apt_id in apt_app.saved_apartments


def test_unsave_not_saved_apartment(apt_app: StatefulApartmentApp) -> None:
    """Unsaving an apartment that's not saved should raise ValueError."""
    apt_id = list(apt_app.apartments.keys())[0]

    # Verify not saved
    assert apt_id not in apt_app.saved_apartments

    # Unsave through state should raise error
    apt_app.set_current_state(ApartmentDetail(apartment_id=apt_id))
    detail_state = _detail_state(apt_app)

    with pytest.raises(ValueError, match="Apartment not in saved list"):
        detail_state.unsave()
