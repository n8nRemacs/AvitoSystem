"""Tests for pure state-machine logic of avito_accounts."""
from datetime import datetime, timedelta, timezone
import pytest

from src.services.account_state import (
    compute_next_state,
    cooldown_duration_for,
    AccountState,
    Event,
)


NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)


def state(**kwargs):
    base = AccountState(
        state="active",
        consecutive_cooldowns=0,
        cooldown_until=None,
        waiting_since=None,
    )
    for k, v in kwargs.items():
        setattr(base, k, v)
    return base


def test_200_resets_counters():
    s = state(state="active", consecutive_cooldowns=2)
    next_s = compute_next_state(s, Event(kind="report", status_code=200), now=NOW)
    assert next_s.state == "active"
    assert next_s.consecutive_cooldowns == 0


def test_403_first_time_starts_5min_cooldown():
    s = state(state="active", consecutive_cooldowns=0)
    next_s = compute_next_state(s, Event(kind="report", status_code=403), now=NOW)
    assert next_s.state == "cooldown"
    # New ladder: first 403 → 5m (was 20m). See incident note in account_state.py.
    assert next_s.cooldown_until == NOW + timedelta(minutes=5)
    assert next_s.consecutive_cooldowns == 1


def test_403_ratchet_climbs_then_caps_at_60m():
    # New bounded ladder: 5 → 10 → 20 → 40 → 60 (cap forever after).
    durations = [5, 10, 20, 40, 60, 60, 60]
    s = state(state="active", consecutive_cooldowns=0)
    for expected_minutes in durations:
        next_s = compute_next_state(s, Event(kind="report", status_code=403), now=NOW)
        assert next_s.cooldown_until == NOW + timedelta(minutes=expected_minutes), \
            f"Expected {expected_minutes}m at consecutive={s.consecutive_cooldowns}"
        s = next_s


def test_401_marks_for_immediate_refresh_no_cooldown():
    s = state(state="active", consecutive_cooldowns=0)
    next_s = compute_next_state(s, Event(kind="report", status_code=401), now=NOW)
    assert next_s.state == "active"
    assert next_s.consecutive_cooldowns == 0
    assert next_s.expires_at == NOW  # форсирует health_checker подобрать


def test_5xx_no_state_change():
    s = state(state="active", consecutive_cooldowns=1)
    next_s = compute_next_state(s, Event(kind="report", status_code=503), now=NOW)
    assert next_s.state == "active"
    assert next_s.consecutive_cooldowns == 1


def test_cooldown_expired_transitions_to_needs_refresh():
    s = state(state="cooldown", cooldown_until=NOW - timedelta(seconds=1))
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.state == "needs_refresh"


def test_cooldown_not_yet_expired_stays_cooldown():
    s = state(state="cooldown", cooldown_until=NOW + timedelta(minutes=10))
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.state == "cooldown"


def test_waiting_refresh_timeout_marks_dead():
    s = state(state="waiting_refresh", waiting_since=NOW - timedelta(minutes=5, seconds=1))
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.state == "dead"


def test_waiting_refresh_within_window_stays():
    s = state(state="waiting_refresh", waiting_since=NOW - timedelta(minutes=4))
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.state == "waiting_refresh"


def test_session_arrived_clears_waiting():
    s = state(state="waiting_refresh", waiting_since=NOW - timedelta(minutes=2))
    next_s = compute_next_state(s, Event(kind="session_arrived"), now=NOW)
    assert next_s.state == "active"
    assert next_s.waiting_since is None


# --- New ladder coverage ----------------------------------------------------

def test_cooldown_ladder_values():
    assert cooldown_duration_for(0) == timedelta(minutes=5)
    assert cooldown_duration_for(1) == timedelta(minutes=10)
    assert cooldown_duration_for(2) == timedelta(minutes=20)
    assert cooldown_duration_for(3) == timedelta(minutes=40)
    assert cooldown_duration_for(4) == timedelta(minutes=60)


