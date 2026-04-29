"""Per-tick проверка состояний accounts pool. Запускается из существующего
health_checker scheduler'а каждые 30 секунд."""
import logging
from datetime import datetime, timedelta, timezone

from app.services.account_pool import AccountPool

log = logging.getLogger(__name__)


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


async def account_tick_iteration(*, pool: AccountPool, now: datetime, tg) -> None:
    accounts = await pool.list_all_accounts()
    for acc in accounts:
        await _process_account(acc, pool=pool, now=now, tg=tg)


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
        if exp and (exp - now) < timedelta(minutes=3):
            try:
                await pool.trigger_refresh_cycle(aid)
                log.info("refresh-cycle triggered for %s (proactive)", aid)
            except Exception as e:
                log.warning("proactive refresh failed for %s: %s", aid, e)
        return
