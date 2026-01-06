# Fix go_back Double-Pop Bug

## Problem Summary

The `StatefulApp` base class provides a `go_back()` method that:
1. Pops from `navigation_stack`
2. Sets `current_state` to the popped state
3. Is automatically added to user tools when `navigation_stack` is not empty

When apps also handle `"go_back"` in their `handle_state_transition()` method by calling `self.go_back()`, it causes a **double-pop** because:
1. User calls `go_back()` → StatefulApp.go_back() pops stack and updates state
2. Event is logged → `handle_state_transition()` is called
3. `handle_state_transition()` sees `fname == "go_back"` and calls `self.go_back()` again → **second pop**

This results in skipping a navigation state.

---

## Affected Apps

### 1. Cab App - `pas/apps/cab/app.py`

**Location**: Lines 53-54
```python
case "go_back":
    self.go_back()
```

**Fix**: Remove this case entirely.

---

### 2. Apartment App - `pas/apps/apartment/app.py`

**Locations**: Lines 75-76, 85-86, 96-97
```python
if fname == "go_back":
    self.load_root_state()
    return
```

**Issues**:
1. Double-pop bug (same as cab)
2. Wrong behavior: uses `load_root_state()` instead of `go_back()`, which clears navigation history instead of respecting it

**Fix**: Remove all three `if fname == "go_back"` blocks from:
- `_handle_detail_transition()`
- `_handle_search_transition()`
- `_handle_saved_transition()`

---

### 3. Reminder App - `pas/apps/reminder/app.py`

**Locations**:
- Lines 162-163: `if fname in {"delete", "go_back"}: self.go_back()`
- Lines 172-173: `if fname in {"save", "go_back"}: self.go_back()`
- Lines 182-183: `if fname in {"save", "go_back"}: self.go_back()`

**Fix**: Remove `"go_back"` from each set, keeping only the legitimate operations:
```python
# Line 162: Change to
if fname == "delete":
    self.go_back()

# Lines 172, 182: Change to
if fname == "save":
    self.go_back()
```

---

### 4. Note App - `pas/apps/note/app.py`

**Location**: Lines 873-877
```python
# Handle go_back action for all states
if fname == "go_back":
    if self.navigation_stack:
        self.go_back()
    return
```

**Fix**: Remove this entire block.

---

## Apps WITHOUT the Bug (for reference)

These apps correctly handle go_back:

### Contacts App - `pas/apps/contacts/app.py`
- Lines 106-108 and 119-120 call `self.go_back()` for operations like `edit_contact` and `delete_contact`
- Does NOT handle `fname == "go_back"` - correct

### Email App - `pas/apps/email/app.py`
- Lines 44-45 and 81-82 call `self.go_back()` for operations like `delete`, `move`, `send_composed_email`
- Does NOT handle `fname == "go_back"` - correct

### Calendar App - `pas/apps/calendar/app.py`
- Lines 149-150, 161-162, 167-169 call `self.go_back()` for operations like `delete`, `save`, `discard`
- Does NOT handle `fname == "go_back"` - correct

### Messaging App - `pas/apps/messaging/app.py`
- Line 80 has comment: `# go_back transitions are handled automatically by StatefulApp.go_back()`
- Does NOT handle `fname == "go_back"` - correct

### Shopping App - `pas/apps/shopping/app.py`
- No go_back handling at all - correct

---

## Secondary Issue: State-Level go_back() Overrides

Some states define their own `go_back()` method as a user tool. This creates a conflict with `StatefulApp.go_back()`:

### Note States - `pas/apps/note/states.py`
- `NoteList.go_back()` (line 36)
- `NoteDetail.go_back()` (line 130)
- `EditNote.go_back()` (line 268)
- `FolderList.go_back()` (line 301)

### Reminder States - `pas/apps/reminder/states.py`
- `ReminderDetail.go_back()` (line 129)

### Apartment States - `pas/apps/apartment/states.py`
- `ApartmentDetail.go_back()` (line 122)
- `ApartmentSearch.go_back()` (line 203)
- `ApartmentFavorites.go_back()` (line 241)

**Potential Issues**:
1. When `navigation_stack` is non-empty, BOTH the state's `go_back()` AND `StatefulApp.go_back()` might appear in user tools
2. The state's `go_back()` doesn't actually pop the navigation stack - it just returns a value
3. If the user calls the state's `go_back()` instead of `StatefulApp.go_back()`, the navigation won't work

**Recommendation**: Investigate whether these state-level `go_back()` methods are necessary. If not, remove them. If they serve a different purpose, consider renaming them to avoid confusion.

---

## Implementation Checklist

### Phase 1: Fix Double-Pop Bug in Apps

