"""Cache backends for :class:`LLMAnalyzer`.

Two implementations behind the same async interface:

* :class:`InMemoryLLMCache` — process-local dict; used for tests and
  local one-shot scripts where we don't want to spin up Postgres.
* :class:`DBLLMCache` — persists every entry into the ``llm_analyses``
  table (see ``app/db/models/llm_analysis.py``) and is what the worker
  uses in production. Designed to never raise out of the worker loop:
  any SQLAlchemy error is logged and the analyzer pretends it was a
  cache miss / a no-op write.

Both adhere to the ``_CacheProto`` Protocol declared in
``app/services/llm_analyzer.py``.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.llm_analysis import LLMAnalysis

log = logging.getLogger(__name__)


class InMemoryLLMCache:
    """Process-local dict-backed cache. Test-only by default."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    async def get(self, cache_key: str) -> dict[str, Any] | None:
        return self._store.get(cache_key)

    async def put(self, **kwargs) -> None:
        cache_key = kwargs["cache_key"]
        self._store[cache_key] = kwargs["result"]


class DBLLMCache:
    """Persist analyzer results into the ``llm_analyses`` table.

    A miss is signalled by returning ``None`` from :meth:`get`. A failed
    DB call is logged and treated as a miss, so an unhealthy DB never
    causes the worker to skip LLM calls — it just degrades to no caching.
    """

    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def get(self, cache_key: str) -> dict[str, Any] | None:
        try:
            async with self._sessionmaker() as session:
                stmt = (
                    select(LLMAnalysis.result)
                    .where(LLMAnalysis.cache_key == cache_key)
                    .limit(1)
                )
                row = (await session.execute(stmt)).scalar_one_or_none()
                if row is None:
                    return None
                if isinstance(row, dict):
                    return row
                # Some drivers may yield JSON-as-text; coerce defensively.
                return dict(row) if hasattr(row, "items") else None
        except Exception:  # pragma: no cover — DB outage path
            log.exception("llm_cache.get_failed cache_key=%s", cache_key)
            return None

    async def put(
        self,
        *,
        cache_key: str,
        type: str,
        listing_id: int | uuid.UUID | None,
        reference_id: int | uuid.UUID | None,
        model: str,
        prompt_version: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        result: dict[str, Any],
    ) -> None:
        # The ``listings`` table uses UUID primary keys. The analyzer hands us
        # the Avito numeric id (int) as ``listing_id`` because that's what's
        # in :class:`shared.models.avito.ListingDetail`. We can't store an
        # int into a UUID FK, so for now we drop the FK link and keep the
        # numeric id inside ``result["_avito_id"]`` for forensic queries.
        # When Block 4 wires the real ``listings`` row UUID through, this
        # branch goes away.
        listing_uuid: uuid.UUID | None = None
        if isinstance(listing_id, uuid.UUID):
            listing_uuid = listing_id

        ref_uuid: uuid.UUID | None = None
        if isinstance(reference_id, uuid.UUID):
            ref_uuid = reference_id

        # Stash the raw avito_id alongside so we can correlate cached rows
        # to listings before Block 4 lands.
        result_with_meta = dict(result)
        if isinstance(listing_id, int):
            result_with_meta["_avito_id"] = listing_id
        if isinstance(reference_id, int):
            result_with_meta["_avito_reference_id"] = reference_id

        try:
            async with self._sessionmaker() as session:
                row = LLMAnalysis(
                    listing_id=listing_uuid,
                    reference_id=ref_uuid,
                    type=type,
                    model=model,
                    prompt_version=prompt_version,
                    cache_key=cache_key,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    result=result_with_meta,
                )
                session.add(row)
                await session.commit()
        except Exception:  # pragma: no cover — DB outage path
            log.exception(
                "llm_cache.put_failed cache_key=%s type=%s", cache_key, type
            )
