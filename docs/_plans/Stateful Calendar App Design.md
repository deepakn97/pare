# Stateful Calendar App Design

## Motivation
- Mirror the email state machine work for the calendar domain so proactive agents navigate realistic calendar flows instead of raw API calls.
- Reuse PAS navigation primitives to gate tool exposure by screen, enabling research on multi-step planning with temporal context.
- Provide a foundation for upcoming calendar + messaging combined tasks in the proactive goal inference project.

## Existing Capabilities
- `are.simulation.apps.calendar.CalendarApp` and `CalendarV2` expose event CRUD, ranged queries, tag filtering, attendee operations, and sandbox-friendly utilities.
- `StatefulApp`/`AppState` (pas.apps.core) already implement navigation stack, late binding, and tool discovery.

## Target Architecture
- New package `pas.apps.calendar` with:
  - `StatefulCalendarApp(StatefulApp, CalendarV2)`: mixes navigation with the Meta ARE backend, initialises default agenda view, performs `handle_state_transition` wiring, and offers helper methods for ID/date resolution.
  - `states.py`: defines navigation states mirroring mobile UI flows (see below).
  - `__init__.py`: exports public symbols for downstream imports/tests.
- Tests in `tests/test_calendar_states.py` assert behaviour prior to implementation.

## Navigation States
### AgendaView
- Represents the main calendar listing for a time window (e.g., today, specific range).
- State data: `start_datetime`, `end_datetime`, optional `tag_filter`, `attendee_filter`.
- User tools:
  - `list_events(offset=0, limit=10)` → delegates to `get_calendar_events_from_to`.
  - `view_by_date(date_str)` → changes window to that day, triggers state transition.
  - `search(query)` → uses `search_events`, optionally narrows by current filters.
  - `filter_by_tag(tag)` / `filter_by_attendee(name)` → produce new `AgendaView` with updated filters.
  - `open_event(event_id/index)` → transitions to `EventDetail`.
  - `start_create_event()` → transitions to `EditEvent` with empty draft.

### EventDetail
- Focused view for a single event.
- State data: `event_id` plus cached `CalendarEvent` for quick follow-up.
- User tools:
  - `refresh()` → re-fetch event details, updates cache.
  - `delete()` / `delete_by_attendee(who)`.
  - `edit_event()` → transitions to `EditEvent` seeded with current event data.
  - `duplicate()` → optional stretch, reuses Edit state.
  - `list_attendees()`.

### EditEvent
- Compose/edit workflow for events (create, update, add attendees).
- Backed by `EditDraft` dataclass storing title, start/end, tag, location, attendees, description, and existing `event_id` if editing.
- User tools:
  - Mutators: `set_title`, `set_time_range`, `set_tag`, `set_description`, `set_location`, `set_attendees`, `add_attendee`, `remove_attendee`.
  - `save()` → updates existing event via `edit_calendar_event` or creates new via `add_calendar_event`, returns new ID, triggers transition back to previous state (detail or agenda) with refreshed data.
  - `discard()` → abandons changes and pops the state.

## State Transitions (`handle_state_transition`)
- Agenda view actions:
  - `open_event_*` ⇒ push EventDetail with resolved event ID, preserve active filters for back navigation.
  - `start_create_event` ⇒ push EditEvent with blank draft.
  - View/filter changes ⇒ instantiate a fresh AgendaView and push previous state onto stack so `go_back` reverses the change.
- Event detail actions:
  - `edit_event` ⇒ push EditEvent seeded from cached event.
  - `delete`/`delete_by_attendee` ⇒ pop back to prior state (usually agenda) to reflect removal.
  - `refresh` stays within state.
- Edit actions:
  - `save` ⇒ if editing existing event, ensure detail state is updated or replaced; if new event, return to AgendaView and optionally auto-open the new detail.
  - `discard` ⇒ pop to previous state without altering backend.

## Testing Plan (`tests/test_calendar_states.py`)
1. **Initialisation**: app starts in `AgendaView` spanning today, stack empty.
2. **Open Event Transition**: completing `open_event_by_id` moves to `EventDetail`, stack keeps previous agenda; go_back returns to original view.
3. **Create Flow**: `start_create_event` → `EditEvent`; saving a new event adds it to backend and returns to agenda; assert new item visible and navigation stack cleaned up.
4. **Edit Flow**: from detail, `edit_event` pushes compose state; after `save`, detail refreshes the edited fields.
5. **Filter Transitions**: applying tag filter produces new AgendaView; go_back removes filter.
6. **Tool Exposure**: each state exposes expected user tools (e.g., `save` only in edit, `delete` only in detail).
7. **Attendee / time validation**: ensure mutator functions update draft and survive `save`.
8. **Edge Cases**: deleting event from detail returns to agenda even when stack has multiple entries.

## Open Questions
- Whether to support multi-day ranges vs single-day view in MVP (tests will assume day-range for simplicity).
- If `save` from `EditEvent` should automatically open the new detail; tests can specify the desired behaviour once implementation decisions are finalised.
- Need to revisit once calendar tasks require recurring events or multi-user calendars.
