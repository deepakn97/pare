# Stateful Contacts App Design

## Motivation
- Mirror the messaging app navigation work so proactive agents experience contacts workflows through realistic, screen-gated tools instead of raw API calls.
- Ensure navigation semantics (list -> detail -> edit) stay aligned with the UI the proactive agent observes inside Meta-ARE.
- Provide consistent abstractions across messaging, email, calendar, and contacts so future RL experiments can share evaluation harnesses.

## Existing Capabilities
- Meta-ARE `ContactsApp` already supports list, search, add, edit, and delete actions for contact records.
- `pas.apps.core.StatefulApp` and `AppState` provide navigation stacks, user tool discovery, and late binding used by other stateful apps.
- Messaging and email state implementations demonstrate back-stack handling, edit surfaces, and user tool filtering patterns we can reuse.

## Target Architecture
- Package: `pas.apps.contacts` with:
  - `StatefulContactsApp(StatefulApp, ContactsApp)`: bridges navigation to the Meta-ARE contacts backend and seeds the initial list view.
  - `states.py`: holds navigation state classes described below.
  - `__init__.py`: exports public symbols for consumers and tests.
- Tests: `tests/test_contacts_states.py` to validate navigation flows prior to full implementation.

## Navigation States
### ContactsList
- Initial screen showing the user's contacts and acting as the entry point for all list-level tooling.
- State data: optional search query and pagination cursor so list refreshes recreate the same view.
- User tools:
  - `list_contacts(offset=0, limit=20)` -> wraps `get_contacts` with pagination.
  - `search_contacts(query)` -> transitions to a fresh `ContactsList` state carrying the query.
  - `open_contact(contact_id/index)` -> transitions to `ContactDetail`.
  - `view_self()` -> opens `ContactDetail` for `get_current_user_details`.
  - `create_contact()` -> transitions to `ContactEdit` with an empty draft.

### ContactDetail
- Focused view for a single contact card, responsible for destructive actions and jump points into editing.
- State data: `contact_id` plus cached detail so repeated navigation does not refetch unnecessarily.
- User tools:
  - `refresh()` -> re-fetch current contact.
  - `delete()` -> removes the contact and pops back to the previous state (typically list).
  - `edit_contact()` -> transitions to `ContactEdit` seeded with the cached data.
  - `share_contact()` -> optional stretch hook for cross-app scenarios.

### ContactEdit
- Dedicated compose/edit surface that isolates write actions from other states.
- State data: `ContactDraft` dataclass storing name, phone numbers, emails, addresses, and existing `contact_id` when editing.
- User tools:
  - Mutators for structured fields: `set_name`, `set_phone`, `add_email`, `remove_email`, etc.
  - `save()` -> uses `add_new_contact` or `edit_contact` depending on draft state, then transitions back to `ContactDetail` or `ContactsList` with refreshed data.
  - `cancel()` -> pops the navigation stack without persisting changes.

## State Transitions (`handle_state_transition`)
- Contacts list actions push detail or edit states, preserving list context on the stack so `go_back` returns to the prior result set.
- Detail actions push edit states for modifications or pop back after deletes; refresh stays in place.
- Edit actions save and replace prior states with updated detail instances, or cancel which simply pops to the previous screen.
- `go_back` is only exposed when the navigation stack contains history, mirroring other stateful apps.

## Testing Plan (`tests/test_contacts_states.py`)
1. **Initialisation**: app starts in `ContactsList` without history; verify exposed user tools.
2. **Open Contact Flow**: `open_contact_by_id` pushes `ContactDetail`, preserves list on stack, and `go_back` restores list.
3. **Create Flow**: `create_contact` pushes `ContactEdit`; `save` with a new draft adds a contact through backend and returns to list with entry visible.
4. **Edit Flow**: from detail, `edit_contact` pushes edit state; after `save`, detail refreshes cached fields.
5. **Delete Flow**: executing `delete` removes the record and returns to list state, ensuring stack is cleaned up.
6. **Search Flow**: search transitions produce a new list state with query stored so repeated `refresh` maintains filtered results.
7. **Tool Exposure Checks**: confirm edit actions only appear in `ContactEdit`, destructive actions only in `ContactDetail`, and list navigation only in `ContactsList`.

## Open Questions
- Whether `save()` should auto-open the refreshed `ContactDetail` after creating a contact or return to the list view directly.
- How to model multi-value fields (phones, emails) in the draft: flattened map vs typed collections.
- If cross-app hooks (e.g., share to messaging) should live in detail state or remain future stretch goals.
