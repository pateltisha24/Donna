"""
Wipe every user's data from Mongo and seed the `demo` user with realistic
content so a first-time visitor immediately sees a populated app.

Usage:
    cd backend
    python scripts/wipe_and_seed.py            # wipe + reseed demo
    python scripts/wipe_and_seed.py --keep-users  # keep `users` collection (auth)

Run with the same `.env` the backend uses (must export MONGODB_URI + MONGODB_DB).
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Make the backend package importable when running as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

# Try project-root .env first, fall back to CWD search.
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
if ROOT_ENV.exists():
    load_dotenv(ROOT_ENV)
else:
    load_dotenv()

from memory.mongo_store import MongoStore, _get_db  # noqa: E402
from models.event import Event  # noqa: E402
from models.task import Priority, Recurrence, Task, TaskStatus  # noqa: E402

DEMO_USER = "demo"


# ---------------------------------------------------------------------------
# Wipe
# ---------------------------------------------------------------------------

USER_DATA_COLLECTIONS = [
    "chats",
    "sessions",
    "tasks",
    "events",
    "profiles",
    "push_subscriptions",
    "app_state",
    "counters",
]


def wipe(keep_users: bool = False) -> None:
    db = _get_db()
    for name in USER_DATA_COLLECTIONS:
        result = db[name].delete_many({})
        print(f"  · cleared {name}: {result.deleted_count} docs")
    if not keep_users:
        result = db["users"].delete_many({})
        print(f"  · cleared users: {result.deleted_count} docs")
    else:
        print("  · kept users collection (auth records preserved)")


# ---------------------------------------------------------------------------
# Seed — demo user
# ---------------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _date(offset_days: int = 0) -> str:
    return (datetime.utcnow().date() + timedelta(days=offset_days)).isoformat()


def seed_demo() -> None:
    store = MongoStore(default_user=DEMO_USER)

    # ---- Profile (so Donna feels personalised) ----
    store.save_profile_doc({
        "name": "Tisha",
        "occupation": "Computer Science student",
        "institution": "University at Buffalo",
        "working_style": "Morning person. Prefers deep work blocks before noon.",
        "procrastination_patterns": "Tends to delay administrative emails until EOD.",
        "wake_time": "07:30",
        "eod_time": "21:30",
        "weekly_schedule": {},
        "known_people": {"Manav": "friend, software engineer"},
        "known_priorities": [
            "Land a great new-grad SWE role",
            "Ship Donna and the lip-reading project on GitHub",
        ],
        "preferences": [
            "Concise replies",
            "Bulleted summaries",
            "Honest second opinions over yes-manning",
        ],
        "major_goals_short": [
            "Crush this week's recruiter screens",
            "Push Donna to production",
        ],
        "major_goals_long": [
            "Senior ML/infra engineer at a top AI lab",
        ],
        "notes": [],
    })
    store.complete_onboarding()
    print("  · profile + onboarding flag set")

    # ---- Chats (3 realistic + 1 fresh) ----
    now = datetime.utcnow()

    def add_chat(
        title: str,
        offset_min: int,
        history: list[dict],
    ) -> str:
        chat_id = str(uuid.uuid4())
        created = now - timedelta(minutes=offset_min)
        db = _get_db()
        db["chats"].insert_one({
            "_id": chat_id,
            "user_id": DEMO_USER,
            "title": title,
            "created_at": _iso(created),
            "updated_at": _iso(created),
            "last_message_at": _iso(created),
            "archived": False,
        })
        if history:
            db["sessions"].insert_one({
                "_id": chat_id,
                "history": history,
                "updated_at": _iso(created),
            })
        return chat_id

    add_chat(
        "Morning briefing — Mon",
        offset_min=60,
        history=[
            {"role": "user", "content": "Good morning. Give me my morning briefing."},
            {
                "role": "assistant",
                "content": (
                    "**Good morning, Tisha.** Here's today at a glance:\n\n"
                    "- **10:00** — Recruiter screen with Stripe (45 min)\n"
                    "- **13:00** — LangGraph deep-dive block (your top-priority item)\n"
                    "- **15:30** — 1:1 with your advisor\n"
                    "- **19:00** — Dinner with Manav\n\n"
                    "You said you'd ship the Donna polish PR by EOD — want me to "
                    "block 16:30–18:30 for it before the dinner?"
                ),
            },
        ],
    )

    add_chat(
        "Emergency replan — interview moved",
        offset_min=180,
        history=[
            {"role": "user", "content": "Stripe just moved the screen to 11am. Replan my day."},
            {
                "role": "assistant",
                "content": (
                    "On it. Pulling the LangGraph block to **15:30**, pushing the "
                    "1:1 with your advisor to **tomorrow 10:00** (sent a tentative), "
                    "and reserving **10:30–10:55** for last-minute Stripe prep. "
                    "Dinner with Manav is untouched. Anything else shifting?"
                ),
            },
        ],
    )

    add_chat(
        "Add weekly classes",
        offset_min=60 * 24,
        history=[
            {
                "role": "user",
                "content": "I have CSE 410 Tue & Thu 11–12:15, and a Wed 14:00 group study every week.",
            },
            {
                "role": "assistant",
                "content": (
                    "Got it — adding three weekly events:\n\n"
                    "- **CSE 410** · Tue & Thu · 11:00–12:15\n"
                    "- **Group study** · Wed · 14:00–15:00\n\n"
                    "I'll send a 15-minute heads-up before each one. Anything else "
                    "regular I should know about?"
                ),
            },
        ],
    )

    add_chat("New chat", offset_min=2, history=[])
    print("  · 4 chats seeded (3 with realistic history + 1 fresh)")

    # ---- Tasks ----
    tasks: list[Task] = [
        Task(
            title="Polish Donna README + deploy demo link",
            date_assigned=_date(0),
            priority=Priority.HIGH,
            status=TaskStatus.IN_PROGRESS,
            duration_estimate=60,
        ),
        Task(
            title="Prep recruiter call talking points",
            date_assigned=_date(0),
            priority=Priority.HIGH,
            duration_estimate=30,
        ),
        Task(
            title="LangGraph deep-dive block",
            date_assigned=_date(0),
            priority=Priority.MEDIUM,
            duration_estimate=90,
        ),
        Task(
            title="Reply to advisor email about thesis topic",
            date_assigned=_date(0),
            priority=Priority.LOW,
            duration_estimate=15,
        ),
        Task(
            title="Standup notes (async)",
            date_assigned=_date(0),
            priority=Priority.MEDIUM,
            status=TaskStatus.DONE,
            duration_estimate=10,
        ),
        Task(
            title="Submit CSE 410 problem set",
            date_assigned=_date(1),
            priority=Priority.HIGH,
            duration_estimate=120,
        ),
    ]
    for t in tasks:
        store.add_task(t)
    print(f"  · {len(tasks)} tasks seeded")

    # ---- Events ----
    events: list[Event] = [
        Event(
            title="Stripe recruiter screen",
            date=_date(0),
            start_time="11:00",
            end_time="11:45",
            location="Zoom",
        ),
        Event(
            title="Dinner with Manav",
            date=_date(0),
            start_time="19:00",
            end_time="20:30",
            location="Anchor Bar",
        ),
        Event(
            title="CSE 410",
            date=_date(0),
            start_time="11:00",
            end_time="12:15",
            location="Davis 113",
            recurrence=Recurrence.WEEKLY,
            recurrence_days=["tue", "thu"],
        ),
        Event(
            title="Group study",
            date=_date(0),
            start_time="14:00",
            end_time="15:00",
            location="Lockwood Library",
            recurrence=Recurrence.WEEKLY,
            recurrence_days=["wed"],
        ),
    ]
    for e in events:
        store.add_event(e)
    print(f"  · {len(events)} events seeded")


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-users",
        action="store_true",
        help="Don't wipe the `users` collection (preserve registered accounts).",
    )
    args = parser.parse_args()

    db_name = os.getenv("MONGODB_DB", "Donna")
    print(f"Target: {db_name}")
    if not os.getenv("MONGODB_URI"):
        sys.exit("MONGODB_URI is not set. Source your .env first.")

    print("\nWiping…")
    wipe(keep_users=args.keep_users)

    print("\nSeeding demo user…")
    seed_demo()

    print("\nDone. Demo user is fully populated.")


if __name__ == "__main__":
    main()
