"""
LangGraph node implementations.

Each node receives the graph State, does work (LLM calls, DB reads/writes),
and returns a dict with state updates.
"""

import logging
import os
from datetime import datetime
from typing import Callable

from groq import Groq

from agent.calendar_events import build_events
from agent.parsing import (
    ALLOWED_PROFILE_FIELDS,
    ParseResult,
    extract_block,
    find_ids,
    has_token,
    loads_loose,
    parse_events,
    parse_profile_update,
    parse_tasks,
    strip_block,
)
from agent.prompts import (
    BASE_SYSTEM,
    CLASSIFY_INTENT_SYSTEM,
    INTENT_TO_EXTRA,
    ONBOARDING_EXTRA,
    build_system_prompt,
)
from memory.chroma_store import ChromaStore
from memory.mongo_store import MongoStore
from models.task import Priority, Recurrence, Task, TaskStatus
from models.user_profile import UserProfile
from utils.time_utils import today_str, tomorrow_str

logger = logging.getLogger("donna.nodes")

# ---------------------------------------------------------------------------
# Groq client
# ---------------------------------------------------------------------------

_groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))


def call_llm(
    messages: list[dict],
    system_prompt: str,
    temperature: float = 0.7,
    on_delta: Callable[[str], None] | None = None,
) -> str:
    """
    Call the LLM and return the full response text.

    When `on_delta` is provided, the response is streamed and each content delta
    is passed to the callback as it arrives (real time-to-first-token). The full
    text is still accumulated and returned so callers can parse control tokens.
    """
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    if on_delta is None:
        response = _groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=full_messages,
            temperature=temperature,
            max_tokens=1024,
        )
        return response.choices[0].message.content

    chunks: list[str] = []
    stream = _groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=full_messages,
        temperature=temperature,
        max_tokens=1024,
        stream=True,
    )
    for event in stream:
        delta = event.choices[0].delta.content or ""
        if delta:
            chunks.append(delta)
            on_delta(delta)
    return "".join(chunks)


def call_llm_with_tools(
    messages: list[dict],
    system_prompt: str,
    tools: list[dict],
    temperature: float = 0.3,
):
    """
    Non-streaming call that lets the model decide whether to call a tool.

    Returns the response message object, which carries either `.tool_calls`
    (structured action requests) or `.content` (a plain reply). This is the
    "decide" half of Donna's decide-then-narrate action loop — far more reliable
    than parsing structured data back out of free-form text.
    """
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    response = _groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=full_messages,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
        max_tokens=1024,
    )
    return response.choices[0].message


# Tool schema mirrors the Task model so the model returns clean, typed args.
CREATE_TASKS_TOOL = {
    "type": "function",
    "function": {
        "name": "create_tasks",
        "description": (
            "Save one or more tasks to the user's task list. Only call this once "
            "the user has clearly confirmed the task(s) they want to add."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "deadline": {"type": "string", "description": "ISO 8601 datetime, optional"},
                            "duration_estimate": {"type": "integer", "description": "minutes, optional"},
                            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                            "date_assigned": {"type": "string", "description": "YYYY-MM-DD; defaults to today"},
                            "recurrence": {"type": "string", "enum": ["none", "daily", "weekdays", "weekly"]},
                            "recurrence_days": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": 'lowercase 3-letter days, e.g. ["mon","wed"]',
                            },
                        },
                        "required": ["title"],
                    },
                }
            },
            "required": ["tasks"],
        },
    },
}


MARK_DONE_TOOL = {
    "type": "function",
    "function": {
        "name": "mark_tasks_done",
        "description": (
            "Mark one or more of today's tasks as completed. Use the task IDs "
            "listed in the system context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_ids": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["task_ids"],
        },
    },
}


MOVE_TASK_TOOL = {
    "type": "function",
    "function": {
        "name": "move_tasks",
        "description": (
            "Move one or more tasks to another day (defaults to tomorrow). Use the "
            "task IDs listed in the system context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_ids": {"type": "array", "items": {"type": "integer"}},
                "to_date": {"type": "string", "description": "YYYY-MM-DD; defaults to tomorrow"},
            },
            "required": ["task_ids"],
        },
    },
}


CREATE_EVENTS_TOOL = {
    "type": "function",
    "function": {
        "name": "create_events",
        "description": (
            "Save one or more timed calendar events. Only call this once the user "
            "has confirmed the event(s)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "date": {"type": "string", "description": "YYYY-MM-DD"},
                            "start_time": {"type": "string", "description": "HH:MM 24h"},
                            "end_time": {"type": "string", "description": "HH:MM 24h, optional"},
                            "location": {"type": "string"},
                            "recurrence": {"type": "string", "enum": ["none", "daily", "weekdays", "weekly"]},
                            "recurrence_days": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": 'lowercase 3-letter days, e.g. ["tue","fri"]',
                            },
                        },
                        "required": ["title", "date", "start_time"],
                    },
                }
            },
            "required": ["events"],
        },
    },
}


CANCEL_EVENTS_TOOL = {
    "type": "function",
    "function": {
        "name": "cancel_events",
        "description": (
            "Cancel/delete one or more calendar events the user no longer wants. "
            "Use the event IDs from the system context. Only call this once the "
            "user has clearly asked to cancel or remove the event(s)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "event_ids": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["event_ids"],
        },
    },
}


REPRIORITIZE_TOOL = {
    "type": "function",
    "function": {
        "name": "reprioritize_tasks",
        "description": "Change the priority of one or more of today's tasks. Use the task IDs from the system context.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_ids": {"type": "array", "items": {"type": "integer"}},
                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["task_ids", "priority"],
        },
    },
}


