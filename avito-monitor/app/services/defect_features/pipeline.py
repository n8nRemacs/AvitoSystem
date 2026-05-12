"""Orchestrates the full defect-feature pipeline for one (listing, profile) pair.

  load_active_keys(profile)
    ↓
  parse_defect_features(active_keys)
    ↓
  upsert_listing_features
    ↓
  compute_bucket(features, rules)
    ↓
  return (bucket, reason)
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.defect_features import repository
from app.services.defect_features.bucket import Bucket, compute_bucket
from app.services.defect_features.llm_parser import parse_defect_features


async def analyze_listing_features(
    *,
    session: AsyncSession,
    listing_id: uuid.UUID,
    profile_id: uuid.UUID,
    title: str,
    description: str,
    parameters: dict[str, Any] | None,
) -> tuple[Bucket, str | None]:
    """Run the parser and bucketing for one (listing, profile) pair.

    No side-effect on user_action — caller decides whether to auto-reject.
    """
    rules = await repository.load_profile_rules(session, profile_id)
    active_keys = {k for k, r in rules.items() if r != "ignore"}
    if not active_keys:
        return ("green", None)

    parsed = await parse_defect_features(
        title=title, description=description,
        parameters=parameters or {}, active_keys=active_keys,
    )

    await repository.upsert_listing_features(
        session, listing_id=listing_id, features=parsed,
    )

    feature_states = {k: v["state"] for k, v in parsed.items()}
    return compute_bucket(feature_states, rules)
