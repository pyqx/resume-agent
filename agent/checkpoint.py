"""Checkpoint management for Agent loop state persistence and recovery.

Purpose: if a request dies mid-loop (crash, disconnect), the next request in
the same session can see what tools already ran. Checkpoints from cleanly
finished runs are deleted, so recovery never injects stale context.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from aiosqlite import Connection

from core.database import DB_WRITE_LOCK

logger = logging.getLogger(__name__)

# Keep at most N checkpoint rows per session.
_KEEP_PER_SESSION = 5


@dataclass
class Checkpoint:
    checkpoint_id: str = field(default_factory=lambda: str(uuid4()))
    session_id: str = ""
    user_id: str = "default"
    working_state_hash: str = ""
    tool_call_history: list[dict] = field(default_factory=list)
    created_at: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "working_state_hash": self.working_state_hash,
            "tool_call_history": self.tool_call_history,
            "created_at": self.created_at,
        }, default=str)


class CheckpointManager:
    """Save and restore Agent loop state for fault tolerance."""

    def __init__(self, db: Connection):
        self._db = db

    @staticmethod
    def compute_hash(data: dict) -> str:
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

    async def save(self, checkpoint: Checkpoint):
        """Persist a checkpoint and prune old rows for the session."""
        if not checkpoint.created_at:
            checkpoint.created_at = datetime.now(timezone.utc).isoformat()

        async with DB_WRITE_LOCK:
            await self._db.execute(
                """INSERT OR REPLACE INTO checkpoints
                   (id, session_id, user_id, checkpoint_data_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    checkpoint.checkpoint_id,
                    checkpoint.session_id,
                    checkpoint.user_id,
                    checkpoint.to_json(),
                    checkpoint.created_at,
                ),
            )
            await self._db.execute(
                """DELETE FROM checkpoints
                   WHERE session_id = ? AND id NOT IN (
                       SELECT id FROM checkpoints
                       WHERE session_id = ?
                       ORDER BY created_at DESC LIMIT ?
                   )""",
                (checkpoint.session_id, checkpoint.session_id, _KEEP_PER_SESSION),
            )
            await self._db.commit()

    async def load(self, session_id: str) -> Checkpoint | None:
        """Load the most recent checkpoint for a session (None if absent/corrupt)."""
        try:
            async with self._db.execute(
                "SELECT * FROM checkpoints WHERE session_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                return None

            row_map = dict(row)
            data = json.loads(row_map["checkpoint_data_json"])
            return Checkpoint(
                checkpoint_id=data.get("checkpoint_id", str(uuid4())),
                session_id=data.get("session_id", session_id),
                user_id=data.get("user_id", "default"),
                working_state_hash=data.get("working_state_hash", ""),
                tool_call_history=data.get("tool_call_history", []),
                created_at=row_map.get("created_at", ""),
            )
        except Exception as e:
            logger.warning("Checkpoint load failed for session %s: %s", session_id, e)
            return None

    def verify(self, checkpoint: Checkpoint, current_state_hash: str) -> bool:
        """True if the checkpoint was taken against the same working state."""
        return bool(
            checkpoint.working_state_hash
            and checkpoint.working_state_hash == current_state_hash
        )

    async def delete(self, session_id: str):
        """Remove all checkpoints for a session (called on clean completion)."""
        async with DB_WRITE_LOCK:
            await self._db.execute(
                "DELETE FROM checkpoints WHERE session_id = ?", (session_id,)
            )
            await self._db.commit()
