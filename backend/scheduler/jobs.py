"""
APScheduler jobs for Donna.

Jobs:
  - morning_briefing_job  : fires at user's wake_time
  - eod_wrap_job          : fires at user's eod_time

Both jobs inject a synthetic "system" message into the conversation so the
LangGraph agent handles them exactly like a real user message.

The scheduler is started from main.py after the FastAPI app is ready.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from memory.chroma_store import ChromaStore
from memory.sqlite_store import SqliteStore
from utils.time_utils import parse_time

logger = logging.getLogger("donna.scheduler")

_scheduler: BackgroundScheduler | None = None

# We import the session store lazily to avoid circular imports
_get_session_store = None  # set by main.py


def set_session_store_getter(getter):
    """Inject the session store getter from main.py."""
    global _get_session_store
    _get_session_store = getter


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------

def morning_briefing_job():
    logger.info("Scheduler: firing morning briefing")
    if _get_session_store is None:
        logger.warning("Session store getter not set — skipping briefing")
        return
    session_store = _get_session_store()

    from agent.graph import donna_graph

    # Use a dedicated scheduler session
    session_id = "scheduler_morning"
    history = session_store.get(session_id, [])

    state = {
        "user_message": "Good morning! Give me my morning briefing.",
        "history": history,
        "intent": "morning_briefing",
    }

    try:
        result = donna_graph.invoke(state)
        new_history = result.get("history", history)
        session_store[session_id] = new_history
        response = result.get("response", "")
        logger.info("Morning briefing response: %s", response[:120])
    except Exception as e:
        logger.error("Morning briefing job error: %s", e)


def eod_wrap_job():
    logger.info("Scheduler: firing EOD wrap")
    if _get_session_store is None:
        logger.warning("Session store getter not set — skipping EOD wrap")
        return
    session_store = _get_session_store()

    from agent.graph import donna_graph

    session_id = "scheduler_eod"
    history = session_store.get(session_id, [])

    state = {
        "user_message": "It's end of day. Let's wrap up.",
        "history": history,
        "intent": "eod_wrap",
    }

    try:
        result = donna_graph.invoke(state)
        new_history = result.get("history", history)
        session_store[session_id] = new_history
        response = result.get("response", "")
        logger.info("EOD wrap response: %s", response[:120])
    except Exception as e:
        logger.error("EOD wrap job error: %s", e)


# ---------------------------------------------------------------------------
# Scheduler management
# ---------------------------------------------------------------------------

def _get_times() -> tuple[tuple[int, int], tuple[int, int]]:
    """Read wake_time and eod_time from SQLite (with defaults)."""
    try:
        sqlite = SqliteStore()
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


def start_scheduler(session_store_getter) -> BackgroundScheduler:
    global _scheduler
    set_session_store_getter(session_store_getter)

    if _scheduler is not None and _scheduler.running:
        return _scheduler

    (wake_h, wake_m), (eod_h, eod_m) = _get_times()

    _scheduler = BackgroundScheduler(timezone="UTC")

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