- [x] **Cab App**: Remove `case "go_back": self.go_back()` from `handle_state_transition()` (already removed)
- [ ] **Apartment App**: Remove three `if fname == "go_back"` blocks
- [ ] **Reminder App**: Remove `"go_back"` from the three condition sets
- [ ] **Note App**: Remove the `if fname == "go_back"` block at lines 873-877

### Phase 2: Investigate State-Level go_back() Methods

- [ ] Analyze why Note states have their own `go_back()` methods
- [ ] Analyze why Reminder states have their own `go_back()` methods
- [ ] Analyze why Apartment states have their own `go_back()` methods
- [ ] Determine if these should be removed or renamed
- [ ] Verify no tests depend on these state-level methods

### Phase 3: Testing

- [x] Run existing tests to verify no regressions (Cab: 19 tests passing)
- [ ] Manually test navigation flows for affected apps:
  - [x] Cab: list_rides → view_quotation → go_back → verify correct state (covered by integration tests)
  - [ ] Apartment: view_apartment → go_back → verify returns to home (not clears stack)
  - [ ] Reminder: open_reminder → go_back → verify correct behavior
  - [ ] Note: open → go_back → verify correct behavior

### Phase 4: Documentation

- [ ] Add comment in `StatefulApp.go_back()` explaining that apps should NOT handle `"go_back"` in `handle_state_transition()`
- [ ] Update any existing design docs that might reference this pattern

---

## Why Tests Don't Catch This Bug

The existing tests are structured as **unit tests** that test components in isolation, not the full integration flow. This is why the double-pop bug goes undetected.

### The Real Flow (where bug occurs)

```
1. User calls state.go_back() (user tool)
2. → StatefulApp.go_back() executes (FIRST POP from navigation_stack)
3. → Event is logged via add_to_log()
4. → handle_state_transition() is triggered
5. → handle_state_transition sees fname == "go_back" and calls self.go_back() (SECOND POP)
```

### How Tests Are Written (bug not visible)

| App | Test Location | Test Pattern | Why Bug Not Caught |
|-----|--------------|--------------|-------------------|
| **Cab** | No test exists | N/A | No go_back test at all |
| **Apartment** | `test_go_back_to_home` (line 231) | `handle_state_transition(make_event(..., go_back))` | Calls handler directly with mock - never calls actual `go_back()` first |
| **Reminder** | `test_go_back_from_detail` (line 193) | `_make_event("go_back", return_value="back")` → `handle_state_transition` | Same - mock event directly to handler |
| **Note** | `test_go_back_from_folder_list` (line 229) | `note_app.go_back()` directly | Calls `go_back()` but never triggers `handle_state_transition()` after |
| **Contacts** | No explicit go_back test | N/A | No bug in app anyway |
| **Email** | `test_go_back_returns_to_previous_folder` (line 137) | `email_app.go_back()` directly | Correct - no handler handling needed |
| **Calendar** | `test_go_back_restores_previous_state` (line 142) | `calendar_app.go_back()` directly | Correct - no handler handling needed |
| **Messaging** | `test_go_back_from_conversation_to_list` (line 64) | `messaging_app.go_back()` directly | Correct - no handler handling needed |
| **Shopping** | No go_back test | N/A | No bug in app anyway |

### Test Pattern Issues

1. **Mock events bypass real flow**: Tests create mock `CompletedEvent` objects and pass them directly to `handle_state_transition()`. This skips the actual tool execution that would trigger `StatefulApp.go_back()`.

2. **Direct method calls skip event logging**: Tests that call `app.go_back()` directly don't go through the event logging system that triggers `handle_state_transition()`.

3. **No multi-level navigation tests**: Tests don't set up 3+ level navigation stacks where a double-pop would be observable (e.g., Home → Detail → Edit → go_back should return to Detail, not Home).

### Additional Test File Issues

**Apartment test imports outdated class name** (`tests/apps/test_apartment_states.py` line 27):
```python
from pas.apps.apartment.states import (
    ...
    ApartmentSaved,  # WRONG - should be ApartmentFavorites
)
```
This test file will fail when run due to the class rename.

---

## Test Coverage Improvements Needed

### Phase 5: Fix Existing Test Issues

- [ ] **Apartment Tests**: Update import from `ApartmentSaved` to `ApartmentFavorites`
- [ ] **Apartment Tests**: Update `isinstance` checks to use `ApartmentFavorites`

### Phase 6: Add Integration Tests (Keep Unit Tests Too)

**Testing Strategy**: We need BOTH unit tests AND integration tests:

1. **Unit tests for `handle_state_transition()`** - Test the handler logic in isolation using mock events. These are valuable for testing specific handler branches and edge cases.

