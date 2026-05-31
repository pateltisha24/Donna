"""
SQLite store — tasks + session/app state (onboarding flag, scheduler prefs).

All DB access goes through SqliteStore. The DB file path defaults to
./data/donna.db and is controlled by the SQLITE_DB_PATH env var.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Optional

from models.event import Event
from models.task import Priority, Recurrence, Task, TaskStatus

# Map Python weekday() (Mon=0) to the abbreviations used in recurrence_days.
_WEEKDAY_ABBR = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _recurrence_matches(
    recurrence: Recurrence, recurrence_days: list[str], date: str, anchor: str
) -> bool:
    """Does a recurring rule occur on `date` (given it starts no earlier than anchor)?"""
    if date < anchor:
        return False
    d = datetime.fromisoformat(date).date()
    if recurrence == Recurrence.DAILY:
        return True
    if recurrence == Recurrence.WEEKDAYS:
        return d.weekday() < 5
    if recurrence == Recurrence.WEEKLY:
        return _WEEKDAY_ABBR[d.weekday()] in [x.lower() for x in recurrence_days]
    return False


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        title=row["title"],
        date=row["date"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        location=row["location"],
        description=row["description"],
        recurrence=Recurrence(row["recurrence"]),
        recurrence_days=json.loads(row["recurrence_days"]),
    )

DB_PATH = os.getenv("SQLITE_DB_PATH", "./data/donna.db")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT    NOT NULL,
    description       TEXT,
    deadline          TEXT,               -- ISO 8601 datetime string
    duration_estimate INTEGER,            -- minutes
    priority          TEXT    NOT NULL DEFAULT 'medium',
    status            TEXT    NOT NULL DEFAULT 'pending',
    created_at        TEXT    NOT NULL,
    date_assigned     TEXT    NOT NULL,   -- YYYY-MM-DD
    tags              TEXT    NOT NULL DEFAULT '[]', -- JSON array
    recurrence        TEXT    NOT NULL DEFAULT 'none',
    recurrence_days   TEXT    NOT NULL DEFAULT '[]', -- JSON array of weekday abbrevs
    parent_id         INTEGER              -- template id for materialised instances
);

CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    history    TEXT NOT NULL DEFAULT '[]',  -- JSON array of {role, content}
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint     TEXT PRIMARY KEY,
    subscription TEXT NOT NULL,             -- full PushSubscription JSON
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    date            TEXT NOT NULL,          -- YYYY-MM-DD anchor / first date
    start_time      TEXT NOT NULL,          -- HH:MM
    end_time        TEXT,
    location        TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    recurrence      TEXT NOT NULL DEFAULT 'none',
    recurrence_days TEXT NOT NULL DEFAULT '[]'
);
"""

