"""
Lightweight eval harness for Donna's agent.

Part 1 — Intent routing accuracy: feed labelled messages through the real
classifier and measure how often it routes correctly.
Part 2 — Action smoke tests: drive the action nodes end-to-end on a throwaway
user and assert the side effects actually happened (task created, marked done).

Run:
    cd backend
    python scripts/eval_agent.py
Exits non-zero if accuracy drops below threshold or an action test fails — so it
can gate CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ROOT_ENV if ROOT_ENV.exists() else None)

from datetime import date  # noqa: E402

from agent.nodes import classify_intent, task_input, task_update  # noqa: E402
from memory.mongo_store import MongoStore, _get_db  # noqa: E402

# (message, expected_intent)
INTENT_CASES = [
    ("Give me my morning briefing", "morning_briefing"),
    ("What does my day look like?", "morning_briefing"),
    ("Add a task: finish the lab report by 5pm", "task_input"),
    ("I need to write three emails today", "task_input"),
    ("I finished the lab report", "task_update"),
    ("Mark the standup notes as done", "task_update"),
    ("Move the reading to tomorrow", "task_update"),
    ("Something urgent came up, replan my day", "emergency_replan"),
    ("My interview got moved to 11, help me rearrange", "emergency_replan"),
    ("What should I work on right now?", "general_checkin"),
    ("I'm done for the day, let's wrap up", "eod_wrap"),
    ("Add a meeting with Sam on Friday at 2pm", "calendar"),
    ("I have class every Tuesday and Thursday at 10", "calendar"),
    ("My name is Priya and I'm a grad student at MIT", "profile_update"),
    ("I prefer deep work in the mornings", "profile_update"),
    ("How am I doing on my goals this week?", "general_checkin"),
]

THRESHOLD = 0.80


def run_intent_eval() -> float:
    print("=" * 60)
    print("PART 1 — Intent routing accuracy")
    print("=" * 60)
    correct = 0
    for msg, expected in INTENT_CASES:
        try:
            got = classify_intent({"user_message": msg}).get("intent")
        except Exception as e:  # noqa: BLE001
            got = f"ERROR({e})"
        ok = got == expected
        correct += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {msg[:48]:<50} -> {got}"
              + ("" if ok else f"  (expected {expected})"))
    acc = correct / len(INTENT_CASES)
    print(f"\n  Accuracy: {correct}/{len(INTENT_CASES)} = {acc:.0%}")
    return acc


def run_action_eval() -> bool:
    print("\n" + "=" * 60)
    print("PART 2 — Action smoke tests (end-to-end)")
    print("=" * 60)
    U = "evaltest"
    db = _get_db()
    for c in ("tasks", "app_state", "counters"):
        db[c].delete_many({"user_id": U})
    store = MongoStore(default_user=U)
    store.complete_onboarding()
    store.save_profile_doc({"name": "Eval", "occupation": "student"})
    ok = True

    today = date.today().isoformat()

    # 1) Create a task via the tool path (propose -> confirm, the reliable flow).
    #    Assert it was saved at all (any date) — this tests the tool pipeline,
    #    independent of the model's date choice.
    r1 = task_input({
        "user_message": "Add a task for today: EVALCHECK write the summary, 30 minutes.",
        "user_id": U, "history": [],
    })
    task_input({
        "user_message": "Yes, add it.",
        "user_id": U, "history": r1.get("history", []),
    })
    created = store.search_tasks(q="EVALCHECK")
    print(f"  [{'PASS' if created else 'FAIL'}] create task via tool -> {len(created)} found")
    ok = ok and bool(created)

    # 2) Mark done via the tool path. Seed a known task on TODAY so task_update
    #    sees its id, then assert the status flips.
    from models.task import Task, Priority
    store.add_task(Task("EVALDONE finish the deck", today, priority=Priority.MEDIUM, duration_estimate=30))
    task_update({
        "user_message": "I finished the EVALDONE finish the deck task, mark it done.",
        "user_id": U, "history": [],
    })
    done = any(
        getattr(t.status, "value", t.status) == "done"
        for t in store.get_tasks_for_date(today) if "EVALDONE" in t.title
    )
    print(f"  [{'PASS' if done else 'FAIL'}] mark task done via tool -> done={done}")
    ok = ok and done

    # cleanup
    for c in ("tasks", "app_state", "counters", "profiles"):
        db[c].delete_many({"user_id": U})
    return ok


def main() -> None:
    acc = run_intent_eval()
    actions_ok = run_action_eval()
    print("\n" + "=" * 60)
    passed = acc >= THRESHOLD and actions_ok
    print(f"RESULT: {'PASS ✅' if passed else 'FAIL ❌'} "
          f"(intent {acc:.0%} ≥ {THRESHOLD:.0%}? {acc >= THRESHOLD}; actions ok? {actions_ok})")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
