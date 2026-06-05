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
from memory.mongo_store import MongoStore
from utils.stream_filter import StreamFilter
from utils.time_utils import today_str

logger = logging.getLogger("donna.routes")
router = APIRouter()

# ---------------------------------------------------------------------------
# Session store — persisted to SQLite so history survives restarts.
# ---------------------------------------------------------------------------

_store = MongoStore()

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


class ChatCreate(BaseModel):
    user_id: str | None = None
    title: str | None = None


class ChatRename(BaseModel):
    title: str


class ChatTitle(BaseModel):
    first_message: str


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str | None = None
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class OAuthUpsert(BaseModel):
    email: str
    name: str | None = None
    image: str | None = None


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

def _ensure_chat(session_id: str) -> str:
    """
    Make sure a chat row exists for this session_id. If the caller passed the
    legacy "default" id (or omitted it), keep using it so old links work; for
    new ids, create the chat row on first message.
    """
    existing = _store.get_chat(session_id)
    if existing is None:
        _store.create_chat(chat_id=session_id, title="New chat")
    return session_id


@router.post("/chat")
async def chat(req: ChatRequest):
    session_id = _ensure_chat(req.session_id or DEFAULT_SESSION)
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

    session_id = _ensure_chat(req.session_id or DEFAULT_SESSION)
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
# Architecture metadata (for the About page)
# ---------------------------------------------------------------------------

@router.get("/agents")
async def describe_agents():
    """Return the four specialist agents and the nodes each one owns."""
    from agent.agents import describe_agents as _describe
    return {"agents": _describe()}


# ---------------------------------------------------------------------------
# Semantic recall (ChromaDB)
# ---------------------------------------------------------------------------

@router.get("/recall")
async def semantic_recall(q: str = Query(..., min_length=2), limit: int = Query(default=5, ge=1, le=20)):
    """Semantic search over indexed assistant messages."""
    from memory.semantic_store import SemanticStore
    try:
        store = SemanticStore()
        return {"query": q, "results": store.recall(q, limit=limit)}
    except Exception as e:
        logger.warning("recall failed: %s", e)
        return {"query": q, "results": [], "error": "recall_unavailable"}


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

@router.get("/conflicts")
async def list_conflicts(date: str = Query(default=None)):
    """Return all event-overlap conflicts for a date (default: today)."""
    target = date or today_str()
    try:
        conflicts = _store.find_event_conflicts(target)
        return {"date": target, "conflicts": conflicts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Chats — multi-conversation support
# ---------------------------------------------------------------------------

@router.get("/chats")
async def list_chats(user_id: str = Query(default="default")):
    return {"chats": _store.list_chats(user_id=user_id)}


@router.post("/chats")
async def create_chat(req: ChatCreate):
    chat = _store.create_chat(user_id=req.user_id or "default", title=req.title or "New chat")
    return chat


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str):
    chat = _store.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.patch("/chats/{chat_id}")
async def rename_chat(chat_id: str, req: ChatRename):
    title = (req.title or "").strip() or "Untitled"
    _store.rename_chat(chat_id, title[:80])
    return {"status": "renamed", "id": chat_id, "title": title[:80]}


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    _store.delete_chat(chat_id)
    return {"status": "deleted", "id": chat_id}


@router.post("/chats/{chat_id}/title")
async def title_chat(chat_id: str, req: ChatTitle):
    """
    Generate a short, sharp 3–5 word title from the first user message via Groq.
    Falls back to a truncated message if the LLM call fails.
    """
    from agent.nodes import call_llm

    chat = _store.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    msg = (req.first_message or "").strip()
    if not msg:
        return {"id": chat_id, "title": chat["title"]}

    system = (
        "You write 3-5 word chat titles. Title-case. No quotes. No trailing "
        "punctuation. No emojis. Respond with ONLY the title."
    )
    try:
        raw = call_llm(
            [{"role": "user", "content": msg[:400]}],
            system,
            temperature=0.4,
        )
        title = (raw or "").strip().strip('"').strip("'")
        # Defensive trim: in case the model rambles, take first line / clip.
        title = title.splitlines()[0][:80] if title else ""
        if not title:
            raise ValueError("empty title")
    except Exception as e:
        logger.warning("title generation failed: %s", e)
        title = (msg[:32] + ("…" if len(msg) > 32 else "")) or "New chat"

    _store.rename_chat(chat_id, title)
    return {"id": chat_id, "title": title}


# ---------------------------------------------------------------------------
# Me — user info & settings
# ---------------------------------------------------------------------------

@router.get("/me")
async def me():
    """Return the current user's profile + settings (single-user app for now)."""
    chroma = ChromaStore()
    profile = chroma.get_profile()
    return {
        "user_id": "default",
        "profile": profile.to_dict(),
    }


class SettingsUpdate(BaseModel):
    name: str | None = None
    wake_time: str | None = None
    eod_time: str | None = None
    working_style: str | None = None


@router.patch("/me/settings")
async def update_settings(req: SettingsUpdate):
    """Update a subset of profile settings (name, times, working style)."""
    chroma = ChromaStore()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        return {"status": "no_changes"}
    profile = chroma.update_profile_fields(**updates)
    # If wake/eod changed, reschedule the briefing jobs.
    if "wake_time" in updates or "eod_time" in updates:
        try:
            from scheduler.jobs import reschedule
            reschedule(profile.wake_time, profile.eod_time)
        except Exception as e:
            logger.warning("reschedule after settings update failed: %s", e)
    return {"status": "updated", "profile": profile.to_dict()}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Auth — email/password + Google upsert
# ---------------------------------------------------------------------------

import re as _re
_EMAIL_RE = _re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _public_user(u: dict) -> dict:
    return {
        "id": u.get("_id"),
        "email": u.get("email"),
        "name": u.get("name"),
        "image": u.get("image"),
        "provider": u.get("provider"),
    }


@router.post("/auth/register")
async def auth_register(req: RegisterRequest):
    email = req.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    if not req.first_name.strip():
        raise HTTPException(status_code=400, detail="First name is required.")

    if _store.find_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with that email already exists.")

    full_name = req.first_name.strip()
    if req.last_name and req.last_name.strip():
        full_name = f"{req.first_name.strip()} {req.last_name.strip()}"

    user = _store.create_user(
        email=email,
        password_hash=_hash_password(req.password),
        name=full_name,
        provider="credentials",
    )
    return {"user": _public_user(user)}


@router.post("/auth/login")
async def auth_login(req: LoginRequest):
    email = req.email.strip().lower()
    user = _store.find_user_by_email(email)
    if not user or not user.get("password_hash"):
        # Same error message either way — don't leak which emails exist.
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not _verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return {"user": _public_user(user)}


@router.post("/auth/oauth-upsert")
async def auth_oauth_upsert(req: OAuthUpsert):
    """
    Called from NextAuth when a Google sign-in succeeds. Creates or fetches the
    user record so OAuth and email/password users share the same `users` table.
    """
    email = req.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email.")
    user = _store.upsert_oauth_user(
        email=email, name=req.name or email.split("@")[0], image=req.image
    )
    return {"user": _public_user(user)}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    from memory.mongo_store import ping
    return {"status": "ok", "mongo": ping()}
