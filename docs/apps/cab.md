# Stateful Cab App

`pare.apps.cab.app.StatefulCabApp` extends the Meta-ARE `CabApp` with PARE navigation.
It launches in `CabHome` and transitions between home, service selection,
quotation, and ride detail flows based on completed cab backend operations.

---

## Navigation States

---

### CabHome

Home screen for cab operations such as listing available rides, viewing the
current ride, and viewing ride history.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_rides(start_location, end_location, ride_time=None)` | `CabApp.list_rides(start_location, end_location, ride_time)` | `list[Ride]` quotations | → `CabServiceOptions(start_location, end_location, ride_time)` |
| `open_current_ride()` | `CabApp.get_current_ride_status()` | Current `Ride` | → `CabRideDetail(ride)` |
| `get_ride_history(offset=0, limit=10)` | `CabApp.get_ride_history(offset, limit)` | Pagination dict of rides | Remains in `CabHome` |

---

### CabServiceOptions

Screen displaying available service types for a given journey.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_service_types()` | Reads `CabApp.d_service_config` | `list[str]` service names | Remains in `CabServiceOptions` |
| `get_quotation(service_type)` | `CabApp.get_quotation(start, end, service_type, ride_time)` | Unbooked `Ride` quotation | → `CabQuotationDetail(ride)` |

---

### CabQuotationDetail

Screen displaying a quotation (ride before booking).

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `show_quotation()` | — | Quotation `Ride` | Remains in `CabQuotationDetail` |
| `order_ride()` | `CabApp.order_ride(start, end, service_type, ride_time)` | Booked `Ride` | → `CabRideDetail(ride)` |

---

### CabRideDetail

Detail view for a specific ride, allowing the user to cancel the ride.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `cancel_ride()` | `CabApp.user_cancel_ride()` | `str` (cancellation message) | → `CabHome` (stack cleared) |

---

## Navigation Helpers

- Navigation transitions are handled in `StatefulCabApp.handle_state_transition`
  based on the completed backend tool name.
- States store the `Ride` object directly for context (not ride index).
- After ride cancellation, the app returns to `CabHome` and clears the navigation stack.
- `go_back()` appears automatically when navigation history exists and pops
  to the previous state.
