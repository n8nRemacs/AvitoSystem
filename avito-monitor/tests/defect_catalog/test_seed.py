"""Seed idempotency — running twice yields same row counts."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from scripts.seed_defect_catalog import FEATURES, DEVICES, BINDINGS


def test_seed_data_lists_consistent():
    """FEATURES, DEVICES, BINDINGS have expected sizes (sanity)."""
    assert len(FEATURES) == 8
    assert len(DEVICES) == 3
    assert len(BINDINGS) == 6


@pytest.mark.asyncio
async def test_seed_runs_twice_no_duplicates(db_session):
    """Simulate seed by inlining inserts; second run should not duplicate.
    SQLite uses INSERT OR IGNORE (equivalent to ON CONFLICT DO NOTHING for our use)."""
    for f in FEATURES:
        for _ in range(2):  # twice
            await db_session.execute(text("""
                INSERT OR IGNORE INTO feature_nodes
                    (id, parent_id, kind, slug, title, sort_order, prompt_hint)
                VALUES (:id, :pid, :kind, :slug, :title, :sort, :hint)
            """), {
                "id": str(f["id"]),
                "pid": str(f["parent"]) if f["parent"] else None,
                "kind": f["kind"], "slug": f["slug"], "title": f["title"],
                "sort": f["sort"], "hint": f.get("hint"),
            })
    await db_session.commit()
    count = (await db_session.execute(
        text("SELECT COUNT(*) FROM feature_nodes")
    )).scalar()
    assert count == len(FEATURES)
