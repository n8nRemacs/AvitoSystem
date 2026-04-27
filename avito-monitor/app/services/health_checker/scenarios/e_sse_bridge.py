"""Scenario E — SSE bridge alive.

PASS: opens ``GET /api/v1/messenger/realtime/events`` (SSE), receives the
       ``connected`` event within 5s AND **any** subsequent event (keepalive,
       new_message, typing, read, disconnected) within 60s. The stream is
       then closed cleanly.
FAIL: connect error, no ``connected`` in 5s, or no further event in 60s.

xapi's ``_sse_generator`` only emits a ``keepalive`` if the broadcast queue
is silent for ``SSE_KEEPALIVE_SEC=30s``. If the WS pushes any real event
(``read``, ``disconnected``, etc.) into the queue, the keepalive timer
resets — so a strict keepalive-only check is flaky. Accepting any event
correctly validates "the bridge is producing output".

When a second test account exists we can swap this for a real self-send
variant without touching surrounding plumbing.
"""
from __future__ import annotations

import asyncio
import time

from app.services.health_checker.scenarios.base import ScenarioResult
from app.services.health_checker.sse_client import SseClient
from app.services.health_checker.xapi_client import XapiClient

SCENARIO = "E"

# Window in which we expect to see each event, in seconds. Override via the
# ``timeout_sec`` kwarg from tests (kept here as constants so the production
# loop uses TZ-spec values).
DEFAULT_CONNECTED_BUDGET_SEC = 5.0
# 60s overall budget — keepalive is every 30s when the queue is silent, but
# real Avito events reset that timer. We accept any post-`connected` event.
DEFAULT_OVERALL_BUDGET_SEC = 60.0


async def scenario_e(
    client: XapiClient,
    *,
    connected_budget_sec: float = DEFAULT_CONNECTED_BUDGET_SEC,
    overall_budget_sec: float = DEFAULT_OVERALL_BUDGET_SEC,
) -> ScenarioResult:
    url = f"{client.base_url}/api/v1/messenger/realtime/events"
    headers = {
        "X-Api-Key": client.api_key,
        "User-Agent": "avito-monitor-healthchecker/0.1.0",
        "Accept": "text/event-stream",
    }
    details: dict = {
        "endpoint": "/api/v1/messenger/realtime/events",
        "connected_budget_ms": int(connected_budget_sec * 1000),
        "overall_budget_ms": int(overall_budget_sec * 1000),
    }

    started = time.monotonic()
    connected_ms: int | None = None
    second_event_ms: int | None = None
    second_event_name: str | None = None

    try:
        # Enforce the overall budget at the iteration level — without this an
        # SSE stream that never yields again would block forever.
        async with asyncio.timeout(overall_budget_sec):
            async with SseClient(url, headers).stream() as events:
                async for evt in events:
                    elapsed = time.monotonic() - started
                    if evt.event_name == "connected" and connected_ms is None:
                        connected_ms = int(elapsed * 1000)
                    elif connected_ms is not None:
                        # Any post-connected event is proof the SSE bridge is alive.
                        second_event_ms = int(elapsed * 1000)
                        second_event_name = evt.event_name
                        break
    except TimeoutError:
        # Expected when the stream stalls: fall through and inspect what we
        # did manage to capture.
        pass
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        details["error"] = f"{type(exc).__name__}: {exc}"
        return ScenarioResult(SCENARIO, "fail", elapsed_ms, details)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    details["connected_ms"] = connected_ms
    details["second_event_ms"] = second_event_ms
    details["second_event_name"] = second_event_name

    if connected_ms is None or connected_ms > int(connected_budget_sec * 1000):
        details["reason"] = (
            f"no connected event within {int(connected_budget_sec * 1000)}ms"
        )
        return ScenarioResult(SCENARIO, "fail", elapsed_ms, details)
    if second_event_ms is None or second_event_ms > int(overall_budget_sec * 1000):
        details["reason"] = (
            f"no post-connected event within {int(overall_budget_sec * 1000)}ms"
        )
        return ScenarioResult(SCENARIO, "fail", elapsed_ms, details)

    # Latency reported = time to first proof-of-life (connected event).
    return ScenarioResult(SCENARIO, "pass", connected_ms, details)
