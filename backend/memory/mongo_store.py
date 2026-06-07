"""
MongoDB-backed primary store for Donna.

Mirrors the public API of `SqliteStore` so callers don't change. Collections
are created on first write — no DDL needed.

Collections:
  users               { _id, email, name, image, provider, created_at, settings }
  profiles            { _id (=user_id), ... profile fields }
  chats               { _id, user_id, title, created_at, updated_at, last_message_at, archived }
  sessions            { _id (=chat_id), history: [{role, content}], updated_at }
  tasks               { _id, user_id, title, deadline, ... }
  events              { _id, user_id, title, date, start_time, ... }
  push_subscriptions  { _id (=endpoint), user_id, subscription, created_at }
  app_state           { _id (=key), value }

`user_id` defaults to "default" so the legacy single-user flow keeps working
until auth is fully wired.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from models.event import Event
from models.task import Priority, Recurrence, Task, TaskStatus

logger = logging.getLogger("donna.mongo")

# Map Python weekday() (Mon=0) to the abbreviations used in recurrence_days.
_WEEKDAY_ABBR = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _recurrence_matches(
    recurrence: Recurrence, recurrence_days: list[str], date_str: str, anchor: str
) -> bool:
    if date_str < anchor:
        return False
    d = datetime.fromisoformat(date_str).date()
    if recurrence == Recurrence.DAILY:
        return True
    if recurrence == Recurrence.WEEKDAYS:
        return d.weekday() < 5
    if recurrence == Recurrence.WEEKLY:
        return _WEEKDAY_ABBR[d.weekday()] in [x.lower() for x in recurrence_days]
    return False


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


# ---------------------------------------------------------------------------
# Module-level client (one per process, thread-safe)
# ---------------------------------------------------------------------------

_client: Optional[MongoClient] = None
_db: Optional[Database] = None
_INDEXES_READY = False


def _get_db() -> Database:
    global _client, _db
    if _db is not None:
        return _db
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB", "Donna")
    if not uri:
        raise RuntimeError(
            "MONGODB_URI is not set. Add it to your .env (see .env.example)."
        )
    _client = MongoClient(uri, appname="donna-backend", serverSelectionTimeoutMS=8000)
    _db = _client[db_name]
    return _db


def ping() -> bool:
    """Quick health check used at startup."""
    try:
        _get_db().command("ping")
        return True
    except Exception as e:
        logger.warning("Mongo ping failed: %s", e)
        return False


def _ensure_indexes_once() -> None:
    """Run index DDL exactly once per process — not per request."""
    global _INDEXES_READY
    if _INDEXES_READY:
        return
    try:
        db = _get_db()
        db["tasks"].create_index([("user_id", ASCENDING), ("date_assigned", ASCENDING)])
        db["tasks"].create_index([("user_id", ASCENDING), ("task_id", ASCENDING)], unique=True)
        db["events"].create_index([("user_id", ASCENDING), ("date", ASCENDING)])
        db["events"].create_index([("user_id", ASCENDING), ("event_id", ASCENDING)], unique=True)
        db["chats"].create_index([("user_id", ASCENDING), ("last_message_at", DESCENDING)])
        db["push_subscriptions"].create_index("user_id")
        db["counters"].create_index("_id")
        _INDEXES_READY = True
    except Exception as e:
        logger.warning("Mongo index setup skipped: %s", e)


# ---------------------------------------------------------------------------
# Helpers: convert between Mongo docs and domain objects
# ---------------------------------------------------------------------------

def _doc_to_task(doc: dict) -> Task:
    deadline = None
    if doc.get("deadline"):
        try:
            deadline = datetime.fromisoformat(doc["deadline"])
        except (ValueError, TypeError):
            deadline = None
    created_at_raw = doc.get("created_at")
    if isinstance(created_at_raw, datetime):
        created_at = created_at_raw
    elif isinstance(created_at_raw, str):
        try:
            created_at = datetime.fromisoformat(created_at_raw)
        except (ValueError, TypeError):
            created_at = datetime.utcnow()
    else:
        created_at = datetime.utcnow()
    return Task(
        id=doc.get("task_id") or doc.get("id"),
        title=doc["title"],
        description=doc.get("description"),
        deadline=deadline,
        duration_estimate=doc.get("duration_estimate"),
        priority=Priority(doc.get("priority", "medium")),
        status=TaskStatus(doc.get("status", "pending")),
        created_at=created_at,
        date_assigned=doc["date_assigned"],
        tags=list(doc.get("tags", [])),
        recurrence=Recurrence(doc.get("recurrence", "none")),
        recurrence_days=list(doc.get("recurrence_days", [])),
        parent_id=doc.get("parent_id"),
    )


def _task_to_doc(task: Task, user_id: str) -> dict:
    return {
        "user_id": user_id,
        "title": task.title,
        "description": task.description,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "duration_estimate": task.duration_estimate,
        "priority": task.priority.value,
        "status": task.status.value,
        "created_at": task.created_at.isoformat() if task.created_at else _now_iso(),
        "date_assigned": task.date_assigned,
        "tags": list(task.tags),
        "recurrence": task.recurrence.value,
        "recurrence_days": list(task.recurrence_days),
        "parent_id": task.parent_id,
    }


def _doc_to_event(doc: dict) -> Event:
    return Event(
        id=doc.get("event_id"),
        title=doc["title"],
        date=doc["date"],
        start_time=doc["start_time"],
        end_time=doc.get("end_time"),
        location=doc.get("location", ""),
        description=doc.get("description", ""),
        recurrence=Recurrence(doc.get("recurrence", "none")),
        recurrence_days=list(doc.get("recurrence_days", [])),
    )


def _event_to_doc(event: Event, user_id: str) -> dict:
    return {
        "user_id": user_id,
        "title": event.title,
        "date": event.date,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "location": event.location,
        "description": event.description,
        "recurrence": event.recurrence.value,
        "recurrence_days": list(event.recurrence_days),
    }


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class MongoStore:
    """
    A drop-in replacement for SqliteStore using MongoDB.

    `user_id` is passed implicitly via the `default_user` constructor arg until
    real auth ties each request to its caller.
    """

    def __init__(self, default_user: str = "default") -> None:
        self.user_id = default_user
        _ensure_indexes_once()

    # ---- collections (always re-resolved so connections recover) ----------

    def _col(self, name: str) -> Collection:
        return _get_db()[name]

    # ---- auto-increment integer ids (for Task / Event APIs) ---------------

    def _next_id(self, counter: str) -> int:
        doc = self._col("counters").find_one_and_update(
            {"_id": counter},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,
        )
        return int(doc["seq"]) if doc else 1

    # ------------------------------------------------------------------
    # Task CRUD
    # ------------------------------------------------------------------

    def add_task(self, task: Task) -> Task:
        task.id = self._next_id("tasks")
        doc = _task_to_doc(task, self.user_id)
        doc["task_id"] = task.id
        self._col("tasks").insert_one(doc)
        return task

    def get_task(self, task_id: int) -> Optional[Task]:
        doc = self._col("tasks").find_one({"user_id": self.user_id, "task_id": task_id})
        return _doc_to_task(doc) if doc else None

    def get_tasks_for_date(self, date_str: str) -> list[Task]:
        self._materialize_recurring(date_str)
        cur = self._col("tasks").find(
            {"user_id": self.user_id, "date_assigned": date_str, "recurrence": "none"}
        ).sort("task_id", ASCENDING)
        return [_doc_to_task(d) for d in cur]

    def get_templates(self) -> list[Task]:
        cur = self._col("tasks").find(
            {
                "user_id": self.user_id,
                "recurrence": {"$ne": "none"},
                "parent_id": None,
            }
        ).sort("task_id", ASCENDING)
        return [_doc_to_task(d) for d in cur]

    @staticmethod
    def _matches(template: Task, date_str: str) -> bool:
        return _recurrence_matches(
            template.recurrence, template.recurrence_days, date_str, template.date_assigned
        )

    def _materialize_recurring(self, date_str: str) -> None:
        for template in self.get_templates():
            if not self._matches(template, date_str):
                continue
            exists = self._col("tasks").find_one(
                {"user_id": self.user_id, "parent_id": template.id, "date_assigned": date_str},
                {"_id": 1},
            )
            if exists:
                continue
            self.add_task(Task(
                title=template.title,
                description=template.description,
                date_assigned=date_str,
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
        query: dict = {"user_id": self.user_id, "recurrence": "none"}
        if q:
            query["title"] = {"$regex": q, "$options": "i"}
        if priority:
            query["priority"] = priority
        if status:
            query["status"] = status
        if date:
            query["date_assigned"] = date
        if tag:
            query["tags"] = tag
        cur = self._col("tasks").find(query).sort([("date_assigned", ASCENDING), ("task_id", ASCENDING)])
        return [_doc_to_task(d) for d in cur]

    def completion_stats(self, days: int = 7, end: Optional[str] = None) -> dict:
        end_date = date.fromisoformat(end) if end else date.today()
        per_day = []
        total = done = 0
        col = self._col("tasks")
        for i in range(days - 1, -1, -1):
            d = (end_date - timedelta(days=i)).isoformat()
            pipeline = [
                {"$match": {"user_id": self.user_id, "date_assigned": d, "recurrence": "none"}},
                {"$group": {"_id": "$status", "c": {"$sum": 1}}},
            ]
            counts = {r["_id"]: r["c"] for r in col.aggregate(pipeline)}
            day_total = sum(counts.values())
            day_done = counts.get("done", 0)
            total += day_total
            done += day_done
            per_day.append({"date": d, "total": day_total, "done": day_done})
        rate = round(done / total, 3) if total else 0.0
        return {"days": per_day, "total": total, "done": done, "completion_rate": rate}

    def insights(self, days: int = 140, end: Optional[str] = None) -> dict:
        """
        Rich productivity analytics over a window, for the Productivity page.

        Returns:
          - `daily`:    dense per-day series (total, done, planned_min, focus_min)
                        — the source for the contribution heatmap.
          - `categories`: time-by-tag breakdown (first tag, or "Untagged"), so the
                        user can see *where* their time goes.
          - `summary`:  totals, completion rate, focus minutes, active days,
                        current streak (consecutive recent days with a completion),
                        and the most-productive day.

        One aggregation for the daily series + one for categories — O(1) round
        trips regardless of window size, unlike completion_stats' per-day loop.
        """
        end_date = date.fromisoformat(end) if end else date.today()
        start_date = end_date - timedelta(days=days - 1)
        start_s, end_s = start_date.isoformat(), end_date.isoformat()
        col = self._col("tasks")
        match = {
            "user_id": self.user_id,
            "recurrence": "none",
            "date_assigned": {"$gte": start_s, "$lte": end_s},
        }

        done_cond = {"$eq": ["$status", "done"]}
        dur = {"$ifNull": ["$duration_estimate", 0]}

        daily_rows = {
            r["_id"]: r
            for r in col.aggregate([
                {"$match": match},
                {"$group": {
                    "_id": "$date_assigned",
                    "total": {"$sum": 1},
                    "done": {"$sum": {"$cond": [done_cond, 1, 0]}},
                    "planned_min": {"$sum": dur},
                    "focus_min": {"$sum": {"$cond": [done_cond, dur, 0]}},
                }},
            ])
        }

        daily = []
        for i in range(days - 1, -1, -1):
            d = (end_date - timedelta(days=i)).isoformat()
            r = daily_rows.get(d)
            daily.append({
                "date": d,
                "total": r["total"] if r else 0,
                "done": r["done"] if r else 0,
                "planned_min": r["planned_min"] if r else 0,
                "focus_min": r["focus_min"] if r else 0,
            })

        categories = [
            {"name": r["_id"], "count": r["count"], "done": r["done"], "minutes": r["minutes"]}
            for r in col.aggregate([
                {"$match": match},
                {"$project": {
                    "status": 1,
                    "duration_estimate": 1,
                    # Bucket by the first tag; tagless tasks fall into "Untagged".
                    "tag": {"$cond": [
                        {"$gt": [{"$size": {"$ifNull": ["$tags", []]}}, 0]},
                        {"$arrayElemAt": ["$tags", 0]},
                        "Untagged",
                    ]},
                }},
                {"$group": {
                    "_id": "$tag",
                    "count": {"$sum": 1},
                    "done": {"$sum": {"$cond": [done_cond, 1, 0]}},
                    "minutes": {"$sum": dur},
                }},
                {"$sort": {"minutes": -1}},
            ])
        ]

        total = sum(d["total"] for d in daily)
        done = sum(d["done"] for d in daily)
        focus = sum(d["focus_min"] for d in daily)
        active_days = sum(1 for d in daily if d["total"] > 0)

        # Current streak: consecutive most-recent days with at least one
        # completion. Today is allowed to be "not done yet" — an empty *today*
        # doesn't break the streak (we just start counting from yesterday),
        # otherwise the streak would reset to 0 every morning.
        streak = 0
        for idx, d in enumerate(reversed(daily)):
            if d["done"] > 0:
                streak += 1
            elif idx == 0:
                continue  # today isn't over yet
            else:
                break

        best = max(daily, key=lambda d: d["done"], default=None)
        best_day = best["date"] if best and best["done"] > 0 else None

        return {
            "range": {"start": start_s, "end": end_s, "days": days},
            "daily": daily,
            "categories": categories,
            "summary": {
                "total": total,
                "done": done,
                "completion_rate": round(done / total, 3) if total else 0.0,
                "focus_minutes": focus,
                "active_days": active_days,
                "current_streak": streak,
                "best_day": best_day,
                "best_day_done": best["done"] if best else 0,
            },
        }

    def get_tasks_by_status(self, status: TaskStatus, date: Optional[str] = None) -> list[Task]:
        query: dict = {"user_id": self.user_id, "status": status.value}
        if date:
            query["date_assigned"] = date
        cur = self._col("tasks").find(query).sort("task_id", ASCENDING)
        return [_doc_to_task(d) for d in cur]

    def update_task(self, task: Task) -> Task:
        update = _task_to_doc(task, self.user_id)
        self._col("tasks").update_one(
            {"user_id": self.user_id, "task_id": task.id},
            {"$set": update},
        )
        return task

    def mark_done(self, task_id: int) -> None:
        self._set_status(task_id, TaskStatus.DONE)

    def move_task(self, task_id: int, new_date: str) -> None:
        self._col("tasks").update_one(
            {"user_id": self.user_id, "task_id": task_id},
            {"$set": {"status": TaskStatus.MOVED.value, "date_assigned": new_date}},
        )

    def delete_task(self, task_id: int) -> None:
        self._col("tasks").delete_one({"user_id": self.user_id, "task_id": task_id})

    def _set_status(self, task_id: int, status: TaskStatus) -> None:
        self._col("tasks").update_one(
            {"user_id": self.user_id, "task_id": task_id},
            {"$set": {"status": status.value}},
        )

    # ------------------------------------------------------------------
    # App state
    # ------------------------------------------------------------------

    def get_state(self, key: str) -> Optional[str]:
        doc = self._col("app_state").find_one({"_id": f"{self.user_id}:{key}"})
        return doc["value"] if doc else None

    def set_state(self, key: str, value: str) -> None:
        self._col("app_state").update_one(
            {"_id": f"{self.user_id}:{key}"},
            {"$set": {"value": value, "user_id": self.user_id, "key": key}},
            upsert=True,
        )

    def is_onboarding_complete(self) -> bool:
        return self.get_state("onboarding_complete") == "true"

    def complete_onboarding(self) -> None:
        self.set_state("onboarding_complete", "true")

    # ------------------------------------------------------------------
    # Sessions (per-chat conversation history)
    # ------------------------------------------------------------------

    def get_history(self, session_id: str) -> list[dict]:
        doc = self._col("sessions").find_one({"_id": session_id})
        return list(doc["history"]) if doc else []

    def save_history(self, session_id: str, history: list[dict]) -> None:
        self._col("sessions").update_one(
            {"_id": session_id},
            {"$set": {"history": list(history), "updated_at": _now_iso()}},
            upsert=True,
        )
        # Bump the parent chat's last_message_at so it floats up in the sidebar.
        self._col("chats").update_one(
            {"_id": session_id},
            {"$set": {"last_message_at": _now_iso(), "updated_at": _now_iso()}},
        )

    def append_message(self, session_id: str, role: str, content: str) -> None:
        self._col("sessions").update_one(
            {"_id": session_id},
            {
                "$push": {"history": {"role": role, "content": content}},
                "$set": {"updated_at": _now_iso()},
                "$setOnInsert": {"_id": session_id},
            },
            upsert=True,
        )

    # ------------------------------------------------------------------
    # Chats
    # ------------------------------------------------------------------

    def create_chat(self, chat_id: Optional[str] = None, user_id: Optional[str] = None, title: str = "New chat") -> dict:
        cid = chat_id or str(uuid.uuid4())
        uid = user_id or self.user_id
        now = _now_iso()
        doc = {
            "_id": cid,
            "user_id": uid,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "last_message_at": None,
            "archived": False,
        }
        self._col("chats").insert_one(doc)
        # Pre-create an empty session doc so first save_history just updates.
        self._col("sessions").update_one(
            {"_id": cid},
            {"$setOnInsert": {"_id": cid, "history": [], "updated_at": now}},
            upsert=True,
        )
        out = dict(doc)
        out["id"] = out.pop("_id")
        return out

    def list_chats(self, user_id: Optional[str] = None) -> list[dict]:
        uid = user_id or self.user_id
        cur = self._col("chats").find({"user_id": uid, "archived": {"$ne": True}}).sort(
            [("last_message_at", DESCENDING), ("updated_at", DESCENDING)]
        )
        out = []
        for d in cur:
            d["id"] = d.pop("_id")
            out.append(d)
        return out

    def get_chat(self, chat_id: str) -> Optional[dict]:
        d = self._col("chats").find_one({"_id": chat_id})
        if not d:
            return None
        d["id"] = d.pop("_id")
        return d

    def rename_chat(self, chat_id: str, title: str) -> None:
        self._col("chats").update_one(
            {"_id": chat_id},
            {"$set": {"title": title, "updated_at": _now_iso()}},
        )

    def touch_chat(self, chat_id: str) -> None:
        now = _now_iso()
        self._col("chats").update_one(
            {"_id": chat_id},
            {"$set": {"last_message_at": now, "updated_at": now}},
        )

    def delete_chat(self, chat_id: str) -> None:
        self._col("chats").delete_one({"_id": chat_id})
        self._col("sessions").delete_one({"_id": chat_id})

    # ------------------------------------------------------------------
    # Push subscriptions
    # ------------------------------------------------------------------

    def save_subscription(self, subscription: dict) -> None:
        endpoint = subscription.get("endpoint")
        if not endpoint:
            return
        self._col("push_subscriptions").update_one(
            {"_id": endpoint},
            {
                "$set": {
                    "user_id": self.user_id,
                    "subscription": subscription,
                    "endpoint": endpoint,
                    "updated_at": _now_iso(),
                },
                "$setOnInsert": {"created_at": _now_iso()},
            },
            upsert=True,
        )

    def get_subscriptions(self) -> list[dict]:
        cur = self._col("push_subscriptions").find({})
        return [d["subscription"] for d in cur if "subscription" in d]

    def delete_subscription(self, endpoint: str) -> None:
        self._col("push_subscriptions").delete_one({"_id": endpoint})

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def add_event(self, event: Event) -> Event:
        event.id = self._next_id("events")
        doc = _event_to_doc(event, self.user_id)
        doc["event_id"] = event.id
        self._col("events").insert_one(doc)
        return event

    def get_event(self, event_id: int) -> Optional[Event]:
        d = self._col("events").find_one({"user_id": self.user_id, "event_id": event_id})
        return _doc_to_event(d) if d else None

    def get_all_events(self) -> list[Event]:
        cur = self._col("events").find({"user_id": self.user_id}).sort(
            [("date", ASCENDING), ("start_time", ASCENDING)]
        )
        return [_doc_to_event(d) for d in cur]

    def delete_event(self, event_id: int) -> None:
        self._col("events").delete_one({"user_id": self.user_id, "event_id": event_id})

    def get_events_for_date(self, date_str: str) -> list[Event]:
        out: list[Event] = []
        for e in self.get_all_events():
            if e.recurrence == Recurrence.NONE:
                if e.date == date_str:
                    out.append(e)
            elif _recurrence_matches(e.recurrence, e.recurrence_days, date_str, e.date):
                out.append(Event(
                    id=e.id, title=e.title, date=date_str, start_time=e.start_time,
                    end_time=e.end_time, location=e.location, description=e.description,
                    recurrence=e.recurrence, recurrence_days=e.recurrence_days,
                ))
        return sorted(out, key=lambda e: e.start_time)

    def get_upcoming_events(self, days: int = 7, start: Optional[str] = None) -> list[Event]:
        start_date = date.fromisoformat(start) if start else date.today()
        out: list[Event] = []
        for i in range(days):
            d = (start_date + timedelta(days=i)).isoformat()
            out.extend(self.get_events_for_date(d))
        return out

    # ------------------------------------------------------------------
    # User profile (stored in `profiles` collection, keyed by user_id)
    # ------------------------------------------------------------------

    def get_profile_doc(self) -> Optional[dict]:
        doc = self._col("profiles").find_one({"_id": self.user_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return doc

    def save_profile_doc(self, data: dict) -> None:
        self._col("profiles").update_one(
            {"_id": self.user_id},
            {"$set": data, "$setOnInsert": {"_id": self.user_id, "created_at": _now_iso()}},
            upsert=True,
        )

    # ------------------------------------------------------------------
    # Users (email/password + Google) — used by /auth endpoints
    # ------------------------------------------------------------------

    def find_user_by_email(self, email: str) -> Optional[dict]:
        email = email.strip().lower()
        if not email:
            return None
        return self._col("users").find_one({"email": email})

    def create_user(
        self,
        email: str,
        password_hash: Optional[str],
        name: str,
        provider: str = "credentials",
        image: Optional[str] = None,
    ) -> dict:
        email = email.strip().lower()
        doc = {
            "_id": str(uuid.uuid4()),
            "email": email,
            "name": name,
            "password_hash": password_hash,
            "provider": provider,
            "image": image,
            "created_at": _now_iso(),
        }
        self._col("users").insert_one(doc)
        return doc

    def upsert_oauth_user(self, email: str, name: str, image: Optional[str] = None) -> dict:
        """Insert-or-fetch a user that signs in via Google (no password)."""
        email = email.strip().lower()
        existing = self.find_user_by_email(email)
        if existing:
            return existing
        return self.create_user(
            email=email, password_hash=None, name=name, provider="google", image=image
        )

    # ------------------------------------------------------------------
    # Conflict detection (overlapping events)
    # ------------------------------------------------------------------

    @staticmethod
    def _time_to_min(t: str) -> int:
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    @staticmethod
    def _event_window(e: Event) -> tuple[int, int]:
        start = MongoStore._time_to_min(e.start_time)
        end = MongoStore._time_to_min(e.end_time) if e.end_time else start + 60
        return start, end

    def find_event_conflicts(self, target_date: str) -> list[dict]:
        """Return all overlapping event pairs on `target_date`."""
        events = self.get_events_for_date(target_date)
        windows = [(e, *self._event_window(e)) for e in events]
        conflicts: list[dict] = []
        for i in range(len(windows)):
            a, a_start, a_end = windows[i]
            for j in range(i + 1, len(windows)):
                b, b_start, b_end = windows[j]
                if a_start < b_end and b_start < a_end:
                    conflicts.append({
                        "date": target_date,
                        "a": {"id": a.id, "title": a.title, "start": a.start_time, "end": a.end_time},
                        "b": {"id": b.id, "title": b.title, "start": b.start_time, "end": b.end_time},
                    })
        return conflicts

    def conflicts_for_event(self, event: Event, target_date: str | None = None) -> list[Event]:
        """Return existing events that overlap with `event` on the given date."""
        d = target_date or event.date
        e_start, e_end = self._event_window(event)
        out: list[Event] = []
        for existing in self.get_events_for_date(d):
            if existing.id == event.id:
                continue
            o_start, o_end = self._event_window(existing)
            if e_start < o_end and o_start < e_end:
                out.append(existing)
        return out
