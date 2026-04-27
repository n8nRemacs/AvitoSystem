"""Scenario G — Bot template + dedup (TZ §2 L4 / §8 acceptance).

Hits the messenger-bot's ``/run-once?dry_run=true`` endpoint twice with the
same synthetic ``channel_id``. The first call must produce action
``sent`` (or ``send_failed`` if dry_run somehow turned off — defensive); the
second must produce ``skipped`` with a reason that mentions "already replied".

PASS conditions (BOTH required):
    1. First call action ∈ {"sent", "send_failed"}.
    2. Second call action == "skipped" AND reason contains "already".

FAIL: anything else, including the bot service being unreachable.

Side-effect cleanup: each run uses a fresh ``test-G-{uuid}`` channel id so
historical rows in ``chat_dialog_state`` accumulate but don't break later runs.
The verify-step CLI command in the implementation report wipes them.
"""
from __future__ import annotations

import os
import time
import uuid

import httpx

from app.services.health_checker.scenarios.base import ScenarioResult
from app.services.health_checker.xapi_client import XapiClient

SCENARIO = "G"

# In-cluster URL for the messenger-bot sidecar. Override with
# ``MESSENGER_BOT_BASE_URL`` if the docker-compose service name changes.
DEFAULT_BOT_URL = "http://messenger-bot:9102"


async def scenario_g(client: XapiClient) -> ScenarioResult:
    """Run the dedup test.

    The ``client`` arg is unused — we hit messenger-bot directly — but the
    signature must match :data:`ScenarioFn` so the runner registry stays
    homogeneous.
    """
    del client  # unused; required by ScenarioFn signature

    bot_url = os.environ.get("MESSENGER_BOT_BASE_URL", DEFAULT_BOT_URL).rstrip("/")
    fake_channel = f"test-G-{uuid.uuid4().hex[:12]}"

    details: dict = {
        "endpoint": f"{bot_url}/run-once",
        "channel_id": fake_channel,
        "dry_run": True,
    }

    started = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp1 = await http.post(
                f"{bot_url}/run-once",
                params={"channel_id": fake_channel, "dry_run": "true"},
            )
            resp2 = await http.post(
                f"{bot_url}/run-once",
                params={"channel_id": fake_channel, "dry_run": "true"},
            )
    except httpx.HTTPError as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        details["error"] = f"messenger-bot unreachable: {type(exc).__name__}: {exc}"
        return ScenarioResult(SCENARIO, "fail", elapsed_ms, details)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    details["first_status"] = resp1.status_code
    details["second_status"] = resp2.status_code

    if resp1.status_code >= 400 or resp2.status_code >= 400:
        details["reason"] = "messenger-bot returned non-2xx"
        return ScenarioResult(SCENARIO, "fail", elapsed_ms, details)

    try:
        v1 = resp1.json()
        v2 = resp2.json()
    except ValueError:
        details["reason"] = "messenger-bot did not return JSON"
        return ScenarioResult(SCENARIO, "fail", elapsed_ms, details)

    details["first_action"] = v1.get("action")
    details["first_reason"] = v1.get("reason")
    details["second_action"] = v2.get("action")
    details["second_reason"] = v2.get("reason")

    first_ok = v1.get("action") in {"sent", "send_failed"}
    second_action = v2.get("action")
    second_reason = (v2.get("reason") or "").lower()
    second_ok = second_action == "skipped" and "already" in second_reason

    if first_ok and second_ok:
        return ScenarioResult(SCENARIO, "pass", elapsed_ms, details)

    if not first_ok:
        details["reason"] = (
            f"first call action={v1.get('action')!r} (expected 'sent' or 'send_failed')"
        )
    elif v1.get("action") == v2.get("action"):
        details["reason"] = (
            f"both calls produced the same action {v1.get('action')!r} "
            f"— dedup did not trip"
        )
    else:
        details["reason"] = (
            f"second call action={second_action!r} reason={v2.get('reason')!r} "
            f"(expected 'skipped' with 'already' in reason)"
        )
    return ScenarioResult(SCENARIO, "fail", elapsed_ms, details)
