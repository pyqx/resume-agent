"""MemoryConsolidator — merges similar memories and flags conflicts."""

import logging

from agent.memory.models import Memory, MemoryChangelog, MemoryType
from agent.memory.store import MemoryStore

logger = logging.getLogger(__name__)

# Confidence adjustments applied during consolidation.
DUPLICATE_CONFIDENCE_BOOST = 0.05
CONFLICT_CONFIDENCE_PENALTY = 0.2
MIN_CONFIDENCE = 0.1
MAX_CONFIDENCE = 1.0
# Above this confidence a memory counts as "high confidence" for conflict flagging.
HIGH_CONFIDENCE_THRESHOLD = 0.5


class MemoryConsolidator:
    """Periodic job: merge same-key duplicates and flag contradictory memories."""

    def __init__(self, store: MemoryStore):
        self._store = store

    async def consolidate(self, user_id: str = "default") -> dict:
        """Run a full consolidation pass.

        Returns stats: ``{"merged": n, "conflicts": m, "checked": k}`` where
        ``merged`` counts soft-deleted duplicates, ``conflicts`` counts flagged
        high-confidence contradictions, and ``checked`` counts memories examined.
        Exceptions are logged and the stats gathered so far are returned.
        """
        stats = {"merged": 0, "conflicts": 0, "checked": 0}
        try:
            await self._merge_similar(user_id, stats)
        except Exception as e:
            logger.warning("Consolidation merge pass failed for user %s: %s", user_id, e)
            return stats
        try:
            await self._detect_conflicts(user_id, stats)
        except Exception as e:
            logger.warning("Conflict detection failed for user %s: %s", user_id, e)
        return stats

    async def _merge_similar(self, user_id: str, stats: dict) -> None:
        """Merge memories with the same type and key.

        SESSION memories are excluded: per-session scratch context must not be
        consolidated into long-term facts.
        """
        for mem_type in MemoryType:
            if mem_type == MemoryType.SESSION:
                continue
            memories = await self._store.get_all_for_user(
                user_id=user_id,
                memory_type=mem_type,
            )
            stats["checked"] += len(memories)

            key_groups: dict[str, list[Memory]] = {}
            for m in memories:
                key_groups.setdefault(m.key, []).append(m)

            for key, group in key_groups.items():
                if len(group) <= 1:
                    continue
                # Keep highest confidence, merge others.
                group.sort(key=lambda m: m.confidence, reverse=True)
                keeper = group[0]
                original_confidence = keeper.confidence
                for dup in group[1:]:
                    if dup.value == keeper.value:
                        keeper.confidence = min(
                            MAX_CONFIDENCE, keeper.confidence + DUPLICATE_CONFIDENCE_BOOST
                        )
                        await self._store.soft_delete(dup.id)
                        stats["merged"] += 1
                        logger.debug("Merged duplicate memory: %s", key)
                    else:
                        keeper.confidence = max(
                            MIN_CONFIDENCE, keeper.confidence - CONFLICT_CONFIDENCE_PENALTY
                        )
                        logger.info(
                            "Value conflict on %s: %r vs %r", key, keeper.value, dup.value
                        )
                if keeper.confidence != original_confidence:
                    # Persist the adjustment — in-memory changes are lost otherwise.
                    await self._store.update_confidence(keeper.id, keeper.confidence)

    async def _detect_conflicts(self, user_id: str, stats: dict) -> None:
        """Flag contradictory profile facts (same key, different values, both
        high confidence). Both memories are kept; each gets a
        ``conflict_flagged`` changelog entry so the conflict is auditable."""
        profile_memories = await self._store.get_all_for_user(
            user_id=user_id,
            memory_type=MemoryType.USER_PROFILE,
        )
        key_groups: dict[str, list[Memory]] = {}
        for m in profile_memories:
            key_groups.setdefault(m.key, []).append(m)

        for key, group in key_groups.items():
            confident = [m for m in group if m.confidence > HIGH_CONFIDENCE_THRESHOLD]
            values = {m.value for m in confident}
            if len(values) <= 1:
                continue
            stats["conflicts"] += 1
            logger.warning("High-confidence conflict: key=%s, values=%s", key, values)
            for m in confident:
                rivals = "; ".join(sorted(v for v in values if v != m.value))
                await self._store.log_change(MemoryChangelog(
                    memory_id=m.id,
                    action="conflict_flagged",
                    old_value=rivals or None,
                    new_value=m.value,
                ))
