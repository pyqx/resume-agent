"""MemoryConsolidator — merges similar memories, flags conflicts, archives stale ones."""

import logging

from agent.memory.models import Memory, MemoryType
from agent.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """Periodic job: merge similar memories, detect conflicts, archive low-activity ones."""

    def __init__(self, store: MemoryStore):
        self._store = store

    async def consolidate(self, user_id: str = "default"):
        """Run full consolidation pass."""
        await self._merge_similar(user_id)
        await self._detect_conflicts(user_id)

    async def _merge_similar(self, user_id: str):
        """Merge memories with the same type and key."""
        for mem_type in MemoryType:
            memories = await self._store.get_all_for_user(
                user_id=user_id,
                memory_type=mem_type,
            )
            key_groups: dict[str, list[Memory]] = {}
            for m in memories:
                key_groups.setdefault(m.key, []).append(m)

            for key, group in key_groups.items():
                if len(group) <= 1:
                    continue
                # Keep highest confidence, merge others
                group.sort(key=lambda m: m.confidence, reverse=True)
                keeper = group[0]
                for dup in group[1:]:
                    if dup.value == keeper.value:
                        keeper.confidence = min(1.0, keeper.confidence + 0.05)
                        await self._store.soft_delete(dup.id)
                        logger.debug(f"Merged duplicate: {dup.key}")
                    else:
                        keeper.confidence = max(0.1, keeper.confidence - 0.2)
                        logger.info(f"Conflict detected: {key} = {keeper.value} vs {dup.value}")

    async def _detect_conflicts(self, user_id: str):
        """Detect contradictory memories (same key, different values, both high confidence)."""
        profile_memories = await self._store.get_all_for_user(
            user_id=user_id,
            memory_type=MemoryType.USER_PROFILE,
        )
        key_groups: dict[str, list[Memory]] = {}
        for m in profile_memories:
            key_groups.setdefault(m.key, []).append(m)

        for key, group in key_groups.items():
            values = {m.value for m in group if m.confidence > 0.5}
            if len(values) > 1:
                logger.warning(f"High-confidence conflict: key={key}, values={values}")
