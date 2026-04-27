"""Unit tests for the SSE listener loop."""
from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.config import Settings
from app.services.messenger_bot import handler as handler_mod
from app.services.messenger_bot import runner as runner_mod

XAPI_BASE = "http://xapi.test"


def make_settings(**overrides) -> Settings:
    base = {
        "app_secret_key": "x" * 32,
        "database_url": "postgresql+asyncpg://t:t@localhost/t",
        "avito_xapi_url": XAPI_BASE,
        "avito_xapi_api_key": "test-key",
        "messenger_bot_enabled": True,
        "messenger_bot_template": "Hi.",
        "messenger_bot_whitelist_own_listings_only": False,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@respx.mock
@pytest.mark.asyncio
async def test_listener_dispatches_event_to_handler(monkeypatch):
    """One ``new_message`` block on the SSE stream → one handler invocation.

    We feed a finite body once, then make subsequent calls fail with a
    ConnectError. The listener consumes events from the first stream, hits
    the next reconnect (which fails), and parks on backoff sleep. We cancel
    explicitly once both events are observed.
    """
    body = (
        b"event: connected\ndata: {\"event\":\"connected\"}\n\n"
        b"event: new_message\ndata: {\"event\":\"new_message\","
        b"\"payload\":{\"channel_id\":\"u2i-runner-1\"}}\n\n"
    )
    call_state = {"first": True}

    def _handler(request: httpx.Request) -> httpx.Response:
        if call_state["first"]:
            call_state["first"] = False
            return httpx.Response(
                200, content=body, headers={"content-type": "text/event-stream"}
            )
        raise httpx.ConnectError("reconnect blocked in test")

    respx.get(f"{XAPI_BASE}/api/v1/messenger/realtime/events").mock(side_effect=_handler)

    received: list[str] = []

    async def fake_safe_handler(evt, *, client, settings=None):
        del client, settings  # unused — required by signature
        received.append(evt.event_name)
        return None

    monkeypatch.setattr(runner_mod, "handle_event_safe", fake_safe_handler)

    settings = make_settings()
    task = asyncio.create_task(runner_mod.listen_forever(settings))
    # Give the loop time to consume both events and dispatch tasks.
    for _ in range(40):
        await asyncio.sleep(0.05)
        if "new_message" in received and "connected" in received:
            break
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert "connected" in received
    assert "new_message" in received


@pytest.mark.asyncio
async def test_listener_reconnects_on_error(monkeypatch):
    """A connect error must transition state to 'reconnecting' and back off."""
    sleeps: list[float] = []

    real_sleep = asyncio.sleep

    async def fake_sleep(t: float):
        sleeps.append(t)
        # Cooperate with cancel by yielding via a 0-sec real sleep
        await real_sleep(0)

    monkeypatch.setattr(runner_mod.asyncio, "sleep", fake_sleep)

    @respx.mock
    async def _run():
        respx.get(f"{XAPI_BASE}/api/v1/messenger/realtime/events").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        settings = make_settings()
        task = asyncio.create_task(runner_mod.listen_forever(settings))
        # Wait until at least one reconnect attempt has been registered.
        for _ in range(50):
            await real_sleep(0.02)
            if runner_mod.RECONNECT_ATTEMPTS >= 1:
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await _run()

    assert runner_mod.RECONNECT_ATTEMPTS >= 1
    assert runner_mod.SSE_STATE in {"reconnecting", "closed"}
    assert sleeps  # at least one backoff sleep happened


def test_make_xapi_client_uses_settings():
    s = make_settings()
    client = runner_mod.make_xapi_client(s)
    assert client.base_url == XAPI_BASE
    assert client.api_key == "test-key"


# Keep handler_mod import live (used elsewhere via monkeypatch in other test
# files; here as a sanity ref so ruff doesn't flag the import).
_ = handler_mod
