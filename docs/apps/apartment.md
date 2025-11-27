"""
Stateful Apartment App
======================

`pas.apps.apartment.app.StatefulApartmentApp` layers PAS navigation on top of
the Meta-ARE `ApartmentListingApp`. It begins in the `ApartmentHome` state and
transitions into search, saved-list view, or apartment detail screens depending
on which user tool completes.

---------------------------------------------------------------------
Navigation States
---------------------------------------------------------------------

ApartmentHome
-------------

| Tool                                      | Backend call(s)                                       | Returns                       | Navigation effect                                              |
| ----------------------------------------- | ------------------------------------------------------ | ----------------------------- | -------------------------------------------------------------- |
| `list_apartments()`                       | `ApartmentListingApp.list_all_apartments()`            | List of all apartments        | Remains in `ApartmentHome`                                     |
| `view_apartment(apartment_id)`            | `ApartmentListingApp.get_apartment_details(...)`       | Apartment object              | → `ApartmentDetail(apartment_id)`                              |
| `open_search()`                           | None                                                   | "open_search"                 | → `ApartmentSearch()`                                          |
| `open_saved()`                            | None                                                   | "open_saved"                  | → `ApartmentSaved()`                                           |

ApartmentSearch
---------------

| Tool                                      | Backend call(s)                                       | Returns                       | Navigation effect                                              |
| ----------------------------------------- | ------------------------------------------------------ | ----------------------------- | -------------------------------------------------------------- |
| `search(filter_args…)`                    | `ApartmentListingApp.search_apartments(...)`           | Filtered list                 | Remains in `ApartmentSearch`                                   |
| `view_apartment(apartment_id)`            | `ApartmentListingApp.get_apartment_details(...)`       | Apartment object              | → `ApartmentDetail(apartment_id)`                              |
| `go_back()`                               | None                                                   | "go_back"                     | → `ApartmentHome()`                                            |

ApartmentSaved
--------------

| Tool                                      | Backend call(s)                                       | Returns                       | Navigation effect                                              |
| ----------------------------------------- | ------------------------------------------------------ | ----------------------------- | -------------------------------------------------------------- |
| `list_saved_apartments()`                 | `ApartmentListingApp.list_saved_apartments()`          | Saved apartment list          | Remains in `ApartmentSaved`                                    |
| `remove_saved_apartment(apartment_id)`    | `ApartmentListingApp.remove_saved_apartment(...)`      | Status                        | Remains in `ApartmentSaved`                                    |
| `view_apartment(apartment_id)`            | `ApartmentListingApp.get_apartment_details(...)`       | Apartment object              | → `ApartmentDetail(apartment_id)`                              |
| `go_back()`                               | None                                                   | "go_back"                     | → `ApartmentHome()`                                            |

ApartmentDetail
---------------

| Tool                                      | Backend call(s)                                       | Returns                       | Navigation effect                                              |
| ----------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------------- |
| `get_apartment_details(apartment_id)`     | `ApartmentListingApp.get_apartment_details(...)`       | Apartment object              | Remains in `ApartmentDetail`                                   |
| `save_apartment(apartment_id)`            | `ApartmentListingApp.save_apartment(...)`              | Status                        | Remains in `ApartmentDetail`                                   |
| `update_apartment(apartment_id, attrs…)`  | `ApartmentListingApp.update_apartment(...)`            | Updated object                | Remains in `ApartmentDetail`                                   |
| `delete_apartment(apartment_id)`          | `ApartmentListingApp.delete_apartment(...)`            | Status                        | → `ApartmentHome()`                                            |
| `go_back()`                               | None                                                   | "go_back"                     | → `ApartmentHome()`                                            |

---------------------------------------------------------------------
Navigation Summary
---------------------------------------------------------------------

- `ApartmentHome → ApartmentDetail` via `view_apartment`
- `ApartmentHome → ApartmentSearch` via `open_search`
- `ApartmentHome → ApartmentSaved` via `open_saved`
- `ApartmentSearch → ApartmentDetail` via `view_apartment`
- `ApartmentSearch → ApartmentHome` via `go_back`
- `ApartmentSaved → ApartmentDetail` via `view_apartment`
- `ApartmentSaved → ApartmentHome` via `go_back`
- `ApartmentDetail → ApartmentHome` via `delete_apartment` or `go_back`
- `update_apartment` keeps user in `ApartmentDetail`
- `save_apartment` / `remove_saved_apartment` keep user in current state

---------------------------------------------------------------------
Navigation Helpers
---------------------------------------------------------------------

- `load_root_state()` resets to `ApartmentHome`
- `set_current_state(...)` pushes a new state instance
- `go_back()` implemented via user tool, returns to root
- `_run_backend_if_needed(...)` triggers backend operations during tests
- `_navigate(...)` maps completed actions to navigation transitions
"""
