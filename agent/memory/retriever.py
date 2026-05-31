"""MemoryRetriever — semantic search + metadata filtering."""

from agent.memory.models import Memory, MemoryType, MemorySearchResult
from agent.memory.store import MemoryStore


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
    ) -> list[MemorySearchResult]:
        """Semantic search for relevant memories."""
        memories = await self._store.search(
            query=query,
            user_id=user_id,
            memory_types=memory_types,
            top_k=top_k,
        )
        # Note: similarity scores are embedded in the Memory objects via _row_to_memory
        # For now return them with default similarity
        return [MemorySearchResult(memory=m, similarity=0.8) for m in memories[:top_k]]

    async def get_profile(self, user_id: str = "default") -> list[Memory]:
        """Get all user profile memories."""
        return await self._store.get_all_for_user(
            user_id=user_id,
            memory_type=MemoryType.USER_PROFILE,
        )

    async def get_preferences(self, user_id: str = "default") -> list[Memory]:
        """Get all user preference memories."""
        return await self._store.get_all_for_user(
            user_id=user_id,
            memory_type=MemoryType.PREFERENCE,
        )

    async def get_session_context(self, user_id: str = "default") -> list[Memory]:
        """Get current session context."""
        return await self._store.get_all_for_user(
            user_id=user_id,
            memory_type=MemoryType.SESSION,
        )

    async def get_feedback_history(self, user_id: str = "default") -> list[Memory]:
        """Get user feedback history."""
        return await self._store.get_all_for_user(
            user_id=user_id,
            memory_type=MemoryType.FEEDBACK,
        )

    async def get_relevant_context(
        self,
        user_message: str,
        user_id: str = "default",
        top_k: int = 15,
    ) -> dict[str, list[Memory]]:
        """Get all relevant context for the current conversation turn.

        Returns memories grouped by type for injection into the context assembler.
        """
        results = await self.search(
            query=user_message,
            user_id=user_id,
            top_k=top_k,
        )

        grouped: dict[str, list[Memory]] = {
            "user_profile": [],
            "preference": [],
            "session": [],
            "feedback": [],
        }

        for r in results:
            grouped.setdefault(r.memory.type.value, []).append(r.memory)

        return grouped
