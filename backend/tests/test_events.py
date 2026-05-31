"""Tests for calendar event storage + occurrence logic."""

import pytest

from memory.sqlite_store import SqliteStore
from models.event import Event
from models.task import Recurrence


@pytest.fixture
def store(tmp_path):
    return SqliteStore(db_path=str(tmp_path / "events.db"))


def _ev(title="Meeting", date="2026-06-01", start="10:00", **kw):
    return Event(title=title, date=date, start_time=start, **kw)


def test_add_and_get_event(store):
    e = store.add_event(_ev(end_time="11:00", location="Room 2"))
    assert e.id is not None
    fetched = store.get_event(e.id)
    assert fetched.title == "Meeting"
    assert fetched.end_time == "11:00"
    assert fetched.location == "Room 2"


def test_one_off_only_on_its_date(store):
    store.add_event(_ev(date="2026-06-01"))
    assert len(store.get_events_for_date("2026-06-01")) == 1
    assert store.get_events_for_date("2026-06-02") == []


def test_weekly_recurs_on_matching_days(store):
    # NLP Lecture, Tue & Fri. 2026-06-02 is a Tuesday, 06-05 is a Friday.
    store.add_event(_ev(title="NLP Lecture", date="2026-06-02",
                        recurrence=Recurrence.WEEKLY, recurrence_days=["tue", "fri"]))
    assert [e.title for e in store.get_events_for_date("2026-06-02")] == ["NLP Lecture"]
    assert [e.title for e in store.get_events_for_date("2026-06-05")] == ["NLP Lecture"]
    assert store.get_events_for_date("2026-06-03") == []  # Wednesday


def test_events_sorted_by_start_time(store):
    store.add_event(_ev(title="Late", start="15:00"))
    store.add_event(_ev(title="Early", start="09:00"))
    titles = [e.title for e in store.get_events_for_date("2026-06-01")]
    assert titles == ["Early", "Late"]


def test_recurring_does_not_fire_before_anchor(store):
    store.add_event(_ev(title="Class", date="2026-06-08",
                        recurrence=Recurrence.WEEKLY, recurrence_days=["mon"]))
    # 2026-06-01 is a Monday but before the anchor date.
    assert store.get_events_for_date("2026-06-01") == []
    assert [e.title for e in store.get_events_for_date("2026-06-08")] == ["Class"]


def test_get_upcoming_events(store):
    store.add_event(_ev(title="Daily standup", date="2026-06-01", recurrence=Recurrence.DAILY))
    upcoming = store.get_upcoming_events(days=3, start="2026-06-01")
    assert [e.title for e in upcoming] == ["Daily standup"] * 3


def test_delete_event(store):
    e = store.add_event(_ev())
    store.delete_event(e.id)
    assert store.get_event(e.id) is None
