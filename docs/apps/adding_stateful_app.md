# Adding a New PAS Stateful App

PAS uses `StatefulApp` wrappers to layer deterministic navigation on top of the Meta-ARE mobile apps so that user tools only expose actions that make sense for the current screen. This guide explains, step by step, how to introduce another stateful app into the system.

## Prerequisites

- Familiarity with the Meta-ARE base app you are wrapping (for example `are.simulation.apps.contacts.ContactsApp`).
- Understanding of `StatefulApp` and `AppState` in `pas/apps/core.py`, including how `set_current_state`, `navigation_stack`, and `go_back` behave.
- Awareness of `StateAwareEnvironmentWrapper` (`pas/environment.py`) because the environment is what delivers `CompletedEvent`s to `handle_state_transition`.
- Ability to run and extend the pytest suites under `tests/`.

## Step-by-step workflow

### 1. Choose a canonical name and base class

1. Decide which Meta-ARE app class you are extending.
2. Pick a canonical lowercase name (contacts, messaging, etc.). This name is used everywhere: `StatefulFooApp(name="foo")`, in `APP_NAME_MAP`, and by `HomeScreenSystemApp.open_app`.

### 2. Scaffold the module layout

Create a new package under `pas/apps/<app_name>/` mirroring the existing apps:

```
pas/apps/<app_name>/
    __init__.py
    app.py
    states.py
```

Export your public classes from `__init__.py` to keep imports consistent with `pas/apps/contacts/__init__.py`. For example:

```python
"""Stateful Foo app module exports."""
from pas.apps.foo.app import StatefulFooApp
from pas.apps.foo.states import FooDetail, FooList

__all__ = ["StatefulFooApp", "FooList", "FooDetail"]
```

This ensures other modules can cleanly import your app components with `from pas.apps.foo import StatefulFooApp`.

### 3. Model navigation states

Define every view or screen as a subclass of `AppState` in `states.py`. Each state:

- Implements `on_enter`/`on_exit` hooks (even if they are no-ops for now). These hooks are useful for logging, cleanup, or state initialization when the user navigates between screens.
- Declares user-facing tools with the `@user_tool()` and `@pas_event_registered()` decorators so the environment can capture telemetry. When the tool needs to mutate data, pass `operation_type=OperationType.WRITE`.
- Accesses the underlying Meta-ARE app through `self.app`, casting to your concrete stateful app when you need type checking.

Example skeleton:

```python
from typing import TYPE_CHECKING, cast

from are.simulation.types import OperationType
from pas.apps.core import AppState
from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from pas.apps.foo.app import StatefulFooApp

class FooList(AppState):
    """Initial state showing a list of foo items."""

    def on_enter(self) -> None:
        """Called when entering this state. Use for logging or initialization."""
        pass

    def on_exit(self) -> None:
        """Called when leaving this state. Use for cleanup."""
        pass

    @user_tool()
    @pas_event_registered()
    def list_items(self) -> list[dict[str, object]]:
        """List all foo items (READ operation)."""
        app = cast("StatefulFooApp", self.app)
        return app.get_items()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def create_item(self, payload: dict[str, object]) -> str:
        """Create a new foo item (WRITE operation)."""
        app = cast("StatefulFooApp", self.app)
        return app.create_item(payload=payload)
```

**Important notes:**
- The `TYPE_CHECKING` import ensures type hints don't cause circular import issues at runtime.
- The `cast()` call helps type checkers (mypy, pyright) understand that `self.app` is your specific app type, not just a generic `StatefulApp`.
- The decorator order matters: `@user_tool()` must come **before** `@pas_event_registered()`.

Use helper methods (for example `queue_contact_transition` in `pas/apps/contacts/app.py`) when a tool needs to remember state between Meta-ARE callbacks. This pattern is necessary when the same Meta-ARE API call (like `get_contact`) can be triggered by different user intents (viewing vs. editing), and you need to distinguish which navigation transition should occur.

### 4. Implement the `Stateful<App>` wrapper

In `app.py`, implement a class that mixes `StatefulApp` with the Meta-ARE base class:

```python
from are.simulation.types import CompletedEvent
from are.simulation.apps.foo import FooApp
from pas.apps.core import StatefulApp
from pas.apps.foo.states import FooList, FooDetail

class StatefulFooApp(StatefulApp, FooApp):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.load_root_state()

    def create_root_state(self) -> FooList:
        return FooList()

    def handle_state_transition(self, event: CompletedEvent) -> None:
        ...
```

Key points:

- Always call `self.load_root_state()` after `super().__init__()` so the navigation stack is initialised.
- `create_root_state` must return a brand-new instance every time (do not reuse cached state objects).
- Use helper attributes such as `_pending_transition` if the Meta-ARE API requires a two-step flow (see `pas/apps/contacts/app.py`).

### 5. Wire transitions inside `handle_state_transition`

