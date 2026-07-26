"""Memory data models — structured facts, not conversation logs."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class MemoryType(str, Enum):
    USER_PROFILE = "user_profile"
    PREFERENCE = "preference"
    SESSION = "session"
    FEEDBACK = "feedback"


@dataclass
class Memory:
    """A single structured memory fact."""
    id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = "default"
    type: MemoryType = MemoryType.SESSION
    key: str = ""
    value: str = ""
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)
    chroma_id: str = ""
    is_deleted: bool = False
    # SQLite returns TEXT timestamps; freshly-built objects carry datetime.
    last_accessed_at: str | datetime | None = field(default_factory=datetime.now)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_text(self) -> str:
        """Embedding document. Content only — a type prefix would make all
        same-type memories look artificially similar to the embedder."""
        return f"{self.key}: {self.value}"


@dataclass
class MemoryChangelog:
    """Record of memory mutations for audit and debugging."""
    id: int = 0
    memory_id: str = ""
    action: str = ""
    old_value: str | None = None
    new_value: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MemorySearchResult:
    """A memory match from semantic search."""
    memory: Memory
    similarity: float = 0.0
