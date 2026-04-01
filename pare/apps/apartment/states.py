from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from are.simulation.apps.apartment_listing import (
    Apartment,  # noqa: TC002 - runtime import required for get_type_hints()
)
from are.simulation.types import OperationType, disable_events

from pare.apps.core import AppState
from pare.apps.tool_decorators import pare_event_registered, user_tool

if TYPE_CHECKING:
    from pare.apps.apartment.app import StatefulApartmentApp

logger = logging.getLogger(__name__)


# Home Screen
class ApartmentHome(AppState):
    """Main screen for listing apartments and navigating to other views."""

    def on_enter(self) -> None:
        """Run when entering the home screen."""
        pass

    def on_exit(self) -> None:
        """Run when exiting the home screen."""
        pass

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def list_apartments(self) -> dict[str, Any]:
        """List all apartments.

        Returns:
            dict[str, Any]: All available apartment records.
        """
        app = cast("StatefulApartmentApp", self.app)
        with disable_events():
            apartments = app.list_all_apartments()

        logger.debug(f"Listed Apartments: {apartments}")

        return apartments

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def view_apartment(self, apartment_id: str) -> Apartment:
        """Open the detail screen for a specific apartment.

        Args:
            apartment_id: Unique identifier for the apartment.

        Returns:
            Apartment: Apartment details.
        """
        app = cast("StatefulApartmentApp", self.app)
        with disable_events():
            return app.get_apartment_details(apartment_id=apartment_id)

    @user_tool()
    @pare_event_registered()
    def open_search(self) -> str:
        """Navigate to the search page.

        Returns:
            str: Confirmation that the search view is open.
        """
        return "Search Apartments view is open."

    @user_tool()
    @pare_event_registered()
    def open_favorites(self) -> dict[str, Apartment]:
        """Navigate to the saved apartments page.

        Returns:
            dict[str, Apartment]: Saved apartments.
        """
        app = cast("StatefulApartmentApp", self.app)
        with disable_events():
            return app.list_saved_apartments()


# Detail Screen
class ApartmentDetail(AppState):
    """Detail screen for a specific apartment."""

    def __init__(self, apartment_id: str) -> None:
        """Initialize the detail screen.

        Args:
            apartment_id: Unique identifier for the apartment.
        """
        super().__init__()
        self.apartment_id = apartment_id

    def on_enter(self) -> None:
        """Run when entering the detail screen."""
        pass

    def on_exit(self) -> None:
        """Run when exiting the detail screen."""
        pass

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def save(self) -> None:
        """Save this apartment to saved apartments lists."""
        app = cast("StatefulApartmentApp", self.app)
        with disable_events():
            return app.save_apartment(apartment_id=self.apartment_id)

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def unsave(self) -> None:
        """Remove this apartment from the saved list."""
        app = cast("StatefulApartmentApp", self.app)
        with disable_events():
            return app.remove_saved_apartment(apartment_id=self.apartment_id)


# Search Screen
class ApartmentSearch(AppState):
    """Screen for searching apartments with optional filtering."""

    def on_enter(self) -> None:
        """Run when entering the search screen."""
        pass

    def on_exit(self) -> None:
        """Run when exiting the search screen."""
        pass

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def search(
        self,
        name: str | None = None,
        location: str | None = None,
        zip_code: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        number_of_bedrooms: int | None = None,
        number_of_bathrooms: int | None = None,
        property_type: str | None = None,
        square_footage: int | None = None,
        furnished_status: str | None = None,
        floor_level: str | None = None,
        pet_policy: str | None = None,
        lease_term: str | None = None,
        amenities: list[str] | None = None,
    ) -> dict[str, Apartment]:
        """Search apartments using optional filtering criteria.

        Returns:
            dict[str, Apartment]: Filtered apartment results.
        """
        app = cast("StatefulApartmentApp", self.app)
        with disable_events():
            return app.search_apartments(
                name=name,
                location=location,
                zip_code=zip_code,
                min_price=min_price,
                max_price=max_price,
                number_of_bedrooms=number_of_bedrooms,
                number_of_bathrooms=number_of_bathrooms,
                property_type=property_type,
                square_footage=square_footage,
                furnished_status=furnished_status,
                floor_level=floor_level,
                pet_policy=pet_policy,
                lease_term=lease_term,
                amenities=amenities,
            )

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def view_apartment(self, apartment_id: str) -> Apartment:
        """Open detail page from search results.

        Args:
            apartment_id: Unique identifier for the apartment.

        Returns:
            Apartment: Apartment details.
        """
        app = cast("StatefulApartmentApp", self.app)
        with disable_events():
            return app.get_apartment_details(apartment_id=apartment_id)


# Saved Apartments
class ApartmentFavorites(AppState):
    """Screen showing saved apartments."""

    def on_enter(self) -> None:
        """Run when entering the saved apartments screen."""
        pass

    def on_exit(self) -> None:
        """Run when exiting the saved apartments screen."""
        pass

    @user_tool()
    @pare_event_registered(operation_type=OperationType.READ)
    def view_apartment(self, apartment_id: str) -> Apartment:
        """View an apartment from the saved list.

        Args:
            apartment_id: Unique identifier for the apartment.

        Returns:
            Apartment: Apartment details.
        """
        app = cast("StatefulApartmentApp", self.app)
        with disable_events():
            return app.get_apartment_details(apartment_id=apartment_id)
