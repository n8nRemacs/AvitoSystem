"""Scenario I — Phone NotificationListener freshness.

V2.1: the AvitoSessionManager APK on the phone runs a NotificationListenerService
that forwards Android notifications from ``com.avito.android`` (and any other
package the user enables) to xapi ``POST /api/v1/notifications``. This scenario
verifies that pipeline is alive end-to-end by polling the freshness of the
latest forwarded notification.

Outcomes
--------
* PASS: ``GET /api/v1/notifications/stats`` returns 200 AND the latest
        forwarded notification is fresher than ``notification_freshness_hours``.
* SKIP: The endpoint works but no notifications have ever been ingested. We
        treat this as "still in warm-up" rather than failure — the phone
        listener may not be granted yet, and we don't want to spam alerts
        before the user finishes wiring it up. Once the very first notification
        lands, the scenario flips to a PASS/FAIL evaluation.
* FAIL: HTTP error, malformed body, missing/unparseable timestamp, or the
        latest notification is too old.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.config import get_settings
from app.services.health_checker.scenarios.base import ScenarioResult
from app.services.health_checker.xapi_client import XapiClient

SCENARIO = "I"
ENDPOINT = "/api/v1/notifications/stats"


async def scenario_i(client: XapiClient) -> ScenarioResult:
    call = await client.get(ENDPOINT)
    details: dict = {
        "endpoint": ENDPOINT,
        "status_code": call.status_code,
    }
    if not call.ok:
        details["error"] = call.error or f"HTTP {call.status_code}"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    body = call.body if isinstance(call.body, dict) else {}
    total = int(body.get("total") or 0)
    last_24h = int(body.get("last_24h") or 0)
    last_received_at_raw = body.get("last_received_at")

    details.update({
        "total": total,
        "last_24h": last_24h,
        "last_received_at": last_received_at_raw,
    })

    # Warm-up: nothing forwarded yet. The phone listener may not be installed
    # or granted access. Don't fire alerts — it's not a fault yet.
    if total == 0:
        details["reason"] = "no notifications ingested yet (phone listener not configured?)"
        return ScenarioResult(SCENARIO, "skip", call.latency_ms, details)

    if not isinstance(last_received_at_raw, str) or not last_received_at_raw:
        details["reason"] = "stats endpoint returned total>0 but no last_received_at"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    try:
        last_dt = datetime.fromisoformat(last_received_at_raw.replace("Z", "+00:00"))
    except ValueError:
        details["reason"] = f"unparseable last_received_at: {last_received_at_raw!r}"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=UTC)

    age_hours = (datetime.now(UTC) - last_dt).total_seconds() / 3600.0
    details["age_hours"] = round(age_hours, 2)

    cutoff_hours = float(get_settings().notification_freshness_hours)
    details["cutoff_hours"] = cutoff_hours

    if age_hours > cutoff_hours:
        details["reason"] = (
            f"last notification {age_hours:.1f}h ago > cutoff {cutoff_hours}h"
        )
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    return ScenarioResult(SCENARIO, "pass", call.latency_ms, details)
