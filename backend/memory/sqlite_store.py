"""
SQLite store — tasks + session/app state (onboarding flag, scheduler prefs).

All DB access goes through SqliteStore. The DB file path defaults to
./data/donna.db and is controlled by the SQLITE_DB_PATH env var.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from models.task import Priority, Task, TaskStatus

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
    tags              TEXT    NOT NULL DEFAULT '[]'  -- JSON array
);

CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
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
                     priority, status, created_at, date_assigned, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        """Return all tasks assigned to a given YYYY-MM-DD date."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE date_assigned = ? ORDER BY id",
                (date,),
            ).fetchall()
        return [_row_to_task(r) for r in rows]

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
                    tags              = ?
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
