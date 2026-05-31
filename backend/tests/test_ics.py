"""Tests for .ics import/export and event-dict building."""

from agent.calendar_events import build_event, build_events
from agent.ics import export_ics, import_ics
from models.event import Event
from models.task import Recurrence


# ---------------------------------------------------------------------------
# build_event (vision / LLM dicts -> Event)
# ---------------------------------------------------------------------------

def test_build_event_one_off():
    e = build_event({"title": "Call Connor", "start_time": "11:00", "date": "2026-06-01"})
    assert e.title == "Call Connor"
    assert e.recurrence == Recurrence.NONE


def test_build_event_weekly():
    e = build_event({"title": "NLP Lecture", "start_time": "10:00", "end_time": "11:30",
                     "recurrence": "weekly", "recurrence_days": ["TUE", "Fri"]})
    assert e.recurrence == Recurrence.WEEKLY
    assert e.recurrence_days == ["tue", "fri"]
    assert e.end_time == "11:30"


def test_build_event_requires_title_and_time():
    assert build_event({"start_time": "10:00"}) is None
    assert build_event({"title": "x"}) is None


def test_build_event_weekly_without_days_becomes_oneoff():
    e = build_event({"title": "x", "start_time": "10:00", "recurrence": "weekly"})
    assert e.recurrence == Recurrence.NONE


def test_build_events_filters_invalid():
    items = [{"title": "Good", "start_time": "09:00"}, {"nope": 1}, "garbage"]
    assert [e.title for e in build_events(items)] == ["Good"]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export_contains_event_and_alarm():
    e = Event(title="Standup", date="2026-06-01", start_time="09:00", end_time="09:15")
    ics = export_ics([e])
    assert "BEGIN:VCALENDAR" in ics
    assert "SUMMARY:Standup" in ics
    assert "DTSTART:20260601T090000" in ics
    assert "TRIGGER:-PT15M" in ics


def test_export_weekly_has_rrule():
    e = Event(title="Class", date="2026-06-02", start_time="10:00",
              recurrence=Recurrence.WEEKLY, recurrence_days=["tue", "fri"])
    ics = export_ics([e])
    assert "RRULE:FREQ=WEEKLY;BYDAY=TU,FR" in ics


# ---------------------------------------------------------------------------
# Import (round-trips through export)
# ---------------------------------------------------------------------------

def test_import_one_off():
    ics = export_ics([Event(title="Meeting", date="2026-06-01", start_time="14:00", end_time="15:00")])
    events = import_ics(ics)
    assert len(events) == 1
    assert events[0].title == "Meeting"
    assert events[0].start_time == "14:00"
    assert events[0].end_time == "15:00"


def test_import_weekly_rrule():
    ics = export_ics([Event(title="Class", date="2026-06-02", start_time="10:00",
                            recurrence=Recurrence.WEEKLY, recurrence_days=["tue", "fri"])])
    events = import_ics(ics)
    assert events[0].recurrence == Recurrence.WEEKLY
    assert sorted(events[0].recurrence_days) == ["fri", "tue"]


def test_import_garbage_returns_empty():
    assert import_ics("not a calendar") == []