def test_cooldown_ladder_hard_cap_at_60m():
    # Hard cap: anything >= 4 returns 60m. Was 24h at >=5, that's the bug.
    for n in (4, 5, 6, 8, 10, 100):
        assert cooldown_duration_for(n) == timedelta(minutes=60), \
            f"consecutive={n} should cap at 60m, not blow up"


# --- 429 handling -----------------------------------------------------------

def test_429_first_time_triggers_5min_cooldown_same_as_403():
    s = state(state="active", consecutive_cooldowns=0)
    next_s = compute_next_state(s, Event(kind="report", status_code=429), now=NOW)
    assert next_s.state == "cooldown"
    assert next_s.cooldown_until == NOW + timedelta(minutes=5)
    assert next_s.consecutive_cooldowns == 1


def test_429_uses_same_bounded_ladder():
    # 429 must never escalate past 60m — it's rate-limit, not ban.
    s = state(state="active", consecutive_cooldowns=0)
    durations = [5, 10, 20, 40, 60, 60]
    for expected in durations:
        next_s = compute_next_state(s, Event(kind="report", status_code=429), now=NOW)
        assert next_s.cooldown_until == NOW + timedelta(minutes=expected)
        s = next_s


def test_429_and_403_share_ladder():
    # Mixed sequence — counter must keep climbing regardless of 403 vs 429.
    s = state(state="active", consecutive_cooldowns=0)
    s = compute_next_state(s, Event(kind="report", status_code=403), now=NOW)
    assert s.consecutive_cooldowns == 1
    s = compute_next_state(s, Event(kind="report", status_code=429), now=NOW)
    assert s.consecutive_cooldowns == 2
    # Second event uses ladder index 1 (count BEFORE increment) → 10m.
    assert s.cooldown_until == NOW + timedelta(minutes=10)


# --- Decay via tick ---------------------------------------------------------

def test_tick_decays_consecutive_after_30m_quiet():
    last = NOW - timedelta(minutes=30)
    s = state(state="active", consecutive_cooldowns=3, last_event_at=last)
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.consecutive_cooldowns == 2
    # last_event_at should advance so we don't re-decay on the next immediate tick
    assert next_s.last_event_at == NOW


def test_tick_no_decay_before_30m():
    last = NOW - timedelta(minutes=29)
    s = state(state="active", consecutive_cooldowns=3, last_event_at=last)
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.consecutive_cooldowns == 3


def test_tick_decay_floors_at_zero():
    # Decay logic shouldn't run when already at 0 (guarded).
    last = NOW - timedelta(hours=2)
    s = state(state="active", consecutive_cooldowns=0, last_event_at=last)
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.consecutive_cooldowns == 0


def test_tick_decay_only_when_active():
    # In cooldown, tick should not decay — it should evaluate cooldown_until instead.
    last = NOW - timedelta(hours=2)
    s = state(
        state="cooldown",
        consecutive_cooldowns=3,
        cooldown_until=NOW + timedelta(minutes=5),
        last_event_at=last,
    )
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.state == "cooldown"
    assert next_s.consecutive_cooldowns == 3


def test_tick_decay_skipped_when_no_last_event_at():
    # Backwards-compat: existing rows without last_event_at must not decay.
    s = state(state="active", consecutive_cooldowns=3, last_event_at=None)
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.consecutive_cooldowns == 3


def test_repeated_ticks_decay_one_step_per_30m():
    # Simulate the originally broken account: consec=8 → recover to 0 over time.
    s = state(
        state="active",
        consecutive_cooldowns=8,
        last_event_at=NOW - timedelta(minutes=30),
    )
    t = NOW
    for expected in [7, 6, 5, 4, 3, 2, 1, 0]:
        s = compute_next_state(s, Event(kind="tick"), now=t)
        assert s.consecutive_cooldowns == expected
        t = t + timedelta(minutes=30)
