"""Scenario B — Token rotation.

PASS: ``GET /sessions/current`` returns 200 AND the most-recent rotation
       timestamp is within the last 24h (i.e. AvitoSessionManager APK has
       refreshed at least once recently).
FAIL: anything else.

Spec field is ``updated_at``; live xapi exposes ``created_at`` (timestamp the
current session row was inserted, which equals the last rotation). We accept
either.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.services.health_checker.scenarios.base import ScenarioResult
from app.services.health_checker.xapi_client import XapiClient

SCENARIO = "B"
MAX_AGE_HOURS = 24.0


def _local_tz() -> ZoneInfo:
    try:
        return ZoneInfo(get_settings().timezone)
    except Exception:
        return ZoneInfo("UTC")


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    # Python's fromisoformat handles ``2026-04-26T18:27:51.690222Z`` only since
    # 3.11+; ensure we strip a trailing 'Z' and pass tzinfo correctly.
    raw = value.rstrip("Z")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


async def scenario_b(client: XapiClient) -> ScenarioResult:
    call = await client.get("/api/v1/sessions/current")
    details: dict = {
        "endpoint": "/api/v1/sessions/current",
        "status_code": call.status_code,
    }
    if not call.ok:
        details["error"] = call.error or f"HTTP {call.status_code}"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    body = call.body if isinstance(call.body, dict) else {}
    raw = body.get("updated_at") or body.get("created_at")
    rotated = _parse_ts(raw)
    details["raw_timestamp"] = raw
    details["parsed_timestamp"] = rotated.isoformat() if rotated else None

    if rotated is None:
        details["reason"] = "no updated_at/created_at in response"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    age = datetime.now(UTC) - rotated
    age_hours = round(age.total_seconds() / 3600.0, 2)
    details["age_hours"] = age_hours

    if age > timedelta(hours=MAX_AGE_HOURS):
        local = rotated.astimezone(_local_tz())
        ts_local = local.strftime("%H:%M")
        tz_label = local.strftime("%Z") or "+00"
        details["reason"] = f"последняя ротация {age_hours:.1f}ч назад в {ts_local} {tz_label}"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)
    if age.total_seconds() < 0:
        # Clock skew: timestamp is in the future. Treat as stale, surface clearly.
        details["reason"] = "rotation timestamp in the future (clock skew?)"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    # PASS — record human-readable rotation timestamp for the recovery message.
    local = rotated.astimezone(_local_tz())
    ts_local = local.strftime("%H:%M")
    details["fresh_for"] = f"последняя ротация {ts_local} (всего {age_hours:.1f}ч назад)"
    return ScenarioResult(SCENARIO, "pass", call.latency_ms, details)
