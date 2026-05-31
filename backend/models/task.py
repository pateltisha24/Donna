from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    MOVED = "moved"


class Recurrence(str, Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKDAYS = "weekdays"   # Mon–Fri
    WEEKLY = "weekly"       # specific weekdays in recurrence_days


@dataclass
class Task:
    title: str
    date_assigned: str                          # ISO date string: YYYY-MM-DD
    id: Optional[int] = None
    description: Optional[str] = None
    deadline: Optional[datetime] = None         # absolute datetime
    duration_estimate: Optional[int] = None     # minutes
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    # Recurrence: a task with recurrence != NONE is a *template* that
    # materialises concrete instances on matching dates. Instances carry
    # parent_id pointing back to their template and recurrence NONE.
    recurrence: Recurrence = Recurrence.NONE
    recurrence_days: list[str] = field(default_factory=list)  # e.g. ["mon","wed"]
    parent_id: Optional[int] = None
