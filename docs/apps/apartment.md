# Stateful Apartment App

`pas.apps.apartment.app.StatefulApartmentApp` extends the Meta-ARE
`ApartmentListingApp` with PAS navigation support.
It launches in `ApartmentHome` and transitions between home, search,
saved, and detail views based on completed apartment backend operations.

---

## Navigation States

---

### ApartmentHome

Main screen for listing apartments and navigating to search or saved views.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_apartments()` | `ApartmentListingApp.list_all_apartments()` | `dict[str, object]` apartment records | Remains in `ApartmentHome` |
| `view_apartment(apartment_id)` | `ApartmentListingApp.get_apartment_details(apartment_id)` | Apartment details dict | → `ApartmentDetail(apartment_id)` |
| `open_search()` | — | Navigation indicator string | → `ApartmentSearch` |
| `open_saved()` | — | Navigation indicator string | → `ApartmentSaved` |

---

### ApartmentDetail

Detail screen for a specific apartment, supporting save, update, and delete actions.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_details()` | `ApartmentListingApp.get_apartment_details(apartment_id)` | Apartment details dict | Remains in `ApartmentDetail` |
| `save()` | `ApartmentListingApp.save_apartment(apartment_id)` | `None` | Remains in `ApartmentDetail` |
| `unsave()` | `ApartmentListingApp.remove_saved_apartment(apartment_id)` | `None` | Remains in `ApartmentDetail` |
| `update_price(new_price)` | `ApartmentListingApp.update_apartment(apartment_id, new_price)` | `None` | Remains in `ApartmentDetail(apartment_id)` |
| `delete()` | `ApartmentListingApp.delete_apartment(apartment_id)` | `None` | → `ApartmentHome` |
| `go_back()` | — | Navigation indicator string | → `ApartmentHome` |

---

### ApartmentSearch

Screen for searching apartments with optional filtering criteria.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `search(...)` | `ApartmentListingApp.search_apartments(...)` | Filtered apartment results dict | Remains in `ApartmentSearch` |
| `view_apartment(apartment_id)` | `ApartmentListingApp.get_apartment_details(apartment_id)` | Apartment details dict | → `ApartmentDetail(apartment_id)` |
| `go_back()` | — | Navigation indicator string | → `ApartmentHome` |

---

### ApartmentSaved

Screen displaying all saved apartments.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_saved()` | `ApartmentListingApp.list_saved_apartments()` | Saved apartments dict | Remains in `ApartmentSaved` |
| `view_apartment(apartment_id)` | `ApartmentListingApp.get_apartment_details(apartment_id)` | Apartment details dict | → `ApartmentDetail(apartment_id)` |
| `unsave(apartment_id)` | `ApartmentListingApp.remove_saved_apartment(apartment_id)` | `None` | Remains in `ApartmentSaved` |
| `go_back()` | — | Navigation indicator string | → `ApartmentHome` |

---

## Navigation Helpers

- Navigation transitions are handled in
  `StatefulApartmentApp.handle_state_transition`
  based on the completed backend tool name.
- `view_apartment` always transitions into `ApartmentDetail`
  using the provided `apartment_id`.
- `save` and `unsave` operations do not trigger navigation changes.
- `update_price` refreshes the current detail view for the same apartment.
- `delete` and `go_back` always return the app to `ApartmentHome`.
- `go_back()` appears automatically when navigation history exists and pops
  to the previous screen.
