# Stateful Apartment App

`pare.apps.apartment.app.StatefulApartmentApp` extends the Meta-ARE
`ApartmentListingApp` with PARE navigation support.
It launches in `ApartmentHome` and transitions between home, search,
favorites, and detail views based on completed apartment backend operations.

---

## State Transition Diagram

```
                                    ○ list_apartments
                                    │
                    ┌───────────────┴───────────────┐
                    │        ApartmentHome          │
                    │         (ROOT STATE)          │
                    └───┬───────────┬───────────┬───┘
                        │           │           │
         view_apartment │           │           │ open_favorites
                        │           │           │
                        │           │           └─────────────────────────────┐
                        │           │ open_search                             │
                        │           │                                         │
                        │           ▼                 ○ search                ▼
                        │   ┌───────────────────┐     │         ┌─────────────────────┐
                        │   │  ApartmentSearch  │◄────┘         │ ApartmentFavorites  │
                        │   └─────────┬─────────┘               └──────────┬──────────┘
                        │             │                                    │
                        │             │ view_apartment                     │ view_apartment
                        │             │                                    │
                        ▼             ▼                                    ▼
      ○ save    ┌─────────────────────────────────────────────────────────────────┐
      │         │                       ApartmentDetail                           │
      ├────────►│                    context: apartment_id                        │◄──┐
      │         └─────────────────────────────────────────────────────────────────┘   │
      └─────────────────────────────────────────────────────────────────────────────○─┘
                                                                              unsave

Legend:
○ = Self-loop (action executes, state unchanged)
→ = Transition to another state
go_back (inherited from StatefulApp) returns to previous state via navigation stack
```

---

## Navigation States

---

### ApartmentHome

Main screen for listing apartments and navigating to search or favorites views.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_apartments()` | `ApartmentListingApp.list_all_apartments()` | `dict[str, Any]` apartment records | Remains in `ApartmentHome` |
| `view_apartment(apartment_id)` | `ApartmentListingApp.get_apartment_details(apartment_id)` | `Apartment` object | → `ApartmentDetail(apartment_id)` |
| `open_search()` | — | Navigation indicator string | → `ApartmentSearch` |
| `open_favorites()` | `ApartmentListingApp.list_saved_apartments()` | `dict[str, Apartment]` saved apartments | → `ApartmentFavorites` |

---

### ApartmentDetail

Detail screen for a specific apartment, supporting save and unsave actions.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `save()` | `ApartmentListingApp.save_apartment(apartment_id)` | `None` | Remains in `ApartmentDetail` |
| `unsave()` | `ApartmentListingApp.remove_saved_apartment(apartment_id)` | `None` | Remains in `ApartmentDetail` |
| `go_back()` | — | Navigation indicator string | → Previous state (via navigation stack) |

---

### ApartmentSearch

Screen for searching apartments with optional filtering criteria.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `search(...)` | `ApartmentListingApp.search_apartments(...)` | `dict[str, Apartment]` filtered results | Remains in `ApartmentSearch` |
| `view_apartment(apartment_id)` | `ApartmentListingApp.get_apartment_details(apartment_id)` | `Apartment` object | → `ApartmentDetail(apartment_id)` |
| `go_back()` | — | Navigation indicator string | → Previous state (via navigation stack) |

**Search parameters:** `name`, `location`, `zip_code`, `min_price`, `max_price`, `number_of_bedrooms`, `number_of_bathrooms`, `property_type`, `square_footage`, `furnished_status`, `floor_level`, `pet_policy`, `lease_term`, `amenities`

---

### ApartmentFavorites

Screen displaying saved apartments.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `view_apartment(apartment_id)` | `ApartmentListingApp.get_apartment_details(apartment_id)` | `Apartment` object | → `ApartmentDetail(apartment_id)` |
| `go_back()` | — | Navigation indicator string | → Previous state (via navigation stack) |

---

## Summary Table

| State | Context | Transitions Out | Self-Loops |
|-------|---------|-----------------|------------|
| **ApartmentHome** | — | `view_apartment` → ApartmentDetail, `open_search` → ApartmentSearch, `open_favorites` → ApartmentFavorites | `list_apartments` |
| **ApartmentDetail** | apartment_id | `go_back` → previous state | `save`, `unsave` |
| **ApartmentSearch** | — | `view_apartment` → ApartmentDetail, `go_back` → previous state | `search` |
| **ApartmentFavorites** | — | `view_apartment` → ApartmentDetail, `go_back` → previous state | — |

---

## Navigation Helpers

- Navigation transitions are handled in
  `StatefulApartmentApp.handle_state_transition`
  based on the completed backend tool name.
- `view_apartment` always transitions into `ApartmentDetail`
  using the provided `apartment_id`.
- `save` and `unsave` operations do not trigger navigation changes.
- `go_back()` is inherited from `StatefulApp` and uses the navigation stack
  to return to the previous state.
