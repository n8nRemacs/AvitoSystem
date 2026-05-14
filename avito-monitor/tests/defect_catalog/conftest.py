"""Fixtures for defect_catalog tests — in-memory async SQLite session
with raw DDL (UUID→TEXT, no Postgres-specific defaults)."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS feature_nodes (
        id          TEXT PRIMARY KEY,
        parent_id   TEXT REFERENCES feature_nodes(id) ON DELETE CASCADE,
        kind        TEXT NOT NULL,
        slug        TEXT NOT NULL,
        title       TEXT NOT NULL,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        prompt_hint TEXT,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (parent_id, slug),
        CHECK (kind IN ('node', 'defect'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS device_nodes (
        id          TEXT PRIMARY KEY,
        parent_id   TEXT REFERENCES device_nodes(id) ON DELETE CASCADE,
        slug        TEXT NOT NULL,
        title       TEXT NOT NULL,
        kind        TEXT,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (parent_id, slug)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS device_feature_bindings (
        id              TEXT PRIMARY KEY,
        device_node_id  TEXT NOT NULL REFERENCES device_nodes(id) ON DELETE CASCADE,
        feature_node_id TEXT NOT NULL REFERENCES feature_nodes(id) ON DELETE CASCADE,
        defect_action   TEXT NOT NULL,
        unknown_action  TEXT NOT NULL,
        disabled        INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (device_node_id, feature_node_id),
        CHECK (defect_action IN ('block', 'info')),
        CHECK (unknown_action IN ('ask', 'skip'))
    )
    """,
]


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        for stmt in _DDL:
            await conn.execute(text(stmt))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(text("PRAGMA foreign_keys = ON"))
        yield s
    await engine.dispose()
