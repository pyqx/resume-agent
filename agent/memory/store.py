"""MemoryStore — ChromaDB + SQLite dual-write with dedup and merge."""

import asyncio
import json
import logging
import uuid

from chromadb.api import ClientAPI
from aiosqlite import Connection

from agent.memory.models import Memory, MemoryType, MemoryChangelog, MemorySearchResult

logger = logging.getLogger(__name__)

# Cosine distance below which a same-type memory counts as a near-duplicate.
DUPLICATE_DISTANCE_THRESHOLD = 0.1


class MemoryStore:
    """Writes to both ChromaDB (vectors) and SQLite (metadata)."""

    def __init__(self, chroma_client: ClientAPI, db: Connection):
        self._chroma = chroma_client
        self._db = db
        # Serializes check-then-act write paths (dedup lookup + insert/merge).
        self._write_lock = asyncio.Lock()
        self._collection = chroma_client.get_or_create_collection(
            name="resume_agent_memories",
            metadata={"hnsw:space": "cosine"},
        )

    # ── Write paths (serialized by _write_lock) ─────────────────────────

    async def add(self, memory: Memory) -> str:
        """Add a new memory. Near-duplicates are merged instead of re-added."""
        async with self._write_lock:
            return await self._add_unlocked(memory)

    async def merge_or_update(self, memory_id: str, new_memory: Memory) -> str:
        """Merge or update an existing memory with new information."""
        async with self._write_lock:
            return await self._merge_or_update_unlocked(memory_id, new_memory)

    async def update_confidence(self, memory_id: str, confidence: float) -> None:
        """Persist a confidence change (used by the consolidator)."""
        confidence = max(0.0, min(1.0, float(confidence)))
        async with self._write_lock:
            async with self._db.execute(
                "SELECT confidence FROM memories WHERE id = ?", (memory_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                logger.warning("update_confidence: memory %s not found", memory_id)
                return
            old_confidence = row["confidence"]
            await self._db.execute(
                "UPDATE memories SET confidence=?, updated_at=datetime('now') WHERE id=?",
                (confidence, memory_id),
            )
            await self._log_change(MemoryChangelog(
                memory_id=memory_id,
                action="update_confidence",
                old_value=str(old_confidence),
                new_value=str(confidence),
            ))
            await self._db.commit()

    async def soft_delete(self, memory_id: str) -> None:
        """Mark a memory deleted in SQLite and drop its vector from Chroma.

        The SQLite row is kept (is_deleted=1) for audit; the vector is removed
        so deleted memories can never surface in semantic search again.
        """
        async with self._write_lock:
            async with self._db.execute(
                "SELECT value, chroma_id FROM memories WHERE id = ?", (memory_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                logger.warning("soft_delete: memory %s not found", memory_id)
                return
            await self._db.execute(
                "UPDATE memories SET is_deleted=1, updated_at=datetime('now') WHERE id=?",
                (memory_id,),
            )
            if row["chroma_id"]:
                try:
                    self._collection.delete(ids=[row["chroma_id"]])
                except Exception as e:
                    logger.warning("Chroma delete failed for memory %s: %s", memory_id, e)
            await self._log_change(MemoryChangelog(
                memory_id=memory_id,
                action="soft_delete",
                old_value=row["value"],
                new_value=None,
            ))
            await self._db.commit()
            logger.info("Soft-deleted memory %s", memory_id)

    async def purge_user(self, user_id: str = "default") -> None:
        """Completely remove all memories, changelog rows, and vectors for a user."""
        async with self._write_lock:
            # Changelog first: the subquery must run while the memories still exist.
            await self._db.execute(
                "DELETE FROM memory_changelog WHERE memory_id IN "
                "(SELECT id FROM memories WHERE user_id = ?)",
                (user_id,),
            )
            async with self._db.execute(
                "DELETE FROM memories WHERE user_id = ?", (user_id,)
            ) as cur:
                deleted = cur.rowcount
            await self._db.commit()
            self._collection.delete(where={"user_id": user_id})
            logger.info("Purged %d memories for user %s", deleted, user_id)

    # ── Read paths ──────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        user_id: str = "default",
        memory_types: list[MemoryType] | None = None,
        top_k: int = 10,
    ) -> list[MemorySearchResult]:
        """Semantic search via ChromaDB, hydrated from SQLite.

        Returns results with real similarity scores (1.0 - cosine distance,
        clamped to [0, 1]), ordered most similar first.
        """
        where: dict = {"user_id": user_id}
        if memory_types:
            type_values = [t.value for t in memory_types]
            # chromadb requires an explicit $and for multi-key filters.
            where = {"$and": [{"user_id": user_id}, {"type": {"$in": type_values}}]}

        results = self._collection.query(
            query_texts=[query],
            n_results=max(1, top_k),
            where=where,
        )

        ids_matrix = results.get("ids") or [[]]
        chroma_ids = ids_matrix[0] if ids_matrix else []
        distances_matrix = results.get("distances") or []
        distances = list(distances_matrix[0]) if distances_matrix else []
        # A missing distance must NOT default to 0 — that would fake a perfect
        # match. Pad with 1.0 (similarity 0.0) instead.
        if len(distances) < len(chroma_ids):
            distances += [1.0] * (len(chroma_ids) - len(distances))

        matches: list[MemorySearchResult] = []
        for cid, dist in zip(chroma_ids, distances):
            async with self._db.execute(
                "SELECT * FROM memories WHERE chroma_id = ? AND is_deleted = 0",
                (cid,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                continue
            dist = 1.0 if dist is None else dist
            similarity = max(0.0, min(1.0, 1.0 - dist))
            matches.append(
                MemorySearchResult(memory=self._row_to_memory(row), similarity=similarity)
            )

        if matches:
            ids = [r.memory.id for r in matches]
            placeholders = ",".join("?" for _ in ids)
            async with self._write_lock:
                await self._db.execute(
                    "UPDATE memories SET last_accessed_at=datetime('now') "
                    f"WHERE id IN ({placeholders})",
                    ids,
                )
                await self._db.commit()

        return matches

    async def get_by_id(self, memory_id: str) -> Memory | None:
        async with self._db.execute(
            "SELECT * FROM memories WHERE id = ? AND is_deleted = 0",
            (memory_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_memory(row) if row else None

    async def get_all_for_user(
        self,
        user_id: str = "default",
        memory_type: MemoryType | None = None,
    ) -> list[Memory]:
        query = "SELECT * FROM memories WHERE user_id = ? AND is_deleted = 0"
        params: list = [user_id]
        if memory_type:
            query += " AND type = ?"
            params.append(memory_type.value)
        query += " ORDER BY updated_at DESC"

        async with self._db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return [self._row_to_memory(r) for r in rows]

    async def get_changelog(self, user_id: str = "default", limit: int = 50) -> list[dict]:
        """Most recent changelog entries for a user, newest first."""
        async with self._db.execute(
            """SELECT c.id, c.memory_id, c.action, c.old_value, c.new_value, c.timestamp
               FROM memory_changelog c
               JOIN memories m ON m.id = c.memory_id
               WHERE m.user_id = ?
               ORDER BY c.id DESC
               LIMIT ?""",
            (user_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "id": r["id"],
                "memory_id": r["memory_id"],
                "action": r["action"],
                "old_value": r["old_value"],
                "new_value": r["new_value"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    async def log_change(self, entry: MemoryChangelog) -> None:
        """Append a standalone changelog entry (used by the consolidator)."""
        async with self._write_lock:
            await self._log_change(entry)
            await self._db.commit()

    # ── Internals (callers must hold _write_lock for the *_unlocked ones) ──

    async def _add_unlocked(self, memory: Memory) -> str:
        existing_id = await self._find_duplicate(memory)
        if existing_id:
            return await self._merge_or_update_unlocked(existing_id, memory)

        chroma_id = str(uuid.uuid4())
        self._collection.add(
            ids=[chroma_id],
            documents=[memory.to_text()],
            metadatas=[{
                "type": memory.type.value,
                "key": memory.key,
                "user_id": memory.user_id,
            }],
        )
        memory.chroma_id = chroma_id

        await self._db.execute(
            """INSERT INTO memories
               (id, user_id, type, key, value, confidence, chroma_id, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (memory.id, memory.user_id, memory.type.value, memory.key,
             memory.value, memory.confidence, chroma_id,
             json.dumps(memory.metadata or {}, ensure_ascii=False)),
        )
        await self._log_change(MemoryChangelog(
            memory_id=memory.id, action="add", old_value=None, new_value=memory.value,
        ))
        await self._db.commit()
        return memory.id

    async def _merge_or_update_unlocked(self, memory_id: str, new_memory: Memory) -> str:
        existing = await self.get_by_id(memory_id)
        if not existing:
            return await self._add_unlocked(new_memory)

        old_value = existing.value

        # For preferences: same key with same value reinforces, different value erodes.
        if new_memory.type == MemoryType.PREFERENCE and existing.key == new_memory.key:
            if existing.value == new_memory.value:
                existing.confidence = min(1.0, existing.confidence + 0.1)
            else:
                existing.confidence = max(0.1, existing.confidence - 0.3)
            existing.value = new_memory.value
        else:
            existing.value = new_memory.value
            existing.confidence = new_memory.confidence

        merged_metadata = {**(existing.metadata or {}), **(new_memory.metadata or {})}

        await self._db.execute(
            """UPDATE memories SET value=?, confidence=?, metadata=?,
               updated_at=datetime('now') WHERE id=?""",
            (existing.value, existing.confidence,
             json.dumps(merged_metadata, ensure_ascii=False), memory_id),
        )

        # Keep the vector store in sync with the merged content.
        if existing.chroma_id:
            try:
                self._collection.update(
                    ids=[existing.chroma_id],
                    documents=[existing.to_text()],
                    metadatas=[{
                        "type": existing.type.value,
                        "key": existing.key,
                        "user_id": existing.user_id,
                    }],
                )
            except Exception as e:
                logger.warning("Chroma update failed for memory %s: %s", memory_id, e)
        else:
            logger.warning("Memory %s has no chroma_id; vector not updated", memory_id)

        await self._log_change(MemoryChangelog(
            memory_id=memory_id, action="merge",
            old_value=old_value, new_value=existing.value,
        ))
        await self._db.commit()
        logger.info("Merged memory %s (key=%s)", memory_id, existing.key)
        return memory_id

    async def _find_duplicate(self, memory: Memory) -> str | None:
        """Find a near-duplicate memory via ChromaDB vector similarity."""
        try:
            results = self._collection.query(
                query_texts=[memory.to_text()],
                n_results=1,
                where={"$and": [
                    {"user_id": memory.user_id},
                    {"type": memory.type.value},
                ]},
            )
            ids = (results.get("ids") or [[]])[0]
            distances = (results.get("distances") or [[]])[0]
            if ids and distances:
                dist = distances[0]
                if dist is not None and dist < DUPLICATE_DISTANCE_THRESHOLD:
                    async with self._db.execute(
                        "SELECT id FROM memories WHERE chroma_id = ? AND is_deleted = 0",
                        (ids[0],),
                    ) as cur:
                        row = await cur.fetchone()
                    if row:
                        return row["id"]
        except Exception as e:
            # Dedup failure must be observable: it silently degrades to
            # duplicate inserts otherwise.
            logger.warning("Duplicate check failed for key %r: %s", memory.key, e)
        return None

    async def _log_change(self, entry: MemoryChangelog) -> None:
        await self._db.execute(
            """INSERT INTO memory_changelog (memory_id, action, old_value, new_value)
               VALUES (?, ?, ?, ?)""",
            (entry.memory_id, entry.action, entry.old_value, entry.new_value),
        )

    def _row_to_memory(self, row) -> Memory:
        raw_metadata = row["metadata"] if "metadata" in row.keys() else None
        try:
            metadata = json.loads(raw_metadata) if raw_metadata else {}
            if not isinstance(metadata, dict):
                metadata = {}
        except (TypeError, ValueError):
            logger.warning("Malformed metadata JSON on memory %s; ignoring", row["id"])
            metadata = {}
        return Memory(
            id=row["id"],
            user_id=row["user_id"],
            type=MemoryType(row["type"]),
            key=row["key"],
            value=row["value"],
            confidence=row["confidence"],
            metadata=metadata,
            chroma_id=row["chroma_id"],
            is_deleted=bool(row["is_deleted"]),
            last_accessed_at=row["last_accessed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
