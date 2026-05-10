"""Tests for the polling humanization helpers in app.tasks.polling.

We don't exercise ``poll_profile`` end-to-end here — that requires a DB and
a mocked account pool (covered by integration smoke tests). Instead we
pin down the pure decision helpers: active-hours guard and the
once-per-hour full-paginate gate.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.tasks.polling import (
    FULL_POLL_INTERVAL,
    _should_full_paginate,
    is_within_active_hours,
)


def _settings(
    *,
    respect: bool = True,
    start: int = 8,
    end: int = 23,
    tz: str = "Europe/Moscow",
):
    """Minimal duck-typed Settings for the helper under test."""
    return SimpleNamespace(
        poll_respect_active_hours=respect,
        poll_active_hours_start=start,
        poll_active_hours_end=end,
        poll_active_hours_timezone=tz,
    )


def _msk(year, month, day, hour, minute=0) -> datetime:
    """Build a UTC-aware datetime that corresponds to the given MSK wall time."""
    return datetime(
        year, month, day, hour, minute, tzinfo=ZoneInfo("Europe/Moscow")
    ).astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# is_within_active_hours
# ---------------------------------------------------------------------------

def test_active_hours_inside_window_msk():
    # 14:00 MSK is well inside the default 8..23 window.
    now = _msk(2026, 5, 10, 14, 0)
    assert is_within_active_hours(now, _settings()) is True


def test_active_hours_at_start_boundary_is_inclusive():
    # Window is half-open [8, 23) — 8:00 must be allowed.
    now = _msk(2026, 5, 10, 8, 0)
    assert is_within_active_hours(now, _settings()) is True


def test_active_hours_at_end_boundary_is_exclusive():
    # 23:00 MSK is the upper bound and must be excluded.
    now = _msk(2026, 5, 10, 23, 0)
    assert is_within_active_hours(now, _settings()) is False


def test_active_hours_overnight_skips():
    # 03:30 MSK — squarely "asleep".
    now = _msk(2026, 5, 10, 3, 30)
    assert is_within_active_hours(now, _settings()) is False


def test_active_hours_override_disables_guard():
    # When the env override is off, even 03:00 MSK passes through.
    now = _msk(2026, 5, 10, 3, 0)
    assert is_within_active_hours(now, _settings(respect=False)) is True


def test_active_hours_uses_configured_tz():
    # 22:00 UTC == 01:00 MSK → outside default window.
    now = datetime(2026, 5, 10, 22, 0, tzinfo=timezone.utc)
    assert is_within_active_hours(now, _settings()) is False


# ---------------------------------------------------------------------------
# _should_full_paginate
# ---------------------------------------------------------------------------

def test_full_paginate_when_never_run():
    profile = SimpleNamespace(last_full_poll_at=None)
    now = datetime.now(timezone.utc)
    assert _should_full_paginate(profile, now) is True


def test_no_full_paginate_when_recent():
    now = datetime.now(timezone.utc)
    profile = SimpleNamespace(
        last_full_poll_at=now - timedelta(minutes=15),
    )
    assert _should_full_paginate(profile, now) is False


def test_full_paginate_when_past_interval():
    now = datetime.now(timezone.utc)
    profile = SimpleNamespace(
        last_full_poll_at=now - FULL_POLL_INTERVAL - timedelta(seconds=1),
    )
    assert _should_full_paginate(profile, now) is True


def test_full_paginate_handles_naive_timestamp():
    # Older rows may have been written with a naive datetime; the helper
    # must not blow up with "can't compare offset-naive and offset-aware".
    now = datetime.now(timezone.utc)
    naive_recent = (now - timedelta(minutes=5)).replace(tzinfo=None)
    profile = SimpleNamespace(last_full_poll_at=naive_recent)
    assert _should_full_paginate(profile, now) is False
