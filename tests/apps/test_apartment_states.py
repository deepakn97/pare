"""
Corrected tests for the Apartment Stateful App.

Key principles:
- Backend operations are executed through state classes.
- handle_state_transition is used to test navigation.
- Methods are called on the current state, not directly on the app.
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


def test_starts_in_home(apt_app: StatefulApartmentApp) -> None:
    assert isinstance(apt_app.current_state, ApartmentHome)


def test_home_to_detail(apt_app: StatefulApartmentApp) -> None:
    apt_id = list(apt_app.apartments.keys())[0]

    # Call view_apartment on the current state (ApartmentHome)
    home_state = apt_app.current_state
    assert isinstance(home_state, ApartmentHome)

    apt_app.handle_state_transition(
        make_event(
            apt_app,
            home_state.view_apartment,
            apartment_id=apt_id,
        )
    )

    assert isinstance(apt_app.current_state, ApartmentDetail)
    assert apt_app.current_state.apartment_id == apt_id


def test_detail_update_stays_in_detail(apt_app: StatefulApartmentApp) -> None:
    apt_id = list(apt_app.apartments.keys())[0]

    # Go to detail
    home_state = apt_app.current_state
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            home_state.view_apartment,
            apartment_id=apt_id,
        )
    )

    detail_state = apt_app.current_state
    assert isinstance(detail_state, ApartmentDetail)

    # Backend update through state method
    detail_state.update_price(new_price=3000.0)

    # Navigation event
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            detail_state.update_price,
            new_price=3000.0,
        )
    )

    assert apt_app.apartments[apt_id].price == 3000.0
    assert isinstance(apt_app.current_state, ApartmentDetail)


def test_detail_delete_goes_home(apt_app: StatefulApartmentApp) -> None:
    apt_id = list(apt_app.apartments.keys())[0]

    # Go to detail
    home_state = apt_app.current_state
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            home_state.view_apartment,
            apartment_id=apt_id,
        )
    )

    detail_state = apt_app.current_state
    assert isinstance(detail_state, ApartmentDetail)

    # Backend delete
    detail_state.delete()

    # Navigation event
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            detail_state.delete,
        )
    )

    assert isinstance(apt_app.current_state, ApartmentHome)
    assert apt_id not in apt_app.apartments


def test_open_search(apt_app: StatefulApartmentApp) -> None:
    home_state = apt_app.current_state
    assert isinstance(home_state, ApartmentHome)

    apt_app.handle_state_transition(
        make_event(apt_app, home_state.open_search)
    )

    assert isinstance(apt_app.current_state, ApartmentSearch)


def test_search_to_detail(apt_app: StatefulApartmentApp) -> None:
    apt_id = list(apt_app.apartments.keys())[1]

    # Open search
    home_state = apt_app.current_state
    apt_app.handle_state_transition(
        make_event(apt_app, home_state.open_search)
    )

    search_state = apt_app.current_state
    assert isinstance(search_state, ApartmentSearch)

    # View apartment from search
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            search_state.view_apartment,
            apartment_id=apt_id,
        )
    )

    assert isinstance(apt_app.current_state, ApartmentDetail)
    assert apt_app.current_state.apartment_id == apt_id


def test_open_saved_and_unsave(apt_app: StatefulApartmentApp) -> None:
    apt_id = list(apt_app.apartments.keys())[0]

    # Backend save through app (initial setup)
    apt_app.save_apartment(apartment_id=apt_id)
    assert apt_id in apt_app.saved_apartments

    # Navigate to saved view
    home_state = apt_app.current_state
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            home_state.open_saved,
        )
    )

    saved_state = apt_app.current_state
    assert isinstance(saved_state, ApartmentSaved)

    # Backend unsave through state
    saved_state.unsave(apartment_id=apt_id)

    # Navigation event
    apt_app.handle_state_transition(
        make_event(
            apt_app,
            saved_state.unsave,
            apartment_id=apt_id,
        )
    )

    assert apt_id not in apt_app.saved_apartments
    assert isinstance(apt_app.current_state, ApartmentSaved)


def test_go_back_to_home(apt_app: StatefulApartmentApp) -> None:
    # Open search
    home_state = apt_app.current_state
    apt_app.handle_state_transition(
        make_event(apt_app, home_state.open_search)
    )

    search_state = apt_app.current_state
    assert isinstance(search_state, ApartmentSearch)

    # Go back
    apt_app.handle_state_transition(
        make_event(apt_app, search_state.go_back)
    )

    assert isinstance(apt_app.current_state, ApartmentHome)
