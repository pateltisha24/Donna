"""Tests for agent nodes: intent routing + task_input recovery (IMPROVEMENTS.md #4/#7)."""

import pytest

from agent import nodes
from models.task import Task, TaskStatus
from models.user_profile import UserProfile


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeSqlite:
    def __init__(self):
        self.added: list[Task] = []
        self.events: list = []

    def get_tasks_for_date(self, date):
        return []

    def get_events_for_date(self, date):
        return []

    def add_task(self, task):
        task.id = len(self.added) + 1
        self.added.append(task)
        return task

    def add_event(self, event):
        event.id = len(self.events) + 1
        self.events.append(event)
        return event

    def conflicts_for_event(self, event, target_date=None):
        return []


class FakeChroma:
    def __init__(self):
        self.updates: list[dict] = []

    def get_profile(self):
        return UserProfile(name="Tisha")

    def update_profile_fields(self, **kw):
        self.updates.append(kw)


@pytest.fixture
def fakes(monkeypatch):
    sqlite, chroma = FakeSqlite(), FakeChroma()
    monkeypatch.setattr(nodes, "get_sqlite", lambda: sqlite)
    monkeypatch.setattr(nodes, "get_chroma", lambda: chroma)
    return sqlite, chroma


def _scripted_llm(monkeypatch, responses):
    """Make nodes.call_llm return successive items from `responses`."""
    calls = {"n": 0}

    def fake(messages, system_prompt, temperature=0.7, on_delta=None):
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(nodes, "call_llm", fake)
    return calls


# ---------------------------------------------------------------------------
# classify_intent
# ---------------------------------------------------------------------------

def test_classify_intent_valid(monkeypatch):
    _scripted_llm(monkeypatch, ["task_input"])
    out = nodes.classify_intent({"user_message": "add a task"})
    assert out["intent"] == "task_input"
    assert out["next_node"] == "task_input"


def test_classify_intent_normalises_whitespace_case(monkeypatch):
    _scripted_llm(monkeypatch, ["  Morning_Briefing \n"])
    out = nodes.classify_intent({"user_message": "brief me"})
    assert out["intent"] == "morning_briefing"


def test_classify_intent_unknown_falls_back(monkeypatch):
    _scripted_llm(monkeypatch, ["banana"])
    out = nodes.classify_intent({"user_message": "???"})
    assert out["intent"] == "general_checkin"


# ---------------------------------------------------------------------------
# task_input: happy path, retry recovery, and surfaced failure
# ---------------------------------------------------------------------------

def test_task_input_saves_valid_tasks(fakes, monkeypatch):
    sqlite, _ = fakes
    _scripted_llm(monkeypatch, [
        'Done! <TASKS_CONFIRMED>[{"title": "Email Bob", "priority": "high"}]</TASKS_CONFIRMED>',
    ])
    out = nodes.task_input({"user_message": "email bob", "history": []})
    assert len(sqlite.added) == 1
    assert sqlite.added[0].title == "Email Bob"
    assert "<TASKS_CONFIRMED>" not in out["response"]


def test_task_input_recovers_via_retry(fakes, monkeypatch):
    sqlite, _ = fakes
    _scripted_llm(monkeypatch, [
        'On it! <TASKS_CONFIRMED>[{title: broken</TASKS_CONFIRMED>',   # malformed
        '<TASKS_CONFIRMED>[{"title": "Recovered"}]</TASKS_CONFIRMED>',  # retry fixes it
    ])
    out = nodes.task_input({"user_message": "x", "history": []})
    assert [t.title for t in sqlite.added] == ["Recovered"]
    assert "couldn't save" not in out["response"].lower()


def test_task_input_surfaces_failure_when_retry_also_fails(fakes, monkeypatch):
    sqlite, _ = fakes
    _scripted_llm(monkeypatch, [
        'Sure <TASKS_CONFIRMED>[{title: broken</TASKS_CONFIRMED>',  # malformed
        'still <TASKS_CONFIRMED>[{nope</TASKS_CONFIRMED>',          # retry still broken
    ])
    out = nodes.task_input({"user_message": "x", "history": []})
    assert sqlite.added == []
    assert "couldn't save" in out["response"].lower()


