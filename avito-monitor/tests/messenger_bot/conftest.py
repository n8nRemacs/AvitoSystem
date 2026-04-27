"""Shared fixtures for messenger-bot unit tests.

The bot module touches the DB through SQLAlchemy async sessionmakers in three
modules: ``handler`` (activity_log inserts), ``dedup`` (chat_dialog_state +
messenger_messages reads/writes), and ``rate_limit`` (messenger_messages reads).

Rather than spinning a Postgres for unit tests, we provide a light fake-session
factory + per-module monkeypatches. The integration smoke is exercised in the
docker-compose verify steps and via scenario G.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeScalarResult:
    """Stand-in for ``Result`` returned by ``session.execute``."""

    def __init__(self, scalar: Any = None, rows: Iterable[Any] | None = None) -> None:
        self._scalar = scalar
        self._rows = list(rows or [])

    def scalar(self) -> Any:
        return self._scalar

    def scalars(self) -> _FakeScalarResult:
        return self

    def all(self) -> list[Any]:
        return self._rows


class FakeSession:
    """Async session double — supports add/commit/execute calls used in tests."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commits: int = 0
        self.executions: list[Any] = []
        self._next_results: list[_FakeScalarResult] = []

    def queue_scalar(self, value: Any) -> None:
        self._next_results.append(_FakeScalarResult(scalar=value))

    def queue_rows(self, rows: Iterable[Any]) -> None:
        self._next_results.append(_FakeScalarResult(rows=rows))

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def execute(self, stmt: Any) -> _FakeScalarResult:
        self.executions.append(stmt)
        if self._next_results:
            return self._next_results.pop(0)
        return _FakeScalarResult(scalar=0, rows=[])

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def make_fake_sessionmaker(session: FakeSession):
    """Return a callable that, when called, returns ``session`` as an async CM."""

    def factory():
        return session

    return factory


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def patch_sessionmaker(monkeypatch, fake_session):
    """Patch get_sessionmaker in every messenger_bot module that imports it."""
    factory = make_fake_sessionmaker(fake_session)

    from app.services.messenger_bot import dedup as dedup_mod
    from app.services.messenger_bot import handler as handler_mod
    from app.services.messenger_bot import rate_limit as rate_limit_mod

    monkeypatch.setattr(dedup_mod, "get_sessionmaker", lambda: factory)
    monkeypatch.setattr(handler_mod, "get_sessionmaker", lambda: factory)
    monkeypatch.setattr(rate_limit_mod, "get_sessionmaker", lambda: factory)

    return fake_session


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Clean module-level singletons between tests."""
    from app.services.messenger_bot import handler, kill_switch, runner, whitelist

    handler.reset_counters_for_tests()
    kill_switch.reset_for_tests()
    whitelist.reset_cache_for_tests()
    runner.SSE_STATE = "initial"  # type: ignore[assignment]
    runner.RECONNECT_ATTEMPTS = 0  # type: ignore[assignment]
    yield
    handler.reset_counters_for_tests()
    kill_switch.reset_for_tests()
    whitelist.reset_cache_for_tests()


def make_async_mock(*, return_value: Any = None) -> AsyncMock:
    return AsyncMock(return_value=return_value)


def make_mock(**kwargs) -> MagicMock:
    return MagicMock(**kwargs)
