"""Navigation state implementations for the stateful calendar app."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import cast

from are.simulation.apps.calendar import DATETIME_FORMAT, CalendarEvent
from are.simulation.tool_utils import user_tool

from pas.apps.core import AppState


def _utc_datetime_from_str(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, DATETIME_FORMAT).replace(tzinfo=UTC)


def _format_timestamp(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), tz=UTC).strftime(DATETIME_FORMAT)


def _normalise_range(start: datetime, end: datetime) -> tuple[str, str]:
    if end < start:
        raise ValueError("End datetime must be after start datetime")
    return (start.strftime(DATETIME_FORMAT), end.strftime(DATETIME_FORMAT))


@dataclass
class EditDraft:
    """Mutable draft representation for creating or editing events."""

    title: str = "Event"
    start_datetime: str | None = None
    end_datetime: str | None = None
    tag: str | None = None
    description: str | None = None
    location: str | None = None
    attendees: list[str] = field(default_factory=list)
    event_id: str | None = None


class AgendaView(AppState):
    """Calendar listing view for a specific time window and optional filters."""

    def __init__(
        self,
        *,
        start_datetime: str,
        end_datetime: str,
        tag_filter: str | None = None,
        attendee_filter: str | None = None,
    ) -> None:
        """Create an agenda view scoped to a datetime window and optional filters."""
        super().__init__()
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self.tag_filter = tag_filter
        self.attendee_filter = attendee_filter

    def on_enter(self) -> None:
        """No-op hook reserved for future caching."""

    def on_exit(self) -> None:
        """No cleanup required when leaving the agenda view."""

    def _events_in_window(self) -> list[CalendarEvent]:
        result = self.app.get_calendar_events_from_to(self.start_datetime, self.end_datetime)
        events: list[CalendarEvent] = result["events"] if isinstance(result, dict) else []
        if self.tag_filter:
            events = [event for event in events if event.tag == self.tag_filter]
        if self.attendee_filter:
            events = [
                event for event in events if any(att.lower() == self.attendee_filter.lower() for att in event.attendees)
            ]
        return events

    @user_tool()
    def list_events(self, offset: int = 0, limit: int = 10) -> dict[str, object]:
        """List events within the active time window respecting current filters."""
        result = self.app.get_calendar_events_from_to(
            self.start_datetime, self.end_datetime, offset=offset, limit=limit
        )
        events = cast("list[CalendarEvent]", result.get("events", []))
        filtered = events
        if self.tag_filter:
            filtered = [event for event in filtered if event.tag == self.tag_filter]
        if self.attendee_filter:
            filtered = [
                event
                for event in filtered
                if any(att.lower() == self.attendee_filter.lower() for att in event.attendees)
            ]
        return {"events": filtered, "range": result.get("range"), "total": len(filtered)}

    @user_tool()
    def search_events(self, query: str) -> list[CalendarEvent]:
        """Search events, applying local filters and window constraints."""
        matches = self.app.search_events(query=query)
        start = _utc_datetime_from_str(self.start_datetime)
        end = _utc_datetime_from_str(self.end_datetime)
        filtered: list[CalendarEvent] = []
        for event in matches:
            if start and event.end_datetime < start.timestamp():
                continue
            if end and event.start_datetime > end.timestamp():
                continue
            if self.tag_filter and event.tag != self.tag_filter:
                continue
            if self.attendee_filter and not any(att.lower() == self.attendee_filter.lower() for att in event.attendees):
                continue
            filtered.append(event)
        return filtered

    @user_tool()
    def open_event_by_id(self, event_id: str) -> CalendarEvent:
        """Open an event by identifier within the current window."""
        return self.app.get_calendar_event(event_id=event_id)

    @user_tool()
    def open_event_by_index(self, index: int) -> CalendarEvent:
        """Open the n-th event in the current window according to ordering."""
        events = self._events_in_window()
        if index < 0 or index >= len(events):
            raise IndexError("Event index out of range")
        return events[index]

    @user_tool()
    def filter_by_tag(self, tag: str) -> list[CalendarEvent]:
        """Preview events with a specific tag."""
        return [event for event in self._events_in_window() if event.tag == tag]

    @user_tool()
    def filter_by_attendee(self, attendee: str) -> list[CalendarEvent]:
        """Preview events containing a specific attendee."""
        attendee_lower = attendee.lower()
        return [
            event for event in self._events_in_window() if any(att.lower() == attendee_lower for att in event.attendees)
        ]

    @user_tool()
    def add_calendar_event_by_attendee(
        self,
        who_add: str,
        title: str = "Event",
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        tag: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
    ) -> str:
        """Create an event on behalf of a specific attendee."""
        return self.app.add_calendar_event_by_attendee(
            who_add=who_add,
            title=title,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            tag=tag,
            description=description,
            location=location,
            attendees=attendees,
        )

    @user_tool()
    def read_today_calendar_events(self) -> dict[str, object]:
        """Return today's events via the backend helper."""
        return self.app.read_today_calendar_events()

    @user_tool()
    def get_all_tags(self) -> list[str]:
        """List all tags present in the calendar."""
        return self.app.get_all_tags()

    @user_tool()
    def get_calendar_events_by_tag(self, tag: str) -> list[CalendarEvent]:
        """Fetch events associated with a specific tag directly from the backend."""
        return self.app.get_calendar_events_by_tag(tag=tag)

    @user_tool()
    def set_day(self, date: str) -> dict[str, str]:
        """Switch the agenda view to the supplied UTC date string (YYYY-MM-DD)."""
        day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
        start, end = _normalise_range(day, day + timedelta(days=1))
        return {"start_datetime": start, "end_datetime": end}

    @user_tool()
    def start_create_event(self) -> str:
        """Begin a new event creation flow."""
        return "draft_started"


