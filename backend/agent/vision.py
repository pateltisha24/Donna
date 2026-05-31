"""
Extract calendar events from an uploaded image (e.g. a screenshot of a weekly
timetable) using Groq's multimodal Llama 4 Scout model.

Returns a list of raw event dicts; conversion to Event objects (and weekday →
date resolution) is handled by agent.calendar_events.
"""

import base64
import logging
import os

from groq import Groq

from agent.parsing import loads_loose

logger = logging.getLogger("donna.vision")

_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

_client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))


def _prompt(today: str) -> str:
    return f"""\
You are reading a screenshot of someone's calendar or weekly timetable.
Today's date is {today}.

Extract every event you can see. Respond with ONLY a JSON array, each item:
{{
  "title": "...",
  "start_time": "HH:MM",          // 24-hour
  "end_time": "HH:MM" or null,
  "location": "" ,
  "date": "YYYY-MM-DD" or null,   // use this only if a specific date is shown
  "recurrence": "none" | "weekly" | "weekdays" | "daily",
  "recurrence_days": []           // lowercase 3-letter days, e.g. ["tue","fri"]
}}

Rules:
- A weekly timetable of classes/shifts is recurring: set recurrence "weekly" and
  recurrence_days to the weekday(s) the item appears under. Leave date null.
- A one-off dated event: set recurrence "none" and fill date.
- If the same titled item appears on multiple weekdays, emit ONE item with all
  those days in recurrence_days.
- Output ONLY the JSON array, no prose."""


def extract_events_from_image(image_bytes: bytes, mime_type: str, today: str) -> list[dict]:
    """Call the vision model and return a list of raw event dicts (best-effort)."""
    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:{mime_type};base64,{b64}"

    resp = _client.chat.completions.create(
        model=_VISION_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": _prompt(today)},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        temperature=0.1,
        max_tokens=2048,
    )
    raw = resp.choices[0].message.content
    try:
        data = loads_loose(raw)
    except ValueError as e:
        logger.warning("vision: could not parse events JSON: %s", e)
        return []
    if isinstance(data, dict):
        data = [data]
    return data if isinstance(data, list) else []
