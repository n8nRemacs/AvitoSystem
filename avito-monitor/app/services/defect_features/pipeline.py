"""Orchestrates the full defect-feature pipeline for one (listing, profile) pair.

  load_active_keys(profile)
    ↓
  parse_defect_features(active_keys)          ← kind='defect'
    ↓
  extract_price_signal_features(title, desc)  ← kind='price_signal'  [Phase 2.1]
    ↓
  read_info_api_features(parameters)          ← kind='info_api'      [Phase 2.1]
    ↓
  upsert_listing_features (all three kinds)
    ↓
  compute_bucket(defect_features_only, rules) ← spec §6.3: only defect affects bucket
    ↓
  return (bucket, reason)
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.defect_features import repository
from app.services.defect_features.bucket import Bucket, compute_bucket
from app.services.defect_features.info_api_reader import read_info_api_features
from app.services.defect_features.llm_parser import parse_defect_features
from app.services.defect_features.price_signal_extractor import extract_price_signal_features


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

    Phase 2.1: also extracts price_signal + info_api features and upserts
    all three kinds in one pass. compute_bucket receives ONLY defect features
    (per spec §6.3 — price_signal / info_api do not affect bucket).

    No side-effect on user_action — caller decides whether to auto-reject.
    """
    rules = await repository.load_profile_rules(session, profile_id)
    active_keys = {k for k, r in rules.items() if r != "ignore"}
    if not active_keys:
        return ("green", None)

    # --- defect features (LLM parser) ---
    parsed = await parse_defect_features(
        title=title, description=description,
        parameters=parameters or {}, active_keys=active_keys,
    )

    # --- price_signal features (batched LLM call) ---
    price_signal = await extract_price_signal_features(
        title=title, description=description,
    )

    # --- info_api features (pure Python, sync) ---
    info_api = read_info_api_features(parameters)

    # --- build unified feature_rows list ---
    feature_rows: list[dict] = []
    for key, feat in parsed.items():
        feature_rows.append({
            "feature_key": key,
            "kind": "defect",
            "state": feat["state"],
            "confidence": feat.get("confidence"),
            "source": feat["source"],
            "evidence": feat.get("evidence"),
        })
    for key, value in price_signal.items():
        feature_rows.append({
            "feature_key": key,
            "kind": "price_signal",
            "value": value,
        })
    for key, value in info_api.items():
        feature_rows.append({
            "feature_key": key,
            "kind": "info_api",
            "value": value,
        })

    await repository.upsert_listing_features(session, listing_id, feature_rows)

    # compute_bucket only considers kind='defect' (spec §6.3)
    feature_states = {k: v["state"] for k, v in parsed.items()}
    return compute_bucket(feature_states, rules)
