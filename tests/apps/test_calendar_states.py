"""Behavioural expectations for the forthcoming StatefulCalendarApp."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest
from are.simulation.apps.calendar import DATETIME_FORMAT, CalendarEvent
from are.simulation.types import Action, CompletedEvent, EventMetadata, EventType

from pare.apps.calendar.app import StatefulCalendarApp
from pare.apps.calendar.states import AgendaView, EditDraft, EditEvent, EventDetail


class SampledCalendarApp(StatefulCalendarApp):
    """Stateful calendar app with typed sample event ids for tests."""

    _work_event_id: str
    _personal_event_id: str


def _agenda(app: StatefulCalendarApp) -> AgendaView:
    state = app.current_state
    assert isinstance(state, AgendaView)
    return state


def _detail(app: StatefulCalendarApp) -> EventDetail:
    state = app.current_state
    assert isinstance(state, EventDetail)
    return state


def _edit(app: StatefulCalendarApp) -> EditEvent:
    state = app.current_state
    assert isinstance(state, EditEvent)
    return state


def _work_event(app: StatefulCalendarApp) -> str:
    assert isinstance(app, SampledCalendarApp)
    return app._work_event_id


def _personal_event(app: StatefulCalendarApp) -> str:
    assert isinstance(app, SampledCalendarApp)
    return app._personal_event_id


if TYPE_CHECKING:
    from collections.abc import Generator


def make_completed_event(
    app: StatefulCalendarApp,
    owner: object,
    function_name: str,
    args: dict[str, object] | None = None,
    *,
    return_value: object | None = None,
) -> CompletedEvent:
    """Fabricate a CompletedEvent mirroring a successful tool invocation."""
    args = args or {}
    function = getattr(owner, function_name)
    action = Action(function=function, args=args, resolved_args=args, app=app)
    metadata = EventMetadata(return_value=return_value, completed=True)
    return CompletedEvent(event_type=EventType.USER, action=action, metadata=metadata)


@pytest.fixture
def calendar_app() -> Generator[StatefulCalendarApp, None, None]:
    """Provide a calendar app pre-populated with sample events."""
    app = SampledCalendarApp(name="calendar")
    target_start = datetime(2024, 1, 1, tzinfo=UTC)
    app.time_manager.reset(start_time=target_start.timestamp())
    start_str, end_str = app._default_day_range()
    app.set_current_state(AgendaView(start_datetime=start_str, end_datetime=end_str))
    app.navigation_stack = []

    base_start = datetime.strptime(start_str, DATETIME_FORMAT)
    base_start = base_start.replace(tzinfo=UTC)

    def timestamp(day_offset: int, hour: int) -> str:
        dt = base_start + timedelta(days=day_offset, hours=hour)
        return dt.strftime(DATETIME_FORMAT)

    work_event_id = app.add_calendar_event(
        title="Team Sync",
        start_datetime=timestamp(0, 9),
        end_datetime=timestamp(0, 10),
        tag="work",
        description="Weekly stand-up",
        location="Zoom",
        attendees=["Alice", "Bob"],
    )
    personal_event_id = app.add_calendar_event(
        title="Dentist Appointment",
        start_datetime=timestamp(1, 14),
        end_datetime=timestamp(1, 15),
        tag="personal",
        description="Routine check-up",
        location="Downtown Clinic",
        attendees=["Shan"],
    )

    app._work_event_id = work_event_id
    app._personal_event_id = personal_event_id

    yield app


class TestInitialState:
    """Expectations immediately after app construction."""

    def test_app_initialises_with_agenda_view(self, calendar_app: StatefulCalendarApp) -> None:
        """Ensure the app starts with an agenda view and empty history."""
        assert isinstance(calendar_app.current_state, AgendaView)
        assert calendar_app.current_state.app is calendar_app
        assert calendar_app.navigation_stack == []
        assert calendar_app.current_state.start_datetime <= calendar_app.current_state.end_datetime


class TestStateTransitions:
    """Navigation transitions derived from completed events."""

    def test_open_event_transitions_to_detail(self, calendar_app: StatefulCalendarApp) -> None:
        """Opening an event should push the detail state onto the stack."""
        agenda_state = _agenda(calendar_app)
        event_id = _work_event(calendar_app)
        event = calendar_app.get_calendar_event(event_id)

        completed = make_completed_event(
            calendar_app, agenda_state, "open_event_by_id", {"event_id": event_id}, return_value=event
        )
        calendar_app.handle_state_transition(completed)

        assert isinstance(calendar_app.current_state, EventDetail)
        assert calendar_app.current_state.event_id == event_id
        assert isinstance(calendar_app.navigation_stack[-1], AgendaView)

    def test_go_back_restores_previous_state(self, calendar_app: StatefulCalendarApp) -> None:
        """`go_back` should return from detail to the prior agenda state."""
        agenda_state = _agenda(calendar_app)
        event_id = _work_event(calendar_app)
        event = calendar_app.get_calendar_event(event_id)
        calendar_app.handle_state_transition(
            make_completed_event(
                calendar_app, agenda_state, "open_event_by_id", {"event_id": event_id}, return_value=event
            )
        )

        assert isinstance(calendar_app.current_state, EventDetail)
        result = calendar_app.go_back()

        assert "AgendaView" in result
        assert isinstance(calendar_app.current_state, AgendaView)

    def test_start_create_event_enters_edit_state(self, calendar_app: StatefulCalendarApp) -> None:
        """Starting a create flow should navigate into the edit state."""
        agenda_state = _agenda(calendar_app)
        calendar_app.handle_state_transition(
            make_completed_event(calendar_app, agenda_state, "start_create_event", return_value="draft_started")
        )

        assert isinstance(calendar_app.current_state, EditEvent)
        assert isinstance(calendar_app.current_state.draft, EditDraft)

    def test_filter_by_tag_pushes_new_agenda_state(self, calendar_app: StatefulCalendarApp) -> None:
        """Filtering by tag should create a new agenda state preserving history."""
        agenda_state = _agenda(calendar_app)
        results = calendar_app.get_calendar_events_by_tag("work")
        calendar_app.handle_state_transition(
            make_completed_event(calendar_app, agenda_state, "filter_by_tag", {"tag": "work"}, return_value=results)
        )

        assert isinstance(calendar_app.current_state, AgendaView)
        assert calendar_app.current_state.tag_filter == "work"
        assert isinstance(calendar_app.navigation_stack[-1], AgendaView)
        assert calendar_app.navigation_stack[-1].tag_filter is None


class TestCreateAndEditFlows:
    """Compose/edit flows for calendar events."""

    def test_create_event_flow_returns_to_agenda(self, calendar_app: StatefulCalendarApp) -> None:
        """Saving a new event should navigate back to the agenda view."""
        agenda_state = _agenda(calendar_app)
        calendar_app.handle_state_transition(
            make_completed_event(calendar_app, agenda_state, "start_create_event", return_value="draft_started")
        )

        edit_state = _edit(calendar_app)
        edit_state.set_title("Project Kickoff")
        edit_state.set_time_range(start_datetime="2024-01-03 11:00:00", end_datetime="2024-01-03 12:00:00")
        edit_state.set_attendees(["Alice", "Shan"])
        edit_state.set_location("HQ Room 1")

        new_event_id = edit_state.save()
        calendar_app.handle_state_transition(
            make_completed_event(calendar_app, edit_state, "save", return_value=new_event_id)
        )

        assert isinstance(calendar_app.current_state, AgendaView)
        assert new_event_id in calendar_app.events

    def test_edit_event_flow_updates_detail(self, calendar_app: StatefulCalendarApp) -> None:
        """Editing from detail should refresh the detail view with new data."""
        agenda_state = _agenda(calendar_app)
        event_id = _work_event(calendar_app)
        event = calendar_app.get_calendar_event(event_id)
        calendar_app.handle_state_transition(
            make_completed_event(
                calendar_app, agenda_state, "open_event_by_id", {"event_id": event_id}, return_value=event
            )
        )

        detail_state = _detail(calendar_app)
        assert isinstance(detail_state, EventDetail)
        calendar_app.handle_state_transition(
            make_completed_event(
                calendar_app,
                detail_state,
                "edit_event",
                return_value={
                    "draft": {
                        "event_id": event_id,
                        "title": event.title,
                        "start_datetime": "2024-01-01 09:00:00",
                        "end_datetime": "2024-01-01 10:00:00",
                        "tag": event.tag,
                        "description": event.description,
                        "location": event.location,
                        "attendees": list(event.attendees),
                    }
                },
            )
        )

        edit_state = _edit(calendar_app)
        edit_state.set_description("Weekly sync with updates")
        edit_state.add_attendee("Carol")
        edit_state.remove_attendee("Bob")

        saved_event_id = edit_state.save()
        calendar_app.handle_state_transition(
            make_completed_event(calendar_app, edit_state, "save", return_value=saved_event_id)
        )

        assert isinstance(calendar_app.current_state, EventDetail)
        refreshed = calendar_app.current_state.event
        assert refreshed is not None
        assert "updates" in refreshed.description
        assert "Bob" not in refreshed.attendees
        assert "Carol" in refreshed.attendees


class TestAdditionalTools:
    """Coverage for additional public CalendarApp helpers exposed via agenda view."""

    def test_add_event_by_attendee(self, calendar_app: StatefulCalendarApp) -> None:
        """Delegating attendee-based creation should persist the event."""
        agenda_state = _agenda(calendar_app)
        result = agenda_state.add_calendar_event_by_attendee(who_add="Eve", title="Planning Session")

        assert result in calendar_app.events
        created = calendar_app.events[result]
        assert "Eve" in created.attendees
        assert created.description is not None
        assert "Eve" in created.description

    def test_read_today_calendar_events(self, calendar_app: StatefulCalendarApp) -> None:
        """Reading today's events should include seeded sample meetings."""
        agenda_state = _agenda(calendar_app)
        today = agenda_state.read_today_calendar_events()

        assert isinstance(today, dict)
        events = cast("list[CalendarEvent]", today.get("events", []))
        event_ids = {event.event_id for event in events}
        assert _work_event(calendar_app) in event_ids

    def test_get_all_tags_tool(self, calendar_app: StatefulCalendarApp) -> None:
        """`get_all_tags` should expose known tag metadata."""
        agenda_state = _agenda(calendar_app)
        tags = agenda_state.get_all_tags()

        assert set(tags) >= {"work", "personal"}

    def test_get_events_by_tag_tool(self, calendar_app: StatefulCalendarApp) -> None:
        """Filtering by tag should return matching event entries."""
        agenda_state = _agenda(calendar_app)
        events = agenda_state.get_calendar_events_by_tag("work")

        assert any(event.event_id == _work_event(calendar_app) for event in events)


class TestToolFiltering:
    """Ensure state-specific user tools surface correctly."""

    def test_agenda_view_tools(self, calendar_app: StatefulCalendarApp) -> None:
        """Agenda view should expose list/search user tools, not edit operations."""
        tools = calendar_app.get_user_tools()
        names = {tool.name for tool in tools}
        assert any("list_events" in name for name in names)
        assert any("open_event_by_id" in name for name in names)
        assert any("add_calendar_event_by_attendee" in name for name in names)
        assert any("read_today_calendar_events" in name for name in names)
        assert not any("save" in name for name in names)

    def test_edit_event_tools(self, calendar_app: StatefulCalendarApp) -> None:
        """Edit state should expose save/go_back but not agenda-only tools."""
        agenda_state = _agenda(calendar_app)
        calendar_app.handle_state_transition(
            make_completed_event(calendar_app, agenda_state, "start_create_event", return_value="draft_started")
        )

        tools = calendar_app.get_user_tools()
        names = {tool.name for tool in tools}
        assert any("save" in name for name in names)
        assert not any("open_event_by_id" in name for name in names)
        assert any("go_back" in name for name in names)
