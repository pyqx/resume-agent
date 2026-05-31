"""Checkpoint management for Agent loop state persistence and recovery."""

import json
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from aiosqlite import Connection

from agent.planner import StrategicPlan

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    checkpoint_id: str = field(default_factory=lambda: str(uuid4()))
    session_id: str = ""
    user_id: str = "default"
    strategic_plan: StrategicPlan | None = None
    current_milestone_id: str = ""
    tactical_progress: dict = field(default_factory=dict)
    pending_questions: list[str] = field(default_factory=list)
    working_state_hash: str = ""
    tool_call_history: list[dict] = field(default_factory=list)
    memory_snapshot_ids: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "current_milestone_id": self.current_milestone_id,
            "tactical_progress": self.tactical_progress,
            "pending_questions": self.pending_questions,
            "working_state_hash": self.working_state_hash,
            "tool_call_history": self.tool_call_history,
            "memory_snapshot_ids": self.memory_snapshot_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }, default=str)


class CheckpointManager:
    """Save and restore Agent loop state for fault tolerance."""

    def __init__(self, db: Connection):
        self._db = db

    @staticmethod
    def compute_hash(data: dict) -> str:
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]

    async def save(self, checkpoint: Checkpoint):
        """Persist a checkpoint to SQLite."""
        now = datetime.now().isoformat()
        checkpoint.updated_at = now
        if not checkpoint.created_at:
            checkpoint.created_at = now

        plan_json = json.dumps(
            checkpoint.strategic_plan, default=str
        ) if checkpoint.strategic_plan else "{}"

        await self._db.execute(
            """INSERT OR REPLACE INTO checkpoints
               (id, session_id, user_id, checkpoint_data_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                checkpoint.checkpoint_id,
                checkpoint.session_id,
                checkpoint.user_id,
                json.dumps({
                    **json.loads(checkpoint.to_json()),
                    "strategic_plan_json": plan_json,
                }),
                checkpoint.created_at,
            ),
        )
        await self._db.commit()

    async def load(self, session_id: str) -> Checkpoint | None:
        """Load the most recent checkpoint for a session."""
        cursor = await self._db.execute(
            "SELECT * FROM checkpoints WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        data = json.loads(row["checkpoint_data_json"])
        return Checkpoint(
            checkpoint_id=data.get("checkpoint_id", str(uuid4())),
            session_id=data.get("session_id", session_id),
            user_id=data.get("user_id", "default"),
            current_milestone_id=data.get("current_milestone_id", ""),
            tactical_progress=data.get("tactical_progress", {}),
            pending_questions=data.get("pending_questions", []),
            working_state_hash=data.get("working_state_hash", ""),
            tool_call_history=data.get("tool_call_history", []),
            memory_snapshot_ids=data.get("memory_snapshot_ids", []),
            created_at=row["created_at"] if "created_at" in row else "",
            updated_at=row["created_at"] if "created_at" in row else "",
        )

    async def verify(self, checkpoint: Checkpoint, current_state_hash: str) -> bool:
        """Verify that the current working state matches the checkpoint."""
        return checkpoint.working_state_hash == current_state_hash

    async def delete(self, session_id: str):
        """Remove all checkpoints for a session."""
        await self._db.execute("DELETE FROM checkpoints WHERE session_id = ?", (session_id,))
        await self._db.commit()
