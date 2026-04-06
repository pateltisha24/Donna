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
