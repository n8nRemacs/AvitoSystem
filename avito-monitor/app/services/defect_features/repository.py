"""DB helpers for listing_features + profile_feature_rules.

Dialect-aware UPSERT — uses postgresql.insert().on_conflict_do_update on Postgres
and falls back to a 'select-then-insert-or-update' pattern on SQLite (for tests).

Phase 2.1: upsert_listing_features now accepts list[dict] with per-feature
kind/value fields in addition to the legacy defect-only {state, source, ...}.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ListingFeature, ProfileFeatureRule


def _is_postgres(session: AsyncSession) -> bool:
    try:
        bind = session.get_bind() if hasattr(session, "get_bind") else session.bind
    except Exception:
        return False
    name = getattr(getattr(bind, "dialect", None), "name", "")
    return name == "postgresql"


async def upsert_listing_features(
    session: AsyncSession,
    listing_id: uuid.UUID,
    features: list[dict[str, Any]],
) -> None:
    """INSERT … ON CONFLICT UPDATE for each feature key (Postgres),
    or SELECT-then-INSERT/UPDATE on other dialects.

    Phase 2.1: `features` is a list of dicts, each with:
        feature_key: str  — required
        kind: str         — 'defect' | 'price_signal' | 'info_api' (default 'defect')
        state: str|None   — required for kind='defect', None for others
        value: dict|None  — structured payload for price_signal/info_api kinds
        confidence: float|None
        source: str|None
        evidence: str|None
    """
    if not features:
        return

    if _is_postgres(session):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(ListingFeature).values([
            {
                "listing_id": listing_id,
                "feature_key": f["feature_key"],
                "kind": f.get("kind", "defect"),
                "state": f.get("state"),
                "value": f.get("value"),
                "confidence": f.get("confidence"),
                "source": f.get("source"),
                "evidence": f.get("evidence"),
                "parsed_at": func.now(),
            }
            for f in features
        ])
        stmt = stmt.on_conflict_do_update(
            index_elements=["listing_id", "feature_key"],
            set_={
                "kind": stmt.excluded.kind,
                "state": stmt.excluded.state,
                "value": stmt.excluded.value,
                "confidence": stmt.excluded.confidence,
                "source": stmt.excluded.source,
                "evidence": stmt.excluded.evidence,
                "parsed_at": stmt.excluded.parsed_at,
            },
        )
        await session.execute(stmt)
    else:
        # Generic fallback (SQLite-friendly for tests).
        for f in features:
            fkey = f["feature_key"]
            existing = (await session.execute(
                select(ListingFeature)
                .where(ListingFeature.listing_id == listing_id,
                       ListingFeature.feature_key == fkey)
            )).scalar_one_or_none()
            if existing is None:
                session.add(ListingFeature(
                    listing_id=listing_id,
                    feature_key=fkey,
                    kind=f.get("kind", "defect"),
                    state=f.get("state"),
                    value=f.get("value"),
                    confidence=f.get("confidence"),
                    source=f.get("source"),
                    evidence=f.get("evidence"),
                ))
            else:
                existing.kind = f.get("kind", "defect")
                existing.state = f.get("state")
                existing.value = f.get("value")
                existing.confidence = f.get("confidence")
                existing.source = f.get("source")
                existing.evidence = f.get("evidence")
    await session.flush()


async def load_listing_features(
    session: AsyncSession, listing_id: uuid.UUID,
) -> dict[str, dict[str, Any]]:
    rows = (await session.execute(
        select(ListingFeature).where(ListingFeature.listing_id == listing_id)
    )).scalars().all()
    return {
        r.feature_key: {
            "kind": r.kind,
            "state": r.state,
            "value": r.value,
            "source": r.source,
            "evidence": r.evidence,
            "confidence": r.confidence,
        }
        for r in rows
    }


async def upsert_profile_rule(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    feature_key: str,
    rule: str,
) -> None:
    if _is_postgres(session):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(ProfileFeatureRule).values(
            profile_id=profile_id, feature_key=feature_key, rule=rule,
        ).on_conflict_do_update(
            index_elements=["profile_id", "feature_key"],
            set_={"rule": rule},
        )
        await session.execute(stmt)
    else:
        existing = (await session.execute(
            select(ProfileFeatureRule)
            .where(ProfileFeatureRule.profile_id == profile_id,
                   ProfileFeatureRule.feature_key == feature_key)
        )).scalar_one_or_none()
        if existing is None:
            session.add(ProfileFeatureRule(
                profile_id=profile_id, feature_key=feature_key, rule=rule,
            ))
        else:
            existing.rule = rule
    await session.flush()


async def load_profile_rules(
    session: AsyncSession, profile_id: uuid.UUID,
) -> dict[str, str]:
    rows = (await session.execute(
        select(ProfileFeatureRule.feature_key, ProfileFeatureRule.rule)
        .where(ProfileFeatureRule.profile_id == profile_id)
    )).all()
    return {r.feature_key: r.rule for r in rows}


async def load_active_feature_keys(
    session: AsyncSession, profile_id: uuid.UUID,
) -> set[str]:
    """All feature keys where rule != 'ignore'."""
    rules = await load_profile_rules(session, profile_id)
    return {k for k, r in rules.items() if r != "ignore"}