UPDATE_PROFILE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_profile",
        "description": (
            "Save new facts the user shared about themselves. Include only the "
            "fields they actually revealed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "occupation": {"type": "string"},
                "institution": {"type": "string"},
                "working_style": {"type": "string"},
                "procrastination_patterns": {"type": "string"},
                "wake_time": {"type": "string", "description": "HH:MM"},
                "eod_time": {"type": "string", "description": "HH:MM"},
                "known_people": {"type": "object", "description": "name -> relationship"},
                "known_priorities": {"type": "array", "items": {"type": "string"}},
                "preferences": {"type": "array", "items": {"type": "string"}},
                "major_goals_short": {"type": "array", "items": {"type": "string"}},
                "major_goals_long": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Shared stores (singletons — initialised lazily so tests can mock them)
# ---------------------------------------------------------------------------

# Stores are constructed PER REQUEST from the graph state's `user_id` so that
# nodes never accidentally read/write another user's data. The (state-less)
# scheduled jobs fall back to "default" — see scheduler/jobs.py.

def get_sqlite(state: dict | None = None) -> MongoStore:
    user_id = (state or {}).get("user_id") or "default"
    return MongoStore(default_user=user_id)


def get_chroma(state: dict | None = None) -> ChromaStore:
    return ChromaStore(get_sqlite(state))


def _day_alerts(sqlite) -> str:
    """
    Surface proactive warnings — double-booked events and an overloaded day — so
    Donna can flag them unprompted in briefings and check-ins instead of waiting
    to be asked. This is the "proactive assistant" behaviour.
    """
    alerts: list[str] = []
    try:
        for c in sqlite.find_event_conflicts(today_str()):
            a, b = c["a"], c["b"]
            alerts.append(f"'{a['title']}' ({a['start']}) overlaps '{b['title']}' ({b['start']})")
    except Exception as e:  # noqa: BLE001
        logger.debug("day_alerts conflicts skipped: %s", e)
    try:
        pending = [
            t for t in sqlite.get_tasks_for_date(today_str())
            if getattr(t.status, "value", t.status) != "done"
        ]
        total = sum((t.duration_estimate or 0) for t in pending)
        if total >= 360:
            alerts.append(
                f"Heavy day: ~{round(total / 60)}h of work across {len(pending)} tasks still to do"
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("day_alerts load skipped: %s", e)
    if not alerts:
        return ""
    return (
        "\n\nPROACTIVE ALERTS — work these into your reply naturally if relevant "
        "(don't just list them robotically):\n" + "\n".join(f"- {a}" for a in alerts)
    )


def _recall_memories(state: dict, k: int = 4) -> str:
    """
    Retrieve snippets from THIS user's past conversations that are semantically
    relevant to their current message, formatted for prompt injection.

    This is the retrieval half of Donna's long-term memory: the profile gives
    her stable facts, this gives her relevant *moments*. Failure is silent —
    personalization is a bonus, never a blocker on the chat path.
    """
    query = (state.get("user_message") or "").strip()
    if len(query) < 3:
        return ""
    try:
        from memory.semantic_store import SemanticStore
        hits = SemanticStore().recall(
            query, limit=k, user_id=state.get("user_id") or "default"
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("recall_memories skipped: %s", e)
        return ""

    lines: list[str] = []
    for h in hits:
        doc = (h.get("document") or "").strip().replace("\n", " ")
        if not doc:
            continue
        if len(doc) > 200:
            doc = doc[:200] + "…"
        who = "They said" if h.get("role") == "user" else "Donna said"
        lines.append(f"  - {who}: {doc}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers: build tasks + recover malformed control blocks via one retry
# ---------------------------------------------------------------------------

def _build_task(td: dict) -> Task:
    """Construct a Task from a validated task dict (title guaranteed present)."""
    deadline = None
    if td.get("deadline"):
        try:
            deadline = datetime.fromisoformat(td["deadline"])
        except (ValueError, TypeError):
            deadline = None

    try:
        priority = Priority(str(td.get("priority", "medium")).lower())
    except ValueError:
        priority = Priority.MEDIUM

    try:
        recurrence = Recurrence(str(td.get("recurrence", "none")).lower())
    except ValueError:
        recurrence = Recurrence.NONE

    recurrence_days = td.get("recurrence_days") or []
    if not isinstance(recurrence_days, list):
        recurrence_days = []

    # A recurring template starts generating from its start date; default to
    # today so it can fire immediately. One-off tasks default to tomorrow.
    default_date = today_str() if recurrence != Recurrence.NONE else tomorrow_str()

    return Task(
        title=str(td["title"]).strip(),
        date_assigned=td.get("date_assigned") or default_date,
        deadline=deadline,
        duration_estimate=td.get("duration_estimate"),
        priority=priority,
        recurrence=recurrence,
        recurrence_days=[str(x).lower()[:3] for x in recurrence_days],
    )


def _retry_for_block(
    history: list[dict],
    system: str,
    tag: str,
    parser: Callable[[str], ParseResult],
) -> ParseResult:
    """
    Ask the model once more to re-emit a valid control block, then re-parse.
    Used only after an initial parse failed. The conversational reply shown to
    the user is unchanged — this silently recovers just the structured payload.
    """
    corrective = (
        system
        + f"\n\nIMPORTANT: your previous <{tag}> block could not be parsed. "
        f"Reply with ONLY a single <{tag}>...</{tag}> block containing strictly "
        "valid JSON (double-quoted keys/strings, no trailing commas, no prose)."
    )
    try:
        retry_resp = call_llm(history, corrective, temperature=0.1)
    except Exception as e:  # network/LLM failure
        return ParseResult(False, error=f"retry call failed: {e}")

    block = extract_block(retry_resp, tag)
    if block is None:
        return ParseResult(False, error="retry produced no block")
    return parser(block)


# ---------------------------------------------------------------------------
# Node: check_onboarding
# ---------------------------------------------------------------------------

def check_onboarding(state: dict) -> dict:
    """
    Decide whether to run onboarding or proceed to intent classification.
    Returns next_node in state.
    """
    sqlite = get_sqlite(state)
    if sqlite.is_onboarding_complete():
        return {"next_node": "classify_intent"}
    return {"next_node": "onboarding"}


# ---------------------------------------------------------------------------
# Node: onboarding
# ---------------------------------------------------------------------------

def onboarding(state: dict) -> dict:
    """
    Multi-turn onboarding flow.  Donna asks questions and builds the profile.
    When she decides onboarding is complete she appends <ONBOARDING_COMPLETE>.
    """
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()

    system = build_system_prompt(profile, [], extra=ONBOARDING_EXTRA)
    history: list[dict] = state.get("history", [])

    # Add the current user message to history before calling LLM
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system, on_delta=state.get("stream_cb"))

    # Check if onboarding is complete
    if has_token(response, "<ONBOARDING_COMPLETE>"):
        response_clean = strip_block(response, "ONBOARDING_COMPLETE")
        # Extract whatever profile info we can from the conversation
        _save_profile_from_conversation(history + [{"role": "assistant", "content": response_clean}], profile, state)
        sqlite.complete_onboarding()
        return {
            "response": response_clean,
            "history": history + [{"role": "assistant", "content": response_clean}],
            "next_node": "end",
        }

    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


def _save_profile_from_conversation(
    history: list[dict],
    existing_profile: UserProfile,
    state: dict,
) -> None:
    """Ask the LLM to extract a profile JSON from the onboarding conversation."""
    chroma = get_chroma(state)
    extraction_prompt = """\
You are a data extraction assistant. Given this onboarding conversation, \
extract the user profile as a JSON object with these keys (use empty \
string / empty list / empty dict for unknown fields):

name, occupation, institution, major_goals_short (list), major_goals_long (list), \
working_style, procrastination_patterns, weekly_schedule (dict day->list), \
known_people (dict name->relation), known_priorities (list), preferences (list), \
wake_time (HH:MM), eod_time (HH:MM)

Respond with ONLY the JSON object, no explanation.\
"""
    try:
        raw = call_llm(history, extraction_prompt, temperature=0.2)
        data = loads_loose(raw)
        if isinstance(data, dict):
            profile = UserProfile.from_dict({**existing_profile.to_dict(), **data})
            chroma.save_profile(profile)
    except Exception as e:
        logger.warning("onboarding profile extraction failed: %s", e)


# ---------------------------------------------------------------------------
# Node: classify_intent
# ---------------------------------------------------------------------------

def classify_intent(state: dict) -> dict:
    """Classify the user's message into one of the known intents."""
    user_msg = state.get("user_message", "")
    history = state.get("history", [])

    # Build a short context for the classifier
    recent = history[-6:] if len(history) > 6 else history
    msgs = recent + [{"role": "user", "content": user_msg}]

    intent = call_llm(msgs, CLASSIFY_INTENT_SYSTEM, temperature=0.1).strip().lower()

    # Sanitise
    valid = {
        "morning_briefing", "task_input", "task_update",
        "emergency_replan", "general_checkin", "profile_update",
        "eod_wrap", "calendar", "onboarding",
    }
    if intent not in valid:
        intent = "general_checkin"

    return {"intent": intent, "next_node": intent}


# ---------------------------------------------------------------------------
# Node: morning_briefing
# ---------------------------------------------------------------------------

def morning_briefing(state: dict) -> dict:
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())
    events = sqlite.get_events_for_date(today_str())

    from agent.prompts import MORNING_BRIEFING_EXTRA
    system = build_system_prompt(profile, tasks, extra=MORNING_BRIEFING_EXTRA, todays_events=events, memories=_recall_memories(state))
    system += _day_alerts(sqlite)

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system, on_delta=state.get("stream_cb"))

    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: task_input
# ---------------------------------------------------------------------------

def task_input(state: dict) -> dict:
    """
    Add tasks via native tool-calling: the model decides (calls `create_tasks`
    only after the user confirms), we execute against the store, then narrate a
    streamed confirmation. Falls back to the control-token path if the tool pass
    errors, so reliability only ever increases.
    """
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import TASK_INPUT_TOOL_EXTRA
    system = build_system_prompt(
        profile, tasks, extra=TASK_INPUT_TOOL_EXTRA, memories=_recall_memories(state)
    )

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    stream_cb = state.get("stream_cb")

    try:
        msg = call_llm_with_tools(history, system, [CREATE_TASKS_TOOL])
    except Exception as e:  # noqa: BLE001
        logger.warning("task_input: tool pass failed (%s); using control-token fallback", e)
        return _task_input_via_tokens(state)

    tool_calls = getattr(msg, "tool_calls", None) or []

    # No action yet — the model is proposing tasks / asking to confirm.
    if not tool_calls:
        response = (msg.content or "").strip()
        if not response:
            return _task_input_via_tokens(state)
        if stream_cb:
            stream_cb(response)
        return {
            "response": response,
            "history": history + [{"role": "assistant", "content": response}],
            "next_node": "end",
        }

    # The user confirmed — execute the structured task list, then narrate.
    saved, titles = _execute_create_tasks(tool_calls, sqlite)
    response = _narrate_saved_tasks(history, titles, saved, stream_cb)
    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


def _execute_create_tasks(tool_calls, sqlite) -> tuple[int, list[str]]:
    """Validate + persist the tasks from one or more create_tasks tool calls."""
    import json
    saved = 0
    titles: list[str] = []
    for tc in tool_calls:
        if getattr(tc.function, "name", "") != "create_tasks":
            continue
        try:
            args = json.loads(tc.function.arguments or "{}")
        except (ValueError, TypeError) as e:
            logger.warning("create_tasks: bad arguments JSON: %s", e)
            continue
        # Reuse the existing validator as defense-in-depth, even on typed args.
        result = parse_tasks(json.dumps(args.get("tasks", [])))
        if not result.ok:
            logger.warning("create_tasks: validation failed: %s", result.error)
            continue
        for td in result.value:
            try:
                task = _build_task(td)
                # Dedup guard: skip if an identical, still-open task already
                # exists that day (e.g. the user re-confirms an already-added task).
                existing = sqlite.get_tasks_for_date(task.date_assigned)
                already = any(
                    e.title.strip().lower() == task.title.strip().lower()
                    and getattr(e.status, "value", e.status) != "done"
                    for e in existing
                )
                if already:
                    logger.info("create_tasks: skipping duplicate %r on %s", task.title, task.date_assigned)
                    titles.append(task.title)
                    continue
                sqlite.add_task(task)
                saved += 1
                titles.append(task.title)
            except Exception as e:  # noqa: BLE001
                logger.warning("create_tasks: could not save %r: %s", td, e)
    return saved, titles


def _narrate_saved_tasks(history, titles, saved, stream_cb) -> str:
    """Stream a warm, in-character confirmation of the just-saved tasks."""
    if saved == 0:
        msg = "I had trouble saving those — could you list them again?"
        if stream_cb:
            stream_cb(msg)
        return msg
    titles_str = "; ".join(t for t in titles if t) or f"{saved} task(s)"
    narrate_system = (
        "You are Donna. You just saved these tasks to the user's list: "
        f"{titles_str}. In 1-2 warm, concise sentences, confirm they're added and "
        "optionally nudge the next step. Do not output JSON, code, or bullet lists."
    )
    return call_llm(history, narrate_system, on_delta=stream_cb)


def _task_input_via_tokens(state: dict) -> dict:
    """Original control-token path, retained as a fallback for the tool pass."""
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import TASK_INPUT_EXTRA
    system = build_system_prompt(profile, tasks, extra=TASK_INPUT_EXTRA, memories=_recall_memories(state))

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system, on_delta=state.get("stream_cb"))

    block = extract_block(response, "TASKS_CONFIRMED")
    response_clean = strip_block(response, "TASKS_CONFIRMED")

    if block is not None:
        result = parse_tasks(block)
        if not result.ok:
            logger.warning("task_input: TASKS_CONFIRMED parse failed (%s); retrying", result.error)
            result = _retry_for_block(
                history + [{"role": "assistant", "content": response}],
                system, "TASKS_CONFIRMED", parse_tasks,
            )

        if result.ok:
            saved = 0
            for td in result.value:
                try:
                    sqlite.add_task(_build_task(td))
                    saved += 1
                except Exception as e:
                    logger.warning("task_input: could not save task %r: %s", td, e)
            if saved == 0:
                response_clean += "\n\nI had trouble saving those — could you list them again?"
        else:
            logger.error("task_input: giving up on TASKS_CONFIRMED (%s)", result.error)
            response_clean += "\n\nI couldn't save that cleanly — could you list the tasks again?"

    return {
        "response": response_clean,
        "history": history + [{"role": "assistant", "content": response_clean}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: task_update
# ---------------------------------------------------------------------------

def task_update(state: dict) -> dict:
    """
    Mark tasks done / move them via native tool-calling (decide -> narrate), with
    a graceful fallback to the control-token path on any tool error.
    """
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import TASK_UPDATE_EXTRA
    system = build_system_prompt(profile, tasks, extra=TASK_UPDATE_EXTRA, memories=_recall_memories(state))

    # Give the model the task IDs it should reference in the tools.
    task_id_context = "\n\nToday's tasks (use these IDs with the tools):\n" + "\n".join(
        f"  ID {t.id}: {t.title} [{t.status.value}]" for t in tasks
    )
    system = system + task_id_context + (
        "\n\nWhen the user reports finishing or wanting to move work, call "
        "mark_tasks_done / move_tasks with the right IDs. If they're only asking "
        "or nothing should change, just reply — don't call a tool."
    )

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    stream_cb = state.get("stream_cb")

    try:
        msg = call_llm_with_tools(history, system, [MARK_DONE_TOOL, MOVE_TASK_TOOL])
    except Exception as e:  # noqa: BLE001
        logger.warning("task_update: tool pass failed (%s); using control-token fallback", e)
        return _task_update_via_tokens(state)

    tool_calls = getattr(msg, "tool_calls", None) or []

    if not tool_calls:
        response = (msg.content or "").strip()
        if not response:
            return _task_update_via_tokens(state)
        if stream_cb:
            stream_cb(response)
        return {
            "response": response,
            "history": history + [{"role": "assistant", "content": response}],
            "next_node": "end",
        }

    done, moved = _execute_task_updates(tool_calls, sqlite)
    response = _narrate_task_update(history, done, moved, stream_cb)
    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


def _execute_task_updates(tool_calls, sqlite) -> tuple[int, int]:
    """Apply mark_tasks_done / move_tasks tool calls. Returns (#done, #moved)."""
    import json
    done = moved = 0
    for tc in tool_calls:
        name = getattr(tc.function, "name", "")
        try:
            args = json.loads(tc.function.arguments or "{}")
        except (ValueError, TypeError) as e:
            logger.warning("task_update: bad arguments JSON: %s", e)
            continue
        if name == "mark_tasks_done":
            for tid in args.get("task_ids", []):
                try:
                    sqlite.mark_done(int(tid))
                    done += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning("mark_done(%s) failed: %s", tid, e)
        elif name == "move_tasks":
            to_date = args.get("to_date") or tomorrow_str()
            for tid in args.get("task_ids", []):
                try:
                    sqlite.move_task(int(tid), to_date)
                    moved += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning("move_task(%s) failed: %s", tid, e)
    return done, moved


def _narrate_task_update(history, done, moved, stream_cb) -> str:
    """Stream a warm confirmation of what changed."""
    if done == 0 and moved == 0:
        msg = "I couldn't match that to a task — which one did you mean?"
        if stream_cb:
            stream_cb(msg)
        return msg
    parts = []
    if done:
        parts.append(f"marked {done} task(s) done")
    if moved:
        parts.append(f"moved {moved} task(s) to a later day")
    narrate_system = (
        "You are Donna. You just " + " and ".join(parts) + " for the user. In 1-2 "
        "warm, concise sentences, confirm it and point them to what's next. No "
        "JSON, code, or bullet lists."
    )
    return call_llm(history, narrate_system, on_delta=stream_cb)


def _task_update_via_tokens(state: dict) -> dict:
    """Original control-token path, retained as a fallback for the tool pass."""
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import TASK_UPDATE_EXTRA
    system = build_system_prompt(profile, tasks, extra=TASK_UPDATE_EXTRA, memories=_recall_memories(state))

    task_id_context = "\n\nTask IDs for today:\n" + "\n".join(
        f"  ID {t.id}: {t.title} [{t.status.value}]" for t in tasks
    )
    system = system + task_id_context + (
        "\n\nIf you identify a task as done, append: <MARK_DONE>task_id</MARK_DONE>"
        "\nIf a task should move to tomorrow, append: <MOVE_TASK>task_id</MOVE_TASK>"
    )

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system, on_delta=state.get("stream_cb"))

    for task_id in find_ids(response, "MARK_DONE"):
        try:
            sqlite.mark_done(task_id)
        except Exception as e:
            logger.warning("task_update: mark_done(%s) failed: %s", task_id, e)

    for task_id in find_ids(response, "MOVE_TASK"):
        try:
            sqlite.move_task(task_id, tomorrow_str())
        except Exception as e:
            logger.warning("task_update: move_task(%s) failed: %s", task_id, e)

    response_clean = strip_block(strip_block(response, "MARK_DONE"), "MOVE_TASK")

    return {
        "response": response_clean,
        "history": history + [{"role": "assistant", "content": response_clean}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: emergency_replan
# ---------------------------------------------------------------------------

def emergency_replan(state: dict) -> dict:
    """
    Actually replan the day: the model orchestrates real changes (add the urgent
    item, reprioritize, move what won't fit) via tools, then Donna narrates a
    decisive summary followed by a concrete diff of what changed. Falls back to a
    descriptive-only reply if the tool pass errors.
    """
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())
    events = sqlite.get_events_for_date(today_str())

    from agent.prompts import EMERGENCY_REPLAN_TOOL_EXTRA
    system = build_system_prompt(
        profile, tasks, extra=EMERGENCY_REPLAN_TOOL_EXTRA,
        todays_events=events, memories=_recall_memories(state),
    )
    task_id_context = "\n\nToday's tasks (use these IDs with the tools):\n" + "\n".join(
        f"  ID {t.id}: {t.title} [{t.priority.value}, {t.status.value}]" for t in tasks
    )
    system = system + task_id_context

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    stream_cb = state.get("stream_cb")
    tools = [REPRIORITIZE_TOOL, MOVE_TASK_TOOL, CREATE_TASKS_TOOL, CREATE_EVENTS_TOOL]

    try:
        msg = call_llm_with_tools(history, system, tools, temperature=0.4)
    except Exception as e:  # noqa: BLE001
        logger.warning("emergency_replan: tool pass failed (%s); using text fallback", e)
        return _emergency_replan_via_text(state)

    tool_calls = getattr(msg, "tool_calls", None) or []

    if not tool_calls:
        # The model judged nothing needs moving (or is asking a question).
        response = (msg.content or "").strip()
        if not response:
            return _emergency_replan_via_text(state)
        if stream_cb:
            stream_cb(response)
        return {
            "response": response,
            "history": history + [{"role": "assistant", "content": response}],
            "next_node": "end",
        }

    changes, undo_record = _execute_replan(tool_calls, sqlite)
    if changes:
        import json as _json
        try:
            sqlite.set_state("last_replan", _json.dumps(undo_record))
        except Exception as e:  # noqa: BLE001
            logger.warning("replan: could not store undo snapshot: %s", e)
    response = _narrate_replan(history, changes, stream_cb)
    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        # Structured payload so the UI can render a diff card + an Undo button.
        "replan": {"changes": changes, "undo": bool(changes)},
        "next_node": "end",
    }


def _execute_replan(tool_calls, sqlite) -> tuple[list[str], dict]:
    """
    Apply the replan tool calls. Returns (human-readable changes, undo_record).
    The undo_record captures the inverse of every change so /replan/undo can
    restore the day exactly.
    """
    import json
    from models.task import Priority
    changes: list[str] = []
    undo: dict = {"created_tasks": [], "created_events": [], "moved": [], "reprioritized": []}
    touched_events = False
    for tc in tool_calls:
        name = getattr(tc.function, "name", "")
        try:
            args = json.loads(tc.function.arguments or "{}")
        except (ValueError, TypeError) as e:
            logger.warning("replan: bad arguments JSON: %s", e)
            continue

        if name == "reprioritize_tasks":
            prio = (args.get("priority") or "high").lower()
            for tid in args.get("task_ids", []):
                try:
                    t = sqlite.get_task(int(tid))
                    if t and t.priority.value != prio:
                        undo["reprioritized"].append({"id": t.id, "from": t.priority.value})
                        t.priority = Priority(prio)
                        sqlite.update_task(t)
                        changes.append(f"Bumped '{t.title}' to {prio} priority")
                except Exception as e:  # noqa: BLE001
                    logger.warning("replan reprioritize(%s) failed: %s", tid, e)

        elif name == "move_tasks":
            to_date = args.get("to_date") or tomorrow_str()
            when = "tomorrow" if to_date == tomorrow_str() else to_date
            for tid in args.get("task_ids", []):
                try:
                    t = sqlite.get_task(int(tid))
                    if t:
                        undo["moved"].append({"id": t.id, "from": t.date_assigned})
                    sqlite.move_task(int(tid), to_date)
                    if t:
                        changes.append(f"Moved '{t.title}' to {when}")
                except Exception as e:  # noqa: BLE001
                    logger.warning("replan move(%s) failed: %s", tid, e)

        elif name == "create_tasks":
            result = parse_tasks(json.dumps(args.get("tasks", [])))
            if result.ok:
                for td in result.value:
                    try:
                        saved = sqlite.add_task(_build_task(td))
                        if getattr(saved, "id", None) is not None:
                            undo["created_tasks"].append(saved.id)
                        changes.append(f"Added task '{str(td.get('title','')).strip()}'")
                    except Exception as e:  # noqa: BLE001
                        logger.warning("replan add task failed: %s", e)

        elif name == "create_events":
            result = parse_events(json.dumps(args.get("events", [])))
            if result.ok:
                for ev in build_events(result.value):
                    try:
                        saved = sqlite.add_event(ev)
                        touched_events = True
                        if getattr(saved, "id", None) is not None:
                            undo["created_events"].append(saved.id)
                        changes.append(f"Added '{saved.title}' at {saved.start_time}")
                    except Exception as e:  # noqa: BLE001
                        logger.warning("replan add event failed: %s", e)

    if touched_events:
        _reschedule_reminders()
    return changes, undo


def _narrate_replan(history, changes, stream_cb) -> str:
    """Stream a calm, decisive summary, then append the concrete diff."""
    if not changes:
        msg = "I looked at your day and nothing needs shifting yet — you're in good shape. What came up?"
        if stream_cb:
            stream_cb(msg)
        return msg
    diff = "\n".join(f"- {c}" for c in changes)
    narrate_system = (
        "You are Donna. You just replanned the user's day and made these changes:\n"
        f"{diff}\n\nIn 1-2 calm, decisive sentences, tell them it's handled and what "
        "to focus on right now. Do NOT re-list the changes — they'll be shown below."
    )
    text = call_llm(history, narrate_system, on_delta=stream_cb)
    diff_block = "\n\n**Here's what I shifted:**\n" + diff
    if stream_cb:
        stream_cb(diff_block)
    return text + diff_block


def _emergency_replan_via_text(state: dict) -> dict:
    """Original descriptive-only replan, retained as a fallback."""
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import EMERGENCY_REPLAN_EXTRA
    system = build_system_prompt(profile, tasks, extra=EMERGENCY_REPLAN_EXTRA, memories=_recall_memories(state))

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system, on_delta=state.get("stream_cb"))

    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: general_checkin
