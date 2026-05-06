"""Per-tick проверка состояний accounts pool. Запускается из существующего
health_checker scheduler'а каждые 30 секунд.

После Phase 4 (manual refresh model): NO proactive refresh triggers.
Two responsibilities: (1) auto-recover expired cooldowns back to active or
needs_refresh; (2) emit one-shot TG alerts on session stale (idempotent)."""
import logging
from datetime import datetime, timedelta, timezone

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


def _is_session_fresh(acc: dict, *, now: datetime) -> bool:
    """True iff session has expires_at > now+5min.

    The 5-minute margin must match the xapi liveness predicate at
    avito-xapi/src/routers/accounts.py poll_claim — otherwise an account
    recovered to 'active' here could still be rejected by xapi as stale,
    causing recover→reject thrash on every tick.
    """
    exp = _parse_ts(acc.get("expires_at"))
    return exp is not None and exp > now + timedelta(minutes=5)


async def _recover_expired_cooldowns(accounts: list[dict], *, pool, now: datetime) -> None:
    """Auto-rebloom: cooldown with cooldown_until in past gets nudged forward.

    - Fresh session → 'active' (account is usable again).
    - Stale session → 'needs_refresh' (session must be refreshed before active).
    Other states are not touched.
    """
    for acc in accounts:
        if acc.get("state") != "cooldown":
            continue
        cd_until = _parse_ts(acc.get("cooldown_until"))
        if cd_until is None or cd_until >= now:
            continue
        next_state = "active" if _is_session_fresh(acc, now=now) else "needs_refresh"
        await pool.patch_state(
            acc["id"],
            next_state,
            reason=f"cooldown expired at {cd_until.isoformat()}, session "
                   f"{'fresh' if next_state == 'active' else 'stale'}",
        )
        log.info(
            "account_tick.recovered id=%s nickname=%s -> %s",
            acc["id"], acc.get("nickname"), next_state,
        )


async def account_tick_iteration(*, pool: AccountPool, now: datetime, tg) -> None:
    accounts = await pool.list_all_accounts()
    await _recover_expired_cooldowns(accounts, pool=pool, now=now)
    # Re-fetch — recovery may have flipped some states; alerts must see latest.
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
