"""Unit tests for V2 reliability — Stage 8 Telegram alerts.

All upstream calls (Telegram API + Postgres) are mocked. No live network.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from app.services.health_checker import alerts as alerts_mod
from app.services.health_checker.alerts import (
    FIRED_SENTINELS,
    build_daily_summary_text,
    check_and_alert_after_persist,
    send_alert,
)
from app.services.health_checker.scenarios.base import ScenarioResult

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _settings(
    *,
    token: str = "test-token",  # noqa: S107 — test fixture, not a real secret
    chat_ids: str = "12345",
    enabled: bool = True,
    threshold: int = 3,
    summary_hour: int = 9,
) -> SimpleNamespace:
    """A tiny duck-typed Settings stub — avoids loading the real .env."""
    return SimpleNamespace(
        telegram_bot_token=token,
        telegram_allowed_user_ids=chat_ids,
        reliability_tg_alert_enabled=enabled,
        reliability_tg_alert_fail_threshold=threshold,
        reliability_tg_alert_daily_summary_hour=summary_hour,
        timezone="Europe/Moscow",
    )


class _FakeHealthCheck:
    """Minimal HealthCheck duck — lets us bypass DB in unit tests."""

    def __init__(
        self,
        scenario: str,
        status: str,
        latency_ms: int | None,
        ts: datetime,
        details: dict | None = None,
    ) -> None:
        self.scenario = scenario
        self.status = status
        self.latency_ms = latency_ms
        self.ts = ts
        self.details = details


# ---------------------------------------------------------------------------
# send_alert — happy path + no-ops + transport errors
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_send_alert_happy_path() -> None:
    route = respx.post(
        "https://api.telegram.org/bottest-token/sendMessage"
    ).mock(return_value=httpx.Response(200, json={"ok": True}))

    sent = await send_alert("hello", settings=_settings())
    assert sent is True
    assert route.called
    body = route.calls.last.request.read().decode()
    assert "12345" in body
    assert "hello" in body


@pytest.mark.asyncio
async def test_send_alert_noop_when_token_empty() -> None:
    sent = await send_alert("x", settings=_settings(token=""))
    assert sent is False


@pytest.mark.asyncio
async def test_send_alert_noop_when_chat_id_empty() -> None:
    sent = await send_alert("x", settings=_settings(chat_ids=""))
    assert sent is False


@pytest.mark.asyncio
async def test_send_alert_noop_when_chat_id_only_whitespace_commas() -> None:
    sent = await send_alert("x", settings=_settings(chat_ids=" , , "))
    assert sent is False


@respx.mock
@pytest.mark.asyncio
async def test_send_alert_returns_false_on_http_error() -> None:
    respx.post(
        "https://api.telegram.org/bottest-token/sendMessage"
    ).mock(return_value=httpx.Response(500, json={"ok": False}))

    sent = await send_alert("hello", settings=_settings())
    assert sent is False  # logged warning, not raised


@respx.mock
@pytest.mark.asyncio
async def test_send_alert_returns_false_on_connect_error() -> None:
    respx.post(
        "https://api.telegram.org/bottest-token/sendMessage"
    ).mock(side_effect=httpx.ConnectError("boom"))

    sent = await send_alert("hello", settings=_settings())
    assert sent is False


@respx.mock
@pytest.mark.asyncio
async def test_send_alert_picks_first_chat_id_from_csv() -> None:
    route = respx.post(
        "https://api.telegram.org/bottest-token/sendMessage"
    ).mock(return_value=httpx.Response(200, json={"ok": True}))

    sent = await send_alert("hi", settings=_settings(chat_ids="111, 222 , 333"))
    assert sent is True
    body = route.calls.last.request.read().decode()
    assert "111" in body
    assert "222" not in body  # only the first one is used as chat target


# ---------------------------------------------------------------------------
# check_and_alert_after_persist
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_sentinels():
    FIRED_SENTINELS.clear()
    yield
    FIRED_SENTINELS.clear()


@pytest.mark.asyncio
async def test_alert_does_not_fire_with_one_fail(monkeypatch) -> None:
    """One fail with no DB history — must NOT fire."""
    s = _settings(threshold=3)
    now = datetime.now(UTC)
    fake_rows = [
        _FakeHealthCheck("A", "fail", 0, now, {"reason": "boom"}),
    ]

    async def fake_fetch(scenario, limit):
        return fake_rows

    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(alerts_mod, "_fetch_recent", fake_fetch)
    monkeypatch.setattr(alerts_mod, "send_alert", sender)

    await check_and_alert_after_persist(
        ScenarioResult(scenario="A", status="fail", latency_ms=0, details={"reason": "boom"}),
        settings=s,
    )

    sender.assert_not_called()
    assert "A" not in FIRED_SENTINELS


@pytest.mark.asyncio
async def test_alert_fires_on_threshold_reached(monkeypatch) -> None:
    """3 fails in a row should fire."""
    s = _settings(threshold=3)
    now = datetime.now(UTC)
    fake_rows = [
        _FakeHealthCheck("A", "fail", 0, now - timedelta(seconds=i), {"reason": "boom"})
        for i in range(3)
    ]

    async def fake_fetch(scenario, limit):
        assert scenario == "A"
        assert limit == 3
        return fake_rows

    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(alerts_mod, "_fetch_recent", fake_fetch)
    monkeypatch.setattr(alerts_mod, "send_alert", sender)

    await check_and_alert_after_persist(
        ScenarioResult(scenario="A", status="fail", latency_ms=0, details={"reason": "boom"}),
        settings=s,
    )

    sender.assert_awaited_once()
    text = sender.await_args.args[0]
    assert "scenario `A`" in text
    assert "3 consecutive" in text
    assert "boom" in text
    assert "A" in FIRED_SENTINELS


@pytest.mark.asyncio
async def test_sentinel_suppresses_repeat_fires(monkeypatch) -> None:
    """4th fail in a row is suppressed by sentinel."""
    s = _settings(threshold=3)
    now = datetime.now(UTC)
    FIRED_SENTINELS["A"] = now  # pre-armed

    async def fake_fetch(scenario, limit):  # pragma: no cover — must not be called
        raise AssertionError("should short-circuit on sentinel")

    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(alerts_mod, "_fetch_recent", fake_fetch)
    monkeypatch.setattr(alerts_mod, "send_alert", sender)

    await check_and_alert_after_persist(
        ScenarioResult(scenario="A", status="fail", latency_ms=0, details={}),
        settings=s,
    )

    sender.assert_not_called()
    assert "A" in FIRED_SENTINELS


@pytest.mark.asyncio
async def test_recovery_alert_fires_on_pass_after_fire(monkeypatch) -> None:
    """First pass after fire → ✅ recovery + sentinel cleared."""
    s = _settings(threshold=3)
    FIRED_SENTINELS["A"] = datetime.now(UTC)
    now = datetime.now(UTC)
    fake_rows = [_FakeHealthCheck("A", "pass", 42, now, {})]

    async def fake_fetch(scenario, limit):
        return fake_rows

    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(alerts_mod, "_fetch_recent", fake_fetch)
    monkeypatch.setattr(alerts_mod, "send_alert", sender)

    await check_and_alert_after_persist(
        ScenarioResult(scenario="A", status="pass", latency_ms=42, details={}),
        settings=s,
    )

    sender.assert_awaited_once()
    text = sender.await_args.args[0]
    assert "recovered" in text.lower()
    assert "A" not in FIRED_SENTINELS  # cleared


@pytest.mark.asyncio
async def test_no_recovery_alert_when_no_sentinel(monkeypatch) -> None:
    """A normal pass without a prior fire must NOT spam the bot."""
    s = _settings(threshold=3)

    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(alerts_mod, "send_alert", sender)

    await check_and_alert_after_persist(
        ScenarioResult(scenario="A", status="pass", latency_ms=42, details={}),
        settings=s,
    )

    sender.assert_not_called()


@pytest.mark.asyncio
async def test_skip_status_does_not_fire(monkeypatch) -> None:
    """``skip`` status must neither fire nor recover."""
    s = _settings(threshold=3)

    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(alerts_mod, "send_alert", sender)

    await check_and_alert_after_persist(
        ScenarioResult(scenario="F", status="skip", latency_ms=0, details={}),
        settings=s,
    )

    sender.assert_not_called()


@pytest.mark.asyncio
async def test_alert_skipped_when_globally_disabled(monkeypatch) -> None:
    s = _settings(enabled=False, threshold=3)

    async def fake_fetch(scenario, limit):  # pragma: no cover
        raise AssertionError("should short-circuit on enabled=False")

    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(alerts_mod, "_fetch_recent", fake_fetch)
    monkeypatch.setattr(alerts_mod, "send_alert", sender)

    await check_and_alert_after_persist(
        ScenarioResult(scenario="A", status="fail", latency_ms=0, details={}),
        settings=s,
    )

    sender.assert_not_called()


@pytest.mark.asyncio
async def test_alert_no_fire_when_only_two_fails_in_db(monkeypatch) -> None:
    """The just-persisted 3rd fail is the trigger, but DB only returns 2 rows."""
    s = _settings(threshold=3)
    now = datetime.now(UTC)
    fake_rows = [
        _FakeHealthCheck("A", "fail", 0, now, {}),
        _FakeHealthCheck("A", "fail", 0, now - timedelta(seconds=10), {}),
    ]

    async def fake_fetch(scenario, limit):
        return fake_rows

    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(alerts_mod, "_fetch_recent", fake_fetch)
    monkeypatch.setattr(alerts_mod, "send_alert", sender)

    await check_and_alert_after_persist(
        ScenarioResult(scenario="A", status="fail", latency_ms=0, details={}),
        settings=s,
    )

    sender.assert_not_called()


@pytest.mark.asyncio
async def test_alert_no_fire_when_third_row_is_pass(monkeypatch) -> None:
    """Most recent N includes a non-fail → no fire."""
    s = _settings(threshold=3)
    now = datetime.now(UTC)
    fake_rows = [
        _FakeHealthCheck("A", "fail", 0, now, {}),
        _FakeHealthCheck("A", "fail", 0, now - timedelta(seconds=10), {}),
        _FakeHealthCheck("A", "pass", 0, now - timedelta(seconds=20), {}),
    ]

    async def fake_fetch(scenario, limit):
        return fake_rows

    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(alerts_mod, "_fetch_recent", fake_fetch)
    monkeypatch.setattr(alerts_mod, "send_alert", sender)

    await check_and_alert_after_persist(
        ScenarioResult(scenario="A", status="fail", latency_ms=0, details={}),
        settings=s,
    )

    sender.assert_not_called()


@pytest.mark.asyncio
async def test_sentinel_set_even_when_send_fails(monkeypatch) -> None:
    """If telegram is down we still mark the sentinel — avoids hammering."""
    s = _settings(threshold=3)
    now = datetime.now(UTC)
    fake_rows = [
        _FakeHealthCheck("B", "fail", 0, now - timedelta(seconds=i), {})
        for i in range(3)
    ]

    async def fake_fetch(scenario, limit):
        return fake_rows

    sender = AsyncMock(return_value=False)  # simulate transport failure
    monkeypatch.setattr(alerts_mod, "_fetch_recent", fake_fetch)
    monkeypatch.setattr(alerts_mod, "send_alert", sender)

    await check_and_alert_after_persist(
        ScenarioResult(scenario="B", status="fail", latency_ms=0, details={}),
        settings=s,
    )

    sender.assert_awaited_once()
    assert "B" in FIRED_SENTINELS


# ---------------------------------------------------------------------------
# build_daily_summary_text — pure formatter
# ---------------------------------------------------------------------------


def test_build_daily_summary_basic_shape() -> None:
    now = datetime(2026, 4, 26, 9, 0, tzinfo=UTC)
    rows = [
        _FakeHealthCheck("A", "pass", 100, now - timedelta(minutes=5)),
        _FakeHealthCheck("A", "pass", 110, now - timedelta(minutes=10)),
        _FakeHealthCheck("A", "fail", 120, now - timedelta(minutes=15), {"reason": "boom"}),
        _FakeHealthCheck("C", "pass", 200, now - timedelta(minutes=5)),
        _FakeHealthCheck("C", "pass", 210, now - timedelta(minutes=10)),
    ]
    text = build_daily_summary_text(rows, window_hours=24, now=now)
    assert "Reliability daily summary" in text
    assert "last 24 h" in text
    assert "A " in text  # padded scenario column
    assert "C " in text
    # A: 2/3 pass = 66.7%
    assert "66.7%" in text
    # C: 2/2 pass = 100.0%
    assert "100.0%" in text
    # No unreachable events recorded
    assert "No service-unreachable events" in text


def test_build_daily_summary_lists_unreachable() -> None:
    now = datetime(2026, 4, 26, 9, 0, tzinfo=UTC)
    rows = [
        _FakeHealthCheck(
            "C",
            "fail",
            None,
            now - timedelta(minutes=2),
            {"error": "ConnectError: connection refused"},
        ),
        _FakeHealthCheck(
            "D",
            "fail",
            None,
            now - timedelta(minutes=5),
            {"error": "service unreachable"},
        ),
        _FakeHealthCheck("A", "pass", 50, now - timedelta(minutes=5)),
    ]
    text = build_daily_summary_text(rows, window_hours=24, now=now)
    assert "Service-unreachable events" in text
    assert "`C`" in text
    assert "`D`" in text
    assert "ConnectError" in text or "unreachable" in text


def test_build_daily_summary_drops_old_rows() -> None:
    """Rows older than ``window_hours`` are excluded."""
    now = datetime(2026, 4, 26, 9, 0, tzinfo=UTC)
    rows = [
        _FakeHealthCheck("A", "pass", 100, now - timedelta(hours=2)),
        # 3 days old: must be filtered out
        _FakeHealthCheck("A", "fail", 999, now - timedelta(hours=72)),
    ]
    text = build_daily_summary_text(rows, window_hours=24, now=now)
    # Only the in-window pass should be counted → 100% pass, 0 fails
    assert "100.0%" in text
    assert " 1 " in text  # 1 run for A (loose check)


def test_build_daily_summary_empty() -> None:
    now = datetime(2026, 4, 26, 9, 0, tzinfo=UTC)
    text = build_daily_summary_text([], window_hours=24, now=now)
    assert "(no rows)" in text


# ---------------------------------------------------------------------------
# api integration — /alerts/test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerts_test_endpoint_short_circuits_on_empty_chat_id(
    monkeypatch,
) -> None:
    from fastapi.testclient import TestClient

    from app.services.health_checker.api import app as fastapi_app

    monkeypatch.setattr(
        alerts_mod,
        "get_settings",
        lambda: _settings(token="t", chat_ids=""),  # noqa: S106 — test stub
    )
    # api.py imports get_settings into its own namespace — patch there too
    from app.services.health_checker import api as api_mod

    monkeypatch.setattr(
        api_mod,
        "get_settings",
        lambda: _settings(token="t", chat_ids=""),  # noqa: S106 — test stub
    )

    with TestClient(fastapi_app) as client:
        resp = client.post("/alerts/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sent"] is False
        assert "TELEGRAM_ALLOWED_USER_IDS" in body["reason"]


@pytest.mark.asyncio
async def test_alerts_test_endpoint_short_circuits_on_empty_token(
    monkeypatch,
) -> None:
    from fastapi.testclient import TestClient

    from app.services.health_checker import api as api_mod
    from app.services.health_checker.api import app as fastapi_app

    monkeypatch.setattr(
        api_mod, "get_settings", lambda: _settings(token="", chat_ids="42")
    )

    with TestClient(fastapi_app) as client:
        resp = client.post("/alerts/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sent"] is False
        assert "TELEGRAM_BOT_TOKEN" in body["reason"]


@pytest.mark.asyncio
async def test_alerts_test_endpoint_sends_when_configured(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.services.health_checker import api as api_mod
    from app.services.health_checker.api import app as fastapi_app

    monkeypatch.setattr(
        api_mod,
        "get_settings",
        lambda: _settings(token="abc", chat_ids="42"),  # noqa: S106 — test stub
    )

    sent_payloads: list[str] = []

    async def fake_send(text, *, settings=None, client=None):
        sent_payloads.append(text)
        return True

    monkeypatch.setattr(api_mod, "send_alert", fake_send)

    with TestClient(fastapi_app) as client:
        resp = client.post("/alerts/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sent"] is True
        assert body["reason"] is None
        assert sent_payloads
        assert "pong" in sent_payloads[0]


# ---------------------------------------------------------------------------
# runner wiring smoke — make sure runner calls our hook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_invokes_alert_hook(monkeypatch) -> None:
    """``run_and_persist`` must call ``check_and_alert_after_persist`` post-persist."""
    from app.services.health_checker import runner as runner_mod

    fake_hook = AsyncMock()
    monkeypatch.setattr(runner_mod, "check_and_alert_after_persist", fake_hook)

    async def fake_persist(result):
        return None

    monkeypatch.setattr(runner_mod, "persist_result", fake_persist)

    async def fake_fn(client):
        return ScenarioResult(scenario="A", status="pass", latency_ms=1, details={})

    client_stub = object()
    result = await runner_mod.run_and_persist("A", fake_fn, client_stub)

    assert result.status == "pass"
    fake_hook.assert_awaited_once()
    persisted_arg = fake_hook.await_args.args[0]
    assert persisted_arg.scenario == "A"
    assert persisted_arg.status == "pass"


@pytest.mark.asyncio
async def test_runner_swallows_alert_errors(monkeypatch) -> None:
    """An exception inside the alert hook must NOT crash the runner."""
    from app.services.health_checker import runner as runner_mod

    async def boom(*a, **kw):
        raise RuntimeError("kaboom")

    async def fake_persist(result):
        return None

    monkeypatch.setattr(runner_mod, "check_and_alert_after_persist", boom)
    monkeypatch.setattr(runner_mod, "persist_result", fake_persist)

    async def fake_fn(client):
        return ScenarioResult(scenario="B", status="fail", latency_ms=1, details={})

    # Must not raise.
    result = await runner_mod.run_and_persist("B", fake_fn, object())
    assert result.status == "fail"


# ---------------------------------------------------------------------------
# _seconds_until_next sanity (used by daily_summary_loop)
# ---------------------------------------------------------------------------


def test_seconds_until_next_is_positive_and_within_24h() -> None:
    delta = alerts_mod._seconds_until_next(9, "Europe/Moscow")
    assert 1.0 <= delta <= 24 * 3600 + 60  # at most a day plus buffer