# ---------------------------------------------------------------------------

def general_checkin(state: dict) -> dict:
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())
    events = sqlite.get_events_for_date(today_str())

    from agent.prompts import GENERAL_CHECKIN_EXTRA
    system = build_system_prompt(profile, tasks, extra=GENERAL_CHECKIN_EXTRA, todays_events=events, memories=_recall_memories(state))
    system += _day_alerts(sqlite)

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system, on_delta=state.get("stream_cb"))

    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: profile_update
# ---------------------------------------------------------------------------

def profile_update(state: dict) -> dict:
    """
    Save personal facts the user shares, via native tool-calling (decide ->
    narrate). Falls back to the control-token path on any tool error.
    """
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import PROFILE_UPDATE_TOOL_EXTRA
    system = build_system_prompt(profile, tasks, extra=PROFILE_UPDATE_TOOL_EXTRA)

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    stream_cb = state.get("stream_cb")

    try:
        msg = call_llm_with_tools(history, system, [UPDATE_PROFILE_TOOL])
    except Exception as e:  # noqa: BLE001
        logger.warning("profile_update: tool pass failed (%s); using control-token fallback", e)
        return _profile_update_via_tokens(state)

    tool_calls = getattr(msg, "tool_calls", None) or []

    if not tool_calls:
        response = (msg.content or "").strip()
        if not response:
            return _profile_update_via_tokens(state)
        if stream_cb:
            stream_cb(response)
        return {
            "response": response,
            "history": history + [{"role": "assistant", "content": response}],
            "next_node": "end",
        }

    fields = _execute_update_profile(tool_calls, chroma)
    narrate_system = (
        "You are Donna. You just noted these facts about the user: "
        f"{', '.join(fields) if fields else 'their latest update'}. Acknowledge it "
        "warmly in one sentence and continue naturally. No JSON, code, or lists."
    )
    response = call_llm(history, narrate_system, on_delta=stream_cb)
    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