# Seed the onboarding flag row on first run (INSERT OR IGNORE keeps it
# idempotent so existing values are never overwritten).
_SEED = """
INSERT OR IGNORE INTO app_state (key, value) VALUES ('onboarding_complete', 'false');
INSERT OR IGNORE INTO app_state (key, value) VALUES ('morning_briefing_time', '08:00');
INSERT OR IGNORE INTO app_state (key, value) VALUES ('eod_wrap_time', '21:00');
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_task(row: sqlite3.Row) -> Task:
    keys = row.keys()
    return Task(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        deadline=datetime.fromisoformat(row["deadline"]) if row["deadline"] else None,
        duration_estimate=row["duration_estimate"],
        priority=Priority(row["priority"]),
        status=TaskStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        date_assigned=row["date_assigned"],
        tags=json.loads(row["tags"]),
        recurrence=Recurrence(row["recurrence"] if "recurrence" in keys else "none"),
        recurrence_days=json.loads(row["recurrence_days"]) if "recurrence_days" in keys else [],
        parent_id=row["parent_id"] if "parent_id" in keys else None,
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class SqliteStore:
    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            conn.executescript(_SEED)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn) -> None:
        """Add columns introduced after the initial schema (idempotent)."""
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
        added = {
            "recurrence": "TEXT NOT NULL DEFAULT 'none'",
            "recurrence_days": "TEXT NOT NULL DEFAULT '[]'",
            "parent_id": "INTEGER",
        }
        for col, decl in added.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {decl}")

    # ------------------------------------------------------------------
    # Task CRUD
    # ------------------------------------------------------------------

    def add_task(self, task: Task) -> Task:
        """Insert a new task and return it with the assigned id."""
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO tasks
                    (title, description, deadline, duration_estimate,
                     priority, status, created_at, date_assigned, tags,
                     recurrence, recurrence_days, parent_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.title,
                    task.description,
                    task.deadline.isoformat() if task.deadline else None,
                    task.duration_estimate,
                    task.priority.value,
                    task.status.value,
                    task.created_at.isoformat(),
                    task.date_assigned,
                    json.dumps(task.tags),
                    task.recurrence.value,
                    json.dumps(task.recurrence_days),
                    task.parent_id,
                ),
            )
            task.id = cur.lastrowid
        return task

    def get_task(self, task_id: int) -> Optional[Task]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return _row_to_task(row) if row else None

    def get_tasks_for_date(self, date: str) -> list[Task]:
        """
        Return concrete tasks for a date, materialising any recurring templates
        that apply. Templates themselves are never returned as actionable tasks.
        """
        self._materialize_recurring(date)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE date_assigned = ? AND recurrence = 'none'"
                " ORDER BY id",
                (date,),
            ).fetchall()
        return [_row_to_task(r) for r in rows]

    def get_templates(self) -> list[Task]:
        """Return all recurring templates (recurrence != none)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE recurrence != 'none' AND parent_id IS NULL"
                " ORDER BY id"
            ).fetchall()
        return [_row_to_task(r) for r in rows]

    @staticmethod
    def _matches(template: Task, date: str) -> bool:
        return _recurrence_matches(
            template.recurrence, template.recurrence_days, date, template.date_assigned
        )

    def _materialize_recurring(self, date: str) -> None:
        """Ensure an instance exists for each recurring template matching `date`."""
        for template in self.get_templates():
            if not self._matches(template, date):
                continue
            with self._conn() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM tasks WHERE parent_id = ? AND date_assigned = ? LIMIT 1",
                    (template.id, date),
                ).fetchone()
            if exists:
                continue
            self.add_task(Task(
                title=template.title,
                description=template.description,
                date_assigned=date,
                duration_estimate=template.duration_estimate,
                priority=template.priority,
                tags=list(template.tags),
                parent_id=template.id,
            ))

    def search_tasks(
        self,
        q: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        date: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> list[Task]:
        """Filter concrete tasks (not templates) by any combination of fields."""
        clauses = ["recurrence = 'none'"]
        params: list = []
        if q:
            clauses.append("LOWER(title) LIKE ?")
            params.append(f"%{q.lower()}%")
        if priority:
            clauses.append("priority = ?")
            params.append(priority)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if date:
            clauses.append("date_assigned = ?")
            params.append(date)

        where = " AND ".join(clauses)
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM tasks WHERE {where} ORDER BY date_assigned, id", params
            ).fetchall()
        tasks = [_row_to_task(r) for r in rows]
        if tag:
            tasks = [t for t in tasks if tag in t.tags]
        return tasks

    def completion_stats(self, days: int = 7, end: Optional[str] = None) -> dict:
        """
        Per-day task counts over the last `days` (by date_assigned), plus totals.
        Reflects existing tasks/instances only — does not retroactively create
        recurring instances for unviewed past days.
        """
        end_date = date.fromisoformat(end) if end else date.today()
        per_day = []
        total = done = 0
        with self._conn() as conn:
            for i in range(days - 1, -1, -1):
                d = (end_date - timedelta(days=i)).isoformat()
                rows = conn.execute(
                    "SELECT status, COUNT(*) AS c FROM tasks"
                    " WHERE date_assigned = ? AND recurrence = 'none' GROUP BY status",
                    (d,),
                ).fetchall()
                counts = {r["status"]: r["c"] for r in rows}
                day_total = sum(counts.values())
                day_done = counts.get("done", 0)
                total += day_total
                done += day_done
                per_day.append({"date": d, "total": day_total, "done": day_done})
        rate = round(done / total, 3) if total else 0.0
        return {"days": per_day, "total": total, "done": done, "completion_rate": rate}

    def get_tasks_by_status(self, status: TaskStatus, date: Optional[str] = None) -> list[Task]:
        with self._conn() as conn:
            if date:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? AND date_assigned = ? ORDER BY id",
                    (status.value, date),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY id",
                    (status.value,),
                ).fetchall()
        return [_row_to_task(r) for r in rows]

    def update_task(self, task: Task) -> Task:
        """Full update of an existing task (by id)."""
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE tasks SET
                    title             = ?,
                    description       = ?,
                    deadline          = ?,
                    duration_estimate = ?,
                    priority          = ?,
                    status            = ?,
                    date_assigned     = ?,
                    tags              = ?,
                    recurrence        = ?,
                    recurrence_days   = ?,
                    parent_id         = ?
                WHERE id = ?
                """,
                (
                    task.title,
                    task.description,
                    task.deadline.isoformat() if task.deadline else None,
                    task.duration_estimate,
                    task.priority.value,
                    task.status.value,
                    task.date_assigned,
                    json.dumps(task.tags),
                    task.recurrence.value,
                    json.dumps(task.recurrence_days),
                    task.parent_id,
                    task.id,
                ),
            )
        return task

    def mark_done(self, task_id: int) -> None:
        self._set_status(task_id, TaskStatus.DONE)

    def move_task(self, task_id: int, new_date: str) -> None:
        """Roll a task over to a new date and mark it as MOVED."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, date_assigned = ? WHERE id = ?",
                (TaskStatus.MOVED.value, new_date, task_id),
            )

    def delete_task(self, task_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def _set_status(self, task_id: int, status: TaskStatus) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE tasks SET status = ? WHERE id = ?",
                (status.value, task_id),
            )

    # ------------------------------------------------------------------
    # App state helpers
    # ------------------------------------------------------------------

    def get_state(self, key: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM app_state WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO app_state (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def is_onboarding_complete(self) -> bool:
        return self.get_state("onboarding_complete") == "true"

    def complete_onboarding(self) -> None:
        self.set_state("onboarding_complete", "true")

    # ------------------------------------------------------------------
    # Session persistence (conversation history survives restarts)
    # ------------------------------------------------------------------

    def get_history(self, session_id: str) -> list[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT history FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return json.loads(row["history"]) if row else []

    def save_history(self, session_id: str, history: list[dict]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, history, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(session_id) DO UPDATE SET"
                " history = excluded.history, updated_at = excluded.updated_at",
                (session_id, json.dumps(history), datetime.utcnow().isoformat()),
            )

    def append_message(self, session_id: str, role: str, content: str) -> None:
        """Append a single message to a session's history."""
        history = self.get_history(session_id)
        history.append({"role": role, "content": content})
        self.save_history(session_id, history)

    # ------------------------------------------------------------------
    # Web Push subscriptions
    # ------------------------------------------------------------------

    def save_subscription(self, subscription: dict) -> None:
        endpoint = subscription.get("endpoint")
        if not endpoint:
            return
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO push_subscriptions (endpoint, subscription, created_at)"
                " VALUES (?, ?, ?)"
                " ON CONFLICT(endpoint) DO UPDATE SET subscription = excluded.subscription",
                (endpoint, json.dumps(subscription), datetime.utcnow().isoformat()),
            )

    def get_subscriptions(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT subscription FROM push_subscriptions").fetchall()
        return [json.loads(r["subscription"]) for r in rows]

    def delete_subscription(self, endpoint: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))

    # ------------------------------------------------------------------
    # Calendar events
    # ------------------------------------------------------------------

    def add_event(self, event: Event) -> Event:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO events"
                " (title, date, start_time, end_time, location, description,"
                "  recurrence, recurrence_days)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.title, event.date, event.start_time, event.end_time,
                    event.location, event.description, event.recurrence.value,
                    json.dumps(event.recurrence_days),
                ),
            )
            event.id = cur.lastrowid
        return event

    def get_event(self, event_id: int) -> Optional[Event]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return _row_to_event(row) if row else None

    def get_all_events(self) -> list[Event]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY date, start_time").fetchall()
        return [_row_to_event(r) for r in rows]

    def delete_event(self, event_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM events WHERE id = ?", (event_id,))

    def get_events_for_date(self, date: str) -> list[Event]:
        """Concrete + recurring events occurring on `date`, sorted by start time."""
        out: list[Event] = []
        for e in self.get_all_events():
            if e.recurrence == Recurrence.NONE:
                if e.date == date:
                    out.append(e)
            elif _recurrence_matches(e.recurrence, e.recurrence_days, date, e.date):
                # Render the template on this date.
                out.append(Event(
                    id=e.id, title=e.title, date=date, start_time=e.start_time,
                    end_time=e.end_time, location=e.location, description=e.description,
                    recurrence=e.recurrence, recurrence_days=e.recurrence_days,
                ))
        return sorted(out, key=lambda e: e.start_time)

    def get_upcoming_events(self, days: int = 7, start: Optional[str] = None) -> list[Event]:
        """All event occurrences from `start` (default today) over `days` days."""
        start_date = date.fromisoformat(start) if start else date.today()
        out: list[Event] = []
        for i in range(days):
            d = (start_date + timedelta(days=i)).isoformat()
            out.extend(self.get_events_for_date(d))
        return out
