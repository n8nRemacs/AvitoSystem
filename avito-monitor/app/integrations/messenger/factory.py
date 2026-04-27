"""Resolve a :class:`MessengerProvider` by channel name."""
from __future__ import annotations

import threading

from app.config import Settings, get_settings
from app.integrations.messenger.base import MessengerError, MessengerProvider
from app.integrations.messenger.max_stub import MaxProvider
from app.integrations.messenger.telegram import TelegramProvider

_lock = threading.Lock()
_telegram: TelegramProvider | None = None


def _telegram_provider(settings: Settings) -> TelegramProvider:
    """Return the process-wide TelegramProvider, building it on first call."""
    global _telegram
    if _telegram is None:
        with _lock:
            if _telegram is None:
                token = (settings.telegram_bot_token or "").strip()
                if not token:
                    raise MessengerError(
                        "TELEGRAM_BOT_TOKEN is empty — cannot build "
                        "TelegramProvider",
                        transient=False,
                    )
                _telegram = TelegramProvider.from_token(token)
    return _telegram


def get_provider(
    channel: str, *, settings: Settings | None = None
) -> MessengerProvider:
    """Return the provider for ``channel``. Raises ``MessengerError`` for unknown."""
    s = settings or get_settings()
    name = (channel or "").lower().strip()
    if name == "telegram":
        return _telegram_provider(s)
    if name == "max":
        return MaxProvider()
    raise MessengerError(
        f"Unknown messenger channel: {channel!r}", transient=False
    )


async def reset_providers() -> None:
    """Test/teardown hook — close the cached Telegram bot session."""
    global _telegram
    with _lock:
        if _telegram is not None:
            await _telegram.close()
            _telegram = None
