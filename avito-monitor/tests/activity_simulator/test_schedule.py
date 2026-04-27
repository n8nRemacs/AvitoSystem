"""Unit tests for the activity-simulator schedule helpers."""
from __future__ import annotations

import random
from collections import Counter
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.services.activity_simulator.schedule import (
    ACTION_WEIGHTS,
    actions_per_hour,
    expected_gap_seconds,
    is_work_hour,
    next_gap_seconds,
    pick_action_name,
)


def _msk(hour: int, minute: int = 0) -> datetime:
    """Build a UTC datetime that lands on ``hour:minute`` Europe/Moscow."""
    msk = ZoneInfo("Europe/Moscow")
    base = datetime(2026, 4, 26, hour, minute, tzinfo=msk)
    return base.astimezone(UTC)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_secret_key="test-secret-key-must-be-at-least-32-chars-long-xxxx",  # noqa: S106 — test fixture
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        activity_sim_enabled=True,
        activity_sim_timezone="Europe/Moscow",
        activity_sim_workhours_start=10,
        activity_sim_workhours_end=22,
        activity_sim_actions_per_hour_work=10,
        activity_sim_actions_per_hour_off=2,
    )


# ----------------------------------------------------------------------
# is_work_hour / actions_per_hour
# ----------------------------------------------------------------------

def test_is_work_hour_at_14_msk(settings: Settings) -> None:
    assert is_work_hour(_msk(14), settings) is True


def test_is_work_hour_at_3_msk(settings: Settings) -> None:
    assert is_work_hour(_msk(3), settings) is False


def test_is_work_hour_boundary(settings: Settings) -> None:
    """Window is half-open [start, end): 22:00 is OFF, 10:00 is WORK."""
    assert is_work_hour(_msk(10), settings) is True
    assert is_work_hour(_msk(22), settings) is False
    assert is_work_hour(_msk(21, 59), settings) is True


def test_actions_per_hour_picks_correct_rate(settings: Settings) -> None:
    assert actions_per_hour(_msk(14), settings) == 10
    assert actions_per_hour(_msk(3), settings) == 2


# ----------------------------------------------------------------------
# next_gap_seconds — rate + jitter
# ----------------------------------------------------------------------

def test_next_gap_seconds_work_hour_range(settings: Settings) -> None:
    """At 10/h the expected gap is 360s; with ±50% jitter the bounds are
    [180, 540]. Sample many to confirm the distribution stays in-range."""
    rng = random.Random(42)  # noqa: S311 — deterministic test seed
    samples = [next_gap_seconds(_msk(14), settings, rng=rng) for _ in range(500)]
    assert all(180.0 <= s <= 540.0 for s in samples), (min(samples), max(samples))
    # Mean should sit close to 360s; allow generous slack.
    avg = sum(samples) / len(samples)
    assert 320.0 <= avg <= 400.0, avg


def test_next_gap_seconds_off_hour_range(settings: Settings) -> None:
    """At 2/h the expected gap is 1800s; ±50% jitter => [900, 2700]."""
    rng = random.Random(7)  # noqa: S311 — deterministic test seed
    samples = [next_gap_seconds(_msk(3), settings, rng=rng) for _ in range(500)]
    assert all(900.0 <= s <= 2700.0 for s in samples), (min(samples), max(samples))


def test_next_gap_seconds_zero_rate_returns_finite(settings: Settings) -> None:
    settings.activity_sim_actions_per_hour_work = 0
    settings.activity_sim_actions_per_hour_off = 0
    gap = next_gap_seconds(_msk(14), settings)
    assert gap == 60.0


def test_expected_gap_seconds_basic() -> None:
    assert expected_gap_seconds(10) == 360.0
    assert expected_gap_seconds(2) == 1800.0
    assert expected_gap_seconds(0) == float("inf")


# ----------------------------------------------------------------------
# pick_action_name — weighted distribution
# ----------------------------------------------------------------------

def test_pick_action_name_distribution_roughly_60_20_10_10() -> None:
    """1000 picks with a fixed seed: each weight should land within ±5%."""
    rng = random.Random(123)  # noqa: S311 — deterministic test seed
    counts: Counter[str] = Counter(pick_action_name(rng) for _ in range(1000))
    # Every action should have appeared at least once.
    assert set(counts.keys()) == set(ACTION_WEIGHTS.keys())
    expected = {name: w / 100.0 for name, w in ACTION_WEIGHTS.items()}
    for name, exp in expected.items():
        actual = counts[name] / 1000.0
        assert abs(actual - exp) < 0.05, (name, exp, actual)


def test_pick_action_name_returns_known_name() -> None:
    name = pick_action_name(random.Random(0))  # noqa: S311 — deterministic test seed
    assert name in ACTION_WEIGHTS
