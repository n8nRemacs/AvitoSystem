"""Kill-switch state for the messenger-bot.

Two layers:

1. ``MESSENGER_BOT_ENABLED`` env var — read at startup via
   :func:`app.config.get_settings`.
2. Runtime override toggled by the ``/pause`` and ``/resume`` HTTP endpoints.
   This override lives only in-process: a container restart resets to the env
   value. Persisting to the ``system_settings`` table is intentionally
   deferred — see TZ §6 (kill-switch is "best-effort runtime", not durable).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings


@dataclass
class KillSwitchState:
    """In-process kill-switch state.

    ``override`` of ``None`` means "fall through to env var"; ``True`` /
    ``False`` are explicit operator pause/resume actions.
    """

    override: bool | None = None

    def is_enabled(self) -> bool:
        if self.override is not None:
            return self.override
        return bool(get_settings().messenger_bot_enabled)

    def pause(self) -> bool:
        self.override = False
        return self.is_enabled()

    def resume(self) -> bool:
        self.override = True
        return self.is_enabled()


# Module-level singleton; the API endpoints + handler share this instance.
_state = KillSwitchState()


def bot_enabled() -> bool:
    return _state.is_enabled()


def pause() -> bool:
    return _state.pause()


def resume() -> bool:
    return _state.resume()


def reset_for_tests() -> None:
    """Reset override to None — used by unit tests, not in prod paths."""
    _state.override = None
