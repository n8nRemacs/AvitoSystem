"""Seed avito_param_catalog from JSON snapshots in DOCS/avito_api_snapshots/.

Run after migration 0010_avito_param_catalog. Idempotent: re-running upserts
``last_seen_at`` and refreshes ``human_name`` if the snapshot was edited; it
will never delete rows added from other sources (blob_decoder, deeplink, etc.).

Usage:
    python -m scripts.seed_avito_param_catalog
    python -m scripts.seed_avito_param_catalog --file DOCS/avito_api_snapshots/iphone_models.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.db.base import dispose_engine, get_sessionmaker
from app.db.models import AvitoParamCatalog


# Snapshot files live alongside avito_regions.json / criteria_templates.yaml
# inside the container build context. The DOCS/avito_api_snapshots/ copy is a
# documentation mirror — same content, different location.
_DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"
_DEFAULT_FILES = [
    _DATA_DIR / "iphone_models.json",
]


def _rows_from_snapshot(snapshot: dict[str, Any], file_path: Path) -> list[dict[str, Any]]:
    """Flatten snapshot's nested {kind: {param_id, values: {name: value}}} into row dicts.

    Each row matches AvitoParamCatalog columns. Snapshot schema is documented
    inline in DOCS/avito_api_snapshots/iphone_models.json.
    """
    category_id = snapshot["category_id_mobile_api"]
    source_ref = file_path.name
    rows: list[dict[str, Any]] = []
    for kind, spec in snapshot["params"].items():
        param_id = spec["param_id"]
        parent_param_id = spec.get("parent_param_id")
        parent_value = spec.get("parent_value")
        for human_name, value in spec["values"].items():
            rows.append({
                "category_id": category_id,
                "param_id": param_id,
                "param_value": value,
                "human_name": human_name,
                "param_kind": kind,
                "parent_param_id": parent_param_id,
                "parent_value": parent_value,
                "source": "manual_json",
                "source_ref": source_ref,
            })
    return rows


async def _upsert(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """ON CONFLICT (category_id, param_id, param_value) DO UPDATE.

    Refresh ``human_name`` and ``last_seen_at`` only — never overwrite a
    higher-trust ``source`` like ``dicts_endpoint`` with manual_json.
    Returns ``(inserted_or_refreshed, total)`` for reporting.
    """
    if not rows:
        return 0, 0

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = insert(AvitoParamCatalog).values(rows)
        do_update = stmt.on_conflict_do_update(
            constraint="uq_avito_param_catalog_natural",
            set_={
                "human_name": stmt.excluded.human_name,
                "last_seen_at": func.now(),
            },
        )
        result = await session.execute(do_update)
        await session.commit()
        # rowcount returns affected rows (insert + update). Postgres counts
        # both, so it equals len(rows) on the happy path.
        return result.rowcount or 0, len(rows)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file", action="append", type=Path,
        help="Snapshot JSON path (repeatable). Defaults to iphone_models.json.",
    )
    args = parser.parse_args()
    files = args.file if args.file else _DEFAULT_FILES

    try:
        for path in files:
            if not path.exists():
                print(f"[skip] {path} — not found")
                continue
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            rows = _rows_from_snapshot(snapshot, path)
            affected, total = await _upsert(rows)
            print(f"[ok]   {path.name}: {affected}/{total} rows upserted")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