`StateAwareEnvironmentWrapper.add_to_log` calls `handle_state_transition` for every `CompletedEvent` emitted by your tools. Use this callback to examine `event.function_name()` and `event.action.args` to decide whether to call `set_current_state(...)` or `go_back()`.

**Safe argument extraction pattern:**

```python
from typing import Any, cast

def handle_state_transition(self, event: CompletedEvent) -> None:
    """Update navigation state based on completed operations."""
    function_name = event.function_name()
    if function_name is None:
        return

    # Safely extract event args - event.action may be ConditionCheckAction in other contexts
    event_args: dict[str, Any] = {}
    action = getattr(event, "action", None)
    if action is not None and hasattr(action, "args"):
        event_args = cast("dict[str, Any]", getattr(action, "args", {}))

    # Route to specific transition handlers
    match function_name:
        case "get_item":
            self._handle_get_item(event_args)
        case "delete_item":
            self._handle_delete_item()
        case "list_items":
            self._handle_list_items()
```

**Patterns to follow:**

- Keep transition logic small and state-aware. Each example app breaks the logic into helper methods (`_handle_mailbox_transition`, `_handle_DETAIL_transition`, etc.) to keep `handle_state_transition` readable.
- Use `load_root_state()` if an action should reset the app completely (e.g., after deleting an item from detail view).
- When you switch to a new state, always instantiate the corresponding `AppState` and pass the minimum data it needs (IDs, folders, etc.):
  ```python
  def _handle_get_item(self, event_args: dict[str, Any]) -> None:
      item_id = event_args.get("item_id")
      if item_id is not None:
          self.set_current_state(FooDetail(item_id=item_id))
  ```
- Remember that `go_back()` pops from `navigation_stack`. Prefer `go_back()` over manually rewinding when you just need to undo the latest screen.

### 6. Register the app with runtime surfaces

#### 6.1 Export from the top-level apps module

Add your app to `pas/apps/__init__.py`:

```python
from pas.apps.foo.app import StatefulFooApp

__all__ = [
    # ... existing exports ...
    "StatefulFooApp",
]
```

#### 6.2 Register in `pas/meta_adapter.py`

Make three key updates:

**a) Add to `APP_NAME_MAP`** (around line 33):

```python
APP_NAME_MAP = {
    "ContactsApp": "contacts",
    "CalendarApp": "calendar",
    "EmailClientApp": "email",
    "MessagingApp": "messaging",
    "FooApp": "foo",  # Add your mapping here
    # ...
}
```

**b) Extend `_convert_meta_app`** (around line 136):

```python
from pas.apps.foo.app import StatefulFooApp  # Add import at top

def _convert_meta_app(meta_app: object) -> object:
    if isinstance(meta_app, ContactsApp):
        return _initialise_stateful_app(meta_app, StatefulContactsApp, name="contacts")
    # ... other apps ...
    if isinstance(meta_app, FooApp):  # Add your conversion
        return _initialise_stateful_app(meta_app, StatefulFooApp, name="foo")
    # ... fallback logic ...
```

**c) Add to `ARG_TRANSFORMERS` if needed** (around line 59):

Only necessary if your app's Meta-ARE methods require argument transformation (e.g., renaming parameters, converting formats). Example from messaging:

```python
def _transform_foo_args(kwargs: dict[str, object], app: object) -> dict[str, object]:
    """Transform 'sender' to 'sender_id' for foo app methods."""
    if "sender" in kwargs and "sender_id" not in kwargs:
        sender_name = kwargs.pop("sender")
        # Look up sender_id from name...
        kwargs["sender_id"] = looked_up_id
    return kwargs

ARG_TRANSFORMERS: dict[str, dict[str, t.Callable]] = {
    "messaging": {
        "add_message": _transform_messaging_args,
        "*": _transform_messaging_args,  # Wildcard applies to all functions
    },
    "foo": {  # Add if needed
        "create_item": _transform_foo_args,
    },
}
```

#### 6.3 Update documentation

1. Add to `mkdocs.yml` navigation structure
2. Link from `docs/apps/index.md` so users can discover your new app
3. Create a dedicated `docs/apps/foo.md` documenting the user-facing API

**Note:** No extra work is needed for `HomeScreenSystemApp`: once the environment registers your app, `open_app` automatically lists it.

### 7. Test and document

#### 7.1 Unit tests for state transitions

Add pytest coverage similar to `tests/test_contacts_states.py`, exercising initial state, transitions, and available tools.

**Example test structure:**

