"""Scenario A — Token freshness.

PASS: ``GET /sessions/current`` returns 200 AND session is valid AND
       remaining TTL > 4 hours.
FAIL: anything else.

We accept two response shapes (TZ §3 normaliser is in flux):

* spec shape: ``{is_valid, hours_left, ...}``
* live xapi:  ``{is_active, ttl_seconds, ttl_human, ...}``
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.services.health_checker.scenarios.base import ScenarioResult
from app.services.health_checker.xapi_client import XapiClient

SCENARIO = "A"
MIN_HOURS_LEFT = 4.0


def _local_tz() -> ZoneInfo:
    try:
        return ZoneInfo(get_settings().timezone)
    except Exception:
        return ZoneInfo("UTC")


def _extract_validity(body: dict | None) -> tuple[bool, float | None]:
    """Return ``(is_valid, hours_left)`` from either spec or live shape."""
    if not isinstance(body, dict):
        return False, None
    # Spec shape (preferred).
    is_valid = body.get("is_valid")
    hours_left = body.get("hours_left")
    if is_valid is not None and hours_left is not None:
        try:
            return bool(is_valid), float(hours_left)
        except (TypeError, ValueError):
            return False, None
    # Live xapi shape.
    is_active = body.get("is_active")
    ttl_seconds = body.get("ttl_seconds")
    if is_active is None and ttl_seconds is None:
        return False, None
    h = float(ttl_seconds) / 3600.0 if ttl_seconds is not None else None
    return bool(is_active), h


def _format_ttl(hours_left: float) -> str:
    """Render hours_left as ``Xч Yм`` (or ``Xм`` if < 1h)."""
    total_min = int(round(hours_left * 60))
    if total_min < 0:
        total_min = abs(total_min)
        h, m = divmod(total_min, 60)
        return f"уже {h}ч {m}м назад" if h else f"уже {m}м назад"
    h, m = divmod(total_min, 60)
    return f"{h}ч {m}м" if h else f"{m}м"


def _format_deadline(body: dict | None, hours_left: float | None) -> str | None:
    """Format expires_at in local TZ as ``HH:MM <TZ>`` (e.g. ``19:08 +04``).

    Prefers the explicit ``expires_at`` ISO string from xapi; falls back to
    reconstructing it from ``now() + hours_left``.
    """
    deadline: datetime | None = None
    iso = body.get("expires_at") if isinstance(body, dict) else None
    if iso:
        try:
            # xapi emits a trailing 'Z'; Python fromisoformat accepts +00:00 only.
            deadline = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except ValueError:
            deadline = None
    if deadline is None and hours_left is not None:
        deadline = datetime.now(timezone.utc) + timedelta(hours=hours_left)
    if deadline is None:
        return None

    local = deadline.astimezone(_local_tz())
    label = local.strftime("%Z") or "+00"
    return f"{local:%H:%M} {label}"


async def scenario_a(client: XapiClient) -> ScenarioResult:
    call = await client.get("/api/v1/sessions/current")
    details: dict = {
        "endpoint": "/api/v1/sessions/current",
        "status_code": call.status_code,
    }
    if not call.ok:
        details["error"] = call.error or f"HTTP {call.status_code}"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    body = call.body if isinstance(call.body, dict) else None
    is_valid, hours_left = _extract_validity(body)
    details["is_valid"] = is_valid
    details["hours_left"] = hours_left
    if isinstance(body, dict) and body.get("expires_at"):
        details["expires_at"] = body["expires_at"]
    deadline_str = _format_deadline(body, hours_left)
    if deadline_str:
        details["expires_at_local"] = deadline_str

    if not is_valid:
        details["reason"] = "session not valid"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)
    if hours_left is None:
        details["reason"] = "could not extract hours_left from response"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)
    if hours_left <= MIN_HOURS_LEFT:
        ttl_str = _format_ttl(hours_left)
        if deadline_str:
            details["reason"] = f"протухнет в {deadline_str} (через {ttl_str})"
        else:
            details["reason"] = f"осталось {ttl_str}"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    # PASS — record human-readable freshness for the recovery message.
    ttl_str = _format_ttl(hours_left)
    if deadline_str:
        details["fresh_for"] = f"свежий до {deadline_str} (ещё {ttl_str})"
    else:
        details["fresh_for"] = f"ещё {ttl_str}"
    return ScenarioResult(SCENARIO, "pass", call.latency_ms, details)
