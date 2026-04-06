"""
LangGraph node implementations.

Each node receives the graph State, does work (LLM calls, DB reads/writes),
and returns a dict with state updates.
"""

import json
import os
import re
from datetime import datetime
from typing import Any

from groq import Groq

from agent.prompts import (
    BASE_SYSTEM,
    CLASSIFY_INTENT_SYSTEM,
    INTENT_TO_EXTRA,
    ONBOARDING_EXTRA,
    build_system_prompt,
)
from memory.chroma_store import ChromaStore
from memory.sqlite_store import SqliteStore
from models.task import Priority, Task, TaskStatus
from models.user_profile import UserProfile
from utils.time_utils import today_str, tomorrow_str

# ---------------------------------------------------------------------------
# Groq client
# ---------------------------------------------------------------------------

_groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))


def call_llm(messages: list[dict], system_prompt: str, temperature: float = 0.7) -> str:
    response = _groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system_prompt}] + messages,
        temperature=temperature,
        max_tokens=1024,
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Shared stores (singletons — initialised lazily so tests can mock them)
# ---------------------------------------------------------------------------

_sqlite_store: SqliteStore | None = None
_chroma_store: ChromaStore | None = None


def get_sqlite() -> SqliteStore:
    global _sqlite_store
    if _sqlite_store is None:
        _sqlite_store = SqliteStore()
    return _sqlite_store


def get_chroma() -> ChromaStore:
    global _chroma_store
    if _chroma_store is None:
        _chroma_store = ChromaStore()
    return _chroma_store


# ---------------------------------------------------------------------------
# Helper: extract JSON blocks from LLM output
# ---------------------------------------------------------------------------

def _extract_block(text: str, tag: str) -> str | None:
    """Extract content between <TAG> ... </TAG>."""
    pattern = rf"<{tag}>(.*?)</{tag}>"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Node: check_onboarding
# ---------------------------------------------------------------------------

def check_onboarding(state: dict) -> dict:
    """
    Decide whether to run onboarding or proceed to intent classification.
    Returns next_node in state.
    """
    sqlite = get_sqlite()
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
    chroma = get_chroma()
    sqlite = get_sqlite()
    profile = chroma.get_profile()

    system = build_system_prompt(profile, [], extra=ONBOARDING_EXTRA)
    history: list[dict] = state.get("history", [])

    # Add the current user message to history before calling LLM
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system)

    # Check if onboarding is complete
    if "<ONBOARDING_COMPLETE>" in response:
        response_clean = response.replace("<ONBOARDING_COMPLETE>", "").strip()
        # Extract whatever profile info we can from the conversation
        _save_profile_from_conversation(history + [{"role": "assistant", "content": response_clean}], profile)
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


def _save_profile_from_conversation(history: list[dict], existing_profile: UserProfile) -> None:
    """Ask the LLM to extract a profile JSON from the onboarding conversation."""
    chroma = get_chroma()
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
        # Strip markdown code fences if present
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        profile = UserProfile.from_dict({**existing_profile.to_dict(), **data})
        chroma.save_profile(profile)
    except Exception:
        pass  # Best-effort — don't crash onboarding on extraction failure


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
        "eod_wrap", "onboarding",
    }
    if intent not in valid:
        intent = "general_checkin"

    return {"intent": intent, "next_node": intent}


# ---------------------------------------------------------------------------
# Node: morning_briefing
# ---------------------------------------------------------------------------

def morning_briefing(state: dict) -> dict:
    chroma = get_chroma()
    sqlite = get_sqlite()
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import MORNING_BRIEFING_EXTRA
    system = build_system_prompt(profile, tasks, extra=MORNING_BRIEFING_EXTRA)

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system)

    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: task_input
# ---------------------------------------------------------------------------

def task_input(state: dict) -> dict:
    chroma = get_chroma()
    sqlite = get_sqlite()
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import TASK_INPUT_EXTRA
    system = build_system_prompt(profile, tasks, extra=TASK_INPUT_EXTRA)

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system)

    # Check if tasks were confirmed
    tasks_json_str = _extract_block(response, "TASKS_CONFIRMED")
    if tasks_json_str:
        response_clean = re.sub(
            r"<TASKS_CONFIRMED>.*?</TASKS_CONFIRMED>", "", response, flags=re.DOTALL
        ).strip()
        try:
            tasks_data = json.loads(tasks_json_str)
            for td in tasks_data:
                # Determine date_assigned
                date_assigned = td.get("date_assigned", tomorrow_str())
                # Parse deadline
                deadline = None
                if td.get("deadline"):
                    try:
                        deadline = datetime.fromisoformat(td["deadline"])
                    except ValueError:
                        pass
                priority_str = td.get("priority", "medium").lower()
                try:
                    priority = Priority(priority_str)
                except ValueError:
                    priority = Priority.MEDIUM

                task = Task(
                    title=td["title"],
                    date_assigned=date_assigned,
                    deadline=deadline,
                    duration_estimate=td.get("duration_estimate"),
                    priority=priority,
                )
                sqlite.add_task(task)
        except Exception:
            pass  # Best-effort

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


