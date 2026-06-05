"""
The four specialist agents Donna is composed of.

Each agent is a thin orchestration layer that owns a coherent set of graph nodes
and shares a single LangGraph state. They exist to make the multi-agent
architecture explicit at the code level — graph.py wires the nodes together,
but `agents.py` is what describes *what* each agent is responsible for.

The four agents:

  1. TaskReasoningAgent  — turns free-form messages into structured tasks,
                           classifies intent, and applies task mutations
                           (done / in-progress / moved) through validated
                           control tokens.

  2. SchedulingAgent     — owns the user's day: morning briefing, EOD wrap,
                           timed calendar events, recurring rules, and the
                           APScheduler reminders that fire them.

  3. ReplanningAgent     — handles emergencies and the EOD rollover. Combines
                           profile-aware preference signals (working style,
                           procrastination patterns) with current load to
                           produce a calm, decisive re-sequence of the day.

  4. ToolExecutionAgent  — the side-effect layer. Validates every structured
                           payload against a schema before any mutation hits
                           the database, runs the conflict-resolution layer
                           on event/task writes, and owns vision OCR, .ics
                           import/export, and web-push delivery.

The graph itself stays in graph.py — these classes don't replace it, they
describe it. Tests import nodes directly; nothing here changes the runtime
graph topology.
"""

from dataclasses import dataclass, field
from typing import Callable

from agent import nodes


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Agent:
    """A specialist agent: a name, the nodes it owns, and a one-line summary."""

    name: str
    summary: str
    nodes: list[Callable] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    @property
    def node_names(self) -> list[str]:
        return [n.__name__ for n in self.nodes]


# ---------------------------------------------------------------------------
# The four agents
# ---------------------------------------------------------------------------

TaskReasoningAgent = Agent(
    name="Task Reasoning Agent",
    summary=(
        "Parses messy thoughts into structured tasks, classifies intent on every "
        "turn, and applies validated state mutations to the task store."
    ),
    nodes=[nodes.classify_intent, nodes.task_input, nodes.task_update],
    tools=["control-token parsing", "validated retries", "intent classifier"],
)

SchedulingAgent = Agent(
    name="Scheduling Agent",
    summary=(
        "Owns the user's day: morning briefing, EOD wrap, calendar events, "
        "recurring rules, and APScheduler reminders."
    ),
    nodes=[nodes.morning_briefing, nodes.eod_wrap, nodes.calendar],
    tools=[
        "APScheduler (cron + date triggers)",
        "recurrence materialization",
        "per-event reminders (15-min lead)",
    ],
)

ReplanningAgent = Agent(
    name="Replanning Agent",
    summary=(
        "Re-sequences the day when something urgent lands; rolls incomplete work "
        "forward at EOD. Preference-aware: respects working style and procrastination "
        "patterns from the user profile."
    ),
    nodes=[nodes.emergency_replan],
    tools=["EOD rollover (move_task)", "profile-aware prioritisation"],
)

ToolExecutionAgent = Agent(
    name="Tool Execution Agent",
    summary=(
        "The side-effect layer. Validates every structured payload before it "
        "mutates state, runs the conflict-resolution layer on event/task writes, "
        "and owns vision OCR, .ics import/export, and web-push delivery."
    ),
    nodes=[
        nodes.onboarding,
        nodes.profile_update,
        nodes.general_checkin,
        nodes.update_memory,
    ],
    tools=[
        "Groq Llama 4 Scout (vision OCR)",
        ".ics import / export (icalendar)",
        "Web Push (VAPID)",
        "conflict-resolution layer",
        "ChromaDB semantic recall",
    ],
)

ALL_AGENTS: list[Agent] = [
    TaskReasoningAgent,
    SchedulingAgent,
    ReplanningAgent,
    ToolExecutionAgent,
]


def describe_agents() -> list[dict]:
    """Serializable agent metadata for the /agents endpoint."""
    return [
        {
            "name": a.name,
            "summary": a.summary,
            "nodes": a.node_names,
            "tools": a.tools,
        }
        for a in ALL_AGENTS
    ]