class EventDetail(AppState):
    """Detailed view of a single calendar event."""

    def __init__(self, event_id: str) -> None:
        """Create a detail view bound to the provided event identifier."""
        super().__init__()
        self.event_id = event_id
        self._event: CalendarEvent | None = None

    def on_enter(self) -> None:
        """Fetch the underlying event when entering the detail view."""
        try:
            self._event = self.app.get_calendar_event(self.event_id)
        except Exception:  # pragma: no cover - defensive for missing fixtures
            self._event = None

    def on_exit(self) -> None:
        """No teardown required; keep cached copy for go_back."""

    @property
    def event(self) -> CalendarEvent | None:
        """Return the cached event instance if available."""
        return self._event

    def _ensure_event(self) -> CalendarEvent | None:
        if self._event is None:
            try:
                self._event = self.app.get_calendar_event(self.event_id)
            except Exception:  # pragma: no cover - underlying data removed
                self._event = None
        return self._event

    @user_tool()
    def refresh(self) -> CalendarEvent:
        """Reload event data from the backend."""
        self._event = self.app.get_calendar_event(self.event_id)
        return self._event

    @user_tool()
    def delete(self) -> str:
        """Delete this event from the calendar."""
        return self.app.delete_calendar_event(event_id=self.event_id)

    @user_tool()
    def delete_by_attendee(self, who_delete: str) -> str:
        """Delete the event as a particular attendee."""
        return self.app.delete_calendar_event_by_attendee(event_id=self.event_id, who_delete=who_delete)

    @user_tool()
    def list_attendees(self) -> list[str]:
        """Return the attendee list for this event."""
        event = self._ensure_event()
        return list(event.attendees) if event else []

    @user_tool()
    def edit_event(self) -> dict[str, object]:
        """Prepare a draft payload for editing this event."""
        event = self._ensure_event()
        if event is None:
            return {"draft": None}
        return {
            "draft": {
                "event_id": event.event_id,
                "title": event.title,
                "start_datetime": _format_timestamp(event.start_datetime),
                "end_datetime": _format_timestamp(event.end_datetime),
                "tag": event.tag,
                "description": event.description,
                "location": event.location,
                "attendees": list(event.attendees),
            }
        }


