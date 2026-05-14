"""Idempotent MVP seed for defect catalog.

Run: python -m scripts.seed_defect_catalog
Re-runs are safe — uses INSERT ... ON CONFLICT DO NOTHING semantics.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import text

from app.db.base import dispose_engine, get_sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_defect_catalog")


# Stable UUIDs for idempotency (so re-run finds same rows).
NS = uuid.UUID("11111111-2222-3333-4444-555555555555")

def fid(path: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"feature:{path}")

def did(path: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"device:{path}")


# Feature catalog: 2 nodes + 6 defects
FEATURES = [
    {"id": fid("case"), "parent": None, "kind": "node",
     "slug": "case", "title": "Корпус", "sort": 1},
    {"id": fid("case/back_broken"), "parent": fid("case"), "kind": "defect",
     "slug": "back_broken", "title": "Задняя крышка разбита", "sort": 1,
     "hint": "defect — продавец явно упоминает разбитую заднюю крышку. ok — упомянуто что задняя целая."},
    {"id": fid("case/midframe_bent"), "parent": fid("case"), "kind": "defect",
     "slug": "midframe_bent", "title": "Midframe погнут", "sort": 2,
     "hint": "defect — корпус погнут / замят. ok — корпус ровный."},
    {"id": fid("case/midframe_cracked"), "parent": fid("case"), "kind": "defect",
     "slug": "midframe_cracked", "title": "Midframe сломан", "sort": 3,
     "hint": "defect — трещина на корпусе / сломан midframe. ok — без трещин."},

    {"id": fid("display"), "parent": None, "kind": "node",
     "slug": "display", "title": "Дисплей", "sort": 2},
    {"id": fid("display/glass_broken"), "parent": fid("display"), "kind": "defect",
     "slug": "glass_broken", "title": "Стекло разбито", "sort": 1,
     "hint": "defect — трещины/сколы на стекле. ok — стекло целое."},
    {"id": fid("display/stains_stripes"), "parent": fid("display"), "kind": "defect",
     "slug": "stains_stripes", "title": "Полосы / пятна", "sort": 2,
     "hint": "defect — пятна / полосы / битые пиксели. ok — изображение чистое."},
    {"id": fid("display/replaced"), "parent": fid("display"), "kind": "defect",
     "slug": "replaced", "title": "Дисплей менялся", "sort": 3,
     "hint": "defect — дисплей менялся. unknown — нет упоминания."},
]

# Device tree: Phone → Apple → iPhone 12 PM
DEVICES = [
    {"id": did("phone"), "parent": None, "slug": "phone", "title": "Phone",
     "kind": "type", "sort": 1},
    {"id": did("phone/apple"), "parent": did("phone"), "slug": "apple",
     "title": "Apple", "kind": "brand", "sort": 1},
    {"id": did("phone/apple/ipm"), "parent": did("phone/apple"), "slug": "ipm",
     "title": "iPhone 12 Pro Max", "kind": "model", "sort": 1},
]

# Bindings: all at Phone level
BINDINGS = [
    (did("phone"), fid("case/back_broken"),       "info",  "skip"),
    (did("phone"), fid("case/midframe_bent"),     "info",  "ask"),
    (did("phone"), fid("case/midframe_cracked"),  "block", "ask"),
    (did("phone"), fid("display/glass_broken"),   "info",  "skip"),
    (did("phone"), fid("display/stains_stripes"), "info",  "ask"),
    (did("phone"), fid("display/replaced"),       "info",  "ask"),
]


async def main() -> None:
    Session = get_sessionmaker()
    async with Session() as session:
        for f in FEATURES:
            await session.execute(text("""
                INSERT INTO feature_nodes
                    (id, parent_id, kind, slug, title, sort_order, prompt_hint)
                VALUES (:id, :pid, :kind, :slug, :title, :sort, :hint)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": str(f["id"]),
                "pid": str(f["parent"]) if f["parent"] else None,
                "kind": f["kind"], "slug": f["slug"], "title": f["title"],
                "sort": f["sort"], "hint": f.get("hint"),
            })
        for d in DEVICES:
            await session.execute(text("""
                INSERT INTO device_nodes
                    (id, parent_id, slug, title, kind, sort_order)
                VALUES (:id, :pid, :slug, :title, :kind, :sort)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": str(d["id"]),
                "pid": str(d["parent"]) if d["parent"] else None,
                "slug": d["slug"], "title": d["title"],
                "kind": d["kind"], "sort": d["sort"],
            })
        for dn, fn, da, ua in BINDINGS:
            bid = uuid.uuid5(NS, f"binding:{dn}:{fn}")
            await session.execute(text("""
                INSERT INTO device_feature_bindings
                    (id, device_node_id, feature_node_id, defect_action, unknown_action)
                VALUES (:id, :dn, :fn, :da, :ua)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": str(bid), "dn": str(dn), "fn": str(fn),
                "da": da, "ua": ua,
            })
        await session.commit()
    log.info(
        "seeded: %d features, %d devices, %d bindings",
        len(FEATURES), len(DEVICES), len(BINDINGS),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        asyncio.run(dispose_engine())
