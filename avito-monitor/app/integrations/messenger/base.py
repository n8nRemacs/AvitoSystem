"""Provider Protocol + value objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class MessengerError(Exception):
    """Raised by a provider when delivery fails permanently or transiently.

    ``transient=True`` tells the caller (``send_notification`` task) that
    a retry is worth it. The default is ``False`` — assume permanent and
    let the operator decide.
    """

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


@dataclass(frozen=True)
class InlineButton:
    """One inline-keyboard button.

    ``url`` and ``callback_data`` are mutually exclusive on Telegram —
    we model that with two factory helpers below so callers can't
    construct a malformed button by accident.
    """

    text: str
    callback_data: str | None = None
    url: str | None = None

    @classmethod
    def link(cls, text: str, url: str) -> "InlineButton":
        return cls(text=text, url=url)

    @classmethod
    def callback(cls, text: str, data: str) -> "InlineButton":
        return cls(text=text, callback_data=data)


@dataclass(frozen=True)
class MessengerMessage:
    """Provider-agnostic outbound message.

    ``text`` is Markdown (Telegram Markdown V1 — same flavour the
    health-checker alerts already use). ``buttons`` is a list of rows;
    each row is a list of buttons rendered side-by-side.
    """

    chat_id: str
    text: str
    buttons: list[list[InlineButton]] = field(default_factory=list)
    disable_preview: bool = True


@runtime_checkable
class MessengerProvider(Protocol):
    """Anything that can deliver a :class:`MessengerMessage`.

    Implementations must:

    * Return ``provider_message_id`` on success — Telegram exposes
      ``message_id`` we may want to edit later (e.g. removing buttons
      after the user clicks "Просмотрено").
    * Raise :class:`MessengerError(transient=True)` on retry-worthy
      failures (timeouts, 5xx, rate-limits). Anything else raises with
      ``transient=False``.
    """

    channel: str  # e.g. "telegram", "max"

    async def send(self, message: MessengerMessage) -> str: ...
