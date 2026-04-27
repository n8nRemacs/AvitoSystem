"""Server-driven Avito token refresh trigger (Block 5+ V2.1 follow-up).

The Avito mobile app refreshes its session JWT only when the old token
is at the edge of expiry — we can't preemptively refresh "to be safe".
So we wait until ``exp - now`` falls into a narrow window (60–180 s),
then POST a ``refresh_token`` command to xapi, which the
AvitoSessionManager APK long-polls for. The APK opens Avito, nudges
the feed with input swipes until the SharedPrefs ``exp`` jumps, and
uploads the fresh session via the existing /sessions endpoint.

This loop runs once per :data:`POLL_INTERVAL_SEC` (default 30 s):

1. ``GET /api/v1/sessions/current`` — read current TTL.
2. If TTL is in ``REFRESH_WINDOW`` (60–180 s) and we're not already
   in cooldown for this device — POST a refresh_token command.
3. Sleep ``CORRELATION_DELAY_SEC`` (90 s) and re-check TTL — if
   it didn't advance, count one strike. After
   :data:`MAX_STRIKES` consecutive failures we send a Telegram
   alert ("открой Avito вручную") and reset the counter.

State is in-process; restarting the health-checker resets strikes,
which is fine — duplicate alerts on a flaky network are preferable to
silent stuck refreshes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from app.config import Settings, get_settings
from app.services.health_checker.alerts import send_alert
from app.services.health_checker.xapi_client import XapiClient

log = structlog.get_logger(__name__)


POLL_INTERVAL_SEC = 30
# Refresh window — we trigger when ttl <= UPPER. There's no lower
# bound: an already-expired token (ttl < 0) is the same lemon, just
# more sour. The only fix is still "open Avito so it refreshes" and
# the cooldown below keeps us from spamming the APK.
REFRESH_WINDOW_UPPER_SEC = 180
COOLDOWN_AFTER_REQUEST_SEC = 300  # don't re-issue command for 5 min
CORRELATION_DELAY_SEC = 90
MAX_STRIKES = 3


_state = {
    "last_request_at": None,  # datetime | None — last command we issued
    "last_request_prev_exp": None,  # int — exp before that command
    "strikes": 0,
}


def _reset_state() -> None:
    _state["last_request_at"] = None
    _state["last_request_prev_exp"] = None
    _state["strikes"] = 0


async def _post_refresh_command(
    client: XapiClient, prev_exp: int | None
) -> bool:
    """POST /api/v1/devices/me/commands with command=refresh_token. True on success.

    ``prev_exp`` is the JWT exp the server currently sees. The APK
    treats it as the authoritative baseline for the "did Avito refresh?"
    check — we hand it down because the APK can't tell whether a fresh
    Avito SharedPrefs read happens before or after Avito's internal
    refresh, but the server-side value is always strictly older.
    """
    res = await client.post(
        "/api/v1/devices/me/commands",
        json_body={
            "command": "refresh_token",
            "payload": {
                "timeout_sec": 90,
                "scroll_interval_sec": 1.5,
                "prev_exp": prev_exp,
            },
            "dedup_window_sec": COOLDOWN_AFTER_REQUEST_SEC,
            "expire_after_sec": 180,
            "issued_by": "health_checker.token_refresher",
        },
    )
    if not res.ok:
        log.warning(
            "token_refresh.post_failed",
            status=res.status_code,
            error=res.error,
        )
        return False
    return True


async def _read_session_status(client: XapiClient) -> tuple[int | None, int | None]:
    """Returns (ttl_seconds, expires_at_unix). None,None on failure or no session."""
    res = await client.get("/api/v1/sessions/current")
    if not res.ok or not isinstance(res.body, dict):
        return None, None
    data = res.body
    if not data.get("is_active"):
        return None, None
    ttl = data.get("ttl_seconds")
    exp_iso = data.get("expires_at")
    exp_unix = None
    if exp_iso:
        try:
            exp_unix = int(
                datetime.fromisoformat(exp_iso.replace("Z", "+00:00")).timestamp()
            )
        except Exception:  # pragma: no cover — defensive
            pass
    return ttl, exp_unix


async def _alert_user_to_open_manually(strikes: int) -> None:
    label = f"{strikes}/{MAX_STRIKES}"
    text = (
        "🚨 *Не удалось обновить токен Avito автоматически*\n"
        f"Подряд неудач: *{label}*. Открой приложение Avito на телефоне "
        "вручную, чтобы оно обновило JWT."
    )
    try:
        await send_alert(text)
    except Exception:
        log.exception("token_refresh.alert_send_failed")


async def _tick(client: XapiClient) -> None:
    """One iteration of the loop. Idempotent + safe to crash-restart."""
    ttl, exp_unix = await _read_session_status(client)

    # If we're past a previous request's correlation window, evaluate it.
    last_request_at: datetime | None = _state["last_request_at"]
    if last_request_at is not None:
        elapsed = (datetime.now(timezone.utc) - last_request_at).total_seconds()
        if elapsed >= CORRELATION_DELAY_SEC:
            prev_exp: int | None = _state["last_request_prev_exp"]
            if prev_exp is not None and exp_unix is not None and exp_unix > prev_exp:
                log.info(
                    "token_refresh.correlated_success",
                    prev_exp=prev_exp,
                    new_exp=exp_unix,
                    strikes_was=_state["strikes"],
                )
                _state["strikes"] = 0
            else:
                _state["strikes"] += 1
                log.warning(
                    "token_refresh.correlated_failure",
                    strikes=_state["strikes"],
                    prev_exp=prev_exp,
                    new_exp=exp_unix,
                )
                if _state["strikes"] >= MAX_STRIKES:
                    await _alert_user_to_open_manually(_state["strikes"])
                    _state["strikes"] = 0  # reset after alerting
            _state["last_request_at"] = None
            _state["last_request_prev_exp"] = None

    # Check whether we're in the refresh window and not in cooldown.
    if ttl is None:
        return
    if ttl > REFRESH_WINDOW_UPPER_SEC:
        return

    # Cooldown — don't spam commands.
    if last_request_at is not None:
        elapsed = (datetime.now(timezone.utc) - last_request_at).total_seconds()
        if elapsed < COOLDOWN_AFTER_REQUEST_SEC:
            return

    log.info(
        "token_refresh.requesting",
        ttl_sec=ttl,
        exp_unix=exp_unix,
    )
    ok = await _post_refresh_command(client, prev_exp=exp_unix)
    if ok:
        _state["last_request_at"] = datetime.now(timezone.utc)
        _state["last_request_prev_exp"] = exp_unix


async def loop(settings: Settings | None = None) -> None:
    """Forever loop — call once and gather as a task."""
    s = settings or get_settings()
    client = XapiClient(base_url=s.avito_xapi_url, api_key=s.avito_xapi_api_key)
    log.info(
        "token_refresh.loop.start",
        poll_interval=POLL_INTERVAL_SEC,
        refresh_window_upper=REFRESH_WINDOW_UPPER_SEC,
        cooldown_sec=COOLDOWN_AFTER_REQUEST_SEC,
    )
    while True:
        try:
            if s.reliability_enabled:
                await _tick(client)
        except asyncio.CancelledError:
            raise
        except Exception:  # never crash the loop
            log.exception("token_refresh.tick_failed")
        await asyncio.sleep(POLL_INTERVAL_SEC)
