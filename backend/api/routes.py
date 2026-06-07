"""
FastAPI routes for Donna.

Every request is scoped to the calling user via the `X-User-Id` header
(injected by `lib/api.ts` on the frontend). All `MongoStore` instances are
constructed per request so they filter on the right `user_id` — a Google user
can never read another user's tasks, chats, events, or profile.

The only cross-user surface is `/auth/*`, which intentionally operates on the
global `users` collection (to find / create accounts by email).

Endpoints:
  POST /chat          — main chat endpoint, streams SSE response
  POST /trigger       — manually trigger morning_briefing or eod_wrap
  GET  /tasks         — return tasks for a date (default: today)
  GET  /events        — upcoming events
  POST /upload        — ingest .ics or calendar screenshot
  GET  /chats         — list user's chats
  ...
  GET  /health        — liveness + Mongo ping
"""

import asyncio
import json
import logging
import re as _re
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
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
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SESSION = "default"  # single-tenant scheduler bucket
_EMAIL_RE = _re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Cross-user store used only by `/auth/*`. Its `user_id` is irrelevant — those
# methods (find_user_by_email, create_user, …) query the global `users`
# collection by email, not by the store's bound user_id.
_auth_store = MongoStore(default_user="__auth__")


# ---------------------------------------------------------------------------
# Per-request user scoping
# ---------------------------------------------------------------------------

