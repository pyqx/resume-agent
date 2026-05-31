"""SQLite database initialization with WAL mode via aiosqlite."""

import aiosqlite
from pathlib import Path

from core.config import settings


async def init_database() -> aiosqlite.Connection:
    """Initialize SQLite database with WAL mode and create base tables."""
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)

    conn = await aiosqlite.connect(str(settings.sqlite_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")

    await _create_tables(conn)
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
