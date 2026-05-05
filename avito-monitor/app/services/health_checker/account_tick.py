"""Per-tick проверка состояний accounts pool. Запускается из существующего
health_checker scheduler'а каждые 30 секунд.

После Phase 4 (manual refresh model): NO proactive refresh triggers.
Only emits TG alerts on session stale (one-shot, idempotent)."""
import logging
from datetime import datetime, timezone

from app.services.account_pool import AccountPool

log = logging.getLogger(__name__)

# Module-level alert state. Idempotency: emit once per fresh→stale transition.
# Reset entry when account becomes fresh again.
# Special key 'pool_dead' tracks the both-stale critical alert.
_alerted_stale_accounts: set[str] = set()


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _is_session_stale(acc: dict, *, now: datetime) -> bool:
    exp = _parse_ts(acc.get("expires_at"))
    return exp is None or exp < now


async def account_tick_iteration(*, pool: AccountPool, now: datetime, tg) -> None:
    accounts = await pool.list_all_accounts()
    await _check_pool_health(accounts, now=now, tg=tg)


async def _check_pool_health(accounts: list[dict], *, now: datetime, tg) -> None:
    stale = [a for a in accounts if _is_session_stale(a, now=now)]
    fresh_ids = {a["id"] for a in accounts if not _is_session_stale(a, now=now)}

    # Per-account "one stale" alert (idempotent)
    for acc in stale:
        aid = acc["id"]
        if aid in _alerted_stale_accounts:
            continue
        nickname = acc.get("nickname") or aid[:8]
        user_id = acc.get("android_user_id", 0)
        other = "Clone" if nickname == "Main" or "Main" in nickname else "Main"
        await tg(
            f"📩 Аккаунт {nickname} протух (last refresh устарел). "
            f"Polling работает на {other}. Открой Avito-app в user_{user_id} "
            f"для восстановления safety net."
        )
        _alerted_stale_accounts.add(aid)

    # Reset alert state for accounts that became fresh again
    _alerted_stale_accounts.intersection_update(
        {x for x in _alerted_stale_accounts if x not in fresh_ids}
        | {"pool_dead"}  # preserve pool_dead key, handled separately below
    )
    for fid in fresh_ids:
        _alerted_stale_accounts.discard(fid)

    # Pool-wide critical alert: both stale
    if len(accounts) >= 2 and len(stale) == len(accounts):
        if "pool_dead" not in _alerted_stale_accounts:
            await tg(
                "🚨 Polling DOWN — все аккаунты протухли. "
                "Срочно открой Avito-app на phone'е (оба пользователя)."
            )
            _alerted_stale_accounts.add("pool_dead")
    else:
        _alerted_stale_accounts.discard("pool_dead")
