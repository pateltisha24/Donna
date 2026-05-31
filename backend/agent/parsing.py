"""
Robust parsing of Donna's control tokens.

The agent embeds structured payloads in its replies using XML-like control
tokens:

    <TASKS_CONFIRMED> [ ...json... ] </TASKS_CONFIRMED>
    <PROFILE_UPDATE>  { ...json... } </PROFILE_UPDATE>
    <MARK_DONE>id</MARK_DONE>
    <MOVE_TASK>id</MOVE_TASK>
    <ONBOARDING_COMPLETE>

Llama 3.3 on Groq emits these imperfectly: missing closing tags, markdown code
fences inside the block, trailing commas, single quotes, stray prose. This
module extracts and repairs those payloads, validates them against our
schemas, and reports failures explicitly so callers never silently drop data.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

# UserProfile fields a PROFILE_UPDATE block is allowed to touch.
ALLOWED_PROFILE_FIELDS = {
    "name", "occupation", "institution", "working_style",
    "procrastination_patterns", "known_people", "known_priorities",
    "preferences", "major_goals_short", "major_goals_long",
    "weekly_schedule", "wake_time", "eod_time", "notes",
}


@dataclass
class ParseResult:
    ok: bool
    value: Any = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Token extraction / stripping
# ---------------------------------------------------------------------------

def extract_block(text: str, tag: str) -> Optional[str]:
    """
    Return the inner content of <TAG>...</TAG>, tolerating a missing closing
    tag (in which case everything after the opening tag is returned).
    Returns None when the opening tag is absent.
    """
    full = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
    if full:
        return full.group(1).strip()
    dangling = re.search(rf"<{tag}>(.*)", text, re.DOTALL | re.IGNORECASE)
    if dangling:
        return dangling.group(1).strip()
    return None


def strip_block(text: str, tag: str) -> str:
    """Remove a control block (paired, dangling, or bare) and tidy whitespace."""
    text = re.sub(rf"<{tag}>.*?</{tag}>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(rf"<{tag}>.*", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(rf"</?{tag}>", "", text, flags=re.IGNORECASE)
    return text.strip()


def has_token(text: str, token: str) -> bool:
    """Case-insensitive presence check for a bare marker like ONBOARDING_COMPLETE."""
    return token.lower() in text.lower()


def find_ids(text: str, tag: str) -> list[int]:
    """Extract integer ids from <TAG>id</TAG> occurrences."""
    return [
        int(m.group(1))
        for m in re.finditer(rf"<{tag}>\s*(\d+)\s*</{tag}>", text, re.IGNORECASE)
    ]


# ---------------------------------------------------------------------------
# Loose JSON parsing (with common LLM-output repairs)
# ---------------------------------------------------------------------------

def _extract_json_span(s: str) -> Optional[str]:
    """Return the substring from the first { or [ to its matching last } or ]."""
    candidates = [i for i in (s.find("{"), s.find("[")) if i != -1]
    if not candidates:
        return None
    start = min(candidates)
    close = "}" if s[start] == "{" else "]"
    end = s.rfind(close)
    if end == -1 or end < start:
        return None
    return s[start : end + 1]


def loads_loose(raw: Optional[str]) -> Any:
    """
    Best-effort JSON parse. Strips markdown fences, then tries progressively
    more aggressive repairs (trailing-comma removal, JSON-span extraction).
    Raises ValueError if nothing parses.
    """
    if not raw or not raw.strip():
        raise ValueError("empty payload")

    s = raw.strip()
    s = re.sub(r"^```(?:json)?", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"```$", "", s).strip()

    attempts = [s]
    no_trailing = re.sub(r",\s*([}\]])", r"\1", s)
    attempts.append(no_trailing)
    span = _extract_json_span(s)
    if span is not None:
        attempts.append(span)
        attempts.append(re.sub(r",\s*([}\]])", r"\1", span))

    for attempt in attempts:
        try:
            return json.loads(attempt)
        except (json.JSONDecodeError, ValueError):
            continue
    raise ValueError("could not parse JSON payload")


# ---------------------------------------------------------------------------
# Schema-aware parsers
# ---------------------------------------------------------------------------

def parse_tasks(raw: str) -> ParseResult:
    """Parse and validate a TASKS_CONFIRMED payload into a list of task dicts."""
    try:
        data = loads_loose(raw)
    except ValueError as e:
        return ParseResult(False, error=f"invalid JSON: {e}")

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return ParseResult(False, error="expected a JSON array of tasks")

    valid = [
        item for item in data
        if isinstance(item, dict) and str(item.get("title", "")).strip()
    ]
    if not valid:
        return ParseResult(False, error="no tasks with a non-empty title")
    return ParseResult(True, value=valid)


def parse_events(raw: str) -> ParseResult:
    """Parse and validate an EVENTS_CONFIRMED payload into a list of event dicts."""
    try:
        data = loads_loose(raw)
    except ValueError as e:
        return ParseResult(False, error=f"invalid JSON: {e}")

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return ParseResult(False, error="expected a JSON array of events")

    valid = [
        item for item in data
        if isinstance(item, dict)
        and str(item.get("title", "")).strip()
        and str(item.get("start_time", "")).strip()
    ]
    if not valid:
        return ParseResult(False, error="no events with a title and start time")
    return ParseResult(True, value=valid)


def parse_profile_update(raw: str) -> ParseResult:
    """Parse a PROFILE_UPDATE payload, keeping only allowed fields."""
    try:
        data = loads_loose(raw)
    except ValueError as e:
        return ParseResult(False, error=f"invalid JSON: {e}")

    if not isinstance(data, dict):
        return ParseResult(False, error="expected a JSON object")

    filtered = {k: v for k, v in data.items() if k in ALLOWED_PROFILE_FIELDS}
    return ParseResult(True, value=filtered)