2. **Integration tests for full workflow** - Test the complete flow: tool execution → event logging → state transition. These catch bugs like double-pop that unit tests miss.

#### Unit Test Pattern (KEEP THIS)

```python
def test_list_rides_transitions_to_service_options(cab_app):
    """Unit test: verify handler responds correctly to list_rides event."""
    event = _make_event(cab_app, cab_app.list_rides, start_location="A", end_location="B")
    cab_app.handle_state_transition(event)

    assert isinstance(cab_app.current_state, CabServiceOptions)
```

This pattern is valuable for:
- Testing specific handler branches
- Testing edge cases in handler logic
- Fast, isolated tests

#### Integration Test Pattern (ADD THIS)

**CRITICAL**: Integration tests must use `StateAwareEnvironmentWrapper` with the app registered.
When you call tools on states, events are automatically logged and state transitions happen via
`@pas_event_registered`. Do NOT create mock events or call `handle_state_transition()` directly.

This pattern catches:
- Double-pop bugs (tool execution + handler both modifying state)
- Event logging issues
- Real-world navigation flows

#### Example: Proper Integration Test for go_back

```python
@pytest.fixture
def env_with_app() -> StateAwareEnvironmentWrapper:
    """Create environment with app registered and opened."""
    env = StateAwareEnvironmentWrapper()
    system_app = HomeScreenSystemApp(name="HomeScreen")
    aui_app = PASAgentUserInterface()
    app = StatefulAppClass(name="app_name")
    env.register_apps([system_app, aui_app, app])
    env._open_app("app_name")
    return env


def test_go_back_integration(env_with_app):
    """Integration test: verify full flow doesn't double-pop."""
    env = env_with_app
    app = env.get_app_with_class(StatefulAppClass)

    # Navigate to create a 3-level stack: Home → Options → Detail → Edit
    # Just call tools on states - state transitions happen automatically!
    _home_state(app).list_items("query")      # → Options
    _options_state(app).view_item("123")      # → Detail
    _detail_state(app).edit_item()            # → Edit

    assert len(app.navigation_stack) == 3
    assert isinstance(app.current_state, EditState)

    # go_back should return to Detail (one level back), NOT Options (two levels back)
    # The @pas_event_registered decorator handles event logging automatically
    app.go_back()

    assert isinstance(app.current_state, DetailState)
    assert len(app.navigation_stack) == 2

    # Go back again → Options
    app.go_back()

    assert isinstance(app.current_state, OptionsState)
    assert len(app.navigation_stack) == 1
```

#### Why This Works

The `@pas_event_registered` decorator on state tools automatically:
1. Creates a `CompletedEvent` with result in `event.metadata.return_value`
2. Calls `app.add_event()` which triggers `env.add_to_log()`
3. `env.add_to_log()` calls `app.handle_state_transition(event)`

**Common mistake**: Do NOT manually call `env.add_to_log()` after tool execution - this causes double processing.

#### Apps Requiring Test Updates

All apps should have BOTH unit tests (for handler logic) AND integration tests (for full flow):

- [x] **Cab App**: Unit tests + integration tests completed (see `tests/apps/test_cab_states.py`)
- [ ] **Apartment App**: Keep `test_go_back_to_home` unit test, add integration test
- [ ] **Reminder App**: Keep `test_go_back_from_detail` unit test, add integration test
- [ ] **Note App**: Keep `test_go_back_from_folder_list` unit test, add integration test
- [ ] **Contacts App**: Keep unit tests, add go_back integration tests
- [ ] **Email App**: Keep unit tests, verify integration coverage
- [ ] **Calendar App**: Keep unit tests, verify integration coverage
- [ ] **Messaging App**: Keep unit tests, verify integration coverage
- [ ] **Shopping App**: Add both unit tests and integration tests

### Phase 7: Establish Testing Standards

- [x] Document both test patterns in a testing guide:
  - Unit test pattern: Testing `handle_state_transition()` with mock events
  - Integration test pattern: Testing full tool execution → event → transition flow
  - (Documented in `.claude/commands/plan-state-tests.md` skill)
- [ ] Add a shared test utility for simulating agent tool execution with event logging
- [ ] Review all existing navigation tests across all apps for coverage of both patterns

---

## Risk Assessment

**Low Risk**: The changes are straightforward removals of redundant code. The correct behavior is already implemented in `StatefulApp.go_back()`.

**Testing Coverage**: Current tests will continue to pass because they don't test the full flow. After fixing the bug, we should add proper integration tests.

**Potential Edge Case**: If any app was relying on the double-pop behavior (unlikely), it would break. However, double-pop is always a bug, so this is acceptable.
