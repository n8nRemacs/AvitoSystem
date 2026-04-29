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


def test_403_first_time_starts_20min_cooldown():
    s = state(state="active", consecutive_cooldowns=0)
    next_s = compute_next_state(s, Event(kind="report", status_code=403), now=NOW)
    assert next_s.state == "cooldown"
    assert next_s.cooldown_until == NOW + timedelta(minutes=20)
    assert next_s.consecutive_cooldowns == 1


def test_403_ratchet_doubles_each_time():
    durations = [20, 40, 80, 160, 24 * 60]
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


def test_consecutive_5_cooldowns_24h():
    assert cooldown_duration_for(5) == timedelta(hours=24)
    assert cooldown_duration_for(6) == timedelta(hours=24)


def test_consecutive_4_cooldowns_160m():
    assert cooldown_duration_for(4) == timedelta(minutes=160)
