"""
ADDITIVE demo enrichment — backfills ~11 weeks of realistic, *tagged* historical
tasks for the `demo` user so the Productivity heatmap and time-by-category
breakdown look like a real, lived-in account.

Unlike wipe_and_seed.py this is NON-destructive: it never wipes collections and
only writes tasks dated strictly in the PAST (offsets -77..-1), so it leaves
today's / tomorrow's seeded tasks, events, chats, and profile untouched.

It is safely re-runnable: it first clears any historical tasks it previously
created in the same past window, then regenerates them deterministically.

Usage:
    cd backend
    python scripts/enrich_demo.py
    python scripts/enrich_demo.py --weeks 16   # wider history
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
if ROOT_ENV.exists():
    load_dotenv(ROOT_ENV)
else:
    load_dotenv()

import os  # noqa: E402

from memory.mongo_store import MongoStore, _get_db  # noqa: E402
from models.event import Event  # noqa: E402
from models.task import Priority, Recurrence, Task, TaskStatus  # noqa: E402

DEMO_USER = "demo"

# Category -> (sample titles, duration range in minutes). The first tag drives
# the "Where your time goes" breakdown, so one tag per task.
CATEGORIES: dict[str, tuple[list[str], tuple[int, int]]] = {
    "thesis": (
        ["Thesis literature review", "Write thesis section", "Run thesis experiment",
         "Summarize advisor feedback"],
        (45, 120),
    ),
    "recruiting": (
        ["LeetCode practice", "System design study", "Recruiter screen prep",
         "Apply to SWE roles", "Mock interview"],
        (30, 90),
    ),
    "coursework": (
        ["CSE 410 problem set", "Read course chapter", "Group project work",
         "Lab assignment writeup"],
        (30, 120),
    ),
    "donna": (
        ["Donna: fix streaming bug", "Donna: build feature", "Donna: polish UI",
         "Donna: write tests"],
        (30, 150),
    ),
    "workout": (
        ["Morning run", "Gym session", "Evening yoga"],
        (30, 60),
    ),
    "admin": (
        ["Clear inbox", "Plan the week", "Submit reimbursement", "Weekly review"],
        (10, 30),
    ),
}

PRIORITIES = [Priority.HIGH, Priority.MEDIUM, Priority.LOW]
PRIORITY_WEIGHTS = [0.3, 0.5, 0.2]


def enrich(weeks: int = 11, seed: int = 42) -> None:
    rng = random.Random(seed)
    store = MongoStore(default_user=DEMO_USER)
    db = _get_db()

    # The demo user has a profile but the chat path gates on this flag; without
    # it every message is forced into onboarding. Ensure demo is "onboarded".
    if not store.is_onboarding_complete():
        store.complete_onboarding()
        print("  · marked demo onboarding complete")

    today = date.today()
    window = weeks * 7
    start = (today - timedelta(days=window)).isoformat()
    end = (today - timedelta(days=1)).isoformat()

    # Idempotency: clear only PAST-window non-recurring tasks (all seed-made).
    res = db["tasks"].delete_many({
        "user_id": DEMO_USER,
        "recurrence": "none",
        "date_assigned": {"$gte": start, "$lte": end},
    })
    print(f"  · cleared {res.deleted_count} prior historical tasks in window")

    made = 0
    for offset in range(window, 0, -1):
        d = today - timedelta(days=offset)
        weekend = d.weekday() >= 5
        recent = offset <= 7  # guarantee a ~week-long current streak

        if weekend:
            n = rng.choice([0, 0, 1, 2])
        else:
            n = rng.choice([2, 3, 3, 4, 5])
            if rng.random() < 0.08:
                n = 0  # the occasional fully-off day keeps it honest
            elif rng.random() < 0.12:
                n = 6  # the occasional big day -> a brightest-level cell
        if recent and n == 0:
            n = rng.choice([2, 3])

        for i in range(n):
            tag = rng.choice(list(CATEGORIES))
            titles, (lo, hi) = CATEGORIES[tag]
            duration = rng.randrange(lo, hi + 1, 5)
            priority = rng.choices(PRIORITIES, weights=PRIORITY_WEIGHTS)[0]

            p_done = 0.9 if recent else (0.7 if not weekend else 0.55)
            done = (i == 0 and recent) or rng.random() < p_done
            status = (
                TaskStatus.DONE if done
                else rng.choice([TaskStatus.PENDING, TaskStatus.MOVED])
            )

            store.add_task(Task(
                title=rng.choice(titles),
                date_assigned=d.isoformat(),
                priority=priority,
                status=status,
                duration_estimate=duration,
                tags=[tag],
            ))
            made += 1

    print(f"  · inserted {made} historical tasks across {window} days "
          f"({start} → {end})")

    enrich_events(store, db, today)


def enrich_events(store: MongoStore, db, today: date) -> None:
    """Add a realistic recurring week + a couple of one-offs so the Calendar
    grid looks lived-in. Idempotent via the `description="demo-seed"` marker —
    leaves any other demo events (added by hand) untouched."""
    res = db["events"].delete_many({"user_id": DEMO_USER, "description": "demo-seed"})
    monday = today - timedelta(days=today.weekday())
    anchor = monday.isoformat()  # recurrence matches by weekday; anchor is just a seed date

    weekly = [
        Event(title="Team standup", date=anchor, start_time="09:30", end_time="09:45",
              location="Zoom", description="demo-seed", recurrence=Recurrence.WEEKDAYS),
        Event(title="CSE 410 Lecture", date=anchor, start_time="11:00", end_time="12:15",
              location="Davis 113", description="demo-seed",
              recurrence=Recurrence.WEEKLY, recurrence_days=["tue", "thu"]),
        Event(title="Thesis advisor sync", date=anchor, start_time="14:00", end_time="14:30",
              location="Zoom", description="demo-seed",
              recurrence=Recurrence.WEEKLY, recurrence_days=["mon"]),
        Event(title="Group study", date=anchor, start_time="15:30", end_time="16:30",
              location="Lockwood Library", description="demo-seed",
              recurrence=Recurrence.WEEKLY, recurrence_days=["wed"]),
        Event(title="Gym", date=anchor, start_time="18:00", end_time="19:00",
              location="Rec Center", description="demo-seed",
              recurrence=Recurrence.WEEKLY, recurrence_days=["mon", "wed", "fri"]),
    ]
    one_offs = [
        Event(title="Lunch with Manav", date=(monday + timedelta(days=2)).isoformat(),
              start_time="12:30", end_time="13:30", location="Elmwood Ave",
              description="demo-seed"),
        Event(title="Recruiter screen — Stripe", date=(monday + timedelta(days=3)).isoformat(),
              start_time="16:00", end_time="16:45", location="Zoom", description="demo-seed"),
    ]
    for e in weekly + one_offs:
        store.add_event(e)
    print(f"  · cleared {res.deleted_count} prior seed events; "
          f"added {len(weekly)} weekly + {len(one_offs)} one-off events")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weeks", type=int, default=11, help="Weeks of history to backfill.")
    args = parser.parse_args()

    if not os.getenv("MONGODB_URI"):
        sys.exit("MONGODB_URI is not set. Source your .env first.")

    print(f"Enriching demo history ({args.weeks} weeks)…")
    enrich(weeks=args.weeks)
    print("\nDone. The demo user now has a lived-in productivity history.")


if __name__ == "__main__":
    main()
