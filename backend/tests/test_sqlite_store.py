"""Tests for SqliteStore task CRUD + app state (IMPROVEMENTS.md #7)."""

import pytest

from memory.sqlite_store import SqliteStore
from models.task import Priority, Recurrence, Task, TaskStatus


@pytest.fixture
def store(tmp_path):
    return SqliteStore(db_path=str(tmp_path / "test.db"))


def _task(title="Test", date="2026-05-30", **kw):
    return Task(title=title, date_assigned=date, **kw)


def test_add_task_assigns_id(store):
    t = store.add_task(_task())
    assert t.id is not None


def test_get_task_roundtrip(store):
    t = store.add_task(_task(title="Roundtrip", priority=Priority.HIGH))
    fetched = store.get_task(t.id)
    assert fetched.title == "Roundtrip"
    assert fetched.priority == Priority.HIGH
    assert fetched.status == TaskStatus.PENDING


def test_get_tasks_for_date_filters(store):
    store.add_task(_task(title="Today", date="2026-05-30"))
    store.add_task(_task(title="Tomorrow", date="2026-05-31"))
    today = store.get_tasks_for_date("2026-05-30")
    assert [t.title for t in today] == ["Today"]


def test_mark_done(store):
    t = store.add_task(_task())
    store.mark_done(t.id)
    assert store.get_task(t.id).status == TaskStatus.DONE


def test_move_task_changes_date_and_status(store):
    t = store.add_task(_task(date="2026-05-30"))
    store.move_task(t.id, "2026-05-31")
    moved = store.get_task(t.id)
    assert moved.date_assigned == "2026-05-31"
    assert moved.status == TaskStatus.MOVED


def test_get_tasks_by_status(store):
    a = store.add_task(_task(title="A"))
    store.add_task(_task(title="B"))
    store.mark_done(a.id)
    done = store.get_tasks_by_status(TaskStatus.DONE)
    assert [t.title for t in done] == ["A"]


def test_delete_task(store):
    t = store.add_task(_task())
    store.delete_task(t.id)
    assert store.get_task(t.id) is None


def test_tags_roundtrip(store):
    t = store.add_task(_task(tags=["work", "urgent"]))
    assert store.get_task(t.id).tags == ["work", "urgent"]


# ---------------------------------------------------------------------------
# App state / onboarding flag
# ---------------------------------------------------------------------------

def test_onboarding_flag_defaults_false(store):
    assert store.is_onboarding_complete() is False


def test_complete_onboarding(store):
    store.complete_onboarding()
    assert store.is_onboarding_complete() is True


def test_state_set_get(store):
    store.set_state("morning_briefing_time", "07:30")
    assert store.get_state("morning_briefing_time") == "07:30"


def test_state_upsert_overwrites(store):
    store.set_state("k", "v1")
    store.set_state("k", "v2")
    assert store.get_state("k") == "v2"


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------

def test_get_history_empty_by_default(store):
    assert store.get_history("default") == []


def test_save_and_get_history(store):
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    store.save_history("default", history)
    assert store.get_history("default") == history


def test_save_history_upserts(store):
    store.save_history("default", [{"role": "user", "content": "1"}])
    store.save_history("default", [{"role": "user", "content": "2"}])
    assert store.get_history("default") == [{"role": "user", "content": "2"}]


def test_append_message(store):
    store.append_message("default", "user", "first")
    store.append_message("default", "assistant", "second")
    assert store.get_history("default") == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]


def test_history_persists_across_store_instances(store):
    store.save_history("default", [{"role": "user", "content": "persisted"}])
    reopened = SqliteStore(db_path=store.db_path)
    assert reopened.get_history("default") == [{"role": "user", "content": "persisted"}]


# ---------------------------------------------------------------------------
# Recurring tasks
# ---------------------------------------------------------------------------

def test_template_not_listed_directly(store):
    # 2026-06-01 is a Monday.
    store.add_task(_task(title="Standup", date="2026-06-01",
                         recurrence=Recurrence.WEEKLY, recurrence_days=["mon"]))
    # On a Tuesday, the weekly-Monday template should not materialise.
    assert store.get_tasks_for_date("2026-06-02") == []


def test_weekly_materialises_on_matching_day(store):
    store.add_task(_task(title="Standup", date="2026-06-01",
                         recurrence=Recurrence.WEEKLY, recurrence_days=["mon"]))
    monday = store.get_tasks_for_date("2026-06-01")
    assert [t.title for t in monday] == ["Standup"]
    assert monday[0].recurrence == Recurrence.NONE  # it's an instance
    assert monday[0].parent_id is not None


def test_daily_materialises_every_day(store):
    store.add_task(_task(title="Journal", date="2026-06-01", recurrence=Recurrence.DAILY))
    assert [t.title for t in store.get_tasks_for_date("2026-06-01")] == ["Journal"]
    assert [t.title for t in store.get_tasks_for_date("2026-06-05")] == ["Journal"]