# ---------------------------------------------------------------------------
# Node: task_update
# ---------------------------------------------------------------------------

def task_update(state: dict) -> dict:
    chroma = get_chroma()
    sqlite = get_sqlite()
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

    response = call_llm(history, system)

    # Process any task mutations
    for match in re.finditer(r"<MARK_DONE>(\d+)</MARK_DONE>", response):
        task_id = int(match.group(1))
        try:
            sqlite.mark_done(task_id)
        except Exception:
            pass

    for match in re.finditer(r"<MOVE_TASK>(\d+)</MOVE_TASK>", response):
        task_id = int(match.group(1))
        try:
            sqlite.move_task(task_id, tomorrow_str())
        except Exception:
            pass

    # Strip control tokens from response
    response_clean = re.sub(r"<(?:MARK_DONE|MOVE_TASK)>\d+</(?:MARK_DONE|MOVE_TASK)>", "", response).strip()

    return {
        "response": response_clean,
        "history": history + [{"role": "assistant", "content": response_clean}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: emergency_replan
# ---------------------------------------------------------------------------

def emergency_replan(state: dict) -> dict:
    chroma = get_chroma()
    sqlite = get_sqlite()
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import EMERGENCY_REPLAN_EXTRA
    system = build_system_prompt(profile, tasks, extra=EMERGENCY_REPLAN_EXTRA)

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system)

    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: general_checkin
# ---------------------------------------------------------------------------

def general_checkin(state: dict) -> dict:
    chroma = get_chroma()
    sqlite = get_sqlite()
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import GENERAL_CHECKIN_EXTRA
    system = build_system_prompt(profile, tasks, extra=GENERAL_CHECKIN_EXTRA)

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system)

    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: profile_update
# ---------------------------------------------------------------------------

def profile_update(state: dict) -> dict:
    chroma = get_chroma()
    sqlite = get_sqlite()
    profile = chroma.get_profile()
    tasks = sqlite.get_tasks_for_date(today_str())

    from agent.prompts import PROFILE_UPDATE_EXTRA
    system = build_system_prompt(profile, tasks, extra=PROFILE_UPDATE_EXTRA)

    history = state.get("history", [])
    user_msg = state.get("user_message", "")
    if user_msg:
        history = history + [{"role": "user", "content": user_msg}]

    response = call_llm(history, system)

    # Extract and apply profile updates
    update_json_str = _extract_block(response, "PROFILE_UPDATE")
    if update_json_str:
        try:
            update_data = json.loads(update_json_str)
            chroma.update_profile_fields(**update_data)
        except Exception:
            pass

    # Strip the control token from the response
    response_clean = re.sub(
        r"<PROFILE_UPDATE>.*?</PROFILE_UPDATE>", "", response, flags=re.DOTALL
    ).strip()

    return {
        "response": response_clean,
        "history": history + [{"role": "assistant", "content": response_clean}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: eod_wrap
# ---------------------------------------------------------------------------

def eod_wrap(state: dict) -> dict:
    chroma = get_chroma()
    sqlite = get_sqlite()
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

    response = call_llm(history, system)

    return {
        "response": response,
        "history": history + [{"role": "assistant", "content": response}],
        "next_node": "end",
    }


# ---------------------------------------------------------------------------
# Node: update_memory  (post-response memory extraction)
# ---------------------------------------------------------------------------

def update_memory(state: dict) -> dict:
    """
    After any response, opportunistically extract new user info and persist it.
    This node is lightweight — any failure is silently swallowed.
    """
    intent = state.get("intent", "")
    # We only do post-response memory extraction for conversational intents
    if intent in ("profile_update", "onboarding", "eod_wrap"):
        return {"response": state.get("response", "")}

    chroma = get_chroma()
    history = state.get("history", [])
    if len(history) < 2:
        return {"response": state.get("response", "")}

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
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        if data:
            chroma.update_profile_fields(**data)
    except Exception:
        pass

    return {"response": state.get("response", "")}