def _execute_update_profile(tool_calls, chroma) -> list[str]:
    """Apply update_profile tool calls. Returns the field names that were saved."""
    import json
    saved_fields: list[str] = []
    for tc in tool_calls:
        if getattr(tc.function, "name", "") != "update_profile":
            continue
        try:
            args = json.loads(tc.function.arguments or "{}")
        except (ValueError, TypeError) as e:
            logger.warning("update_profile: bad arguments JSON: %s", e)
            continue
        fields = {k: v for k, v in args.items() if v not in (None, "", [], {})}
        if not fields:
            continue
        try:
            chroma.update_profile_fields(**fields)
            saved_fields.extend(fields.keys())
        except Exception as e:  # noqa: BLE001
            logger.warning("update_profile: save failed: %s", e)
    return saved_fields


def _profile_update_via_tokens(state: dict) -> dict:
    """Original control-token path, retained as a fallback for the tool pass."""
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import PROFILE_UPDATE_EXTRA
    system = build_system_prompt(profile, tasks, extra=PROFILE_UPDATE_EXTRA)

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system, on_delta=state.get("stream_cb"))

    block = extract_block(response, "PROFILE_UPDATE")
    response_clean = strip_block(response, "PROFILE_UPDATE")

    if block is not None:
        result = parse_profile_update(block)
        if not result.ok:
            logger.warning("profile_update: parse failed (%s); retrying", result.error)
            result = _retry_for_block(
                history + [{"role": "assistant", "content": response}],
                system, "PROFILE_UPDATE", parse_profile_update,
            )
        if result.ok and result.value:
            try:
                chroma.update_profile_fields(**result.value)
            except Exception as e:
                logger.warning("profile_update: save failed: %s", e)
        elif not result.ok:
            logger.warning("profile_update: gave up on PROFILE_UPDATE (%s)", result.error)

    return {
        "response": response_clean,
        "history": history + [{"role": "assistant", "content": response_clean}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: calendar  (create timed events from chat)
# ---------------------------------------------------------------------------

def calendar(state: dict) -> dict:
    """
    Create timed events via native tool-calling (decide -> narrate), preserving the
    conflict-detection layer and reminder rescheduling. Falls back to the
    control-token path on any tool error.
    """
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())
    events = sqlite.get_events_for_date(today_str())
    upcoming = sqlite.get_upcoming_events(days=14)

    from agent.prompts import CALENDAR_TOOL_EXTRA
    system = build_system_prompt(profile, tasks, extra=CALENDAR_TOOL_EXTRA, todays_events=events)
    # Give the model event IDs so it can cancel the right one on request.
    id_lines = "\n".join(
        f"  ID {e.id}: {e.title} on {e.date} at {e.start_time}"
        for e in upcoming if getattr(e, "id", None) is not None
    )
    if id_lines:
        system = system + "\n\nUpcoming event IDs (use these to cancel):\n" + id_lines

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    stream_cb = state.get("stream_cb")

    try:
        msg = call_llm_with_tools(history, system, [CREATE_EVENTS_TOOL, CANCEL_EVENTS_TOOL])
    except Exception as e:  # noqa: BLE001
        logger.warning("calendar: tool pass failed (%s); using control-token fallback", e)
        return _calendar_via_tokens(state)

    tool_calls = getattr(msg, "tool_calls", None) or []

    if not tool_calls:
        # Deterministic safety net for cancellation: the weaker model sometimes
        # replies instead of calling cancel_events. If the user clearly wants to
        # cancel and exactly one upcoming event matches, cancel it ourselves so
        # the action is reliable rather than model-dependent.
        umsg = (user_msg or "").lower()
        if any(k in umsg for k in ("cancel", "remove", "delete", "drop", "call off")):
            matches = [
                e for e in upcoming
                if getattr(e, "id", None) is not None and _event_matches_phrase(e.title, umsg)
            ]
            if len(matches) == 1:
                cancelled = _cancel_event_ids([matches[0].id], sqlite)
                response = _narrate_calendar_actions(history, [], 0, [], cancelled, stream_cb)
                return {
                    "response": response,
                    "history": history + [{"role": "assistant", "content": response}],
                    "next_node": "end",
                }

        response = (msg.content or "").strip()
        if not response:
            return _calendar_via_tokens(state)
        if stream_cb:
            stream_cb(response)
        return {
            "response": response,
            "history": history + [{"role": "assistant", "content": response}],
            "next_node": "end",
        }

    create_calls = [tc for tc in tool_calls if getattr(tc.function, "name", "") == "create_events"]
    cancel_calls = [tc for tc in tool_calls if getattr(tc.function, "name", "") == "cancel_events"]
    saved, titles, conflict_msgs = (
        _execute_create_events(create_calls, sqlite) if create_calls else (0, [], [])
    )
    cancelled = _execute_cancel_events(cancel_calls, sqlite) if cancel_calls else []
    # Backstop: the user clearly meant to cancel but nothing was removed (the model
    # called the wrong tool or a non-existent id). Try a deterministic single match.
    umsg = (user_msg or "").lower()
    if not cancelled and any(k in umsg for k in ("cancel", "remove", "delete", "drop", "call off")):
        current = sqlite.get_upcoming_events(days=14)
        m = [e for e in current if getattr(e, "id", None) is not None and _event_matches_phrase(e.title, umsg)]
        if len(m) == 1:
            cancelled = _cancel_event_ids([m[0].id], sqlite)
    response = _narrate_calendar_actions(history, titles, saved, conflict_msgs, cancelled, stream_cb)
    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


def _event_matches_phrase(title: str, msg: str) -> bool:
    """True if the lowercased user message clearly refers to this event title."""
    import re
    t = (title or "").lower().strip()
    if t and t in msg:
        return True
    tokens = [w for w in re.findall(r"[a-z0-9]+", t) if len(w) >= 4]
    return any(w in msg for w in tokens)


def _cancel_event_ids(event_ids, sqlite) -> list[str]:
    """Delete events by id; returns the titles that were cancelled."""
    cancelled: list[str] = []
    touched = False
    for eid in event_ids:
        try:
            ev = sqlite.get_event(int(eid))
            sqlite.delete_event(int(eid))
            touched = True
            cancelled.append(ev.title if ev else f"event {eid}")
        except Exception as e:  # noqa: BLE001
            logger.warning("cancel: could not delete %s: %s", eid, e)
    if touched:
        _reschedule_reminders()
    return cancelled


def _execute_cancel_events(tool_calls, sqlite) -> list[str]:
    """Delete the requested events; returns the titles that were cancelled."""
    import json
    ids: list = []
    for tc in tool_calls:
        if getattr(tc.function, "name", "") != "cancel_events":
            continue
        try:
            args = json.loads(tc.function.arguments or "{}")
        except (ValueError, TypeError) as e:
            logger.warning("cancel_events: bad arguments JSON: %s", e)
            continue
        ids.extend(args.get("event_ids", []))
    return _cancel_event_ids(ids, sqlite)


def _narrate_calendar_actions(history, titles, saved, conflict_msgs, cancelled, stream_cb) -> str:
    """Confirm whatever calendar changes were just made (adds and/or cancels)."""
    did: list[str] = []
    if saved:
        did.append("added " + "; ".join(t for t in titles if t))
    if cancelled:
        did.append("cancelled " + "; ".join(cancelled))
    if not did:
        msg = "I couldn't make that calendar change — could you restate it?"
        if stream_cb:
            stream_cb(msg)
        return msg
    narrate_system = (
        "You are Donna. You just updated the user's calendar — " + "; ".join(did) +
        ". In 1-2 warm, concise sentences, confirm the change(s). Do not output "
        "JSON, code, or bullet lists."
    )
    text = call_llm(history, narrate_system, on_delta=stream_cb)
    if conflict_msgs:
        extra = "\n\n" + "\n".join(conflict_msgs)
        if stream_cb:
            stream_cb(extra)
        text += extra
    return text


def _execute_create_events(tool_calls, sqlite) -> tuple[int, list[str], list[str]]:
    """Validate + persist events, returning (#saved, titles, conflict warnings)."""
    import json
    saved = 0
    titles: list[str] = []
    conflict_msgs: list[str] = []
    for tc in tool_calls:
        if getattr(tc.function, "name", "") != "create_events":
            continue
        try:
            args = json.loads(tc.function.arguments or "{}")
        except (ValueError, TypeError) as e:
            logger.warning("create_events: bad arguments JSON: %s", e)
            continue
        result = parse_events(json.dumps(args.get("events", [])))
        if not result.ok:
            logger.warning("create_events: validation failed: %s", result.error)
            continue
        for ev in build_events(result.value):
            # Conflict-resolution layer: flag overlaps but still save, so the user
            # can decide — silently dropping the write would be worse.
            try:
                overlaps = sqlite.conflicts_for_event(ev)
                saved_ev = sqlite.add_event(ev)
                saved += 1
                titles.append(saved_ev.title)
                if overlaps:
                    names = ", ".join(f"'{o.title}' ({o.start_time})" for o in overlaps)
                    conflict_msgs.append(
                        f"Heads up: '{saved_ev.title}' at {saved_ev.start_time} "
                        f"overlaps with {names}. Want me to move one?"
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("create_events: could not save event: %s", e)
    if saved:
        _reschedule_reminders()
    return saved, titles, conflict_msgs


def _narrate_saved_events(history, titles, saved, conflict_msgs, stream_cb) -> str:
    """Stream a warm confirmation, then append any conflict warnings verbatim."""
    if saved == 0:
        msg = "I had trouble adding those — could you restate the event?"
        if stream_cb:
            stream_cb(msg)
        return msg
    titles_str = "; ".join(t for t in titles if t) or f"{saved} event(s)"
    narrate_system = (
        "You are Donna. You just added these events to the user's calendar: "
        f"{titles_str}. In 1-2 warm, concise sentences, confirm they're on the "
        "calendar. Do not output JSON, code, or bullet lists."
    )
    text = call_llm(history, narrate_system, on_delta=stream_cb)
    if conflict_msgs:
        extra = "\n\n" + "\n".join(conflict_msgs)
        if stream_cb:
            stream_cb(extra)
        text += extra
    return text


def _calendar_via_tokens(state: dict) -> dict:
    """Original control-token path, retained as a fallback for the tool pass."""
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())
    events = sqlite.get_events_for_date(today_str())

    from agent.prompts import CALENDAR_EXTRA
    system = build_system_prompt(profile, tasks, extra=CALENDAR_EXTRA, todays_events=events)

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system, on_delta=state.get("stream_cb"))

    block = extract_block(response, "EVENTS_CONFIRMED")
    response_clean = strip_block(response, "EVENTS_CONFIRMED")

    if block is not None:
        result = parse_events(block)
        if not result.ok:
            logger.warning("calendar: EVENTS_CONFIRMED parse failed (%s); retrying", result.error)
            result = _retry_for_block(
                history + [{"role": "assistant", "content": response}],
                system, "EVENTS_CONFIRMED", parse_events,
            )
        if result.ok:
            saved = 0
            conflict_msgs: list[str] = []
            for ev in build_events(result.value):
                try:
                    overlaps = sqlite.conflicts_for_event(ev)
                    saved_ev = sqlite.add_event(ev)
                    saved += 1
                    if overlaps:
                        names = ", ".join(f"'{o.title}' ({o.start_time})" for o in overlaps)
                        conflict_msgs.append(
                            f"Heads up: '{saved_ev.title}' at {saved_ev.start_time} "
                            f"overlaps with {names}. Want me to move one?"
                        )
                except Exception as e:
                    logger.warning("calendar: could not save event: %s", e)
            if saved:
                _reschedule_reminders()
                if conflict_msgs:
                    response_clean += "\n\n" + "\n".join(conflict_msgs)
            else:
                response_clean += "\n\nI had trouble saving those — could you restate them?"
        else:
            logger.error("calendar: giving up on EVENTS_CONFIRMED (%s)", result.error)
            response_clean += "\n\nI couldn't add that cleanly — could you restate the event?"

    return {
        "response": response_clean,
        "history": history + [{"role": "assistant", "content": response_clean}],
        "next_node": "end",
    }


