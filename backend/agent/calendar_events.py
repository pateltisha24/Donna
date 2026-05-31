"""Convert raw event dicts (from vision / the LLM) into validated Event objects."""

import re
from typing import Optional

from models.event import Event
from models.task import Recurrence
from utils.time_utils import today_str

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _norm_time(value) -> Optional[str]:
    if not value:
        return None
    s = str(value).strip()
    m = _TIME_RE.match(s)
    if m:
        h, mn = int(m.group(1)), m.group(2)
        if 0 <= h <= 23:
            return f"{h:02d}:{mn}"
    return None


def build_event(d: dict, default_date: Optional[str] = None) -> Optional[Event]:
    title = str(d.get("title", "")).strip()
    start = _norm_time(d.get("start_time"))
    if not title or not start:
        return None

    try:
        recurrence = Recurrence(str(d.get("recurrence", "none")).lower())
    except ValueError:
        recurrence = Recurrence.NONE

    raw_days = d.get("recurrence_days") or []
    days = [str(x).lower()[:3] for x in raw_days] if isinstance(raw_days, list) else []

    # Weekly recurrence needs at least one day; otherwise treat as one-off.
    if recurrence == Recurrence.WEEKLY and not days:
        recurrence = Recurrence.NONE

    return Event(
        title=title,
        date=d.get("date") or default_date or today_str(),
        start_time=start,
        end_time=_norm_time(d.get("end_time")),
        location=str(d.get("location") or ""),
        description=str(d.get("description") or ""),
        recurrence=recurrence,
        recurrence_days=days,
    )


def build_events(items: list, default_date: Optional[str] = None) -> list[Event]:
    out = []
    for it in items:
        if isinstance(it, dict):
            ev = build_event(it, default_date)
            if ev:
                out.append(ev)
    return out
