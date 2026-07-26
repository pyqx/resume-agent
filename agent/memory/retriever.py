"""MemoryRetriever — semantic search + metadata filtering."""

import logging

from agent.memory.models import Memory, MemoryType, MemorySearchResult
from agent.memory.store import MemoryStore

logger = logging.getLogger(__name__)

# Results below this cosine similarity are treated as noise and dropped.
MIN_SIMILARITY = 0.25
# Hard cap on how many vectors a single search may pull.
MAX_TOP_K = 50
# Per-type caps applied when assembling conversation context.
TYPE_QUOTAS: dict[MemoryType, int] = {
    MemoryType.USER_PROFILE: 4,
    MemoryType.PREFERENCE: 4,
    MemoryType.SESSION: 4,
    MemoryType.FEEDBACK: 3,
}


class MemoryRetriever:
    """Retrieves memories by semantic search with type filtering."""

    def __init__(self, store: MemoryStore):
        self._store = store

    async def search(
        self,
        query: str,
        user_id: str = "default",
        memory_types: list[MemoryType] | None = None,
        top_k: int = 10,
        min_similarity: float = MIN_SIMILARITY,
    ) -> list[MemorySearchResult]:
        """Semantic search for relevant memories.

        Similarity scores come straight from the store (1.0 - cosine distance);
        matches below ``min_similarity`` are filtered out.
        """
        top_k = max(1, min(int(top_k), MAX_TOP_K))
        results = await self._store.search(
            query=query,
            user_id=user_id,
            memory_types=memory_types,
            top_k=top_k,
        )
        return [r for r in results if r.similarity >= min_similarity][:top_k]

    async def get_profile(self, user_id: str = "default") -> list[Memory]:
        """Get all user profile memories (most recently updated first)."""
        return await self._store.get_all_for_user(
            user_id=user_id,
            memory_type=MemoryType.USER_PROFILE,
        )

    async def get_preferences(self, user_id: str = "default") -> list[Memory]:
        """Get all user preference memories (most recently updated first)."""
        return await self._store.get_all_for_user(
            user_id=user_id,
            memory_type=MemoryType.PREFERENCE,
        )

    async def get_session_context(self, user_id: str = "default") -> list[Memory]:
        """Get session-scoped memories (most recently updated first)."""
        return await self._store.get_all_for_user(
            user_id=user_id,
            memory_type=MemoryType.SESSION,
        )

    async def get_feedback_history(self, user_id: str = "default") -> list[Memory]:
        """Get user feedback history (most recently updated first)."""
        return await self._store.get_all_for_user(
            user_id=user_id,
            memory_type=MemoryType.FEEDBACK,
        )

    async def get_relevant_context(
        self,
        user_message: str,
        user_id: str = "default",
        session_id: str | None = None,
        top_k: int = 15,
    ) -> dict[str, list[Memory]]:
        """Get relevant memories for the current turn, grouped by type.

        - SESSION memories are scoped to ``session_id`` when one is given
          (other conversations' scratch context is never relevant).
        - Each type is capped by TYPE_QUOTAS.
        - When semantic search yields nothing for a type, fall back to the most
          recently updated stored entries of that type.
        """
        results = await self.search(query=user_message, user_id=user_id, top_k=top_k)

        grouped: dict[str, list[Memory]] = {t.value: [] for t in MemoryType}
        for r in results:
            grouped.setdefault(r.memory.type.value, []).append(r.memory)

        if session_id is not None:
            grouped[MemoryType.SESSION.value] = self._filter_session(
                grouped[MemoryType.SESSION.value], session_id
            )

        fallbacks = {
            MemoryType.USER_PROFILE: self.get_profile,
            MemoryType.PREFERENCE: self.get_preferences,
            MemoryType.SESSION: self.get_session_context,
            MemoryType.FEEDBACK: self.get_feedback_history,
        }
        for mem_type, quota in TYPE_QUOTAS.items():
            bucket = grouped[mem_type.value]
            if not bucket:
                try:
                    recent = await fallbacks[mem_type](user_id=user_id)
                except Exception as e:
                    logger.warning("Fallback fetch failed for %s: %s", mem_type.value, e)
                    recent = []
                if mem_type == MemoryType.SESSION and session_id is not None:
                    recent = self._filter_session(recent, session_id)
                bucket = recent
            grouped[mem_type.value] = bucket[:quota]

        return grouped

    @staticmethod
    def _filter_session(memories: list[Memory], session_id: str) -> list[Memory]:
        """Keep only SESSION memories that belong to the current session."""
        return [
            m for m in memories
            if (m.metadata or {}).get("session_id") == session_id
        ]
