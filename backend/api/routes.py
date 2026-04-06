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
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.graph import donna_graph
from memory.chroma_store import ChromaStore
from memory.sqlite_store import SqliteStore
from utils.time_utils import today_str

logger = logging.getLogger("donna.routes")
router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory session store  {session_id: [history messages]}
# ---------------------------------------------------------------------------

_sessions: dict[str, list[dict]] = {}


def get_sessions() -> dict:
    return _sessions


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class TriggerRequest(BaseModel):
    event: str  # "morning_briefing" | "eod_wrap"
    session_id: str | None = None


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

async def _stream_text(text: str) -> AsyncGenerator[str, None]:
    """Yield the response word-by-word as SSE data events."""
    words = text.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == 0 else " " + word
        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        await asyncio.sleep(0.02)  # slight delay for streaming effect
    yield f"data: {json.dumps({'done': True})}\n\n"


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@router.post("/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or "default"
    history = _sessions.get(session_id, [])

    state = {
        "user_message": req.message,
        "history": history,
    }

    # Run the graph (blocking in a thread so we don't block the event loop)
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, donna_graph.invoke, state)
    except Exception as e:
        logger.error("Graph error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    response_text = result.get("response", "I'm not sure how to respond to that.")
    new_history = result.get("history", history)
    _sessions[session_id] = new_history

    return StreamingResponse(
        _stream_text(response_text),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Manual trigger endpoint
# ---------------------------------------------------------------------------

@router.post("/trigger")
async def trigger(req: TriggerRequest):
    event = req.event
    if event not in ("morning_briefing", "eod_wrap"):
        raise HTTPException(status_code=400, detail="event must be morning_briefing or eod_wrap")

    session_id = req.session_id or f"trigger_{event}"
    history = _sessions.get(session_id, [])

    messages = {
        "morning_briefing": "Good morning! Give me my morning briefing.",
        "eod_wrap": "It's end of day. Let's wrap up.",
    }

    state = {
        "user_message": messages[event],
        "history": history,
        "intent": event,
    }

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, donna_graph.invoke, state)
    except Exception as e:
        logger.error("Trigger error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    response_text = result.get("response", "")
    new_history = result.get("history", history)
    _sessions[session_id] = new_history

    return StreamingResponse(
        _stream_text(response_text),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
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
# Tasks endpoint
# ---------------------------------------------------------------------------

@router.get("/tasks")
async def get_tasks(date: str = Query(default=None)):
    target_date = date or today_str()
    try:
        sqlite = SqliteStore()
        tasks = sqlite.get_tasks_for_date(target_date)
        return [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "deadline": t.deadline.isoformat() if t.deadline else None,
                "duration_estimate": t.duration_estimate,
                "priority": t.priority.value,
                "status": t.status.value,
                "date_assigned": t.date_assigned,
                "tags": t.tags,
            }
            for t in tasks
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok"}
