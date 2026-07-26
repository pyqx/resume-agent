"""SQLite database initialization with WAL mode via aiosqlite."""

import asyncio
import logging
from pathlib import Path

import aiosqlite

from core.config import settings

logger = logging.getLogger(__name__)

# Serializes multi-statement write sequences on the shared connection so one
# writer's commit cannot land in the middle of another writer's sequence.
# (Single-user deployment: one process, low write volume.)
DB_WRITE_LOCK = asyncio.Lock()


async def init_database() -> aiosqlite.Connection:
    """Initialize SQLite database with WAL mode and create base tables."""
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)

    try:
        conn = await aiosqlite.connect(str(settings.sqlite_path))
    except Exception as e:
        raise RuntimeError(
            f"Failed to open SQLite database at {settings.sqlite_path}: {e}"
        ) from e
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.execute("PRAGMA busy_timeout=5000")

    await _create_tables(conn)
    await _migrate(conn)
    return conn


async def _create_tables(conn: aiosqlite.Connection):
    """Create base tables for the application."""
    await conn.executescript("""
        -- Resume versions
        CREATE TABLE IF NOT EXISTS resume_versions (
            id TEXT PRIMARY KEY,
            parent_id TEXT,
            name TEXT NOT NULL,
            notes TEXT DEFAULT '',
            resume_data_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Memory metadata (vectors in ChromaDB)
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            chroma_id TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            is_deleted INTEGER DEFAULT 0,
            last_accessed_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id, is_deleted);
        CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(user_id, type, is_deleted);

        -- Memory change log
        CREATE TABLE IF NOT EXISTS memory_changelog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id TEXT NOT NULL,
            action TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_changelog_memory ON memory_changelog(memory_id);

        -- Checkpoints
        CREATE TABLE IF NOT EXISTS checkpoints (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            checkpoint_data_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON checkpoints(session_id);

        -- Conversation sessions
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'default',
            title TEXT DEFAULT 'New Conversation',
            resume_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, updated_at DESC);

        -- Chat messages within a session
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'agent')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

    """)
    await conn.commit()


async def _migrate(conn: aiosqlite.Connection):
    """Additive migrations for databases created by older versions."""
    async with conn.execute("PRAGMA table_info(memories)") as cur:
        columns = {row["name"] for row in await cur.fetchall()}
    if "metadata" not in columns:
        logger.info("Migrating: adding memories.metadata column")
        await conn.execute(
            "ALTER TABLE memories ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'"
        )
        await conn.commit()