def test_task_input_no_block_is_passthrough(fakes, monkeypatch):
    sqlite, _ = fakes
    _scripted_llm(monkeypatch, ["What time should I schedule that?"])
    out = nodes.task_input({"user_message": "i need to do laundry", "history": []})
    assert sqlite.added == []
    assert out["response"] == "What time should I schedule that?"


# ---------------------------------------------------------------------------
# profile_update
# ---------------------------------------------------------------------------

def test_might_have_personal_info():
    assert nodes._might_have_personal_info("I'm a designer at Acme")
    assert nodes._might_have_personal_info("my deadline is friday")
    assert not nodes._might_have_personal_info("what's next?")
    assert not nodes._might_have_personal_info("mark that done")


def test_update_memory_skips_when_no_cue(fakes, monkeypatch):
    _, chroma = fakes
    called = {"n": 0}
    monkeypatch.setattr(nodes, "call_llm", lambda *a, **k: called.__setitem__("n", called["n"] + 1) or "{}")
    out = nodes.update_memory({
        "intent": "general_checkin",
        "user_message": "what should I do next?",
        "history": [{"role": "user", "content": "what should I do next?"},
                    {"role": "assistant", "content": "Start with the deck."}],
    })
    assert called["n"] == 0  # no extraction call fired
    assert out["response"] == ""


def test_update_memory_runs_when_cue_present(fakes, monkeypatch):
    _, chroma = fakes
    _scripted_llm(monkeypatch, ['{"occupation": "lawyer"}'])
    nodes.update_memory({
        "intent": "general_checkin",
        "user_message": "by the way I'm a lawyer",
        "history": [{"role": "user", "content": "by the way I'm a lawyer"},
                    {"role": "assistant", "content": "Noted."}],
    })
    assert chroma.updates == [{"occupation": "lawyer"}]


def test_profile_update_applies_filtered_fields(fakes, monkeypatch):
    _, chroma = fakes
    _scripted_llm(monkeypatch, [
        'Noted. <PROFILE_UPDATE>{"occupation": "engineer", "bogus": 1}</PROFILE_UPDATE>',
    ])
    out = nodes.profile_update({"user_message": "i'm an engineer", "history": []})
    assert chroma.updates == [{"occupation": "engineer"}]
    assert "<PROFILE_UPDATE>" not in out["response"]


# ---------------------------------------------------------------------------
# calendar node
# ---------------------------------------------------------------------------

def test_calendar_creates_events(fakes, monkeypatch):
    sqlite, _ = fakes
    monkeypatch.setattr(nodes, "_reschedule_reminders", lambda: None)
    _scripted_llm(monkeypatch, [
        'Booked it. <EVENTS_CONFIRMED>[{"title": "Dentist", "date": "2026-06-02", '
        '"start_time": "15:00", "end_time": "15:30"}]</EVENTS_CONFIRMED>',
    ])
    out = nodes.calendar({"user_message": "dentist tuesday 3pm", "history": []})
    assert [e.title for e in sqlite.events] == ["Dentist"]
    assert sqlite.events[0].start_time == "15:00"
    assert "<EVENTS_CONFIRMED>" not in out["response"]


def test_calendar_recovers_via_retry(fakes, monkeypatch):
    sqlite, _ = fakes
    monkeypatch.setattr(nodes, "_reschedule_reminders", lambda: None)
    _scripted_llm(monkeypatch, [
        'Sure <EVENTS_CONFIRMED>[{title: broken</EVENTS_CONFIRMED>',
        '<EVENTS_CONFIRMED>[{"title": "Standup", "start_time": "09:00", '
        '"recurrence": "weekly", "recurrence_days": ["mon"]}]</EVENTS_CONFIRMED>',
    ])
    out = nodes.calendar({"user_message": "standup mondays 9am", "history": []})
    assert [e.title for e in sqlite.events] == ["Standup"]
    assert "couldn't add" not in out["response"].lower()


def test_calendar_no_block_passthrough(fakes, monkeypatch):
    sqlite, _ = fakes
    _scripted_llm(monkeypatch, ["What time on Tuesday works?"])
    out = nodes.calendar({"user_message": "i have a meeting tuesday", "history": []})
    assert sqlite.events == []
    assert out["response"] == "What time on Tuesday works?"
