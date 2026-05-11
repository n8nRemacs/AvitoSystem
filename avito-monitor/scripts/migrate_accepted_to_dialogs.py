"""One-off post-deploy migration: seed seller_dialogs for already-accepted lots.

Run AFTER alembic migration 0013 applies + the deploy of code that
auto-creates dialogs on accept. Without this script, all already-accepted
lots would be invisible in the new kanban (no SellerDialog row).

Strategy:
  - Find every (profile_id, listing_id) in profile_listings with
    user_action='accepted' AND no existing SellerDialog row.
  - Insert a SellerDialog at stage='contact' with operator_mode=true.
  - **Do NOT auto-send greeting** — operator already may have chatted
    manually. operator_mode=true means LLM and auto-greeting stay silent.

The cards appear in the kanban Контакт column with a "ручной режим"
badge so operator can decide what to do with each.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import asyncpg


SQL_FIND_GAPS = """
SELECT pl.profile_id, pl.listing_id
FROM profile_listings pl
LEFT JOIN seller_dialogs sd
  ON sd.profile_id = pl.profile_id AND sd.listing_id = pl.listing_id
WHERE pl.user_action = 'accepted'
  AND sd.id IS NULL
"""

SQL_INSERT = """
INSERT INTO seller_dialogs
    (id, profile_id, listing_id, stage, operator_mode, opened_at)
VALUES
    ($1, $2, $3, 'contact', true, now())
"""


async def main() -> None:
    url = os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        rows = await conn.fetch(SQL_FIND_GAPS)
        print(f"accepted lots without dialog: {len(rows)}")
        for r in rows:
            await conn.execute(
                SQL_INSERT,
                uuid.uuid4(),
                r["profile_id"],
                r["listing_id"],
            )
        print(f"inserted: {len(rows)} dialogs at stage=contact operator_mode=true")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
