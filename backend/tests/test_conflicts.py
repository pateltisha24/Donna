"""Tests for the conflict-resolution layer (event overlap detection)."""

import pytest

from memory.sqlite_store import SqliteStore
from models.event import Event


@pytest.fixture
def store(tmp_path):
    return SqliteStore(db_path=str(tmp_path / "conflicts.db"))


def _ev(title="Meeting", date="2026-06-05", start="10:00", end="11:00", **kw):
    return Event(title=title, date=date, start_time=start, end_time=end, **kw)


# ---------------------------------------------------------------------------
# find_event_conflicts
# ---------------------------------------------------------------------------

def test_no_conflicts_when_events_are_sequential(store):
    store.add_event(_ev(title="A", start="09:00", end="10:00"))
    store.add_event(_ev(title="B", start="10:00", end="11:00"))
    assert store.find_event_conflicts("2026-06-05") == []


def test_no_conflicts_when_events_on_different_days(store):
    store.add_event(_ev(title="A", date="2026-06-05", start="10:00", end="11:00"))
    store.add_event(_ev(title="B", date="2026-06-06", start="10:00", end="11:00"))
    assert store.find_event_conflicts("2026-06-05") == []


def test_conflict_when_events_overlap(store):
    store.add_event(_ev(title="Standup", start="10:00", end="10:30"))
    store.add_event(_ev(title="1:1 with manager", start="10:15", end="11:00"))
    conflicts = store.find_event_conflicts("2026-06-05")
    assert len(conflicts) == 1
    titles = {conflicts[0]["a"]["title"], conflicts[0]["b"]["title"]}
    assert titles == {"Standup", "1:1 with manager"}


def test_conflict_when_one_event_contains_another(store):
    store.add_event(_ev(title="All-hands", start="09:00", end="12:00"))
    store.add_event(_ev(title="Coffee chat", start="10:00", end="10:30"))
    assert len(store.find_event_conflicts("2026-06-05")) == 1


def test_event_without_end_time_treated_as_60_minutes(store):
    # No end_time → defaults to 60-minute block, so this overlaps 09:30–10:30 window.
    store.add_event(_ev(title="Open-ended", start="09:00", end=None))
    store.add_event(_ev(title="Sync", start="09:30", end="10:30"))
    assert len(store.find_event_conflicts("2026-06-05")) == 1


# ---------------------------------------------------------------------------
# conflicts_for_event
# ---------------------------------------------------------------------------

def test_conflicts_for_event_returns_existing_overlaps(store):
    store.add_event(_ev(title="Standup", start="10:00", end="10:30"))
    proposed = _ev(title="Recruiter call", start="10:15", end="11:00")
    overlaps = store.conflicts_for_event(proposed)
    assert [o.title for o in overlaps] == ["Standup"]


def test_conflicts_for_event_ignores_self(store):
    saved = store.add_event(_ev(title="Standup", start="10:00", end="10:30"))
    # The same event shouldn't conflict with itself.
    assert store.conflicts_for_event(saved) == []
