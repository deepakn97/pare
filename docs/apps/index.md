# PAS App APIs

Use these pages to explore the current user-facing tool surface for each PAS stateful app. Every document lists all `@user_tool` methods, the Meta-ARE calls they wrap, return values, and navigation effects.

- Need to create another app surface? Follow the [Adding a Stateful App](./adding_stateful_app.md) guide.

- [Stateful Contacts App](./contacts.md)
- [Stateful Messaging App](./messaging.md)
- [Stateful Email App](./email.md)
- [Stateful Calendar App](./calendar.md)
- [Stateful Cab App](./cab.md)
- [Stateful Apartment App](./apartment.md)
- [Stateful Reminder App](./reminder.md)
- [Stateful Shopping App](./shopping.md)
- [Stateful Note App](./notes.md)
- [Stateful Food Delivery App](./food_delivery.md)


## Navigation Framework Recap
- Every stateful app inherits from `pas.apps.core.StatefulApp`, which binds a navigation state (`AppState`) before surfacing its tools.
- `AppState.get_available_actions()` inspects the bound instance for `@user_tool`s so only the active screen's tools appear.
- `go_back()` is automatically available when the navigation stack contains history and removes the topmost state while returning a short confirmation string.
