"""
Time utility helpers.
"""

from datetime import date, datetime, timedelta


def today_str() -> str:
    """Return today's date as YYYY-MM-DD."""
    return date.today().isoformat()


def tomorrow_str() -> str:
    """Return tomorrow's date as YYYY-MM-DD."""
    return (date.today() + timedelta(days=1)).isoformat()


def now_str() -> str:
    """Return current time as HH:MM."""
    return datetime.now().strftime("%H:%M")


def parse_time(t: str) -> tuple[int, int]:
    """Parse 'HH:MM' into (hour, minute)."""
    parts = t.split(":")
    return int(parts[0]), int(parts[1])


def friendly_datetime() -> str:
    return datetime.now().strftime("%A, %B %d %Y at %H:%M")
