"""Unit tests for the six health-checker scenarios.

All upstream xapi calls are mocked via ``respx`` so these tests run offline.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.services.health_checker.runner import persist_result, run_all_once, run_named_once
from app.services.health_checker.scenarios import REGISTRY
from app.services.health_checker.scenarios.a_token_freshness import scenario_a
from app.services.health_checker.scenarios.b_token_rotation import scenario_b
from app.services.health_checker.scenarios.base import ScenarioResult
from app.services.health_checker.scenarios.c_messenger_alive import scenario_c
from app.services.health_checker.scenarios.d_messenger_roundtrip import scenario_d
from app.services.health_checker.scenarios.e_sse_bridge import scenario_e
from app.services.health_checker.scenarios.f_messenger_typing import scenario_f
from app.services.health_checker.scenarios.g_bot_dedup import scenario_g
from app.services.health_checker.scenarios.i_notification_freshness import scenario_i
from app.services.health_checker.sse_client import SseClient, SseEvent
from app.services.health_checker.xapi_client import XapiClient

XAPI_BASE = "http://xapi.test"


def make_client() -> XapiClient:
    return XapiClient(base_url=XAPI_BASE, api_key="test-key")


def _now_iso(offset_hours: float = 0.0) -> str:
    return (datetime.now(UTC) + timedelta(hours=offset_hours)).isoformat()


# ----------------------------------------------------------------------
# A. token freshness
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_scenario_a_pass_with_live_shape() -> None:
    """xapi live response with ttl > 4h should PASS."""
    respx.get(f"{XAPI_BASE}/api/v1/sessions/current").mock(
        return_value=httpx.Response(
            200,
            json={
                "is_active": True,
                "ttl_seconds": 18 * 3600,  # 18h
                "ttl_human": "18h 0m",
                "expires_at": _now_iso(18),
                "created_at": _now_iso(-1),
                "device_id": "abc",
                "fingerprint_preview": "A2.aaaa...",
            },
        )
    )
    result = await scenario_a(make_client())
    assert result.scenario == "A"
    assert result.status == "pass"
    assert result.details["is_valid"] is True
    assert result.details["hours_left"] == pytest.approx(18.0, rel=1e-3)


@respx.mock
@pytest.mark.asyncio
async def test_scenario_a_fail_when_ttl_below_threshold() -> None:
    """ttl_seconds < 4h => FAIL."""
    respx.get(f"{XAPI_BASE}/api/v1/sessions/current").mock(
        return_value=httpx.Response(
            200,
            json={"is_active": True, "ttl_seconds": 3600, "ttl_human": "1h"},
        )
    )
    result = await scenario_a(make_client())
    assert result.status == "fail"
    assert "hours_left=1.00 <= 4.0" in result.details["reason"]


@respx.mock
@pytest.mark.asyncio
async def test_scenario_a_fail_on_no_session() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/sessions/current").mock(
        return_value=httpx.Response(200, json={"is_active": False})
    )
    result = await scenario_a(make_client())
    assert result.status == "fail"
    assert result.details["reason"] == "session not valid"


# ----------------------------------------------------------------------
# B. token rotation
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_scenario_b_pass_recent_rotation() -> None:
    """created_at within last 24h => PASS."""
    respx.get(f"{XAPI_BASE}/api/v1/sessions/current").mock(
        return_value=httpx.Response(
            200,
            json={"is_active": True, "created_at": _now_iso(-2)},  # 2h ago
        )
    )
    result = await scenario_b(make_client())
    assert result.status == "pass"
    assert 1.5 < result.details["age_hours"] < 2.5


@respx.mock
@pytest.mark.asyncio
async def test_scenario_b_fail_stale_rotation() -> None:
    """created_at > 24h ago => FAIL."""
    respx.get(f"{XAPI_BASE}/api/v1/sessions/current").mock(
        return_value=httpx.Response(
            200,
            json={"is_active": True, "created_at": _now_iso(-30)},  # 30h ago
        )
    )
    result = await scenario_b(make_client())
    assert result.status == "fail"
    assert "stale" in result.details["reason"]


# ----------------------------------------------------------------------
# C. messenger alive
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_scenario_c_pass_on_200() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(200, json={"channels": [{"id": "u2i-foo"}]}),
    )
    result = await scenario_c(make_client())
    assert result.status == "pass"
    assert result.details["status_code"] == 200
    assert result.details["returned_channels"] == 1


@respx.mock
@pytest.mark.asyncio
async def test_scenario_c_fail_on_500() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(500, json={"detail": "boom"}),
    )
    result = await scenario_c(make_client())
    assert result.status == "fail"
    assert result.details["status_code"] == 500


@respx.mock
@pytest.mark.asyncio
async def test_scenario_c_fail_on_transport_error() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    result = await scenario_c(make_client())
    assert result.status == "fail"
    assert result.details["status_code"] is None
    assert "ConnectError" in (result.details.get("error") or "")


# ----------------------------------------------------------------------
# D. messenger round-trip
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_scenario_d_pass_fast() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/unread-count").mock(
        return_value=httpx.Response(200, json={"count": 0}),
    )
    result = await scenario_d(make_client())
    assert result.status == "pass"
    assert result.details["unread_count"] == 0
    assert result.latency_ms < 1500


@respx.mock
@pytest.mark.asyncio
async def test_scenario_d_fail_on_non_200() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/unread-count").mock(
        return_value=httpx.Response(503, json={"detail": "down"}),
    )
    result = await scenario_d(make_client())
    assert result.status == "fail"
    assert result.details["status_code"] == 503


@respx.mock
@pytest.mark.asyncio
async def test_scenario_d_fail_on_slow_latency() -> None:
    """Patch xapi_client to return latency_ms above the budget without
    actually sleeping (keeps the test fast)."""
    from app.services.health_checker import xapi_client as xc

    real_get = xc.XapiClient.get

    async def slow_get(self, path: str, params=None):
        result = await real_get(self, path, params)
        # mutate via dataclass replace-style assignment
        result.latency_ms = 1800
        return result

    respx.get(f"{XAPI_BASE}/api/v1/messenger/unread-count").mock(
        return_value=httpx.Response(200, json={"count": 5}),
    )

    with patch.object(xc.XapiClient, "get", slow_get):
        result = await scenario_d(make_client())

    assert result.status == "fail"
    assert result.latency_ms == 1800
    assert "latency 1800ms" in result.details["reason"]


# ----------------------------------------------------------------------
# Registry / runner integration
# ----------------------------------------------------------------------

def test_registry_has_all_scenarios() -> None:
    assert sorted(REGISTRY.keys()) == ["A", "B", "C", "D", "E", "F", "G", "I"]


@pytest.mark.asyncio
async def test_persist_result_writes_row() -> None:
    """Verify the persistence function calls SQLAlchemy properly.

    We can't open a real DB here, so we patch ``get_sessionmaker`` with an
    AsyncMock and assert that ``add`` + ``commit`` were called with a
    correctly populated ``HealthCheck``.
    """
    from app.db.models import HealthCheck
    from app.services.health_checker import runner as runner_mod

    fake_session = AsyncMock()
    # ``async with sessionmaker()`` -> object with .__aenter__ / .__aexit__
    fake_cm = AsyncMock()
    fake_cm.__aenter__.return_value = fake_session
    fake_cm.__aexit__.return_value = None

    fake_sessionmaker = lambda: fake_cm  # noqa: E731 — tiny test stub

    with patch.object(runner_mod, "get_sessionmaker", return_value=fake_sessionmaker):
        await persist_result(
            ScenarioResult(
                scenario="A",
                status="pass",
                latency_ms=42,
                details={"endpoint": "/x", "status_code": 200},
            )
        )

    fake_session.add.assert_called_once()
    added = fake_session.add.call_args.args[0]
    assert isinstance(added, HealthCheck)
    assert added.scenario == "A"
    assert added.status == "pass"
    assert added.latency_ms == 42
    assert added.details == {"endpoint": "/x", "status_code": 200}
    fake_session.commit.assert_awaited_once()


@respx.mock
@pytest.mark.asyncio
async def test_run_all_once_executes_all_registered(monkeypatch) -> None:
    """End-to-end shake of the scheduler dispatch — every scenario exits."""
    from app.services.health_checker import runner as runner_mod

    # Stub persistence so we don't need a DB.
    persisted: list[ScenarioResult] = []

    async def fake_persist(result: ScenarioResult) -> None:
        persisted.append(result)

    monkeypatch.setattr(runner_mod, "persist_result", fake_persist)
    monkeypatch.setattr(
        runner_mod, "make_xapi_client", lambda settings=None: make_client()
    )
    monkeypatch.setenv("MESSENGER_BOT_BASE_URL", "http://bot.test:9102")

    respx.get(f"{XAPI_BASE}/api/v1/sessions/current").mock(
        return_value=httpx.Response(
            200,
            json={"is_active": True, "ttl_seconds": 10 * 3600, "created_at": _now_iso(-1)},
        )
    )
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(200, json={"channels": [{"id": "u2i-x"}]}),
    )
    respx.get(f"{XAPI_BASE}/api/v1/messenger/unread-count").mock(
        return_value=httpx.Response(200, json={"count": 0}),
    )
    # E: SSE bridge — connected + keepalive in a single body suffice.
    respx.get(f"{XAPI_BASE}/api/v1/messenger/realtime/events").mock(
        return_value=httpx.Response(
            200,
            content=(
                b"event: connected\ndata: {\"event\":\"connected\"}\n\n"
                b"event: keepalive\ndata: {\"event\":\"keepalive\"}\n\n"
            ),
            headers={"content-type": "text/event-stream"},
        ),
    )
    # F: mark-read POST round-trip on the picked channel.
    respx.post(f"{XAPI_BASE}/api/v1/messenger/channels/u2i-x/read").mock(
        return_value=httpx.Response(200, json={"status": "ok"}),
    )

    # G: messenger-bot dedup — first sent, second skipped.
    g_calls = {"n": 0}

    def _bot_handler(request: httpx.Request) -> httpx.Response:
        g_calls["n"] += 1
        if g_calls["n"] == 1:
            return httpx.Response(
                200,
                json={"action": "sent", "channel_id": "x", "message_id": "m"},
            )
        return httpx.Response(
            200,
            json={"action": "skipped", "reason": "already replied"},
        )

    respx.post("http://bot.test:9102/run-once").mock(side_effect=_bot_handler)

    # I: notification freshness — return a fresh ingest so I passes.
    respx.get(f"{XAPI_BASE}/api/v1/notifications/stats").mock(
        return_value=httpx.Response(
            200,
            json={
                "total": 5,
                "last_24h": 5,
                "last_received_at": _now_iso(-0.1),
                "by_source": {"android_notification": 5},
                "by_package": {"com.avito.android": 5},
            },
        ),
    )

    results = await run_all_once()
    assert {r.scenario for r in results} == {"A", "B", "C", "D", "E", "F", "G", "I"}
    assert all(r.status == "pass" for r in results), [
        (r.scenario, r.status, r.details) for r in results
    ]
    assert len(persisted) == 8


@respx.mock
@pytest.mark.asyncio
async def test_run_named_once_unknown_scenario_raises(monkeypatch) -> None:
    from app.services.health_checker import runner as runner_mod

    async def fake_persist(result: ScenarioResult) -> None:
        return None

    monkeypatch.setattr(runner_mod, "persist_result", fake_persist)
    monkeypatch.setattr(
        runner_mod, "make_xapi_client", lambda settings=None: make_client()
    )

    with pytest.raises(KeyError):
        await run_named_once("Z")


# ----------------------------------------------------------------------
# SSE client unit
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_sse_client_parses_event_blocks() -> None:
    """SseClient yields one SseEvent per blank-line-separated block."""
    body = (
        b"event: connected\ndata: {\"a\":1}\n\n"
        b"event: keepalive\ndata: {\"b\":2}\n\n"
    )
    respx.get("http://sse.test/x").mock(
        return_value=httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )
    )
    seen: list[SseEvent] = []
    async with SseClient("http://sse.test/x").stream() as events:
        async for evt in events:
            seen.append(evt)

    assert len(seen) == 2
    assert seen[0].event_name == "connected"
    assert seen[0].data == {"a": 1}
    assert seen[1].event_name == "keepalive"
    assert seen[1].data == {"b": 2}


# ----------------------------------------------------------------------
# E. SSE bridge
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_scenario_e_pass_connected_then_keepalive() -> None:
    body = (
        b"event: connected\ndata: {\"event\":\"connected\"}\n\n"
        b"event: keepalive\ndata: {\"event\":\"keepalive\"}\n\n"
    )
    respx.get(f"{XAPI_BASE}/api/v1/messenger/realtime/events").mock(
        return_value=httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )
    )
    result = await scenario_e(make_client())
    assert result.scenario == "E"
    assert result.status == "pass"
    assert result.details["connected_ms"] is not None
    assert result.details["keepalive_ms"] is not None
    assert result.details["connected_ms"] <= result.details["keepalive_ms"]


@pytest.mark.asyncio
async def test_scenario_e_fail_when_no_keepalive(monkeypatch) -> None:
    """Only ``connected`` arrives; ``keepalive`` budget elapses → FAIL.

    We use a custom ``MockTransport`` whose body hangs after the first event
    so the scenario hits its overall budget. Patched at the SseClient level
    via dependency injection of the httpx client.
    """

    async def slow_body():
        yield b"event: connected\ndata: {\"event\":\"connected\"}\n\n"
        # never yields more — caller must hit the budget
        await asyncio.sleep(10)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=slow_body(),
            headers={"content-type": "text/event-stream"},
        )

    transport = httpx.MockTransport(handler)
    injected_client = httpx.AsyncClient(transport=transport)

    from app.services.health_checker import sse_client as sse_mod
    from app.services.health_checker.scenarios import e_sse_bridge as e_mod

    real_sse_init = sse_mod.SseClient.__init__

    def patched_init(self, url, headers=None, *, timeout=None, client=None):
        real_sse_init(self, url, headers, timeout=timeout, client=injected_client)

    monkeypatch.setattr(sse_mod.SseClient, "__init__", patched_init)
    # Re-import binding the patched class is unnecessary because scenario_e
    # references SseClient via the module attr lookup at call time.

    try:
        result = await e_mod.scenario_e(
            make_client(),
            connected_budget_sec=0.5,
            overall_budget_sec=0.3,
        )
    finally:
        await injected_client.aclose()

    assert result.scenario == "E"
    assert result.status == "fail"
    assert result.details["connected_ms"] is not None
    assert result.details["keepalive_ms"] is None
    assert "keepalive" in result.details["reason"]


@respx.mock
@pytest.mark.asyncio
async def test_scenario_e_fail_on_connect_error() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/realtime/events").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    result = await scenario_e(make_client())
    assert result.status == "fail"
    assert "ConnectError" in (result.details.get("error") or "")


# ----------------------------------------------------------------------
# F. messenger mark-read round-trip
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_scenario_f_pass_on_2xx() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(200, json={"channels": [{"id": "u2i-abc"}]})
    )
    read_route = respx.post(
        f"{XAPI_BASE}/api/v1/messenger/channels/u2i-abc/read"
    ).mock(return_value=httpx.Response(200, json={"status": "ok"}))

    result = await scenario_f(make_client())
    assert result.scenario == "F"
    assert result.status == "pass"
    assert result.details["channel_id"] == "u2i-abc"
    assert result.details["read_status_code"] == 200
    assert read_route.called
    assert result.latency_ms < 1500


@respx.mock
@pytest.mark.asyncio
async def test_scenario_f_skip_when_no_channels() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(200, json={"channels": []})
    )
    result = await scenario_f(make_client())
    assert result.status == "skip"
    assert "no channels" in result.details["reason"]


@respx.mock
@pytest.mark.asyncio
async def test_scenario_f_fail_on_5xx() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(200, json={"channels": [{"id": "u2i-zzz"}]})
    )
    respx.post(f"{XAPI_BASE}/api/v1/messenger/channels/u2i-zzz/read").mock(
        return_value=httpx.Response(503, json={"detail": "down"})
    )
    result = await scenario_f(make_client())
    assert result.status == "fail"
    assert result.details["read_status_code"] == 503


# ----------------------------------------------------------------------
# G. Bot template + dedup (TZ §2 L4 / §8 acceptance)
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_scenario_g_pass_when_second_call_skipped(monkeypatch) -> None:
    """First call ``sent`` + second call ``skipped: already replied`` → PASS."""
    monkeypatch.setenv("MESSENGER_BOT_BASE_URL", "http://bot.test:9102")

    calls = {"n": 0}

    def _bot_handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={
                    "action": "sent",
                    "reason": None,
                    "channel_id": "fake",
                    "message_id": "dry-run-aaa",
                    "details": {"dry_run": True},
                },
            )
        return httpx.Response(
            200,
            json={
                "action": "skipped",
                "reason": "already replied (dialog_state)",
                "channel_id": "fake",
                "message_id": None,
                "details": {},
            },
        )

    respx.post("http://bot.test:9102/run-once").mock(side_effect=_bot_handler)

    result = await scenario_g(make_client())
    assert result.scenario == "G"
    assert result.status == "pass", result.details
    assert result.details["first_action"] == "sent"
    assert result.details["second_action"] == "skipped"


@respx.mock
@pytest.mark.asyncio
async def test_scenario_g_fail_when_second_also_sent(monkeypatch) -> None:
    """If both calls produce ``sent`` → dedup is broken → FAIL."""
    monkeypatch.setenv("MESSENGER_BOT_BASE_URL", "http://bot.test:9102")

    respx.post("http://bot.test:9102/run-once").mock(
        return_value=httpx.Response(
            200,
            json={
                "action": "sent",
                "reason": None,
                "channel_id": "fake",
                "message_id": "dry-run-x",
                "details": {"dry_run": True},
            },
        )
    )

    result = await scenario_g(make_client())
    assert result.status == "fail"
    assert "did not trip" in (result.details.get("reason") or "")


@respx.mock
@pytest.mark.asyncio
async def test_scenario_g_fail_when_bot_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("MESSENGER_BOT_BASE_URL", "http://bot.test:9102")
    respx.post("http://bot.test:9102/run-once").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    result = await scenario_g(make_client())
    assert result.status == "fail"
    assert "unreachable" in (result.details.get("error") or "")


@respx.mock
@pytest.mark.asyncio
async def test_scenario_g_pass_when_send_failed_then_skipped(monkeypatch) -> None:
    """Spec acceptance: first call ``send_failed`` is also a valid first state."""
    monkeypatch.setenv("MESSENGER_BOT_BASE_URL", "http://bot.test:9102")

    calls = {"n": 0}

    def _h(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={
                    "action": "send_failed",
                    "reason": "HTTP 503",
                    "channel_id": "fake",
                    "message_id": None,
                    "details": {"status_code": 503},
                },
            )
        return httpx.Response(
            200,
            json={
                "action": "skipped",
                "reason": "already replied (dialog_state)",
                "channel_id": "fake",
                "message_id": None,
                "details": {},
            },
        )

    respx.post("http://bot.test:9102/run-once").mock(side_effect=_h)

    result = await scenario_g(make_client())
    assert result.status == "pass"


# ----------------------------------------------------------------------
# I. notification listener freshness (V2.1)
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_scenario_i_pass_fresh_notification() -> None:
    """A recent forwarded notification → PASS."""
    respx.get(f"{XAPI_BASE}/api/v1/notifications/stats").mock(
        return_value=httpx.Response(
            200,
            json={
                "total": 12,
                "last_24h": 8,
                "last_received_at": _now_iso(-0.5),  # 30 min ago
                "by_source": {"android_notification": 12},
                "by_package": {"com.avito.android": 12},
            },
        )
    )
    result = await scenario_i(make_client())
    assert result.scenario == "I"
    assert result.status == "pass"
    assert result.details["total"] == 12
    assert result.details["age_hours"] < 1.0


@respx.mock
@pytest.mark.asyncio
async def test_scenario_i_skip_when_no_notifications_yet() -> None:
    """No notifications ingested ever → SKIP (warm-up, no alert)."""
    respx.get(f"{XAPI_BASE}/api/v1/notifications/stats").mock(
        return_value=httpx.Response(
            200,
            json={"total": 0, "last_24h": 0, "last_received_at": None,
                  "by_source": {}, "by_package": {}},
        )
    )
    result = await scenario_i(make_client())
    assert result.status == "skip"
    assert "no notifications ingested yet" in result.details["reason"]


@respx.mock
@pytest.mark.asyncio
async def test_scenario_i_fail_when_notification_too_old() -> None:
    """Last notification older than the configured cutoff → FAIL."""
    respx.get(f"{XAPI_BASE}/api/v1/notifications/stats").mock(
        return_value=httpx.Response(
            200,
            json={
                "total": 1,
                "last_24h": 0,
                "last_received_at": _now_iso(-48),  # 48h ago, default cutoff is 12h
                "by_source": {"android_notification": 1},
                "by_package": {"com.avito.android": 1},
            },
        )
    )
    result = await scenario_i(make_client())
    assert result.status == "fail"
    assert "last notification" in result.details["reason"]
    assert result.details["age_hours"] > 12.0


@respx.mock
@pytest.mark.asyncio
async def test_scenario_i_fail_on_http_error() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/notifications/stats").mock(
        return_value=httpx.Response(500, json={"detail": "boom"}),
    )
    result = await scenario_i(make_client())
    assert result.status == "fail"
    assert result.details["status_code"] == 500


@respx.mock
@pytest.mark.asyncio
async def test_scenario_i_fail_on_unparseable_timestamp() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/notifications/stats").mock(
        return_value=httpx.Response(
            200,
            json={"total": 3, "last_24h": 1, "last_received_at": "not-a-date"},
        )
    )
    result = await scenario_i(make_client())
    assert result.status == "fail"
    assert "unparseable" in result.details["reason"]
