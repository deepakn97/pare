from __future__ import annotations

from typing import TYPE_CHECKING, cast

from are.simulation.types import OperationType

from pas.apps.core import AppState
from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from pas.apps.apartment.app import StatefulApartmentApp


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
    @pas_event_registered(operation_type=OperationType.READ)
    def list_apartments(self) -> list[dict[str, object]]:
        """List all apartments.

        Returns:
            list[dict[str, object]]: All available apartment records.
        """
        app = cast("StatefulApartmentApp", self.app)
        return app.list_all_apartments()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def view_apartment(self, apartment_id: str) -> dict[str, object]:
        """Open the detail screen for a specific apartment.

        Args:
            apartment_id: Unique identifier for the apartment.

        Returns:
            dict[str, object]: Apartment details.
        """
        app = cast("StatefulApartmentApp", self.app)
        return app.get_apartment_details(apartment_id=apartment_id)

    @user_tool()
    @pas_event_registered()
    def open_search(self) -> str:
        """Navigate to the search page.

        Returns:
            str: Navigation indicator used by PAS.
        """
        return "open_search"

    @user_tool()
    @pas_event_registered()
    def open_saved(self) -> str:
        """Navigate to the saved apartments page.

        Returns:
            str: Navigation indicator used by PAS.
        """
        return "open_saved"

    @user_tool()
    @pas_event_registered()
    def open_create(self) -> str:
        """Navigate to the apartment creation flow.

        Returns:
            str: Navigation indicator used by PAS.
        """
        return "open_create"


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
    @pas_event_registered(operation_type=OperationType.READ)
    def get_details(self) -> dict[str, object]:
        """Load apartment details.

        Returns:
            dict[str, object]: Apartment details.
        """
        app = cast("StatefulApartmentApp", self.app)
        return app.get_apartment_details(apartment_id=self.apartment_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def save(self) -> None:
        """Save this apartment to favorites."""
        app = cast("StatefulApartmentApp", self.app)
        return app.save_apartment(apartment_id=self.apartment_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def unsave(self) -> None:
        """Remove this apartment from the saved list."""
        app = cast("StatefulApartmentApp", self.app)
        return app.remove_saved_apartment(apartment_id=self.apartment_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def update_price(self, new_price: float) -> None:
        """Update the price of this apartment.

        Args:
            new_price: Updated price value.
        """
        app = cast("StatefulApartmentApp", self.app)
        return app.update_apartment(
            apartment_id=self.apartment_id,
            new_price=new_price,
        )

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def delete(self) -> None:
        """Delete this apartment."""
        app = cast("StatefulApartmentApp", self.app)
        return app.delete_apartment(apartment_id=self.apartment_id)

    @user_tool()
    @pas_event_registered()
    def go_back(self) -> str:
        """Return to the home screen.

        Returns:
            str: Navigation indicator used by PAS.
        """
        return "go_back"


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
    @pas_event_registered(operation_type=OperationType.READ)
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
    ) -> list[dict[str, object]]:
        """Search apartments using optional filtering criteria.

        Returns:
            list[dict[str, object]]: Filtered apartment results.
        """
        app = cast("StatefulApartmentApp", self.app)
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
    @pas_event_registered(operation_type=OperationType.READ)
    def view_apartment(self, apartment_id: str) -> dict[str, object]:
        """Open detail page from search results.

        Args:
            apartment_id: Unique identifier for the apartment.

        Returns:
            dict[str, object]: Apartment details.
        """
        app = cast("StatefulApartmentApp", self.app)
        return app.get_apartment_details(apartment_id=apartment_id)

    @user_tool()
    @pas_event_registered()
    def go_back(self) -> str:
        """Return to the home screen.

        Returns:
            str: Navigation indicator used by PAS.
        """
        return "go_back"


# Saved Apartments
class ApartmentSaved(AppState):
    """Screen showing saved apartments."""

    def on_enter(self) -> None:
        """Run when entering the saved apartments screen."""
        pass

    def on_exit(self) -> None:
        """Run when exiting the saved apartments screen."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_saved(self) -> list[dict[str, object]]:
        """List all saved apartments.

        Returns:
            list[dict[str, object]]: Saved apartments.
        """
        app = cast("StatefulApartmentApp", self.app)
        return app.list_saved_apartments()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def view_apartment(self, apartment_id: str) -> dict[str, object]:
        """View an apartment from the saved list.

        Args:
            apartment_id: Unique identifier for the apartment.

        Returns:
            dict[str, object]: Apartment details.
        """
        app = cast("StatefulApartmentApp", self.app)
        return app.get_apartment_details(apartment_id=apartment_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def unsave(self, apartment_id: str) -> None:
        """Remove an apartment from the saved list.

        Args:
            apartment_id: Unique identifier for the apartment.
        """
        app = cast("StatefulApartmentApp", self.app)
        return app.remove_saved_apartment(apartment_id=apartment_id)

    @user_tool()
    @pas_event_registered()
    def go_back(self) -> str:
        """Return to the home screen.

        Returns:
            str: Navigation indicator used by PAS.
        """
        return "go_back"
