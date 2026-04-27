"""Messenger provider abstraction (Block 5).

Notifications are rendered once and dispatched through a pluggable
:class:`MessengerProvider`. ``TelegramProvider`` is the only real
implementation in V1; ``MaxProvider`` is a stub that raises so callers
fail loud the moment ``profile.notification_channels`` lists a channel
we don't support yet.

See ``app/prompts/messenger/*.md`` for templates and
``app/integrations/messenger/buttons.py`` for inline-button schemas.
"""
from app.integrations.messenger.base import (
    InlineButton,
    MessengerError,
    MessengerMessage,
    MessengerProvider,
)
from app.integrations.messenger.factory import get_provider

__all__ = [
    "InlineButton",
    "MessengerError",
    "MessengerMessage",
    "MessengerProvider",
    "get_provider",
]
