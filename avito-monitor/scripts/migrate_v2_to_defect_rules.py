"""Pre-migration helper: V2 profile_criteria → defect-style profile_feature_rules.

Run BEFORE applying alembic 0016 (which drops profile_criteria table).

Usage:
  python -m scripts.migrate_v2_to_defect_rules --profile <uuid>            # dry-run for one profile
  python -m scripts.migrate_v2_to_defect_rules --all                       # dry-run for all profiles
  python -m scripts.migrate_v2_to_defect_rules --all --apply               # apply upserts to DB

Strategy:
- Read profile_criteria rows (enabled=true).
- Map V2 key → defect key(s) per the table below.
- For each profile, print current defect rules + proposed additions/changes.
- --apply does INSERT ... ON CONFLICT DO NOTHING on profile_feature_rules
  (existing operator-set rules are preserved, only fills gaps).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

import asyncpg

V2_TO_DEFECT_MAP: dict[str, list[str]] = {
    "icloud_locked": ["locks.icloud_linked"],
    "screen_broken": ["display.glass_broken"],
    "not_starting": ["operability.no_boot"],
    "modem_broken": ["sensors.sim"],
    "biometric_broken": ["sensors.face_id", "sensors.touch_id"],
    "parts_only": ["operability.parts_only"],
    "frp_locked": ["locks.frp_locked"],
    "account_blocked": ["locks.vendor_account"],
    # Dropped (no defect equivalent): memory_gte, title_matches_model,
    # battery_health, repaired_components, cameras_work
}


async def fetch_v2_rules(
    conn: asyncpg.Connection, profile_id: str | None
) -> list[dict[str, Any]]:
    base_sql = """
        SELECT pc.profile_id::text AS profile_id,
               COALESCE(t.key, pc.custom_key) AS criterion_key,
               pc.is_hard
        FROM profile_criteria pc
        LEFT JOIN criteria_templates t ON t.id = pc.template_id
        WHERE pc.is_hard = true
    """
    if profile_id:
        sql = base_sql + " AND pc.profile_id = $1::uuid ORDER BY pc.profile_id, criterion_key"
        return await conn.fetch(sql, profile_id)
    sql = base_sql + " ORDER BY pc.profile_id, criterion_key"
    return await conn.fetch(sql)


async def fetch_defect_rules(
    conn: asyncpg.Connection, profile_id: str
) -> dict[str, str]:
    rows = await conn.fetch(
        "SELECT feature_key, rule FROM profile_feature_rules "
        "WHERE profile_id = $1::uuid",
        profile_id,
    )
    return {r["feature_key"]: r["rule"] for r in rows}


async def main(args: argparse.Namespace) -> int:
    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        exists = await conn.fetchval(
            "SELECT to_regclass('public.profile_criteria') IS NOT NULL"
        )
        if not exists:
            print(
                "profile_criteria table not found — migration 0016 has already been "
                "applied. Nothing to migrate."
            )
            return 0

        v2_rows = await fetch_v2_rules(
            conn, args.profile if not args.all else None
        )
        by_profile: dict[str, list[str]] = {}
        for r in v2_rows:
            by_profile.setdefault(r["profile_id"], []).append(r["criterion_key"])

        if not by_profile:
            print("No V2 profile_criteria rows found. Nothing to migrate.")
            return 0

        total_proposed = 0
        for profile_id, v2_keys in by_profile.items():
            current = await fetch_defect_rules(conn, profile_id)
            print(f"\n=== Profile {profile_id} ===")
            print(f"V2 enabled criteria: {sorted(v2_keys)}")
            print(f"Current defect rules count: {len(current)}")

            proposed_inserts: list[tuple[str, str]] = []
            for v2k in v2_keys:
                defect_keys = V2_TO_DEFECT_MAP.get(v2k, [])
                if not defect_keys:
                    print(f"  [DROP]   {v2k!r:30s} — no defect equivalent")
                    continue
                for dk in defect_keys:
                    if dk in current:
                        print(
                            f"  [KEEP]   {v2k!r:30s} → {dk!r:30s} "
                            f"(already has rule={current[dk]!r})"
                        )
                    else:
                        proposed_inserts.append((dk, "red"))
                        print(
                            f"  [INSERT] {v2k!r:30s} → {dk!r:30s} = 'red'"
                        )

            total_proposed += len(proposed_inserts)
            if args.apply and proposed_inserts:
                async with conn.transaction():
                    for dk, rule in proposed_inserts:
                        await conn.execute(
                            "INSERT INTO profile_feature_rules "
                            "(profile_id, feature_key, rule) "
                            "VALUES ($1::uuid, $2, $3) "
                            "ON CONFLICT (profile_id, feature_key) DO NOTHING",
                            profile_id, dk, rule,
                        )
                print(f"  APPLIED {len(proposed_inserts)} inserts.")

        print(f"\nTotal proposed inserts: {total_proposed}")
        if not args.apply:
            print("DRY RUN. Re-run with --apply to commit.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--profile", type=str, help="Profile UUID")
    g.add_argument("--all", action="store_true", help="Process all profiles")
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually apply (default: dry-run)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args)))
