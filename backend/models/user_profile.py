"""
UserProfile dataclass — stored in ChromaDB as a JSON document.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserProfile:
    # Identity
    name: str = ""
    occupation: str = ""
    institution: str = ""  # company or school

    # Goals
    major_goals_short: list[str] = field(default_factory=list)
    major_goals_long: list[str] = field(default_factory=list)

    # Work style
    working_style: str = ""          # e.g. "morning person", "night owl"
    procrastination_patterns: str = ""

    # Schedule
    weekly_schedule: dict = field(default_factory=dict)  # {"Monday": ["9am lecture"]}
    wake_time: str = "08:00"         # HH:MM 24h
    eod_time: str = "21:00"          # HH:MM 24h

    # Social graph
    known_people: dict = field(default_factory=dict)  # {"Manav": "boyfriend"}

    # Priorities & preferences
    known_priorities: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)

    # Accumulated notes
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "occupation": self.occupation,
            "institution": self.institution,
            "major_goals_short": self.major_goals_short,
            "major_goals_long": self.major_goals_long,
            "working_style": self.working_style,
            "procrastination_patterns": self.procrastination_patterns,
            "weekly_schedule": self.weekly_schedule,
            "wake_time": self.wake_time,
            "eod_time": self.eod_time,
            "known_people": self.known_people,
            "known_priorities": self.known_priorities,
            "preferences": self.preferences,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UserProfile":
        return cls(
            name=d.get("name", ""),
            occupation=d.get("occupation", ""),
            institution=d.get("institution", ""),
            major_goals_short=d.get("major_goals_short", []),
            major_goals_long=d.get("major_goals_long", []),
            working_style=d.get("working_style", ""),
            procrastination_patterns=d.get("procrastination_patterns", ""),
            weekly_schedule=d.get("weekly_schedule", {}),
            wake_time=d.get("wake_time", "08:00"),
            eod_time=d.get("eod_time", "21:00"),
            known_people=d.get("known_people", {}),
            known_priorities=d.get("known_priorities", []),
            preferences=d.get("preferences", []),
            notes=d.get("notes", []),
        )

    def to_prompt_str(self) -> str:
        """Human-readable summary for injection into the system prompt."""
        # Join a list defensively: skip None/empty items and coerce to str, so a
        # stray None in a profile list can never crash prompt-building.
        def _join(items, sep=", "):
            return sep.join(str(x).strip() for x in (items or []) if x and str(x).strip())

        lines = []
        if self.name:
            lines.append(f"Name: {self.name}")
        if self.occupation:
            lines.append(f"Occupation: {self.occupation}")
        if self.institution:
            lines.append(f"Institution/Company: {self.institution}")
        if _join(self.major_goals_short):
            lines.append(f"Short-term goals: {_join(self.major_goals_short)}")
        if _join(self.major_goals_long):
            lines.append(f"Long-term goals: {_join(self.major_goals_long)}")
        if self.working_style:
            lines.append(f"Working style: {self.working_style}")
        if self.procrastination_patterns:
            lines.append(f"Procrastination patterns: {self.procrastination_patterns}")
        if self.weekly_schedule:
            sched = "; ".join(f"{k}: {_join(v)}" for k, v in self.weekly_schedule.items())
            lines.append(f"Weekly schedule: {sched}")
        if self.known_people:
            people = ", ".join(f"{k} ({v})" for k, v in self.known_people.items() if k)
            lines.append(f"Known people: {people}")
        if _join(self.known_priorities):
            lines.append(f"Known priorities: {_join(self.known_priorities)}")
        if _join(self.preferences):
            lines.append(f"Preferences: {_join(self.preferences)}")
        if self.notes:
            lines.append(f"Notes: {_join(self.notes[-5:], ' | ')}")  # last 5 notes
        return "\n".join(lines) if lines else "No profile yet."
