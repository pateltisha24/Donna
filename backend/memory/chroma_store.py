"""
User-profile store.

Profiles live in the MongoDB `profiles` collection (keyed by user_id). This
class wraps the storage so all callers (`get_chroma()`, `ChromaStore`) keep
working unchanged.

The `ChromaStore` name is a backwards-compat alias from when the profile was
in ChromaDB. ChromaDB itself is now used only for semantic conversation recall
in `semantic_store.py` — not for the profile.
"""

import logging
from typing import Optional

from memory.mongo_store import MongoStore
from models.user_profile import UserProfile

logger = logging.getLogger("donna.profile")

_LIST_FIELDS = {
    "major_goals_short", "major_goals_long",
    "known_priorities", "preferences", "notes",
}
_DICT_FIELDS = {"weekly_schedule", "known_people"}


class ProfileStore:
    def __init__(self, store: Optional[MongoStore] = None):
        self._store = store or MongoStore()

    # ------------------------------------------------------------------
    # Profile read / write
    # ------------------------------------------------------------------

    def get_profile(self) -> UserProfile:
        data = self._store.get_profile_doc()
        if not data:
            return UserProfile()
        try:
            return UserProfile.from_dict(data)
        except (ValueError, TypeError) as e:
            logger.warning("Corrupt profile data, returning blank: %s", e)
            return UserProfile()

    def save_profile(self, profile: UserProfile) -> None:
        self._store.save_profile_doc(profile.to_dict())

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
        self.update_profile_fields(notes=[note])


# Backwards-compatible alias — callers still import ChromaStore.
ChromaStore = ProfileStore
