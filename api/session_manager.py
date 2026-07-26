"""Session manager for conversation persistence."""

import logging
import uuid

import aiosqlite

from core.database import DB_WRITE_LOCK

logger = logging.getLogger(__name__)

_MAX_LIST_LIMIT = 200


class SessionManager:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def create_session(self, user_id: str = "default", resume_id: str = "") -> str:
        session_id = str(uuid.uuid4())
        async with DB_WRITE_LOCK:
            await self._db.execute(
                "INSERT INTO sessions (id, user_id, resume_id) VALUES (?, ?, ?)",
                (session_id, user_id, resume_id or None),
            )
            await self._db.commit()
        return session_id

    async def get_session(self, session_id: str) -> dict | None:
        """Fetch a single session row (replaces list-and-scan lookups)."""
        async with self._db.execute(
            """SELECT s.id, s.user_id, s.title, s.resume_id, s.created_at, s.updated_at,
                      (SELECT COUNT(*) FROM messages WHERE session_id = s.id) AS message_count
               FROM sessions s WHERE s.id = ?""",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_sessions(self, user_id: str = "default", limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), _MAX_LIST_LIMIT))
        async with self._db.execute(
            """SELECT s.id, s.title, s.resume_id, s.created_at, s.updated_at,
                      (SELECT COUNT(*) FROM messages WHERE session_id = s.id) AS message_count
               FROM sessions s
               WHERE s.user_id = ?
               ORDER BY s.updated_at DESC
               LIMIT ?""",
            (user_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def save_message(self, session_id: str, role: str, content: str):
        if role not in ("user", "agent"):
            raise ValueError(f"Invalid message role: {role}")
        async with DB_WRITE_LOCK:
            await self._db.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            await self._db.execute(
                "UPDATE sessions SET updated_at = datetime('now') WHERE id = ?",
                (session_id,),
            )
            await self._db.commit()

    async def get_messages(self, session_id: str, limit: int = 200) -> list[dict]:
        """Most recent `limit` messages in chronological order."""
        limit = max(1, min(int(limit), 1000))
        async with self._db.execute(
            """SELECT id, role, content, created_at FROM (
                   SELECT id, role, content, created_at
                   FROM messages WHERE session_id = ?
                   ORDER BY id DESC LIMIT ?
               ) ORDER BY id ASC""",
            (session_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def set_title_once(self, session_id: str, title: str):
        """Set the title only if it is still the default (first user message wins)."""
        async with DB_WRITE_LOCK:
            await self._db.execute(
                "UPDATE sessions SET title = ? WHERE id = ? AND title = 'New Conversation'",
                (title, session_id),
            )
            await self._db.commit()

    async def update_title(self, session_id: str, title: str):
        """Explicit rename (user-initiated)."""
        async with DB_WRITE_LOCK:
            await self._db.execute(
                "UPDATE sessions SET title = ?, updated_at = datetime('now') WHERE id = ?",
                (title, session_id),
            )
            await self._db.commit()

    async def set_resume_id(self, session_id: str, resume_id: str):
        async with DB_WRITE_LOCK:
            await self._db.execute(
                "UPDATE sessions SET resume_id = ? WHERE id = ?",
                (resume_id or None, session_id),
            )
            await self._db.commit()

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session, its messages (FK cascade) and its checkpoints."""
        async with DB_WRITE_LOCK:
            await self._db.execute(
                "DELETE FROM checkpoints WHERE session_id = ?", (session_id,)
            )
            cursor = await self._db.execute(
                "DELETE FROM sessions WHERE id = ?", (session_id,)
            )
            await self._db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Session deleted: %s", session_id)
        return deleted
