"""Unit tests for the kill-switch state machine."""
from __future__ import annotations

import pytest

from app.config import get_settings
from app.services.messenger_bot import kill_switch


@pytest.fixture(autouse=True)
def _reset_kill_switch():
    kill_switch.reset_for_tests()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    kill_switch.reset_for_tests()
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_kill_switch_defaults_to_env(monkeypatch):
    """No override → reads ``MESSENGER_BOT_ENABLED`` from settings."""
    monkeypatch.setenv("MESSENGER_BOT_ENABLED", "true")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    assert kill_switch.bot_enabled() is True


def test_kill_switch_pause_overrides_env(monkeypatch):
    monkeypatch.setenv("MESSENGER_BOT_ENABLED", "true")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    assert kill_switch.bot_enabled() is True
    new_state = kill_switch.pause()
    assert new_state is False
    assert kill_switch.bot_enabled() is False


def test_kill_switch_resume_overrides_env_off(monkeypatch):
    """Even if env says false, /resume turns the bot on."""
    monkeypatch.setenv("MESSENGER_BOT_ENABLED", "false")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    assert kill_switch.bot_enabled() is False
    new_state = kill_switch.resume()
    assert new_state is True
    assert kill_switch.bot_enabled() is True
