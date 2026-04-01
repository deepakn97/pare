# PARE Apps Overview

Use this section to understand what actions are available inside the benchmark. Each app page lists the user-facing `@user_tool` methods, the backend calls they wrap, return values, and navigation effects.

## How To Use This In Practice

Most users come here for one of three reasons:

1. To see what a benchmark scenario can do inside a given app.
2. To filter scenarios by app usage before running experiments.
3. To choose which apps are allowed when generating new scenarios.

### Find scenarios that use a given app

```bash
uv run pare scenarios list --apps StatefulEmailApp
```

### Restrict scenario generation to a set of apps

```bash
uv run pare scenarios generate --apps StatefulEmailApp --apps StatefulCalendarApp
```

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

## Navigation Framework Recap
- Every stateful app inherits from `pare.apps.core.StatefulApp`, which binds a navigation state (`AppState`) before surfacing its tools.
- `AppState.get_available_actions()` inspects the bound instance for `@user_tool`s so only the active screen's tools appear.
- `go_back()` is automatically available when the navigation stack contains history and removes the topmost state while returning a short confirmation string.
