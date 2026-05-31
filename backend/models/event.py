"""
Calendar event model.

Events are timed (start/end), unlike tasks. A non-recurring event is a single
dated entry; a recurring event (e.g. a weekly class) is a template that renders
on every matching date — we compute occurrences on the fly rather than
persisting instances, since events aren't "completed" the way tasks are.
"""

from dataclasses import dataclass, field
from typing import Optional

from models.task import Recurrence  # reuse the same recurrence vocabulary


@dataclass
class Event:
    title: str
    date: str                                   # YYYY-MM-DD (anchor / first date)
    start_time: str                             # HH:MM 24h
    id: Optional[int] = None
    end_time: Optional[str] = None              # HH:MM 24h
    location: str = ""
    description: str = ""
    recurrence: Recurrence = Recurrence.NONE
    recurrence_days: list[str] = field(default_factory=list)  # ["tue","fri"]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "date": self.date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "location": self.location,
            "description": self.description,
            "recurrence": self.recurrence.value,
            "recurrence_days": self.recurrence_days,
        }
