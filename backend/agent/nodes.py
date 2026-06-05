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
    system = build_system_prompt(profile, tasks, extra=MORNING_BRIEFING_EXTRA, todays_events=events)

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
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import TASK_INPUT_EXTRA
    system = build_system_prompt(profile, tasks, extra=TASK_INPUT_EXTRA)

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system, on_delta=state.get("stream_cb"))

    # A TASKS_CONFIRMED block is only present once the user has confirmed.
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
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import TASK_UPDATE_EXTRA
    system = build_system_prompt(profile, tasks, extra=TASK_UPDATE_EXTRA)

    # Inject task IDs into system so LLM can reference them
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

    # Process any task mutations
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

    # Strip control tokens from response
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
    chroma = get_chroma(state)
    sqlite = get_sqlite(state)
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import EMERGENCY_REPLAN_EXTRA
    system = build_system_prompt(profile, tasks, extra=EMERGENCY_REPLAN_EXTRA)

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
    system = build_system_prompt(profile, tasks, extra=GENERAL_CHECKIN_EXTRA, todays_events=events)

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

    # Extract and apply profile updates
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
                # Conflict-resolution layer: check overlaps *before* saving so we
                # can flag them to the user. We still save, then let the user
                # decide to reschedule — silently dropping the write would be
                # worse than a clear collision warning.
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
    try:
        from memory.semantic_store import SemanticStore
        history_for_index = state.get("history", [])
        if history_for_index:
            last = history_for_index[-1]
            if last.get("role") == "assistant" and last.get("content"):
                SemanticStore().index_message(
                    session_id=state.get("session_id", "default"),
                    role="assistant",
                    content=last["content"],
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