def _reschedule_reminders() -> None:
    """Rebuild event reminder jobs after a calendar change (best-effort)."""
    try:
        from scheduler.jobs import reschedule_event_reminders
        reschedule_event_reminders()
    except Exception as e:  # scheduler may not be running (e.g. in tests)
        logger.debug("reschedule reminders skipped: %s", e)


# ---------------------------------------------------------------------------
# Node: eod_wrap
# ---------------------------------------------------------------------------

def eod_wrap(state: dict) -> dict:
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()

    today = today_str()
    tmrw = tomorrow_str()
    all_tasks = sqlite.get_tasks_for_date(today)

    # Roll over incomplete tasks
    for task in all_tasks:
        if task.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
            if task.id is not None:
                sqlite.move_task(task.id, tmrw)

    # Refresh after mutations
    done_tasks = sqlite.get_tasks_by_status(TaskStatus.DONE, date=today)
    moved_tasks = sqlite.get_tasks_by_status(TaskStatus.MOVED, date=tmrw)

    from agent.prompts import EOD_WRAP_EXTRA
    system = build_system_prompt(profile, all_tasks, extra=EOD_WRAP_EXTRA)

    eod_context = (
        f"\n\nDone today: {[t.title for t in done_tasks]}"
        f"\nMoved to tomorrow: {[t.title for t in moved_tasks]}"
    )
    system = system + eod_context

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system, on_delta=state.get("stream_cb"))

    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: update_memory  (post-response memory extraction)
