"""
LangGraph StateGraph for Donna.

Flow:
  START
    -> check_onboarding
    -> (onboarding | classify_intent)
    -> classify_intent -> one of the intent nodes
    -> update_memory
    -> END
"""

from typing import Any, Callable, Optional
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class DonnaState(TypedDict, total=False):
    user_message: str
    history: list[dict]         # [{role, content}, ...]
    intent: str
    response: str
    next_node: str
    stream_cb: Optional[Callable[[str], None]]  # per-request token sink (not persisted)
    # CRITICAL: these must be declared, or LangGraph strips them from the state
    # before nodes run — silently defaulting every chat to the "default" user.
    user_id: str
    session_id: str
    replan: dict  # structured replan result (changes + undo flag) for the UI


# ---------------------------------------------------------------------------
# Import node functions
# ---------------------------------------------------------------------------

from agent.nodes import (
    calendar,
    check_onboarding,
    classify_intent,
    eod_wrap,
    emergency_replan,
    general_checkin,
    morning_briefing,
    onboarding,
    profile_update,
    task_input,
    task_update,
    update_memory,
)


# ---------------------------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------------------------

def route_after_onboarding_check(state: DonnaState) -> str:
    return state.get("next_node", "classify_intent")


def route_after_classify(state: DonnaState) -> str:
    return state.get("intent", "general_checkin")


def route_after_intent_node(state: DonnaState) -> str:
    """All intent nodes go to update_memory before ending."""
    return "update_memory"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    g = StateGraph(DonnaState)

    # Register nodes
    g.add_node("check_onboarding", check_onboarding)
    g.add_node("onboarding", onboarding)
    g.add_node("classify_intent", classify_intent)
    g.add_node("morning_briefing", morning_briefing)
    g.add_node("task_input", task_input)
    g.add_node("task_update", task_update)
    g.add_node("emergency_replan", emergency_replan)
    g.add_node("general_checkin", general_checkin)
    g.add_node("profile_update", profile_update)
    g.add_node("eod_wrap", eod_wrap)
    g.add_node("calendar", calendar)
    g.add_node("update_memory", update_memory)

    # Entry
    g.add_edge(START, "check_onboarding")

    # After onboarding check
    g.add_conditional_edges(
        "check_onboarding",
        route_after_onboarding_check,
        {
            "onboarding": "onboarding",
            "classify_intent": "classify_intent",
        },
    )

    # After onboarding node completes -> update_memory then end
    g.add_edge("onboarding", "update_memory")

    # After classification -> dispatch to intent node
    g.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        {
            "morning_briefing": "morning_briefing",
            "task_input": "task_input",
            "task_update": "task_update",
            "emergency_replan": "emergency_replan",
            "general_checkin": "general_checkin",
            "profile_update": "profile_update",
            "eod_wrap": "eod_wrap",
            "calendar": "calendar",
            "onboarding": "onboarding",
        },
    )

    # All intent nodes -> update_memory -> END
    for node in (
        "morning_briefing",
        "task_input",
        "task_update",
        "emergency_replan",
        "general_checkin",
        "profile_update",
        "eod_wrap",
        "calendar",
    ):
        g.add_edge(node, "update_memory")

    g.add_edge("update_memory", END)

    return g.compile()


# Singleton compiled graph
donna_graph = build_graph()
