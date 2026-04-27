"""Scenario F — HTTP messenger send round-trip (mark-read variant).

We MUST NOT inject real chat traffic on the user's account. Originally this
scenario used the typing indicator, but Avito mobile API removed
``/1/messenger/read`` (404 upstream). Switched to mark-read which is
idempotent on already-read channels and exercises the same POST round-trip:

1. ``GET /messenger/channels?limit=1`` to pick any existing channel.
   * 0 channels → SKIP (clear reason; nothing to test against).
2. ``POST /messenger/channels/{id}/read`` (empty body) — idempotent, does
   NOT alter state when channel is already read.

PASS: HTTP 2xx and round-trip latency < 1500 ms.
FAIL: any other outcome.
"""
from __future__ import annotations

from app.services.health_checker.scenarios.base import ScenarioResult
from app.services.health_checker.xapi_client import XapiClient

SCENARIO = "F"
MAX_LATENCY_MS = 1500


async def scenario_f(client: XapiClient) -> ScenarioResult:
    list_call = await client.get("/api/v1/messenger/channels", params={"limit": 1})
    details: dict = {
        "endpoint": "/api/v1/messenger/channels/{id}/read",
        "list_status_code": list_call.status_code,
        "max_latency_ms": MAX_LATENCY_MS,
    }
    if not list_call.ok:
        details["error"] = list_call.error or f"HTTP {list_call.status_code}"
        return ScenarioResult(SCENARIO, "fail", list_call.latency_ms, details)

    channel_id = _extract_first_channel_id(list_call.body)
    details["channel_id"] = channel_id
    if not channel_id:
        details["reason"] = "no channels available to exercise read endpoint"
        return ScenarioResult(SCENARIO, "skip", list_call.latency_ms, details)

    read_call = await client.post(
        f"/api/v1/messenger/channels/{channel_id}/read",
        json_body={},
    )
    details["read_status_code"] = read_call.status_code

    if not read_call.ok:
        details["error"] = read_call.error or f"HTTP {read_call.status_code}"
        return ScenarioResult(SCENARIO, "fail", read_call.latency_ms, details)

    if read_call.latency_ms >= MAX_LATENCY_MS:
        details["reason"] = (
            f"latency {read_call.latency_ms}ms >= {MAX_LATENCY_MS}ms"
        )
        return ScenarioResult(SCENARIO, "fail", read_call.latency_ms, details)

    return ScenarioResult(SCENARIO, "pass", read_call.latency_ms, details)


def _extract_first_channel_id(body: object) -> str | None:
    """Pull the first channel id out of the xapi list response.

    xapi shape is ``{"channels": [{"id": "u2i-..."}]}`` but we accept a few
    nearby shapes defensively (``items`` / top-level list).
    """
    if isinstance(body, dict):
        for key in ("channels", "items", "data"):
            value = body.get(key)
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, dict):
                    cid = first.get("id") or first.get("channel_id")
                    if isinstance(cid, str) and cid:
                        return cid
    if isinstance(body, list) and body:
        first = body[0]
        if isinstance(first, dict):
            cid = first.get("id") or first.get("channel_id")
            if isinstance(cid, str) and cid:
                return cid
    return None
