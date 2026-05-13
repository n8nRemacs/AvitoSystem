"""Cache backends for :class:`LLMAnalyzer`.

Two implementations behind the same async interface:

* :class:`InMemoryLLMCache` — process-local dict; used for tests and
  local one-shot scripts where we don't want to spin up Postgres.
* :class:`DBLLMCache` — NOTE: the llm_analyses table was dropped in
  migration 0016_unified_criteria (Phase 2.1). DBLLMCache is now a
  no-op stub that always returns a cache miss on get and silently drops
  puts. This preserves the LLMAnalyzer.compare_to_reference call-path
  (Price Intelligence) without crashing — it just runs uncached until
  a replacement cache table is added in a future migration.

Both adhere to the ``_CacheProto`` Protocol declared in
``app/services/llm_analyzer.py``.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

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
    """No-op stub — llm_analyses table dropped in migration 0016.

    Always returns None from get() and silently drops put() calls.
    Price Intelligence compare_to_reference remains functional but
    runs uncached until a replacement cache table is provisioned
    (Phase 2.1 Task 5+).
    """

    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def get(self, cache_key: str) -> dict[str, Any] | None:
        return None

    async def put(self, **kwargs) -> None:
        pass