def test_weekdays_skips_weekend(store):
    store.add_task(_task(title="Email triage", date="2026-06-01", recurrence=Recurrence.WEEKDAYS))
    # 2026-06-06 is a Saturday.
    assert store.get_tasks_for_date("2026-06-06") == []
    # 2026-06-05 is a Friday.
    assert [t.title for t in store.get_tasks_for_date("2026-06-05")] == ["Email triage"]


def test_materialise_is_idempotent(store):
    store.add_task(_task(title="Journal", date="2026-06-01", recurrence=Recurrence.DAILY))
    store.get_tasks_for_date("2026-06-01")
    second = store.get_tasks_for_date("2026-06-01")
    assert len(second) == 1  # no duplicate instance


def test_instance_status_persists(store):
    store.add_task(_task(title="Journal", date="2026-06-01", recurrence=Recurrence.DAILY))
    inst = store.get_tasks_for_date("2026-06-01")[0]
    store.mark_done(inst.id)
    again = store.get_tasks_for_date("2026-06-01")[0]
    assert again.status == TaskStatus.DONE


def test_recurrence_survives_migration(tmp_path):
    # Simulate an old DB without the recurrence columns, then reopen.
    import sqlite3
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
        " description TEXT, deadline TEXT, duration_estimate INTEGER,"
        " priority TEXT NOT NULL DEFAULT 'medium', status TEXT NOT NULL DEFAULT 'pending',"
        " created_at TEXT NOT NULL, date_assigned TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]');"
        "CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
    )
    conn.execute(
        "INSERT INTO tasks (title, priority, status, created_at, date_assigned, tags)"
        " VALUES ('Legacy', 'medium', 'pending', '2026-06-01T00:00:00', '2026-06-01', '[]')"
    )
    conn.commit()
    conn.close()

    store = SqliteStore(db_path=db)  # triggers migration
    tasks = store.get_tasks_for_date("2026-06-01")
    assert [t.title for t in tasks] == ["Legacy"]
    assert tasks[0].recurrence == Recurrence.NONE


# ---------------------------------------------------------------------------
# Search & filters
# ---------------------------------------------------------------------------

def test_search_by_keyword(store):
    store.add_task(_task(title="Email Bob"))
    store.add_task(_task(title="Call Alice"))
    assert [t.title for t in store.search_tasks(q="email")] == ["Email Bob"]


def test_search_by_priority(store):
    store.add_task(_task(title="A", priority=Priority.HIGH))
    store.add_task(_task(title="B", priority=Priority.LOW))
    assert [t.title for t in store.search_tasks(priority="high")] == ["A"]


def test_search_by_status(store):
    a = store.add_task(_task(title="A"))
    store.add_task(_task(title="B"))
    store.mark_done(a.id)
    assert [t.title for t in store.search_tasks(status="done")] == ["A"]


def test_search_by_tag(store):
    store.add_task(_task(title="Tagged", tags=["work"]))
    store.add_task(_task(title="Untagged"))
    assert [t.title for t in store.search_tasks(tag="work")] == ["Tagged"]


def test_search_excludes_templates(store):
    store.add_task(_task(title="Standup", recurrence=Recurrence.DAILY))
    assert store.search_tasks(q="standup") == []


def test_search_combined_filters(store):
    store.add_task(_task(title="Urgent email", priority=Priority.HIGH, date="2026-06-01"))
    store.add_task(_task(title="Urgent call", priority=Priority.LOW, date="2026-06-01"))
    results = store.search_tasks(q="urgent", priority="high", date="2026-06-01")
    assert [t.title for t in results] == ["Urgent email"]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def test_completion_stats_shape(store):
    stats = store.completion_stats(days=7, end="2026-06-07")
    assert len(stats["days"]) == 7
    assert stats["days"][-1]["date"] == "2026-06-07"
    assert stats["total"] == 0 and stats["completion_rate"] == 0.0


def test_completion_stats_counts(store):
    a = store.add_task(_task(title="A", date="2026-06-07"))
    store.add_task(_task(title="B", date="2026-06-07"))
    store.mark_done(a.id)
    stats = store.completion_stats(days=1, end="2026-06-07")
    day = stats["days"][0]
    assert day["total"] == 2 and day["done"] == 1
    assert stats["completion_rate"] == 0.5


# ---------------------------------------------------------------------------
# Push subscriptions
# ---------------------------------------------------------------------------

def _sub(endpoint="https://push.example/abc"):
    return {"endpoint": endpoint, "keys": {"p256dh": "x", "auth": "y"}}


def test_save_and_get_subscription(store):
    store.save_subscription(_sub())
    subs = store.get_subscriptions()
    assert len(subs) == 1 and subs[0]["endpoint"] == "https://push.example/abc"


def test_save_subscription_upserts_by_endpoint(store):
    store.save_subscription(_sub())
    store.save_subscription(_sub())  # same endpoint
    assert len(store.get_subscriptions()) == 1


def test_delete_subscription(store):
    store.save_subscription(_sub())
    store.delete_subscription("https://push.example/abc")
    assert store.get_subscriptions() == []


def test_save_subscription_without_endpoint_is_noop(store):
    store.save_subscription({"keys": {}})
    assert store.get_subscriptions() == []
