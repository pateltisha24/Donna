"""
Semantic store backed by ChromaDB (PersistentClient — no separate service).

We index Donna's assistant responses so the user can ask things like
"remember when we talked about X?" and get a real semantic match instead of
keyword scanning.

Design choices:

  * `chromadb.PersistentClient(path=...)` keeps everything in a single file-based
    store on the same volume as SQLite. No extra Docker service, no port to open,
    no operational surface area beyond a directory.

  * Embedding uses Chroma's bundled default (small ONNX model, downloaded once
    on first run). This is good enough for "did we talk about X" recall over a
    single user's chat history and adds no cloud dependency.

  * Initialisation is lazy and fault-tolerant: if Chroma fails to load (e.g.
    onnxruntime is missing in a stripped deployment), every method becomes a
    no-op and the rest of Donna keeps working. We never want a recall failure
    to break the main chat path.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("donna.semantic")

DEFAULT_PATH = os.getenv("CHROMA_DB_PATH", "./data/chroma")
COLLECTION_NAME = "donna_messages"


class SemanticStore:
    """Lazy-initialised semantic index of assistant messages."""

    _instance: Optional["SemanticStore"] = None
    _lock = threading.Lock()

    def __new__(cls, path: str = DEFAULT_PATH) -> "SemanticStore":
        # Singleton — the Chroma client is expensive to create. Threads share one.
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._path = path
                cls._instance._client = None
                cls._instance._collection = None
                cls._instance._initialised = False
                cls._instance._disabled = False
        return cls._instance

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _ensure_ready(self) -> bool:
        if self._initialised:
            return not self._disabled
        if self._disabled:
            return False

        try:
            import chromadb  # type: ignore

            os.makedirs(self._path, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self._path)
            self._collection = self._client.get_or_create_collection(COLLECTION_NAME)
            self._initialised = True
            logger.info("Semantic store ready at %s", self._path)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Semantic store disabled: %s", e)
            self._disabled = True
            self._initialised = True
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        user_id: str = "default",
    ) -> None:
        """Index a single message. Silent no-op if the store is disabled.

        Every document is tagged with `user_id` so `recall()` can scope results
        to one person — recall must never surface another user's history.
        """
        if not content or not content.strip():
            return
        if not self._ensure_ready():
            return
        try:
            # Include role in the fallback id: index_message is called twice per
            # turn (user + assistant) and a bare session+timestamp id can collide
            # at microsecond resolution, silently overwriting one document.
            mid = message_id or f"{session_id}-{role}-{datetime.utcnow().timestamp()}"
            self._collection.add(  # type: ignore[union-attr]
                ids=[mid],
                documents=[content],
                metadatas=[{
                    "user_id": user_id,
                    "session_id": session_id,
                    "role": role,
                    "ts": datetime.utcnow().isoformat(),
                }],
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("index_message failed: %s", e)

    def recall(
        self, query: str, limit: int = 5, user_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Semantic search over indexed messages. Returns a list of dicts:
        [{document, role, session_id, ts, score}]. Empty list on any error.

        When `user_id` is given, results are filtered to that user only.
        """
        if not self._ensure_ready():
            return []
        try:
            query_kwargs: dict[str, Any] = {
                "query_texts": [query],
                "n_results": max(1, min(limit, 20)),
            }
            if user_id is not None:
                query_kwargs["where"] = {"user_id": user_id}
            result = self._collection.query(**query_kwargs)  # type: ignore[union-attr]
            docs = (result.get("documents") or [[]])[0]
            metas = (result.get("metadatas") or [[]])[0]
            dists = (result.get("distances") or [[]])[0]
            out: list[dict[str, Any]] = []
            for i, doc in enumerate(docs):
                meta = metas[i] if i < len(metas) else {}
                dist = dists[i] if i < len(dists) else None
                out.append({
                    "document": doc,
                    "role": meta.get("role"),
                    "session_id": meta.get("session_id"),
                    "ts": meta.get("ts"),
                    "score": (1.0 - dist) if isinstance(dist, (int, float)) else None,
                })
            return out
        except Exception as e:  # noqa: BLE001
            logger.debug("recall failed: %s", e)
            return []

    def reset(self) -> None:
        """Drop the collection (useful in tests)."""
        if not self._ensure_ready():
            return
        try:
            self._client.delete_collection(COLLECTION_NAME)  # type: ignore[union-attr]
            self._collection = self._client.get_or_create_collection(COLLECTION_NAME)  # type: ignore[union-attr]
        except Exception as e:  # noqa: BLE001
            logger.debug("reset failed: %s", e)
