"""Whitelist middleware — drops every update from a non-allowed user.

``TELEGRAM_ALLOWED_USER_IDS`` is a CSV in the env. We parse once on
build and keep a frozenset for O(1) checks. An empty/missing list
means "deny everything" — the safer default for a personal bot. If
the user wants the bot open to anyone, they can set ``*`` (handled
explicitly).
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

log = logging.getLogger(__name__)


def parse_allowed_ids(raw: str) -> tuple[frozenset[int], bool]:
    """Return (ids, allow_all). ``"*"`` → allow_all=True, ids ignored."""
    raw = (raw or "").strip()
    if raw == "*":
        return frozenset(), True
    if not raw:
        return frozenset(), False
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            log.warning("whitelist.bad_id value=%r", part)
    return frozenset(ids), False


class WhitelistMiddleware(BaseMiddleware):
    def __init__(self, allowed_ids: frozenset[int], *, allow_all: bool = False) -> None:
        self._allowed = allowed_ids
        self._allow_all = allow_all

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = self._extract_user_id(event)
        if user_id is None:
            return await handler(event, data)

        if self._allow_all or user_id in self._allowed:
            return await handler(event, data)

        log.info("whitelist.denied user_id=%s", user_id)
        # Tell the user once so a typo on the env side is debuggable.
        try:
            if isinstance(event, Message):
                await event.answer("Доступ запрещён.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Доступ запрещён.", show_alert=True)
        except Exception:
            log.exception("whitelist.deny_reply_failed user_id=%s", user_id)
        return None

    @staticmethod
    def _extract_user_id(event: TelegramObject) -> int | None:
        if isinstance(event, Message) and event.from_user:
            return event.from_user.id
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user.id
        return None
