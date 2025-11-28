# Stateful Cab App

`pas.apps.cab.app.StatefulCabApp` layers PAS navigation on top of the Meta-ARE `CabApp`.
It begins in the `CabHome` state and transitions into service selection, quotation review,
or ride detail screens depending on which user tool completes.

---

## Navigation States

---

## CabHome

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_rides(start_location, end_location, ride_time=None)` | `CabApp.list_rides(...)` | List of ride service options | Completed event transitions to `CabServiceOptions(start, end, ride_time)` |
| `get_quotation(start_location, end_location, service_type, ride_time=None)` | `CabApp.get_quotation(...)` | Quotation object | Completed event transitions to `CabQuotationDetail(ride_obj)` |
| `order_ride(start_location, end_location, service_type, ride_time=None)` | `CabApp.order_ride(...)` | Ride object / ride_id | Completed event transitions to `CabRideDetail(ride_id)` |
| `get_ride_history(offset=0, limit=10)` | `CabApp.get_ride_history(offset, limit)` | List of past rides | No navigation change |

---

## CabServiceOptions

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_service_types()` | Reads `d_service_config` | Sorted list of service types | Remains in `CabServiceOptions` |
| `view_quotation(service_type)` | `CabApp.get_quotation(...)` | Quotation object | Completed event transitions to `CabQuotationDetail(ride_obj)` |

---

## CabQuotationDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `show_quotation()` | Local return of stored `ride_obj` | Quotation object | Remains in `CabQuotationDetail` |
| `confirm_order()` | `CabApp.order_ride(...)` using quotation data | Confirmed ride object | Completed event transitions to `CabRideDetail(ride_id)` |

---

## CabRideDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_current_ride_status()` | `CabApp.get_current_ride_status()` | Status dict | Remains in `CabRideDetail` |
| `get_ride()` | `CabApp.get_ride(ride_id)` | Full ride object | Remains in `CabRideDetail` |
| `user_cancel_ride()` | `CabApp.user_cancel_ride()` | Status string | Completed event resets app to `CabHome` |
| `end_ride()` | `CabApp.end_ride()` | Status string | Completed event resets app to `CabHome` |

---

## Navigation Summary

- `CabHome → CabServiceOptions` via `list_rides`
- `CabHome → CabQuotationDetail` via `get_quotation`
- `CabHome → CabRideDetail` via `order_ride`
- `CabServiceOptions → CabQuotationDetail` via `view_quotation`
- `CabQuotationDetail → CabRideDetail` via `confirm_order`
- `CabRideDetail → CabHome` via `user_cancel_ride` or `end_ride`
- Unrecognized events: no navigation change

---

## Navigation Helpers

- `load_root_state()` resets app to `CabHome`
- `set_current_state(...)` pushes a new state instance
- `go_back()` works when navigation stack is non-empty
