"""
APScheduler jobs for Donna.

Jobs:
  - morning_briefing_job  : fires at user's wake_time
  - eod_wrap_job          : fires at user's eod_time

Both jobs inject a synthetic "system" message into the conversation so the
LangGraph agent handles them exactly like a real user message. The generated
briefing is persisted into the default session so it's waiting for the user
the next time they open Donna.

The scheduler is started from main.py after the FastAPI app is ready.
"""

import logging
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

# Scheduler timezone is configurable so a deployed instance can run on the
# user's local time rather than UTC. Falls back to UTC for safety in tests.
SCHEDULER_TZ = os.getenv("SCHEDULER_TZ", "UTC")

from memory.chroma_store import ChromaStore
from memory.mongo_store import MongoStore
from models.task import Recurrence
from utils.time_utils import parse_time

logger = logging.getLogger("donna.scheduler")

_scheduler: BackgroundScheduler | None = None

# Scheduled briefings land in the same session the user sees on open.
DEFAULT_SESSION = "default"

# How many minutes before an event to send its reminder.
REMINDER_LEAD_MIN = 15


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------

def _run_scheduled(event: str, user_message: str, title: str) -> None:
    """Run an intent through the graph, persist it, and push a notification."""
    from agent.graph import donna_graph
    from notify.push import send_to_all

    store = MongoStore()
    history = store.get_history(DEFAULT_SESSION)

    state = {
        "user_message": user_message,
        "history": history,
        "intent": event,
    }

    try:
        result = donna_graph.invoke(state)
        response = result.get("response", "")
        store.save_history(DEFAULT_SESSION, result.get("history", history))
        logger.info("%s delivered: %s", event, response[:120])
        if response:
            # Notification bodies should be short; trim to a teaser.
            body = response if len(response) <= 160 else response[:157] + "…"
            send_to_all(title, body, store=store)
    except Exception as e:
        logger.error("%s job error: %s", event, e)


# ---------------------------------------------------------------------------
# Per-event reminders (15 min before)
# ---------------------------------------------------------------------------

def _event_reminder_job(title: str, start_time: str) -> None:
    from notify.push import send_to_all
    send_to_all(f"Soon: {title}", f"Starts at {start_time}")


def _cron_day_of_week(event) -> str:
    if event.recurrence == Recurrence.DAILY:
        return "*"
    if event.recurrence == Recurrence.WEEKDAYS:
        return "mon-fri"
    return ",".join(event.recurrence_days)


def reschedule_event_reminders() -> None:
    """Rebuild all per-event reminder jobs from the events table."""
    if _scheduler is None or not _scheduler.running:
        return

    for job in list(_scheduler.get_jobs()):
        if job.id.startswith("event_reminder_"):
            _scheduler.remove_job(job.id)

    store = MongoStore()
    for e in store.get_all_events():
        h, m = parse_time(e.start_time)
        lead = h * 60 + m - REMINDER_LEAD_MIN
        if lead < 0:  # reminder would fall on the previous day — skip edge case
            continue
        rh, rm = divmod(lead, 60)
        job_id = f"event_reminder_{e.id}"

        if e.recurrence == Recurrence.NONE:
            try:
                run_at = datetime.fromisoformat(f"{e.date}T{rh:02d}:{rm:02d}:00")
            except ValueError:
                continue
            if run_at <= datetime.now():
                continue
            _scheduler.add_job(
                _event_reminder_job, DateTrigger(run_date=run_at),
                args=[e.title, e.start_time], id=job_id, replace_existing=True,
            )
        else:
            _scheduler.add_job(
                _event_reminder_job,
                CronTrigger(day_of_week=_cron_day_of_week(e), hour=rh, minute=rm),
                args=[e.title, e.start_time], id=job_id, replace_existing=True,
            )
    logger.info("Rescheduled event reminders")


def morning_briefing_job():
    logger.info("Scheduler: firing morning briefing")
    _run_scheduled(
        "morning_briefing", "Good morning! Give me my morning briefing.",
        title="Your morning briefing",
    )


def eod_wrap_job():
    logger.info("Scheduler: firing EOD wrap")
    _run_scheduled(
        "eod_wrap", "It's end of day. Let's wrap up.",
        title="End-of-day wrap",
    )


# ---------------------------------------------------------------------------
# Scheduler management
# ---------------------------------------------------------------------------

def _get_times() -> tuple[tuple[int, int], tuple[int, int]]:
    """Read wake_time and eod_time from app_state (with defaults)."""
    try:
        sqlite = MongoStore()
        wake_raw = sqlite.get_state("morning_briefing_time") or "08:00"
        eod_raw = sqlite.get_state("eod_wrap_time") or "21:00"

        # Also check ChromaDB profile for user-configured times
        try:
            chroma = ChromaStore()
            profile = chroma.get_profile()
            if profile.wake_time:
                wake_raw = profile.wake_time
            if profile.eod_time:
                eod_raw = profile.eod_time
        except Exception:
            pass

        return parse_time(wake_raw), parse_time(eod_raw)
    except Exception:
        return (8, 0), (21, 0)


def start_scheduler() -> BackgroundScheduler:
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        return _scheduler

    (wake_h, wake_m), (eod_h, eod_m) = _get_times()

    _scheduler = BackgroundScheduler(timezone=SCHEDULER_TZ)

    _scheduler.add_job(
        morning_briefing_job,
        CronTrigger(hour=wake_h, minute=wake_m),
        id="morning_briefing",
        replace_existing=True,
        name="Morning Briefing",
    )

    _scheduler.add_job(
        eod_wrap_job,
        CronTrigger(hour=eod_h, minute=eod_m),
        id="eod_wrap",
        replace_existing=True,
        name="EOD Wrap",
    )

    _scheduler.start()
    logger.info(
        "Scheduler started. Morning at %02d:%02d, EOD at %02d:%02d",
        wake_h, wake_m, eod_h, eod_m,
    )
    reschedule_event_reminders()
    return _scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


def reschedule(wake_time: str, eod_time: str):
    """Reschedule jobs after profile update."""
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        return
    wh, wm = parse_time(wake_time)
    eh, em = parse_time(eod_time)

    _scheduler.reschedule_job(
        "morning_briefing", trigger=CronTrigger(hour=wh, minute=wm)
    )
    _scheduler.reschedule_job(
        "eod_wrap", trigger=CronTrigger(hour=eh, minute=em)
    )
    logger.info("Rescheduled: morning %s, EOD %s", wake_time, eod_time)
