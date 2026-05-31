"""MemoryStore — ChromaDB + SQLite dual-write with dedup and merge."""

import uuid

from chromadb.api import ClientAPI
from aiosqlite import Connection

from agent.memory.models import Memory, MemoryType, MemoryChangelog


class MemoryStore:
    """Writes to both ChromaDB (vectors) and SQLite (metadata)."""

    def __init__(self, chroma_client: ClientAPI, db: Connection):
        self._chroma = chroma_client
        self._db = db
        self._collection = chroma_client.get_or_create_collection(
            name="resume_agent_memories",
            metadata={"hnsw:space": "cosine"},
        )

    async def add(self, memory: Memory) -> str:
        """Add a new memory. Checks for duplicates first."""
        # Check for near-duplicates via cosine similarity
        existing_id = await self._find_duplicate(memory)
        if existing_id:
            return await self.merge_or_update(existing_id, memory)

        # Write to ChromaDB
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

        # Write to SQLite
        await self._db.execute(
            """INSERT INTO memories (id, user_id, type, key, value, confidence, chroma_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (memory.id, memory.user_id, memory.type.value,
             memory.key, memory.value, memory.confidence, chroma_id),
        )
        await self._log_change(memory.id, "add", None, memory.value)
        await self._db.commit()

        return memory.id

    async def search(
        self,
        query: str,
        user_id: str = "default",
        memory_types: list[MemoryType] | None = None,
        top_k: int = 10,
    ) -> list[Memory]:
        """Semantic search via ChromaDB + metadata filter from SQLite."""
        where_filter = {"user_id": user_id}
        if memory_types:
            type_values = [t.value for t in memory_types]
            if len(type_values) == 1:
                where_filter["type"] = type_values[0]

        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter,
        )

        memories = []
        if results["ids"] and results["ids"][0]:
            chroma_ids = results["ids"][0]
            distances = results["distances"][0] if results["distances"] else [0] * len(chroma_ids)

            for cid, dist in zip(chroma_ids, distances):
                cursor = await self._db.execute(
                    "SELECT * FROM memories WHERE chroma_id = ? AND is_deleted = 0",
                    (cid,),
                )
                row = await cursor.fetchone()
                if row:
                    memories.append(self._row_to_memory(row, similarity=1.0 - dist))

        return memories

    async def get_by_id(self, memory_id: str) -> Memory | None:
        cursor = await self._db.execute(
            "SELECT * FROM memories WHERE id = ? AND is_deleted = 0",
            (memory_id,),
        )
        row = await cursor.fetchone()
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

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_memory(r) for r in rows]

    async def merge_or_update(self, memory_id: str, new_memory: Memory) -> str:
        """Merge or update an existing memory with new information."""
        existing = await self.get_by_id(memory_id)
        if not existing:
            return await self.add(new_memory)

        old_value = existing.value

        # For preferences: if same key with different value, update confidence
        if new_memory.type == MemoryType.PREFERENCE and existing.key == new_memory.key:
            if existing.value == new_memory.value:
                existing.confidence = min(1.0, existing.confidence + 0.1)
            else:
                existing.confidence = max(0.1, existing.confidence - 0.3)
            existing.value = new_memory.value
        elif new_memory.type == MemoryType.USER_PROFILE:
            existing.value = new_memory.value
            existing.confidence = new_memory.confidence
        else:
            existing.value = new_memory.value
            existing.confidence = new_memory.confidence

        await self._db.execute(
            """UPDATE memories SET value=?, confidence=?, updated_at=datetime('now')
               WHERE id=?""",
            (existing.value, existing.confidence, memory_id),
        )
        await self._log_change(memory_id, "merge", old_value, existing.value)
        await self._db.commit()
        return memory_id

    async def soft_delete(self, memory_id: str):
        await self._db.execute(
            "UPDATE memories SET is_deleted=1, updated_at=datetime('now') WHERE id=?",
            (memory_id,),
        )
        await self._log_change(memory_id, "soft_delete", None, None)
        await self._db.commit()

    async def purge_user(self, user_id: str = "default"):
        """Completely remove all memories for a user."""
        cursor = await self._db.execute(
            "SELECT chroma_id FROM memories WHERE user_id = ?",
            (user_id,),
        )
        rows = await cursor.fetchall()
        chroma_ids = [r[0] for r in rows if r[0]]
        if chroma_ids:
            self._collection.delete(ids=chroma_ids)
        await self._db.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
        await self._db.execute("DELETE FROM memory_changelog WHERE memory_id IN (SELECT id FROM memories WHERE user_id = ?)", (user_id,))
        await self._db.commit()

    async def _find_duplicate(self, memory: Memory) -> str | None:
        """Find near-duplicate memory via ChromaDB vector similarity."""
        try:
            results = self._collection.query(
                query_texts=[memory.to_text()],
                n_results=1,
                where={"user_id": memory.user_id, "type": memory.type.value},
            )
            if results["ids"] and results["ids"][0] and results["distances"] and results["distances"][0]:
                dist = results["distances"][0][0]
                if dist < 0.1:
                    chroma_id = results["ids"][0][0]
                    cursor = await self._db.execute(
                        "SELECT id FROM memories WHERE chroma_id = ? AND is_deleted = 0",
                        (chroma_id,),
                    )
                    row = await cursor.fetchone()
                    if row:
                        return row[0]
        except Exception:
            pass
        return None

    async def _log_change(self, memory_id: str, action: str, old_val: str | None, new_val: str | None):
        await self._db.execute(
            "INSERT INTO memory_changelog (memory_id, action, old_value, new_value) VALUES (?, ?, ?, ?)",
            (memory_id, action, old_val, new_val),
        )

    def _row_to_memory(self, row, similarity: float = 0.0) -> Memory:
        return Memory(
            id=row["id"],
            user_id=row["user_id"],
            type=MemoryType(row["type"]),
            key=row["key"],
            value=row["value"],
            confidence=row["confidence"],
            chroma_id=row["chroma_id"],
            is_deleted=bool(row["is_deleted"]),
            last_accessed_at=row["last_accessed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
