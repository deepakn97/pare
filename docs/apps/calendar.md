# Stateful Calendar App

`pas.apps.calendar.app.StatefulCalendarApp` layers PAS navigation on top of the Meta-ARE `CalendarV2`. It opens in an `AgendaView` for the simulated current day and transitions into event detail or edit states when the corresponding tools complete.

## Navigation States

### AgendaView

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_events(offset: int = 0, limit: int = 10)` | `CalendarV2.get_calendar_events_from_to(start_datetime, end_datetime, offset=offset, limit=limit)` with local tag/attendee filtering | Dict containing filtered `events`, backend `range`, and count | Remains in `AgendaView` |
| `search_events(query: str)` | `CalendarV2.search_events(query=query)` then pruned to active window and filters | `list[CalendarEvent]` within current window/filter scope | Remains in `AgendaView` |
| `open_event_by_id(event_id: str)` | `CalendarV2.get_calendar_event(event_id=event_id)` | `CalendarEvent` object | Completed event transitions to `EventDetail(event_id)` |
| `open_event_by_index(index: int)` | Reads cached window (`_events_in_window()`), returns `events[index]` | `CalendarEvent` object (raises `IndexError` if out of range) | Completed event transitions to `EventDetail` for selected event |
| `filter_by_tag(tag: str)` | Local filter over cached window | `list[CalendarEvent]` matching tag | Completed event replaces state with new `AgendaView(tag_filter=tag)` |
| `filter_by_attendee(attendee: str)` | Local filter over cached window | `list[CalendarEvent]` containing attendee (case-insensitive) | Completed event replaces state with new `AgendaView(attendee_filter=attendee)` |
| `add_calendar_event_by_attendee(who_add: str, title: str = "Event", start_datetime: Optional[str] = None, end_datetime: Optional[str] = None, tag: Optional[str] = None, description: Optional[str] = None, location: Optional[str] = None, attendees: Optional[list[str]] = None)` | `CalendarV2.add_calendar_event_by_attendee(...)` | Newly created event id | Remains in `AgendaView` |
| `read_today_calendar_events()` | `CalendarV2.read_today_calendar_events()` | Dict of today's events | No navigation change |
| `get_all_tags()` | `CalendarV2.get_all_tags()` | `list[str]` of tags | No navigation change |
| `get_calendar_events_by_tag(tag: str)` | `CalendarV2.get_calendar_events_by_tag(tag=tag)` | `list[CalendarEvent]` | No navigation change |
| `set_day(date: str)` | Local UTC range computation for supplied date | Dict with `start_datetime`/`end_datetime` strings | Completed event replaces state with new `AgendaView` over returned range |
| `start_create_event()` | Emits sentinel string; event metadata seeds draft | String `"draft_started"` | Completed event pushes `EditEvent` with blank draft |

### EventDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `refresh()` | `CalendarV2.get_calendar_event(event_id=current)` | Updated `CalendarEvent` | Remains in `EventDetail` |
| `delete()` | `CalendarV2.delete_calendar_event(event_id=current)` | Backend status string | On success pops back to previous state |
| `delete_by_attendee(who_delete: str)` | `CalendarV2.delete_calendar_event_by_attendee(event_id=current, who_delete=who_delete)` | Backend status string | On success pops back to previous state |
| `list_attendees()` | Uses cached event or refetches | `list[str]` attendees | Remains in `EventDetail` |
| `edit_event()` | Builds draft dict from cached event metadata | Dict with `draft` payload | Completed event transitions to `EditEvent` pre-populated with draft |

### EditEvent

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `set_title(title: str)` | Draft mutation only | Dict `{"title": title}` | Remains in `EditEvent` |
| `set_time_range(start_datetime: str, end_datetime: str)` | Draft mutation only | Dict with updated start/end | Remains in `EditEvent` |
| `set_tag(tag: Optional[str])` | Draft mutation only | Dict `{"tag": tag}` | Remains in `EditEvent` |
| `set_description(description: Optional[str])` | Draft mutation only | Dict `{"description": description}` | Remains in `EditEvent` |
| `set_location(location: Optional[str])` | Draft mutation only | Dict `{"location": location}` | Remains in `EditEvent` |
| `set_attendees(attendees: list[str])` | Draft mutation only | Dict `{"attendees": attendees}` | Remains in `EditEvent` |
| `add_attendee(attendee: str)` | Draft mutation only (append if unique) | Dict `{"attendees": updated_list}` | Remains in `EditEvent` |
| `remove_attendee(attendee: str)` | Draft mutation only (filter) | Dict `{"attendees": updated_list}` | Remains in `EditEvent` |
| `save()` | Existing drafts call `CalendarV2.edit_calendar_event`; new drafts call `CalendarV2.add_calendar_event` | Event id string | Updates prior state (detail/agenda) and pops back |
| `discard()` | Draft reset only | String `"draft_discarded"` | Pops back to previous state |

## Navigation Helpers
- `go_back()` is surfaced automatically when the navigation stack contains history (e.g., from detail back to agenda).
- Agenda filters (`filter_by_tag`, `filter_by_attendee`, `set_day`) replace the current state instance rather than pushing, keeping back navigation aligned with user expectations.
