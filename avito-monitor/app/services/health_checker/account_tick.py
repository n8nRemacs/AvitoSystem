"""Per-tick проверка состояний accounts pool. Запускается из существующего
health_checker scheduler'а каждые 30 секунд."""
import logging
from datetime import datetime, timedelta, timezone

from app.services.account_pool import AccountPool

log = logging.getLogger(__name__)

# Module-level set: tracks accounts that have been alerted for consecutive_cooldowns >= 5.
# Reset when consecutive_cooldowns drops to 0.
_alerted_24h: set[str] = set()


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


async def account_tick_iteration(*, pool: AccountPool, now: datetime, tg) -> None:
    accounts = await pool.list_all_accounts()
    for acc in accounts:
        await _process_account(acc, pool=pool, now=now, tg=tg)
        await _maybe_emit_consecutive_alert(acc, tg=tg)


async def _process_account(acc: dict, *, pool: AccountPool, now: datetime, tg) -> None:
    state = acc.get("state")
    aid = acc["id"]

    if state == "cooldown":
        until = _parse_ts(acc.get("cooldown_until"))
        if until and until < now:
            try:
                await pool.trigger_refresh_cycle(aid)
                log.info("refresh-cycle triggered for %s (post-cooldown)", aid)
            except Exception as e:
                log.warning("refresh-cycle failed for %s: %s", aid, e)
        return

    if state == "waiting_refresh":
        since = _parse_ts(acc.get("waiting_since"))
        if since and (now - since) > timedelta(minutes=5):
            await pool.patch_state(aid, "dead", reason="waiting_refresh timeout 5m")
            await tg(
                f"⚠️ Account {acc.get('nickname')} (Android-user "
                f"{acc.get('android_user_id')}) не получил refresh за 5 минут. "
                f"Открой вручную или проверь APK."
            )
        return

    if state == "active":
        exp = _parse_ts(acc.get("expires_at"))
        # Trigger refresh when:
        #   1. expires_at is missing (no active session — pool can't poll anyway)
        #   2. expires_at < now + 30min (proactive — give Avito-app time to refresh
        #      while IP is still clean and the JWT hasn't fully expired)
        if exp is None or (exp - now) < timedelta(minutes=30):
            try:
                await pool.trigger_refresh_cycle(aid)
                log.info("refresh-cycle triggered for %s (proactive, exp=%s)", aid, exp)
            except Exception as e:
                log.warning("proactive refresh failed for %s: %s", aid, e)
        return


async def _maybe_emit_consecutive_alert(acc: dict, *, tg) -> None:
    """Idempotent TG-alert: fires once when consecutive_cooldowns >= 5,
    resets when account recovers (consecutive=0)."""
    aid = acc["id"]
    consec = acc.get("consecutive_cooldowns") or 0

    if consec >= 5 and aid not in _alerted_24h:
        # Alert fires once
        await tg(
            f"🚨 Account {acc.get('nickname')} лежит в 24h cooldown "
            f"(consecutive={consec}). Проверь вручную."
        )
        _alerted_24h.add(aid)
        return

    if consec == 0 and aid in _alerted_24h:
        # Reset alert state on recovery
        _alerted_24h.discard(aid)
