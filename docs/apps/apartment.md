# Stateful Apartment App

`pas.apps.apartment.app.StatefulApartmentApp` layers PAS navigation on top of the
Meta-ARE `ApartmentListingApp`. The app starts in the `ApartmentHome` state and
transitions between search, saved-list, and apartment detail views based on
completed user tools.

---

## Navigation States

---

## ApartmentHome

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_apartments()` | `ApartmentListingApp.list_all_apartments()` | Apartment dict | Remains in `ApartmentHome` |
| `view_apartment(apartment_id)` | `ApartmentListingApp.get_apartment_details(...)` | Apartment object | → `ApartmentDetail(apartment_id)` |
| `open_search()` | None | Indicator | → `ApartmentSearch()` |
| `open_saved()` | None | Indicator | → `ApartmentSaved()` |

---

## ApartmentSearch

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `search(filters…)` | `ApartmentListingApp.search_apartments(...)` | Filtered apartment dict | Remains in `ApartmentSearch` |
| `view_apartment(apartment_id)` | `ApartmentListingApp.get_apartment_details(...)` | Apartment object | → `ApartmentDetail(apartment_id)` |
| `go_back()` | None | Indicator | → `ApartmentHome()` |

---

## ApartmentSaved

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_saved()` | `ApartmentListingApp.list_saved_apartments()` | Saved apartment dict | Remains in `ApartmentSaved` |
| `unsave(apartment_id)` | `ApartmentListingApp.remove_saved_apartment(...)` | Status | Remains in `ApartmentSaved` |
| `view_apartment(apartment_id)` | `ApartmentListingApp.get_apartment_details(...)` | Apartment object | → `ApartmentDetail(apartment_id)` |
| `go_back()` | None | Indicator | → `ApartmentHome()` |

---

## ApartmentDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_details()` | `ApartmentListingApp.get_apartment_details(...)` | Apartment object | Remains in `ApartmentDetail` |
| `save()` | `ApartmentListingApp.save_apartment(...)` | Status | Remains in `ApartmentDetail` |
| `update_price(new_price)` | `ApartmentListingApp.update_apartment(...)` | Apartment ID | Remains in `ApartmentDetail` |
| `delete()` | `ApartmentListingApp.delete_apartment(...)` | Status | → `ApartmentHome()` |
| `go_back()` | None | Indicator | → `ApartmentHome()` |

---

## Navigation Summary

- `ApartmentHome → ApartmentDetail` via `view_apartment`
- `ApartmentHome → ApartmentSearch` via `open_search`
- `ApartmentHome → ApartmentSaved` via `open_saved`
- `ApartmentSearch → ApartmentDetail` via `view_apartment`
- `ApartmentSearch → ApartmentHome` via `go_back`
- `ApartmentSaved → ApartmentDetail` via `view_apartment`
- `ApartmentSaved → ApartmentHome` via `go_back`
- `ApartmentDetail → ApartmentHome` via `delete` or `go_back`
- `save` / `update_price` remain in `ApartmentDetail`
- `unsave` remains in `ApartmentSaved`

---

## Navigation Helpers

- `load_root_state()` resets the app to `ApartmentHome`
- `set_current_state(...)` replaces the current navigation state
- `go_back()` always returns to the root (`ApartmentHome`) for simplicity and deterministic behavior
