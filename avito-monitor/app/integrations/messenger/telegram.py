"""Telegram provider built on aiogram 3.

We deliberately keep the provider thin: it owns just enough of the bot
to call ``send_message``. The long-polling daemon that handles incoming
commands lives in ``app/integrations/telegram/bot.py`` and shares
nothing with this module beyond the bot token from settings.

Callback data scheme: see ``app/integrations/messenger/buttons.py`` —
the bot's callback handler unpacks the same scheme.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions


def _no_preview() -> LinkPreviewOptions:
    return LinkPreviewOptions(is_disabled=True)

from app.integrations.messenger.base import (
    InlineButton,
    MessengerError,
    MessengerMessage,
    MessengerProvider,
)

log = logging.getLogger(__name__)


def _to_keyboard(rows: list[list[InlineButton]]) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    keyboard = []
    for row in rows:
        kb_row = []
        for btn in row:
            if btn.url:
                kb_row.append(InlineKeyboardButton(text=btn.text, url=btn.url))
            else:
                kb_row.append(
                    InlineKeyboardButton(
                        text=btn.text, callback_data=btn.callback_data or ""
                    )
                )
        if kb_row:
            keyboard.append(kb_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None


class TelegramProvider(MessengerProvider):
    """Aiogram-backed Telegram delivery.

    Construct with an explicit token or let ``from_settings`` pull from
    config. The bot instance is cheap to keep alive; we share a single
    one across the worker process.
    """

    channel = "telegram"

    def __init__(self, *, bot: Bot) -> None:
        self._bot = bot

    @classmethod
    def from_token(
        cls, token: str, *, proxy_url: str | None = None
    ) -> "TelegramProvider":
        session = None
        if proxy_url:
            try:
                session = AiohttpSession(proxy=proxy_url)
            except RuntimeError as exc:
                # aiogram raises when aiohttp_socks is missing. We log
                # and fall back to a direct connection — better to fail
                # at send time than restart-loop the whole service.
                log.warning(
                    "telegram.proxy_unavailable url=%s err=%s — falling back to direct",
                    proxy_url, exc,
                )
        bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode="Markdown"),
            session=session,
        )
        return cls(bot=bot)

    async def send(self, message: MessengerMessage) -> str:
        keyboard = _to_keyboard(message.buttons)
        try:
            sent = await self._bot.send_message(
                chat_id=message.chat_id,
                text=message.text,
                reply_markup=keyboard,
                link_preview_options=_no_preview() if message.disable_preview else None,
            )
        except TelegramRetryAfter as exc:
            raise MessengerError(
                f"telegram rate-limit, retry_after={exc.retry_after}s",
                transient=True,
            ) from exc
        except (TelegramNetworkError, TelegramServerError) as exc:
            raise MessengerError(
                f"telegram transport: {type(exc).__name__}: {exc}",
                transient=True,
            ) from exc
        except TelegramAPIError as exc:
            # 4xx (bad token, blocked by user, ...) — permanent.
            raise MessengerError(
                f"telegram api: {type(exc).__name__}: {exc}",
                transient=False,
            ) from exc
        return str(sent.message_id)

    async def close(self) -> None:
        await self._bot.session.close()
