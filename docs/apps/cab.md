# Stateful Cab App

`pas.apps.cab.app.StatefulCabApp` layers PAS navigation on top of the Meta-ARE
`CabApp`. It augments the cab backend with navigation-aware state transitions
while preserving the underlying cab semantics.

The application always begins in the `CabHome` state. Navigation transitions
are triggered **only after backend operations complete** (via
`CompletedEvent`), ensuring deterministic and testable state changes.

---

## Navigation States

---

## CabHome

Initial entry point for all cab-related interactions. From this state, users
can search for available services, request quotations, or directly order a ride.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_rides(start_location, end_location, ride_time=None)` | `CabApp.list_rides(...)` | List of available service options | **On completion**, transitions to `CabServiceOptions(start, end, ride_time)` |
| `get_quotation(start_location, end_location, service_type, ride_time=None)` | `CabApp.get_quotation(...)` | Quotation `Ride` object | **On completion**, transitions to `CabQuotationDetail(ride_obj)` |
| `order_ride(start_location, end_location, service_type, ride_time=None)` | `CabApp.order_ride(...)` | Confirmed `Ride` object | **On completion**, transitions to `CabRideDetail(ride_index)` |
| `get_ride_history(offset=0, limit=10)` | `CabApp.get_ride_history(offset, limit)` | List of past rides | No navigation change |

---

## CabServiceOptions

Intermediate state representing service-type selection for a given route.

This state is entered after route search and allows the user to explore
available service tiers before booking.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_service_types()` | Reads `CabApp.d_service_config` | Sorted list of service types | Remains in `CabServiceOptions` |
| `view_quotation(service_type)` | `CabApp.get_quotation(...)` | Quotation `Ride` object | **On completion**, transitions to `CabQuotationDetail(ride_obj)` |

---

## CabQuotationDetail

Read-only state showing a quotation prior to booking.

The quotation is stored locally in the state and reused when confirming
the order.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `show_quotation()` | Local state access | Quotation `Ride` object | Remains in `CabQuotationDetail` |
| `confirm_order()` | `CabApp.order_ride(...)` using quotation data | Confirmed `Ride` object | **On completion**, transitions to `CabRideDetail(ride_index)` |

---

## CabRideDetail

State representing an active or historical ride. All ride lifecycle actions
are performed from this state.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_current_ride_status()` | `CabApp.get_current_ride_status()` | Ride status object | Remains in `CabRideDetail` |
| `get_ride()` | `CabApp.get_ride(ride_index)` | Full `Ride` object | Remains in `CabRideDetail` |
| `user_cancel_ride()` | `CabApp.user_cancel_ride()` | Status message | **On completion**, resets app to `CabHome` |
| `end_ride()` | `CabApp.end_ride()` | Status message | **On completion**, resets app to `CabHome` |

---

## Navigation Summary

- `CabHome → CabServiceOptions` via `list_rides`
- `CabHome → CabQuotationDetail` via `get_quotation`
- `CabHome → CabRideDetail` via `order_ride`
- `CabServiceOptions → CabQuotationDetail` via `view_quotation`
- `CabQuotationDetail → CabRideDetail` via `confirm_order`
- `CabRideDetail → CabHome` via `user_cancel_ride` or `end_ride`
- Unrecognized or read-only events result in **no navigation change**

---

## Navigation Helpers

- `load_root_state()`
  Resets the application to the root `CabHome` state.

- `set_current_state(state)`
  Pushes a new navigation state instance onto the navigation stack.

- Navigation transitions are **event-driven** and occur only after backend
  operations emit a `CompletedEvent`.

- `disable_events()` is used within state tools to prevent recursive or
  duplicate event emission during backend calls.
