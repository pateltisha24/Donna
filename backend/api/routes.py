"""
FastAPI routes for Donna.

Endpoints:
  POST /chat          — main chat endpoint, streams SSE response
  POST /trigger       — manually trigger morning_briefing or eod_wrap
  GET  /profile       — return current user profile
  GET  /tasks         — return tasks for a date (default: today)
  GET  /health        — health check
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from agent.graph import donna_graph
from memory.chroma_store import ChromaStore
from memory.sqlite_store import SqliteStore
from utils.stream_filter import StreamFilter
from utils.time_utils import today_str

logger = logging.getLogger("donna.routes")
router = APIRouter()

# ---------------------------------------------------------------------------
# Session store — persisted to SQLite so history survives restarts.
# ---------------------------------------------------------------------------

_store = SqliteStore()

# The default session for the single-user app. Scheduled briefings are
# written here so they're waiting when the user next opens Donna.
DEFAULT_SESSION = "default"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class TriggerRequest(BaseModel):
    event: str  # "morning_briefing" | "eod_wrap"
    session_id: str | None = None


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict


class UnsubscribeRequest(BaseModel):
    endpoint: str


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_DONE = object()  # sentinel: graph finished


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _run_and_stream(session_id: str, state: dict) -> AsyncGenerator[str, None]:
    """
    Run the graph in a worker thread while streaming the model's tokens to the
    client as they arrive. Control tokens are filtered out before display, and
    the authoritative cleaned response is persisted once the graph completes.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    sfilter = StreamFilter()
    emitted = {"any": False}

    def on_delta(delta: str) -> None:
        safe = sfilter.feed(delta)
        if safe:
            emitted["any"] = True
            loop.call_soon_threadsafe(queue.put_nowait, _sse({"chunk": safe}))

    state["stream_cb"] = on_delta
    history = state.get("history", [])
    holder: dict = {}

    async def runner():
        try:
            result = await loop.run_in_executor(None, donna_graph.invoke, state)
            holder["result"] = result
            # Persist as soon as the graph completes, so the turn is saved even
            # if the client disconnects before the stream finishes draining.
            _store.save_history(session_id, result.get("history", history))
        except Exception as e:  # noqa: BLE001
            holder["error"] = e
            logger.error("Graph error: %s", e, exc_info=True)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    task = asyncio.create_task(runner())

    while True:
        item = await queue.get()
        if item is _DONE:
            break
        yield item

    await task

    if "error" in holder:
        yield _sse({"error": "Sorry — I hit a problem. Please try again."})
        yield _sse({"done": True})
        return

    result = holder.get("result", {})
    tail = sfilter.flush()
    if tail:
        yield _sse({"chunk": tail})

    # Fallback: if nothing streamed (e.g. an unexpected path), send full text.
    if not emitted["any"] and not tail:
        yield _sse({"chunk": result.get("response", "I'm not sure how to respond to that.")})

    yield _sse({"done": True})


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@router.post("/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or DEFAULT_SESSION
    state = {
        "user_message": req.message,
        "history": _store.get_history(session_id),
    }
    return StreamingResponse(
        _run_and_stream(session_id, state),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ---------------------------------------------------------------------------
# Manual trigger endpoint
# ---------------------------------------------------------------------------

@router.post("/trigger")
async def trigger(req: TriggerRequest):
    event = req.event
    if event not in ("morning_briefing", "eod_wrap"):
        raise HTTPException(status_code=400, detail="event must be morning_briefing or eod_wrap")

    session_id = req.session_id or DEFAULT_SESSION
    messages = {
        "morning_briefing": "Good morning! Give me my morning briefing.",
        "eod_wrap": "It's end of day. Let's wrap up.",
    }
    state = {
        "user_message": messages[event],
        "history": _store.get_history(session_id),
        "intent": event,
    }
    return StreamingResponse(
        _run_and_stream(session_id, state),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ---------------------------------------------------------------------------
# Profile endpoint
# ---------------------------------------------------------------------------

@router.get("/profile")
async def get_profile():
    try:
        chroma = ChromaStore()
        profile = chroma.get_profile()
        return profile.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Tasks endpoints
# ---------------------------------------------------------------------------

def _task_to_dict(t) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "deadline": t.deadline.isoformat() if t.deadline else None,
        "duration_estimate": t.duration_estimate,
        "priority": t.priority.value,
        "status": t.status.value,
        "date_assigned": t.date_assigned,
        "tags": t.tags,
        "recurrence": t.recurrence.value,
        "recurrence_days": t.recurrence_days,
    }


@router.get("/tasks")
async def get_tasks(date: str = Query(default=None)):
    target_date = date or today_str()
    try:
        tasks = _store.get_tasks_for_date(target_date)
        return [_task_to_dict(t) for t in tasks]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_tasks(
    q: str = Query(default=None),
    priority: str = Query(default=None),
    status: str = Query(default=None),
    date: str = Query(default=None),
    tag: str = Query(default=None),
):
    try:
        tasks = _store.search_tasks(q=q, priority=priority, status=status, date=date, tag=tag)
        return [_task_to_dict(t) for t in tasks]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics")
async def analytics(days: int = Query(default=7, ge=1, le=90)):
    try:
        return _store.completion_stats(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Calendar events
# ---------------------------------------------------------------------------

def _event_to_dict(e) -> dict:
    return e.to_dict()


@router.get("/events")
async def get_events(days: int = Query(default=7, ge=1, le=60)):
    """Upcoming event occurrences over the next `days` days."""
    try:
        return [_event_to_dict(e) for e in _store.get_upcoming_events(days=days)]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/events/{event_id}")
async def delete_event(event_id: int):
    from scheduler.jobs import reschedule_event_reminders
    _store.delete_event(event_id)
    reschedule_event_reminders()
    return {"status": "deleted"}


@router.get("/calendar.ics")
async def export_calendar():
    """Download all events as an .ics file (with 15-min alarms) for Apple Calendar."""
    from agent.ics import export_ics
    ics = export_ics(_store.get_all_events())
    return Response(
        content=ics,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=donna.ics"},
    )


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    """
    Ingest a calendar from a screenshot (vision model) or an .ics file, create
    the events, and (re)schedule their reminders.
    """
    from agent.calendar_events import build_events
    from agent.ics import import_ics
    from agent.vision import extract_events_from_image
    from scheduler.jobs import reschedule_event_reminders

    data = await file.read()
    name = (file.filename or "").lower()
    ctype = (file.content_type or "").lower()

    try:
        if name.endswith(".ics") or "calendar" in ctype:
            events = import_ics(data)
        elif ctype.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            raw = extract_events_from_image(data, ctype or "image/png", today_str())
            events = build_events(raw)
        else:
            raise HTTPException(status_code=400, detail="Upload an image or an .ics file.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload parse error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Couldn't read that file.")

    created = [_event_to_dict(_store.add_event(e)) for e in events]
    reschedule_event_reminders()

    if created:
        msg = f"Added {len(created)} event{'s' if len(created) != 1 else ''} to your schedule."
    else:
        msg = "I couldn't find any events in that file."
    return {"created": created, "message": msg}


# ---------------------------------------------------------------------------
# Web Push
# ---------------------------------------------------------------------------

@router.get("/push/vapid-public-key")
async def vapid_public_key():
    from notify.push import VAPID_PUBLIC_KEY, push_enabled
    return {"key": VAPID_PUBLIC_KEY, "enabled": push_enabled()}


@router.post("/push/subscribe")
async def push_subscribe(sub: PushSubscription):
    _store.save_subscription(sub.model_dump())
    return {"status": "subscribed"}


@router.post("/push/unsubscribe")
async def push_unsubscribe(req: UnsubscribeRequest):
    _store.delete_subscription(req.endpoint)
    return {"status": "unsubscribed"}


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

@router.get("/history")
async def get_history(session_id: str = Query(default=DEFAULT_SESSION)):
    """Return persisted conversation history for a session."""
    return {"session_id": session_id, "messages": _store.get_history(session_id)}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok"}
