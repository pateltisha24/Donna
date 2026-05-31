"""
User-profile store.

This was originally backed by ChromaDB, but the profile is a single JSON
document that we never run semantic search over — ChromaDB was acting as an
over-engineered key/value store and an extra service to babysit. It now lives
in SQLite (app_state, one key). The class name `ChromaStore` is kept so the
many callers don't have to change; `ProfileStore` is the preferred alias for
new code.
"""

import json
import logging

from memory.sqlite_store import SqliteStore
from models.user_profile import UserProfile

logger = logging.getLogger("donna.profile")

_PROFILE_KEY = "user_profile"

_LIST_FIELDS = {
    "major_goals_short", "major_goals_long",
    "known_priorities", "preferences", "notes",
}
_DICT_FIELDS = {"weekly_schedule", "known_people"}


class ProfileStore:
    def __init__(self, store: SqliteStore | None = None):
        self._store = store or SqliteStore()

    # ------------------------------------------------------------------
    # Profile read / write
    # ------------------------------------------------------------------

    def get_profile(self) -> UserProfile:
        """Return the stored profile, or a blank UserProfile if none exists yet."""
        raw = self._store.get_state(_PROFILE_KEY)
        if not raw:
            return UserProfile()
        try:
            return UserProfile.from_dict(json.loads(raw))
        except (ValueError, TypeError) as e:
            logger.warning("Corrupt profile JSON, returning blank: %s", e)
            return UserProfile()

    def save_profile(self, profile: UserProfile) -> None:
        self._store.set_state(_PROFILE_KEY, json.dumps(profile.to_dict()))

    # ------------------------------------------------------------------
    # Convenience patch helpers
    # ------------------------------------------------------------------

    def update_profile_fields(self, **kwargs) -> UserProfile:
        """
        Merge updates into the stored profile and save.

        List fields are extended (deduped), dict fields are merged, scalars are
        overwritten. Unknown keys are ignored.
        """
        profile = self.get_profile()

        for key, value in kwargs.items():
            if not hasattr(profile, key):
                continue
            if key in _LIST_FIELDS:
                existing: list = getattr(profile, key)
                items = value if isinstance(value, list) else [value]
                for item in items:
                    if item not in existing:
                        existing.append(item)
                setattr(profile, key, existing)
            elif key in _DICT_FIELDS:
                existing_dict: dict = getattr(profile, key)
                if isinstance(value, dict):
                    existing_dict.update(value)
                setattr(profile, key, existing_dict)
            else:
                setattr(profile, key, value)

        self.save_profile(profile)
        return profile

    def add_note(self, note: str) -> None:
        """Append a free-text note to the profile."""
        self.update_profile_fields(notes=[note])


# Backwards-compatible alias — callers still import ChromaStore.
ChromaStore = ProfileStore
