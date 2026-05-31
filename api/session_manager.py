"""Session manager for conversation persistence."""

import uuid
import aiosqlite


class SessionManager:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def create_session(self, user_id: str = "default", resume_id: str = "") -> str:
        session_id = str(uuid.uuid4())
        await self._db.execute(
            "INSERT INTO sessions (id, user_id, resume_id) VALUES (?, ?, ?)",
            (session_id, user_id, resume_id or None),
        )
        await self._db.commit()
        return session_id

    async def list_sessions(self, user_id: str = "default", limit: int = 50) -> list:
        cursor = await self._db.execute(
            """SELECT s.id, s.title, s.resume_id, s.created_at, s.updated_at,
                      (SELECT COUNT(*) FROM messages WHERE session_id = s.id) as message_count
               FROM sessions s
               WHERE s.user_id = ?
               ORDER BY s.updated_at DESC
               LIMIT ?""",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def save_message(self, session_id: str, role: str, content: str):
        await self._db.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        await self._db.execute(
            "UPDATE sessions SET updated_at = datetime('now') WHERE id = ?",
            (session_id,),
        )
        await self._db.commit()

    async def get_messages(self, session_id: str) -> list:
        cursor = await self._db.execute(
            "SELECT id, role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def update_title(self, session_id: str, title: str):
        await self._db.execute(
            "UPDATE sessions SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (title, session_id),
        )
        await self._db.commit()

    async def delete_session(self, session_id: str):
        await self._db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        await self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await self._db.commit()
