"""Pure state-machine логика avito_accounts. No DB, no IO."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal


StateName = Literal["active", "cooldown", "needs_refresh", "waiting_refresh", "dead"]


@dataclass
class AccountState:
    state: StateName
    consecutive_cooldowns: int = 0
    cooldown_until: datetime | None = None
    waiting_since: datetime | None = None
    expires_at: datetime | None = None


@dataclass
class Event:
    kind: Literal["report", "tick", "session_arrived"]
    status_code: int | None = None


def cooldown_duration_for(consecutive: int) -> timedelta:
    """Ratchet: 20m → 40m → 80m → 160m → 24h+."""
    if consecutive >= 5:
        return timedelta(hours=24)
    return timedelta(minutes=20 * (2 ** (consecutive - 1))) if consecutive > 0 else timedelta(minutes=20)


def compute_next_state(curr: AccountState, event: Event, *, now: datetime) -> AccountState:
    if event.kind == "report":
        sc = event.status_code or 0
        if sc == 200:
            return replace(curr, state="active", consecutive_cooldowns=0)
        if sc == 403:
            new_consec = curr.consecutive_cooldowns + 1
            return replace(
                curr,
                state="cooldown",
                consecutive_cooldowns=new_consec,
                cooldown_until=now + cooldown_duration_for(new_consec),
            )
        if sc == 401:
            return replace(curr, expires_at=now)
        return curr  # 5xx / network — no-op

    if event.kind == "tick":
        if curr.state == "cooldown" and curr.cooldown_until and curr.cooldown_until < now:
            return replace(curr, state="needs_refresh")
        if curr.state == "waiting_refresh" and curr.waiting_since \
                and (now - curr.waiting_since) > timedelta(minutes=5):
            return replace(curr, state="dead")
        return curr

    if event.kind == "session_arrived":
        return replace(curr, state="active", waiting_since=None)

    return curr
