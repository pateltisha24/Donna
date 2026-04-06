"""
ChromaDB store for the user profile.

One collection ("donna_user_profile") with a single document (id="profile").
We store the entire profile as JSON in the document metadata and use the
to_prompt_str() as the document text so semantic search also works.
"""

import json
import logging
import os
import time
from typing import Optional

import chromadb
from chromadb.config import Settings

from models.user_profile import UserProfile

logger = logging.getLogger("donna.chroma")

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

COLLECTION_NAME = "donna_user_profile"
PROFILE_DOC_ID = "profile"

_MAX_RETRIES = 5
_RETRY_DELAY = 2  # seconds


class ChromaStore:
    def __init__(self):
        self._client = chromadb.HttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
            settings=Settings(anonymized_telemetry=False),
        )
        # Retry collection creation — ChromaDB may still be initialising
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._collection = self._client.get_or_create_collection(
                    name=COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"},
                )
                return
            except Exception as exc:
                logger.warning(
                    "ChromaDB not ready (attempt %d/%d): %s",
                    attempt, _MAX_RETRIES, exc,
                )
                if attempt == _MAX_RETRIES:
                    raise
                time.sleep(_RETRY_DELAY)

    # ------------------------------------------------------------------
    # Profile read / write
    # ------------------------------------------------------------------

    def get_profile(self) -> UserProfile:
        """Return the stored profile, or a blank UserProfile if none exists yet."""
        results = self._collection.get(ids=[PROFILE_DOC_ID], include=["metadatas"])
        if not results["ids"]:
            return UserProfile()
        raw = results["metadatas"][0].get("json", "{}")
        return UserProfile.from_dict(json.loads(raw))

    def save_profile(self, profile: UserProfile) -> None:
        """Upsert the profile document."""
        profile_dict = profile.to_dict()
        # ChromaDB metadata values must be str | int | float | bool
        # We store the full profile as a JSON string under the "json" key.
        metadata = {"json": json.dumps(profile_dict)}
        document_text = profile.to_prompt_str()

        existing = self._collection.get(ids=[PROFILE_DOC_ID], include=["metadatas"])
        if existing["ids"]:
            self._collection.update(
                ids=[PROFILE_DOC_ID],
                documents=[document_text],
                metadatas=[metadata],
            )
        else:
            self._collection.add(
                ids=[PROFILE_DOC_ID],
                documents=[document_text],
                metadatas=[metadata],
            )

    # ------------------------------------------------------------------
    # Convenience patch helpers
    # ------------------------------------------------------------------

    def update_profile_fields(self, **kwargs) -> UserProfile:
        """
        Merge scalar/list/dict updates into the stored profile and save.

        Supported kwargs match UserProfile fields.  List fields are extended,
        dict fields are merged (not replaced), scalars are overwritten.
        """
        profile = self.get_profile()

        _LIST_FIELDS = {
            "major_goals_short", "major_goals_long",
            "known_priorities", "preferences", "notes",
        }
        _DICT_FIELDS = {"weekly_schedule", "known_people"}

        for key, value in kwargs.items():
            if not hasattr(profile, key):
                continue
            if key in _LIST_FIELDS:
                existing: list = getattr(profile, key)
                if isinstance(value, list):
                    for item in value:
                        if item not in existing:
                            existing.append(item)
                else:
                    if value not in existing:
                        existing.append(value)
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
