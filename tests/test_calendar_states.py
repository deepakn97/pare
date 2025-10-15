"""Behavioural expectations for the forthcoming StatefulCalendarApp."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest

from are.simulation.apps.calendar import DATETIME_FORMAT
from are.simulation.types import Action, CompletedEvent, EventMetadata, EventType

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.calendar.states import AgendaView, EditDraft, EditEvent, EventDetail


def make_completed_event(
    app: StatefulCalendarApp,
    owner: object,
    function_name: str,
    args: dict | None = None,
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

    app = StatefulCalendarApp(name="calendar")
    target_start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    app.time_manager.reset(start_time=target_start.timestamp())
    start_str, end_str = app._default_day_range()
    app.set_current_state(AgendaView(start_datetime=start_str, end_datetime=end_str))
    app.navigation_stack = []

    base_start = datetime.strptime(start_str, DATETIME_FORMAT)
    base_start = base_start.replace(tzinfo=timezone.utc)

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

    setattr(app, "_work_event_id", work_event_id)
    setattr(app, "_personal_event_id", personal_event_id)

    yield app


class TestInitialState:
    """Expectations immediately after app construction."""

    def test_app_initialises_with_agenda_view(self, calendar_app: StatefulCalendarApp) -> None:
        assert isinstance(calendar_app.current_state, AgendaView)
        assert calendar_app.current_state.app is calendar_app
        assert calendar_app.navigation_stack == []
        assert calendar_app.current_state.start_datetime <= calendar_app.current_state.end_datetime


class TestStateTransitions:
    """Navigation transitions derived from completed events."""

    def test_open_event_transitions_to_detail(self, calendar_app: StatefulCalendarApp) -> None:
        agenda_state = calendar_app.current_state
        event_id = getattr(calendar_app, "_work_event_id")
        event = calendar_app.get_calendar_event(event_id)

        completed = make_completed_event(
            calendar_app,
            agenda_state,
            "open_event_by_id",
            {"event_id": event_id},
            return_value=event,
        )
        calendar_app.handle_state_transition(completed)

        assert isinstance(calendar_app.current_state, EventDetail)
        assert calendar_app.current_state.event_id == event_id
        assert isinstance(calendar_app.navigation_stack[-1], AgendaView)

    def test_go_back_restores_previous_state(self, calendar_app: StatefulCalendarApp) -> None:
        agenda_state = calendar_app.current_state
        event_id = getattr(calendar_app, "_work_event_id")
        event = calendar_app.get_calendar_event(event_id)
        calendar_app.handle_state_transition(
            make_completed_event(
                calendar_app,
                agenda_state,
                "open_event_by_id",
                {"event_id": event_id},
                return_value=event,
            )
        )

        assert isinstance(calendar_app.current_state, EventDetail)
        result = calendar_app.go_back()

        assert "AgendaView" in result
        assert isinstance(calendar_app.current_state, AgendaView)

    def test_start_create_event_enters_edit_state(
        self, calendar_app: StatefulCalendarApp
    ) -> None:
        agenda_state = calendar_app.current_state
        calendar_app.handle_state_transition(
            make_completed_event(
                calendar_app,
                agenda_state,
                "start_create_event",
                return_value="draft_started",
            )
        )

        assert isinstance(calendar_app.current_state, EditEvent)
        assert isinstance(calendar_app.current_state.draft, EditDraft)

    def test_filter_by_tag_pushes_new_agenda_state(
        self, calendar_app: StatefulCalendarApp
    ) -> None:
        agenda_state = calendar_app.current_state
        results = calendar_app.get_calendar_events_by_tag("work")
        calendar_app.handle_state_transition(
            make_completed_event(
                calendar_app,
                agenda_state,
                "filter_by_tag",
                {"tag": "work"},
                return_value=results,
            )
        )

        assert isinstance(calendar_app.current_state, AgendaView)
        assert calendar_app.current_state.tag_filter == "work"
        assert isinstance(calendar_app.navigation_stack[-1], AgendaView)
        assert calendar_app.navigation_stack[-1].tag_filter is None


class TestCreateAndEditFlows:
    """Compose/edit flows for calendar events."""

    def test_create_event_flow_returns_to_agenda(
        self, calendar_app: StatefulCalendarApp
    ) -> None:
        agenda_state = calendar_app.current_state
        calendar_app.handle_state_transition(
            make_completed_event(
                calendar_app,
                agenda_state,
                "start_create_event",
                return_value="draft_started",
            )
        )

        edit_state = calendar_app.current_state
        assert isinstance(edit_state, EditEvent)

        edit_state.set_title("Project Kickoff")
        edit_state.set_time_range(
            start_datetime="2024-01-03 11:00:00",
            end_datetime="2024-01-03 12:00:00",
        )
        edit_state.set_attendees(["Alice", "Shan"])
        edit_state.set_location("HQ Room 1")

        new_event_id = edit_state.save()
        calendar_app.handle_state_transition(
            make_completed_event(
                calendar_app,
                edit_state,
                "save",
                return_value=new_event_id,
            )
        )

        assert isinstance(calendar_app.current_state, AgendaView)
        assert new_event_id in calendar_app.events

    def test_edit_event_flow_updates_detail(self, calendar_app: StatefulCalendarApp) -> None:
        agenda_state = calendar_app.current_state
        event_id = getattr(calendar_app, "_work_event_id")
        event = calendar_app.get_calendar_event(event_id)
        calendar_app.handle_state_transition(
            make_completed_event(
                calendar_app,
                agenda_state,
                "open_event_by_id",
                {"event_id": event_id},
                return_value=event,
            )
        )

        detail_state = calendar_app.current_state
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

        edit_state = calendar_app.current_state
        assert isinstance(edit_state, EditEvent)
        edit_state.set_description("Weekly sync with updates")
        edit_state.add_attendee("Carol")
        edit_state.remove_attendee("Bob")

        saved_event_id = edit_state.save()
        calendar_app.handle_state_transition(
            make_completed_event(
                calendar_app,
                edit_state,
                "save",
                return_value=saved_event_id,
            )
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
        agenda_state = calendar_app.current_state
        result = agenda_state.add_calendar_event_by_attendee(
            who_add="Eve",
            title="Planning Session",
        )

        assert result in calendar_app.events
        created = calendar_app.events[result]
        assert "Eve" in created.attendees
        assert created.description is not None
        assert "Eve" in created.description

    def test_read_today_calendar_events(self, calendar_app: StatefulCalendarApp) -> None:
        agenda_state = calendar_app.current_state
        today = agenda_state.read_today_calendar_events()

        assert isinstance(today, dict)
        events = today.get("events", [])  # type: ignore[arg-type]
        event_ids = {event.event_id for event in events}
        work_event_id = getattr(calendar_app, "_work_event_id")
        assert work_event_id in event_ids

    def test_get_all_tags_tool(self, calendar_app: StatefulCalendarApp) -> None:
        agenda_state = calendar_app.current_state
        tags = agenda_state.get_all_tags()

        assert set(tags) >= {"work", "personal"}

    def test_get_events_by_tag_tool(self, calendar_app: StatefulCalendarApp) -> None:
        agenda_state = calendar_app.current_state
        events = agenda_state.get_calendar_events_by_tag("work")

        work_event_id = getattr(calendar_app, "_work_event_id")
        assert any(event.event_id == work_event_id for event in events)


class TestToolFiltering:
    """Ensure state-specific user tools surface correctly."""

    def test_agenda_view_tools(self, calendar_app: StatefulCalendarApp) -> None:
        tools = calendar_app.get_user_tools()
        names = {tool.name for tool in tools}
        assert any("list_events" in name for name in names)
        assert any("open_event_by_id" in name for name in names)
        assert any("add_calendar_event_by_attendee" in name for name in names)
        assert any("read_today_calendar_events" in name for name in names)
        assert not any("save" in name for name in names)

    def test_edit_event_tools(self, calendar_app: StatefulCalendarApp) -> None:
        agenda_state = calendar_app.current_state
        calendar_app.handle_state_transition(
            make_completed_event(
                calendar_app,
                agenda_state,
                "start_create_event",
                return_value="draft_started",
            )
        )

        tools = calendar_app.get_user_tools()
        names = {tool.name for tool in tools}
        assert any("save" in name for name in names)
        assert not any("open_event_by_id" in name for name in names)
        assert any("go_back" in name for name in names)