class EditEvent(AppState):
    """Compose/edit state for calendar events."""

    def __init__(self, draft: EditDraft | None = None) -> None:
        """Initialise the edit state, optionally seeding it with an existing draft."""
        super().__init__()
        if draft is None:
            self.draft = EditDraft()
        else:
            self.draft = replace(draft)
            self.draft.attendees = list(draft.attendees)
        original = replace(self.draft)
        original.attendees = list(self.draft.attendees)
        self._original = original

    def on_enter(self) -> None:
        """Invalidate cached tools to pick up latest draft mutations."""
        self._cached_tools = None

    def on_exit(self) -> None:
        """Reset tool cache on exit."""
        self._cached_tools = None

    def _mark_dirty(self) -> None:
        self._cached_tools = None

    @user_tool()
    def set_title(self, title: str) -> dict[str, object]:
        """Update the draft title."""
        self.draft.title = title
        self._mark_dirty()
        return {"title": self.draft.title}

    @user_tool()
    def set_time_range(self, start_datetime: str, end_datetime: str) -> dict[str, object]:
        """Set the draft start/end datetimes."""
        self.draft.start_datetime = start_datetime
        self.draft.end_datetime = end_datetime
        self._mark_dirty()
        return {"start_datetime": self.draft.start_datetime, "end_datetime": self.draft.end_datetime}

    @user_tool()
    def set_tag(self, tag: str | None) -> dict[str, object]:
        """Assign a label/tag to the draft."""
        self.draft.tag = tag
        self._mark_dirty()
        return {"tag": self.draft.tag}

    @user_tool()
    def set_description(self, description: str | None) -> dict[str, object]:
        """Replace the draft description."""
        self.draft.description = description
        return {"description": self.draft.description}

    @user_tool()
    def set_location(self, location: str | None) -> dict[str, object]:
        """Update the draft location."""
        self.draft.location = location
        return {"location": self.draft.location}

    @user_tool()
    def set_attendees(self, attendees: list[str]) -> dict[str, object]:
        """Overwrite the current attendee list."""
        self.draft.attendees = attendees
        self._mark_dirty()
        return {"attendees": list(self.draft.attendees)}

    @user_tool()
    def add_attendee(self, attendee: str) -> dict[str, object]:
        """Append an attendee to the draft if not already present."""
        if attendee not in self.draft.attendees:
            self.draft.attendees.append(attendee)
            self._mark_dirty()
        return {"attendees": list(self.draft.attendees)}

    @user_tool()
    def remove_attendee(self, attendee: str) -> dict[str, object]:
        """Remove an attendee from the draft if included."""
        self.draft.attendees = [a for a in self.draft.attendees if a != attendee]
        self._mark_dirty()
        return {"attendees": list(self.draft.attendees)}

    @user_tool()
    def save(self) -> str:
        """Persist current draft to backend, returning the event id."""
        if self.draft.event_id:
            self.app.edit_calendar_event(
                event_id=self.draft.event_id,
                title=self.draft.title if self.draft.title != self._original.title else None,
                start_datetime=self.draft.start_datetime,
                end_datetime=self.draft.end_datetime,
                tag=self.draft.tag,
                description=self.draft.description,
                location=self.draft.location,
                attendees=self.draft.attendees,
            )
            return self.draft.event_id

        event_id = self.app.add_calendar_event(
            title=self.draft.title,
            start_datetime=self.draft.start_datetime,
            end_datetime=self.draft.end_datetime,
            tag=self.draft.tag,
            description=self.draft.description,
            location=self.draft.location,
            attendees=self.draft.attendees or [],
        )
        self.draft.event_id = event_id
        return event_id

    @user_tool()
    def discard(self) -> str:
        """Discard current draft and stay within compose state."""
        self.draft = EditDraft()
        self._original = replace(self.draft)
        self._mark_dirty()
        return "draft_discarded"
