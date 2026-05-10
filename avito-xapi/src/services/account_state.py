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
    # last_event_at — used by tick() to decay consecutive_cooldowns when an
    # account has been quiet ≥30m. Optional; if None, decay is skipped.
    last_event_at: datetime | None = None


@dataclass
class Event:
    kind: Literal["report", "tick", "session_arrived"]
    status_code: int | None = None


# Hard cap: cooldown never exceeds 60 minutes. Was 24h at consec≥5; that
# parked accounts so long the pool drained (incident 2026-05-08, account
# auto-431483569). New ladder is bounded so a bad burst can't permanently
# remove an account from rotation.
_COOLDOWN_LADDER_MINUTES = {
    0: 5,
    1: 10,
    2: 20,
    3: 40,
}
_COOLDOWN_CAP_MINUTES = 60


def cooldown_duration_for(consecutive: int) -> timedelta:
    """Bounded ladder: 5m → 10m → 20m → 40m → 60m (hard cap)."""
    minutes = _COOLDOWN_LADDER_MINUTES.get(consecutive, _COOLDOWN_CAP_MINUTES)
    return timedelta(minutes=minutes)


def compute_next_state(curr: AccountState, event: Event, *, now: datetime) -> AccountState:
    if event.kind == "report":
        sc = event.status_code or 0
        if sc == 200:
            return replace(curr, state="active", consecutive_cooldowns=0, last_event_at=now)
        # 403 = soft-ban / device-fingerprint friction; 429 = rate-limit.
        # Both routed through same bounded ladder. 429 must NEVER escalate
        # past the 60m cap — it's a transient signal to back off, not a ban.
        if sc in (403, 429):
            # Ladder is keyed on the count BEFORE this event:
            # 0 prior cooldowns → 5m, 1 → 10m, 2 → 20m, 3 → 40m, 4+ → 60m cap.
            duration = cooldown_duration_for(curr.consecutive_cooldowns)
            return replace(
                curr,
                state="cooldown",
                consecutive_cooldowns=curr.consecutive_cooldowns + 1,
                cooldown_until=now + duration,
                last_event_at=now,
            )
        if sc == 401:
            return replace(curr, expires_at=now, last_event_at=now)
        return curr  # 5xx / network — no-op

    if event.kind == "tick":
        if curr.state == "cooldown" and curr.cooldown_until and curr.cooldown_until < now:
            return replace(curr, state="needs_refresh")
        if curr.state == "waiting_refresh" and curr.waiting_since \
                and (now - curr.waiting_since) > timedelta(minutes=5):
            return replace(curr, state="dead")
        # Decay: when active and quiet for ≥30m, drop one cooldown step so a
        # past bad burst doesn't permanently bias future cooldown durations.
        if (
            curr.state == "active"
            and curr.consecutive_cooldowns > 0
            and curr.last_event_at is not None
            and (now - curr.last_event_at) >= timedelta(minutes=30)
        ):
            return replace(
                curr,
                consecutive_cooldowns=curr.consecutive_cooldowns - 1,
                last_event_at=now,
            )
        return curr

    if event.kind == "session_arrived":
        return replace(curr, state="active", waiting_since=None, last_event_at=now)

    return curr
