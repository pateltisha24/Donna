"""
Import and export iCalendar (.ics) data.

Import uses the `icalendar` library (handles folding, timezones, RRULE).
Export hand-builds a VCALENDAR with a 15-minute VALARM on each event so that,
once imported into Apple Calendar, native reminders also fire.
"""

import logging
from datetime import date, datetime
from typing import Union

from icalendar import Calendar

from models.event import Event
from models.task import Recurrence

logger = logging.getLogger("donna.ics")

# icalendar BYDAY codes <-> our lowercase abbreviations.
_BYDAY_TO_ABBR = {"MO": "mon", "TU": "tue", "WE": "wed", "TH": "thu",
                  "FR": "fri", "SA": "sat", "SU": "sun"}
_ABBR_TO_BYDAY = {v: k for k, v in _BYDAY_TO_ABBR.items()}
_WEEKDAY_ORDER = ["mon", "tue", "wed", "thu", "fri"]


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _rrule_to_recurrence(rrule) -> tuple[Recurrence, list[str]]:
    if not rrule:
        return Recurrence.NONE, []
    freq = (rrule.get("FREQ") or [""])[0]
    if freq == "DAILY":
        return Recurrence.DAILY, []
    if freq == "WEEKLY":
        bydays = [_BYDAY_TO_ABBR.get(b, "") for b in rrule.get("BYDAY", [])]
        bydays = [b for b in bydays if b]
        if bydays and all(d in _WEEKDAY_ORDER for d in bydays) and len(bydays) == 5:
            return Recurrence.WEEKDAYS, []
        return Recurrence.WEEKLY, bydays
    return Recurrence.NONE, []


def import_ics(data: Union[str, bytes]) -> list[Event]:
    """Parse VEVENTs from .ics content into Event objects (best-effort)."""
    try:
        cal = Calendar.from_ical(data)
    except Exception as e:  # noqa: BLE001
        logger.warning("ics import failed: %s", e)
        return []

    events: list[Event] = []
    for comp in cal.walk("VEVENT"):
        summary = str(comp.get("summary", "")).strip()
        dtstart = comp.get("dtstart")
        if not summary or dtstart is None:
            continue
        start = dtstart.dt
        if isinstance(start, datetime):
            d, start_time = start.date().isoformat(), start.strftime("%H:%M")
        elif isinstance(start, date):
            d, start_time = start.isoformat(), "00:00"
        else:
            continue

        end_time = None
        dtend = comp.get("dtend")
        if dtend is not None and isinstance(dtend.dt, datetime):
            end_time = dtend.dt.strftime("%H:%M")

        recurrence, days = _rrule_to_recurrence(comp.get("rrule"))

        events.append(Event(
            title=summary,
            date=d,
            start_time=start_time,
            end_time=end_time,
            location=str(comp.get("location", "")),
            description=str(comp.get("description", "")),
            recurrence=recurrence,
            recurrence_days=days,
        ))
    return events


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _dt(date_str: str, time_str: str) -> str:
    return f"{date_str.replace('-', '')}T{time_str.replace(':', '')}00"


def _rrule_line(event: Event) -> str:
    if event.recurrence == Recurrence.DAILY:
        return "RRULE:FREQ=DAILY"
    if event.recurrence == Recurrence.WEEKDAYS:
        return "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    if event.recurrence == Recurrence.WEEKLY and event.recurrence_days:
        days = ",".join(_ABBR_TO_BYDAY[d] for d in event.recurrence_days if d in _ABBR_TO_BYDAY)
        if days:
            return f"RRULE:FREQ=WEEKLY;BYDAY={days}"
    return ""


def export_ics(events: list[Event], alarm_minutes: int = 15) -> str:
    """Build a VCALENDAR string with a VALARM on each event."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Donna//Calendar//EN",
        "CALSCALE:GREGORIAN",
    ]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for e in events:
        if not e.id and e.id != 0:
            uid = f"{e.title}-{e.date}-{e.start_time}@donna"
        else:
            uid = f"donna-{e.id}@donna"
        end_time = e.end_time or e.start_time
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_dt(e.date, e.start_time)}",
            f"DTEND:{_dt(e.date, end_time)}",
            f"SUMMARY:{e.title}",
        ]
        if e.location:
            lines.append(f"LOCATION:{e.location}")
        rrule = _rrule_line(e)
        if rrule:
            lines.append(rrule)
        lines += [
            "BEGIN:VALARM",
            f"TRIGGER:-PT{alarm_minutes}M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{e.title}",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
