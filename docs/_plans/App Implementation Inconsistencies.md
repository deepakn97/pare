# App Implementation Inconsistencies

This document catalogs inconsistencies across the stateful app implementations in `pas/apps/`. These should be addressed to establish a consistent pattern for all apps.

## 1. State Transition Dispatch Patterns

Different apps use different patterns for routing function names to state transitions:

### Pattern A: Match Statement (contacts, reminder)

```python
# contacts/app.py
match function_name:
    case "get_contact":
        self._handle_get_contact(event_args)
    case "edit_contact":
        self._handle_edit_contact(event_args)
```

### Pattern B: State-First isinstance Checks (email, calendar, shopping)

```python
# email/app.py
if isinstance(current_state, MailboxView):
    self._handle_mailbox_transition(current_state, function_name, args, event)
    return
if isinstance(current_state, EmailDetail):
    self._handle_detail_transition(function_name, event)
    return
```

### Pattern C: Dispatch Method with if/elif Chains (apartment, cab)

```python
# cab/app.py
def _dispatch(self, fname: str, event: CompletedEvent, args: dict[str, Any]) -> None:
    if fname == "list_rides":
        self._handle_list_rides(args)
    elif fname == "get_quotation":
        self._handle_get_quotation(event)
```

### Pattern D: Dynamic Method Lookup (note)

```python
# note/app.py
def _apply_transition(self, func: str, args: dict[str, object], result: str | None) -> None:
    handler = getattr(self, f"_transition_{func}", None)
    if callable(handler):
        handler(args, result)
```

### Pattern E: Simple Inline (messaging)

```python
# messaging/app.py
if isinstance(current_state, ConversationList) and function_name in {"open_conversation", "read_conversation"}:
    args = event.action.resolved_args or event.action.args
    conversation_id = args.get("conversation_id")
    if conversation_id:
        self.set_current_state(ConversationOpened(conversation_id))
```

---

## 2. Event Args Extraction

Apps extract action arguments differently:

| App | Pattern |
|-----|---------|
| email, calendar, shopping | `action.resolved_args or action.args` |
| apartment, cab | `action.args or {}` |
| contacts | `getattr(action, "args", {})` with `cast("dict[str, Any]", ...)` |
| reminder | `cast("dict[str, Any]", action.args)` |
| note | `getattr(event.action, "args", {})` |
| messaging | `event.action.resolved_args or event.action.args` |

**Question**: Should we always prefer `resolved_args` over `args`? What's the semantic difference?

---

## 3. Class Definition Style

### Regular Class (most apps)

```python
class StatefulContactsApp(StatefulApp, ContactsApp):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.load_root_state()
```

### Dataclass (note)

```python
@dataclass
class StatefulNoteApp(StatefulApp):
    name: str | None = None
    folders: dict[str, NoteFolder] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.name or "note")
        self.load_root_state()
```

### Custom Signature (shopping)

```python
class StatefulShoppingApp(StatefulApp, ShoppingApp):
    def __init__(self, name: str = "shopping", **kwargs: object) -> None:
        StatefulApp.__init__(self, name)
        ShoppingApp.__init__(self, **kwargs)
        self.load_root_state()
```

---

## 4. Metadata/Return Value Access

### With Null Check (email, calendar)

```python
metadata_value = event.metadata.return_value if event.metadata else None
```

### Direct Access (note)

```python
result = event.metadata.return_value  # No null check - potential AttributeError
```

---

## 5. Back Navigation Handling

### Standard (most apps)

Use inherited `StatefulApp.go_back()` method or `load_root_state()`:

```python
if self.navigation_stack:
    self.go_back()
else:
    self.load_root_state()
```

### Override as User Tool (apartment)

```python
@user_tool()
def go_back(self) -> str:
    """Navigate back to the home screen."""
    return "go_back"
```

This breaks the expected behavior since it returns a string instead of actually navigating.

---

## 6. Bugs in Note App

### Incomplete Statement (line 101)

```python
if isinstance(folder_name, str):
    try:
        folder_name = NotesFolderName(folder_name)
    except ValueError:
        NotesFolderName.  # <-- Incomplete, syntax error
```

### Missing Field in Note Dataclass

The `Note` dataclass references `folder` attribute in multiple places but doesn't define it as a field:

```python
@dataclass
class Note:
    note_id: str
    title: str
    content: str
    pinned: bool = False
    attachments: dict[str, bytes] | None = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())
    # folder: str  <-- Missing!
```

But used in:
- `create_note()`: `Note(nid, "", "", folder)` - passing 4 positional args
- `move_note()`: `note.folder = new_folder`
- `get_state()`: `"folder": n.folder`

---

## 7. Handler Method Return Patterns

### Return Bool to Signal Handled (reminder)

```python
def _handle_backend_ops(self, fname: str, args: dict[str, Any]) -> bool:
    match fname:
        case "add_reminder":
            self.set_current_state(ReminderList())
            return True
    return False

# Usage:
if self._handle_backend_ops(function_name, event_args):
    return
if self._handle_list_ops(function_name, event_args):
    return
```

### Return None / Use Early Return (email, calendar)

```python
def _handle_mailbox_transition(self, ...) -> None:
    if function_name in {"open_email_by_id", "open_email_by_index"}:
        ...
        return
    if function_name == "switch_folder":
        ...
        return
```

---

## Recommendations

1. **Pick one dispatch pattern** - suggest Pattern B (state-first isinstance) for complex apps, Pattern A (match) for simpler apps
2. **Standardize args extraction** - always use `action.resolved_args or action.args`
3. **Standardize class definition** - use regular classes, not dataclasses for apps
4. **Always null-check metadata** - `event.metadata.return_value if event.metadata else None`
5. **Fix note app bugs** before merging
6. **Document the chosen patterns** in CLAUDE.md or a developer guide