# ---------------------------------------------------------------------------

# Cheap signals that a user message might contain new personal info worth
# extracting. If none are present we skip the extraction LLM call entirely,
# which is the common case ("what's next?", "mark that done", "thanks").
_MEMORY_CUES = (
    "i'm", "i am", "im ", "my ", "i work", "i live", "i study", "i go to",
    "i prefer", "i like", "i love", "i hate", "i usually", "i tend", "i always",
    "i never", "call me", "my name", "i go by", "i have a", "based in",
    "remember that", "fyi", "by the way", "just so you know",
)


def _might_have_personal_info(text: str) -> bool:
    t = text.lower()
    return any(cue in t for cue in _MEMORY_CUES)


def update_memory(state: dict) -> dict:
    """
    After a response, opportunistically extract new user info and persist it.
    Also semantically index the assistant's response so future turns can recall
    relevant context via ChromaDB.

    Profile extraction is gated by a cheap heuristic so we don't fire a second
    LLM call on every turn — only when the user message plausibly contains
    something to learn. Semantic indexing always runs (no LLM cost).
    """
    # Semantic indexing always runs — never gated, never expensive. Failure is
    # silent so a broken vector store can't break the chat path.
    #
    # CRITICAL: every document MUST be tagged with this user's id. recall() filters
    # by user_id, so an untagged write (user_id="default") is invisible to a real
    # logged-in user and personalization silently does nothing. We index BOTH the
    # user's own words and Donna's reply — the user's words are the most valuable
    # thing to recall later ("you mentioned you hate morning meetings").
    try:
        from memory.semantic_store import SemanticStore
        store = SemanticStore()
        uid = state.get("user_id") or "default"
        sid = state.get("session_id", "default")

        user_msg = (state.get("user_message") or "").strip()
        if user_msg:
            store.index_message(session_id=sid, role="user", content=user_msg, user_id=uid)

        history_for_index = state.get("history", [])
        if history_for_index:
            last = history_for_index[-1]
            if last.get("role") == "assistant" and last.get("content"):
                store.index_message(
                    session_id=sid,
                    role="assistant",
                    content=last["content"],
                    user_id=uid,
                )
    except Exception as e:  # noqa: BLE001
        logger.debug("semantic index skipped: %s", e)

    intent = state.get("intent", "")
    # These intents already handle their own writes / aren't about the user.
    if intent in ("profile_update", "onboarding", "eod_wrap", "calendar"):
        return {"response": state.get("response", "")}

    history = state.get("history", [])
    if len(history) < 2:
        return {"response": state.get("response", "")}

    user_msg = state.get("user_message", "")
    if not _might_have_personal_info(user_msg):
        return {"response": state.get("response", "")}

    chroma = get_chroma(state)
    # Only look at the last exchange
    recent = history[-2:]
    extraction_prompt = """\
You are a data extraction assistant. Look at this conversation exchange and \
extract any NEW personal information the user revealed about themselves.

If you find nothing new, respond with exactly: {}

Otherwise respond with a JSON object with any of these keys:
name, occupation, institution, working_style, procrastination_patterns, \
known_people (dict), known_priorities (list), preferences (list), \
major_goals_short (list), major_goals_long (list), weekly_schedule (dict), \
wake_time (HH:MM), eod_time (HH:MM), notes (list)

Respond with ONLY the JSON, no explanation.\
"""
    try:
        raw = call_llm(recent, extraction_prompt, temperature=0.1)
        data = loads_loose(raw)
        if isinstance(data, dict) and data:
            allowed = {k: v for k, v in data.items() if k in ALLOWED_PROFILE_FIELDS}
            if allowed:
                chroma.update_profile_fields(**allowed)
    except Exception as e:
        logger.debug("update_memory: extraction skipped (%s)", e)

    return {"response": state.get("response", "")}
