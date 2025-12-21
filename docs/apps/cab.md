# Stateful Cab App

`pas.apps.cab.app.StatefulCabApp` extends the Meta-ARE `CabApp` with PAS navigation.
It launches in `CabHome` and transitions between home, service selection,
quotation, and ride detail flows based on completed cab backend operations.

---

## Navigation States

---

### CabHome

Home screen for cab operations such as listing rides, requesting quotations,
ordering rides, and viewing ride history.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_rides(start_location, end_location, ride_time=None)` | `CabApp.list_rides(start_location, end_location, ride_time)` | `list[Ride]` quotations | → `CabServiceOptions(start_location, end_location, ride_time)` |
| `get_quotation(start_location, end_location, service_type, ride_time=None)` | `CabApp.get_quotation(...)` | Unbooked `Ride` quotation | → `CabQuotationDetail(ride)` |
| `order_ride(start_location, end_location, service_type, ride_time=None)` | `CabApp.order_ride(...)` | Booked `Ride` | → `CabRideDetail(ride_index)` |
| `get_ride_history(offset=0, limit=10)` | `CabApp.get_ride_history(offset, limit)` | Pagination dict of rides | Remains in `CabHome` |

---

### CabServiceOptions

Screen displaying available service types for a given journey.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_service_types()` | Reads `CabApp.d_service_config` | `list[str]` service names | Remains in `CabServiceOptions` |
| `view_quotation(service_type)` | `CabApp.get_quotation(start, end, service_type, ride_time)` | Unbooked `Ride` quotation | → `CabQuotationDetail(ride)` |

---

### CabQuotationDetail

Screen displaying a quotation (ride before booking).

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `show_quotation()` | — | Quotation `Ride` | Remains in `CabQuotationDetail` |
| `confirm_order()` | `CabApp.order_ride(start, end, service_type, ride_time)` | Booked `Ride` | → `CabRideDetail(ride_index)` |

---

### CabRideDetail

Detail view for a specific ride, including status checks and ride lifecycle actions.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_ride()` | `CabApp.get_ride(ride_index)` | `Ride` details | Remains in `CabRideDetail` |
| `get_current_ride_status()` | `CabApp.get_current_ride_status()` | Updated `Ride` | Remains in `CabRideDetail` |
| `user_cancel_ride()` | `CabApp.user_cancel_ride()` | `None` | → `CabHome` |
| `end_ride()` | `CabApp.end_ride()` | `None` | → `CabHome` |

---

## Navigation Helpers

- Navigation transitions are handled in `StatefulCabApp.handle_state_transition`
  based on the completed backend tool name.
- Ride-to-detail navigation resolves the ride index by matching `ride_id`
  against `CabApp.ride_history`.
- After ride cancellation or completion, the app always returns to `CabHome`.
- `go_back()` appears automatically when navigation history exists and pops
  to the previous state.
