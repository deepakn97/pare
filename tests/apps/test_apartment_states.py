"""
Corrected tests for the Apartment Stateful App.

Key principles:
- Backend operations are executed explicitly.
- handle_state_transition is only used to test navigation.
- No fixture is ever used at module scope.
"""

from typing import Any

import pytest

from are.simulation.types import (
    Action,
    CompletedEvent,
    EventMetadata,
    EventType,
)

from pas.apps.apartment.app import StatefulApartmentApp
from pas.apps.apartment.states import (
    ApartmentHome,
    ApartmentDetail,
    ApartmentSearch,
    ApartmentSaved,
)


# ----------------------------------------------------------------------
# Helper: create ARE-style CompletedEvent for navigation testing
# ----------------------------------------------------------------------
def make_event(
    app: StatefulApartmentApp,
    func: callable,
    **kwargs: Any,
) -> CompletedEvent:
    action = Action(
        function=func,
        args={"self": app, **kwargs},
        app=app,
    )
    return CompletedEvent(
        event_id="test-event",
        event_type=EventType.USER,
        action=action,
        metadata=EventMetadata(),
        event_time=0,
    )


# ----------------------------------------------------------------------
# Fixture
# ----------------------------------------------------------------------
@pytest.fixture
def apt_app() -> StatefulApartmentApp:
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


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
def test_starts_in_home(apt_app: StatefulApartmentApp) -> None:
    assert isinstance(apt_app.current_state, ApartmentHome)


def test_home_to_detail(apt_app: StatefulApartmentApp) -> None:
    apt_id = list(apt_app.apartments.keys())[0]

    apt_app.handle_state_transition(
        make_event(
            apt_app,
            apt_app.get_apartment_details,
            apartment_id=apt_id,
        )
    )

    assert isinstance(apt_app.current_state, ApartmentDetail)
    assert apt_app.current_state.apartment_id == apt_id


def test_detail_update_stays_in_detail(apt_app: StatefulApartmentApp) -> None:
    apt_id = list(apt_app.apartments.keys())[0]

    # Go to detail
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            apt_app.get_apartment_details,
            apartment_id=apt_id,
        )
    )

    # Backend update (real mutation)
    apt_app.update_apartment(
        apartment_id=apt_id,
        new_price=3000.0,
    )

    # Navigation event only
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            apt_app.update_apartment,
            apartment_id=apt_id,
            new_price=3000.0,
        )
    )

    assert apt_app.apartments[apt_id].price == 3000.0
    assert isinstance(apt_app.current_state, ApartmentDetail)


def test_detail_delete_goes_home(apt_app: StatefulApartmentApp) -> None:
    apt_id = list(apt_app.apartments.keys())[0]

    # Go to detail
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            apt_app.get_apartment_details,
            apartment_id=apt_id,
        )
    )


    apt_app.current_state.delete()
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            apt_app.current_state.delete,
        )
    )

    assert isinstance(apt_app.current_state, ApartmentHome)
    assert apt_id not in apt_app.apartments


def test_open_search(apt_app: StatefulApartmentApp) -> None:
    apt_app.handle_state_transition(
        make_event(apt_app, apt_app.open_search)
    )

    assert isinstance(apt_app.current_state, ApartmentSearch)


def test_search_to_detail(apt_app: StatefulApartmentApp) -> None:
    apt_id = list(apt_app.apartments.keys())[1]

    apt_app.handle_state_transition(
        make_event(apt_app, apt_app.open_search)
    )
    assert isinstance(apt_app.current_state, ApartmentSearch)

    apt_app.handle_state_transition(
        make_event(
            apt_app,
            apt_app.get_apartment_details,
            apartment_id=apt_id,
        )
    )

    assert isinstance(apt_app.current_state, ApartmentDetail)
    assert apt_app.current_state.apartment_id == apt_id


def test_open_saved_and_unsave(apt_app: StatefulApartmentApp) -> None:
    apt_id = list(apt_app.apartments.keys())[0]

    # Backend save
    apt_app.save_apartment(apartment_id=apt_id)

    # Navigation event
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            apt_app.save_apartment,
            apartment_id=apt_id,
        )
    )

    assert apt_id in apt_app.saved_apartments

    # Open saved view
    apt_app.handle_state_transition(
        make_event(apt_app, apt_app.open_saved)
    )
    assert isinstance(apt_app.current_state, ApartmentSaved)

    # Backend unsave
    apt_app.remove_saved_apartment(apartment_id=apt_id)

    # Navigation event
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            apt_app.remove_saved_apartment,
            apartment_id=apt_id,
        )
    )

    assert apt_id not in apt_app.saved_apartments
    assert isinstance(apt_app.current_state, ApartmentSaved)


def test_go_back_to_home(apt_app: StatefulApartmentApp) -> None:
    apt_app.handle_state_transition(
        make_event(apt_app, apt_app.open_search)
    )
    assert isinstance(apt_app.current_state, ApartmentSearch)

    apt_app.handle_state_transition(
        make_event(apt_app, apt_app.go_back)
    )
    assert isinstance(apt_app.current_state, ApartmentHome)