```python
"""Tests for the stateful foo app navigation flow."""
from typing import Any
import pytest
from are.simulation.types import Action, CompletedEvent, EventMetadata, EventType

from pas.apps.foo.app import StatefulFooApp
from pas.apps.foo.states import FooList, FooDetail

def _make_event(app: StatefulFooApp, func: callable, **kwargs: Any) -> CompletedEvent:
    """Utility to build a minimal CompletedEvent for state transition tests."""
    action = Action(function=func, args={"self": app, **kwargs}, app=app)
    return CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=EventMetadata(),
        event_time=0,
        event_id="test-event"
    )

@pytest.fixture
def foo_app() -> StatefulFooApp:
    """Create a foo app with test data."""
    app = StatefulFooApp(name="foo")
    # Add test data...
    return app

def test_app_starts_in_list_state(foo_app: StatefulFooApp) -> None:
    """App should boot into FooList with empty navigation stack."""
    assert isinstance(foo_app.current_state, FooList)
    assert foo_app.navigation_stack == []

def test_open_item_transitions_to_detail(foo_app: StatefulFooApp) -> None:
    """Opening an item should push FooDetail state."""
    foo_app.current_state.open_item("item-123")
    event = _make_event(foo_app, foo_app.get_item, item_id="item-123")
    foo_app.handle_state_transition(event)

    assert isinstance(foo_app.current_state, FooDetail)
    assert len(foo_app.navigation_stack) == 1
```

**Note:** Different test files use slightly different helper names (`_make_event`, `make_completed_event`, etc.). Choose a consistent naming convention for your test suite.

#### 7.2 Integration tests

Add integration-style tests if the app has complex transitions involving queued events or environment interactions. See `tests/test_contacts_environment.py` as a template for testing:
- Environment wrapper integration
- Tool availability in different states
- Multi-step workflows

#### 7.3 Documentation

- Create `docs/apps/foo.md` documenting all user-facing tools
- Add comprehensive docstrings to all public methods (tool methods, state classes, app class) so `mkdocstrings` can auto-generate API docs
- Update `mkdocs.yml` to include your new documentation page

## Common pitfalls and best practices

### ❌ Don't: Reuse state instances

```python
# WRONG - creates state once and reuses it
def __init__(self):
    super().__init__()
    self._root = FooList()  # ❌ Cached instance

def create_root_state(self) -> FooList:
    return self._root  # ❌ Returns same instance
```

```python
# CORRECT - creates fresh state each time
def create_root_state(self) -> FooList:
    return FooList()  # ✅ New instance every time
```

**Why?** State instances may accumulate stale data. Fresh instances ensure clean state.

### ❌ Don't: Skip decorator order

```python
# WRONG decorator order
@pas_event_registered()  # ❌ This should be second
@user_tool()
def my_tool(self): ...
```

```python
# CORRECT decorator order
@user_tool()              # ✅ This should be first
@pas_event_registered()
def my_tool(self): ...
```

### ❌ Don't: Forget `load_root_state()` in `__init__`

```python
# WRONG - navigation stack not initialized
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    # ❌ Missing load_root_state()
```

```python
# CORRECT - properly initialized
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.load_root_state()  # ✅ Initialize navigation
```

### ✅ Do: Use TYPE_CHECKING to avoid circular imports

```python
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pas.apps.foo.app import StatefulFooApp  # Only imported for type checking

# In your method:
app = cast("StatefulFooApp", self.app)  # String literal, not actual import
```

### ✅ Do: Safely extract event arguments

Always use defensive programming when extracting event args to handle edge cases:

```python
event_args: dict[str, Any] = {}
action = getattr(event, "action", None)
if action is not None and hasattr(action, "args"):
    event_args = cast("dict[str, Any]", getattr(action, "args", {}))
```

### ✅ Do: Add descriptive docstrings

All `@user_tool()` methods should have clear docstrings explaining:
- What the tool does
- What parameters mean
- What it returns
- Any side effects (state transitions, data mutations)

## Reference checklist

- [ ] Folder created under `pas/apps/<app_name>/` with `__init__.py`, `states.py`, and `app.py`
- [ ] `__init__.py` exports all public classes with proper `__all__` declaration
- [ ] Every state inherits from `AppState`, implements `on_enter`/`on_exit`, and only exposes user tools decorated with `@user_tool()` + `@pas_event_registered()` (in that order)
- [ ] State methods use `TYPE_CHECKING` and `cast()` for proper type hints
- [ ] `Stateful<App>` mixes `StatefulApp` with the Meta-ARE base class, calls `load_root_state()` in `__init__`, and overrides `create_root_state` and `handle_state_transition`
- [ ] `create_root_state` returns a fresh instance every time (not cached)
- [ ] `handle_state_transition` safely extracts event args using defensive getattr pattern
- [ ] Canonical name added to `pas/apps/__init__.py` exports
- [ ] Canonical name added to `pas/meta_adapter.APP_NAME_MAP`
- [ ] App conversion logic added to `pas/meta_adapter._convert_meta_app`
- [ ] If needed, argument transformers added to `pas/meta_adapter.ARG_TRANSFORMERS`
- [ ] Unit tests added covering initial state, state transitions, and tool availability
- [ ] Integration tests added if app has complex multi-step workflows
- [ ] User-facing tools documented in `docs/apps/<app_name>.md`
- [ ] MkDocs navigation (`mkdocs.yml`) and `docs/apps/index.md` updated to reference the new app
