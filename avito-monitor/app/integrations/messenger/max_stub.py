"""Stub Max-messenger provider — raises until we wire it up in V2."""
from __future__ import annotations

from app.integrations.messenger.base import (
    MessengerError,
    MessengerMessage,
    MessengerProvider,
)


class MaxProvider(MessengerProvider):
    """V2 placeholder. The factory still returns it so the rest of the
    pipeline can be tested with ``profile.notification_channels=['max']``
    — the per-notification dispatch then fails loudly instead of
    silently dropping the message."""

    channel = "max"

    async def send(self, message: MessengerMessage) -> str:  # pragma: no cover
        raise MessengerError(
            "Max messenger provider is not implemented yet (V2 feature). "
            "Switch the profile's notification_channels back to ['telegram'] "
            "or wait for the V2 Max integration.",
            transient=False,
        )