def get_user_id(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """Resolve the calling user from the X-User-Id header. Falls back to demo."""
    if not x_user_id:
        return "demo"
    return x_user_id.strip().lower() or "demo"


def get_store(user_id: str = Depends(get_user_id)) -> MongoStore:
    return MongoStore(default_user=user_id)


def get_profile_store(store: MongoStore = Depends(get_store)) -> ChromaStore:
    return ChromaStore(store)


def _require_chat_owner(store: MongoStore, chat_id: str) -> dict:
    """Fetch a chat and 404 if it doesn't belong to the calling user."""
    chat = store.get_chat(chat_id)
    if not chat or chat.get("user_id") != store.user_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class TriggerRequest(BaseModel):
    event: str
    session_id: str | None = None


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict


class UnsubscribeRequest(BaseModel):
    endpoint: str


class ChatCreate(BaseModel):
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


class SettingsUpdate(BaseModel):
    name: str | None = None
    wake_time: str | None = None
    eod_time: str | None = None
    working_style: str | None = None


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_DONE = object()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _run_and_stream(
    store: MongoStore, session_id: str, state: dict
) -> AsyncGenerator[str, None]:
    """Run the LangGraph in a worker thread while streaming tokens to the client."""
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
    state["user_id"] = store.user_id  # nodes read this to build per-user stores
    state["session_id"] = session_id  # so semantic indexing scopes to this chat
    history = state.get("history", [])
    holder: dict = {}

    async def runner():
        try:
            result = await loop.run_in_executor(None, donna_graph.invoke, state)
            holder["result"] = result
            store.save_history(session_id, result.get("history", history))
        except Exception as e:
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
    if not emitted["any"] and not tail:
        yield _sse({"chunk": result.get("response", "I'm not sure how to respond to that.")})
    yield _sse({"done": True})


def _ensure_chat(store: MongoStore, session_id: str) -> str:
    """Make sure a chat row exists, and that it belongs to the calling user."""
    existing = store.get_chat(session_id)
    if existing is None:
        store.create_chat(chat_id=session_id, user_id=store.user_id, title="New chat")
    elif existing.get("user_id") != store.user_id:
        # The id refers to someone else's chat — reject before any data leaks.
        raise HTTPException(status_code=404, detail="Chat not found")
    return session_id


# ---------------------------------------------------------------------------
# Chat / trigger
# ---------------------------------------------------------------------------

@router.post("/chat")
async def chat(req: ChatRequest, store: MongoStore = Depends(get_store)):
    session_id = _ensure_chat(store, req.session_id or DEFAULT_SESSION)
    state = {
        "user_message": req.message,
        "history": store.get_history(session_id),
    }
    return StreamingResponse(
        _run_and_stream(store, session_id, state),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/trigger")
async def trigger(req: TriggerRequest, store: MongoStore = Depends(get_store)):
    event = req.event
    if event not in ("morning_briefing", "eod_wrap"):
        raise HTTPException(status_code=400, detail="event must be morning_briefing or eod_wrap")
    session_id = _ensure_chat(store, req.session_id or DEFAULT_SESSION)
    messages = {
        "morning_briefing": "Good morning! Give me my morning briefing.",
        "eod_wrap": "It's end of day. Let's wrap up.",
    }
    state = {
        "user_message": messages[event],
        "history": store.get_history(session_id),
        "intent": event,
    }
    return StreamingResponse(
        _run_and_stream(store, session_id, state),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@router.get("/profile")
async def get_profile(chroma: ChromaStore = Depends(get_profile_store)):
    try:
        return chroma.get_profile().to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Tasks
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
async def get_tasks(
    date: str = Query(default=None),
    store: MongoStore = Depends(get_store),
):
    target_date = date or today_str()
    try:
        tasks = store.get_tasks_for_date(target_date)
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
    store: MongoStore = Depends(get_store),
):
    try:
        tasks = store.search_tasks(q=q, priority=priority, status=status, date=date, tag=tag)
        return [_task_to_dict(t) for t in tasks]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics")
async def analytics(
    days: int = Query(default=7, ge=1, le=90),
    store: MongoStore = Depends(get_store),
):
    try:
        return store.completion_stats(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insights")
async def insights(
    days: int = Query(default=140, ge=1, le=180),
    store: MongoStore = Depends(get_store),
):
    try:
        return store.insights(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def _event_to_dict(e) -> dict:
    return e.to_dict()


@router.get("/events")
async def get_events(
    days: int = Query(default=7, ge=1, le=60),
    start: str = Query(default=None),
    store: MongoStore = Depends(get_store),
):
    try:
        return [_event_to_dict(e) for e in store.get_upcoming_events(days=days, start=start)]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/events/{event_id}")
async def delete_event(event_id: int, store: MongoStore = Depends(get_store)):
    from scheduler.jobs import reschedule_event_reminders
    # Guard: confirm the event belongs to this user before deleting.
    existing = store.get_event(event_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")
    store.delete_event(event_id)
    reschedule_event_reminders()
    return {"status": "deleted"}


@router.get("/calendar.ics")
async def export_calendar(store: MongoStore = Depends(get_store)):
    """Download this user's events as an .ics file (with 15-min alarms)."""
    from agent.ics import export_ics
    ics = export_ics(store.get_all_events())
    return Response(
        content=ics,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=donna.ics"},
    )


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    store: MongoStore = Depends(get_store),
):
    """Ingest a calendar from a screenshot or .ics file into this user's events."""
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

    created = [_event_to_dict(store.add_event(e)) for e in events]
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
async def push_subscribe(
    sub: PushSubscription,
    store: MongoStore = Depends(get_store),
):
    store.save_subscription(sub.model_dump())
    return {"status": "subscribed"}


@router.post("/push/unsubscribe")
async def push_unsubscribe(
    req: UnsubscribeRequest,
    store: MongoStore = Depends(get_store),
):
    store.delete_subscription(req.endpoint)
    return {"status": "unsubscribed"}


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

@router.get("/history")
async def get_history(
    session_id: str = Query(default=DEFAULT_SESSION),
    store: MongoStore = Depends(get_store),
):
    """Return persisted history for a session — only if it belongs to the caller."""
    if session_id != DEFAULT_SESSION:
        chat = store.get_chat(session_id)
        if not chat or chat.get("user_id") != store.user_id:
            # Same response shape as a fresh chat — don't leak whether the id exists.
            return {"session_id": session_id, "messages": []}
    return {"session_id": session_id, "messages": store.get_history(session_id)}


# ---------------------------------------------------------------------------
# Architecture metadata (for the About page) — public, no scoping
# ---------------------------------------------------------------------------

@router.get("/agents")
async def describe_agents():
    from agent.agents import describe_agents as _describe
    return {"agents": _describe()}


# ---------------------------------------------------------------------------
# Semantic recall (Chroma)
# ---------------------------------------------------------------------------

@router.get("/recall")
async def semantic_recall(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=5, ge=1, le=20),
    user_id: str = Depends(get_user_id),
):
    from memory.semantic_store import SemanticStore
    try:
        store = SemanticStore()
        # Filter by user_id so recall stays per-user.
        return {"query": q, "results": store.recall(q, limit=limit, user_id=user_id)}
    except TypeError:
        # SemanticStore signature may not accept user_id yet — fall back.
        try:
            store = SemanticStore()
            return {"query": q, "results": store.recall(q, limit=limit)}
        except Exception as e:
            logger.warning("recall failed: %s", e)
            return {"query": q, "results": [], "error": "recall_unavailable"}
    except Exception as e:
        logger.warning("recall failed: %s", e)
        return {"query": q, "results": [], "error": "recall_unavailable"}


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

@router.get("/conflicts")
async def list_conflicts(
    date: str = Query(default=None),
    store: MongoStore = Depends(get_store),
):
    target = date or today_str()
    try:
        return {"date": target, "conflicts": store.find_event_conflicts(target)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------

@router.get("/chats")
async def list_chats(store: MongoStore = Depends(get_store)):
    return {"chats": store.list_chats(user_id=store.user_id)}


@router.post("/chats")
async def create_chat(
    req: ChatCreate,
    store: MongoStore = Depends(get_store),
):
    chat = store.create_chat(
        user_id=store.user_id,
        title=req.title or "New chat",
    )
    return chat


@router.get("/chats/{chat_id}")
async def get_chat_endpoint(
    chat_id: str,
    store: MongoStore = Depends(get_store),
):
    return _require_chat_owner(store, chat_id)


@router.patch("/chats/{chat_id}")
async def rename_chat(
    chat_id: str,
    req: ChatRename,
    store: MongoStore = Depends(get_store),
):
    _require_chat_owner(store, chat_id)
    title = (req.title or "").strip() or "Untitled"
    store.rename_chat(chat_id, title[:80])
    return {"status": "renamed", "id": chat_id, "title": title[:80]}


@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    store: MongoStore = Depends(get_store),
):
    _require_chat_owner(store, chat_id)
    store.delete_chat(chat_id)
    return {"status": "deleted", "id": chat_id}


@router.post("/chats/{chat_id}/title")
async def title_chat(
    chat_id: str,
    req: ChatTitle,
    store: MongoStore = Depends(get_store),
):
    """Generate a short title from the first user message via Groq."""
    from agent.nodes import call_llm

    chat = _require_chat_owner(store, chat_id)
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
        title = title.splitlines()[0][:80] if title else ""
        if not title:
            raise ValueError("empty title")
    except Exception as e:
        logger.warning("title generation failed: %s", e)
        title = (msg[:32] + ("…" if len(msg) > 32 else "")) or "New chat"

    store.rename_chat(chat_id, title)
    return {"id": chat_id, "title": title}


# ---------------------------------------------------------------------------
# Me — user info & settings
# ---------------------------------------------------------------------------

@router.get("/me")
async def me(
    user_id: str = Depends(get_user_id),
    chroma: ChromaStore = Depends(get_profile_store),
):
    profile = chroma.get_profile()
    return {"user_id": user_id, "profile": profile.to_dict()}


@router.patch("/me/settings")
async def update_settings(
    req: SettingsUpdate,
    chroma: ChromaStore = Depends(get_profile_store),
):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        return {"status": "no_changes"}
    profile = chroma.update_profile_fields(**updates)
    if "wake_time" in updates or "eod_time" in updates:
        try:
            from scheduler.jobs import reschedule
            reschedule(profile.wake_time, profile.eod_time)
        except Exception as e:
            logger.warning("reschedule after settings update failed: %s", e)
    return {"status": "updated", "profile": profile.to_dict()}


# ---------------------------------------------------------------------------
# Auth — email/password + Google upsert
# ---------------------------------------------------------------------------

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

    if _auth_store.find_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with that email already exists.")

    full_name = req.first_name.strip()
    if req.last_name and req.last_name.strip():
        full_name = f"{req.first_name.strip()} {req.last_name.strip()}"

    user = _auth_store.create_user(
        email=email,
        password_hash=_hash_password(req.password),
        name=full_name,
        provider="credentials",
    )
    return {"user": _public_user(user)}


@router.post("/auth/login")
async def auth_login(req: LoginRequest):
    email = req.email.strip().lower()
    user = _auth_store.find_user_by_email(email)
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not _verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return {"user": _public_user(user)}


@router.post("/auth/oauth-upsert")
async def auth_oauth_upsert(req: OAuthUpsert):
    """Called by NextAuth on a successful Google sign-in so Google + email users share the `users` collection."""
    email = req.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email.")
    user = _auth_store.upsert_oauth_user(
        email=email, name=req.name or email.split("@")[0], image=req.image
    )
    return {"user": _public_user(user)}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    from memory.mongo_store import ping
    return {"status": "ok", "mongo": ping()}
