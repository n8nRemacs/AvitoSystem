"""Long-polling Telegram bot — entry point for the ``telegram-bot`` service.

Wires up ``aiogram.Bot`` + ``Dispatcher`` with the whitelist middleware
and the slash-command + callback routers. Started via
``python -m app.integrations.telegram``.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.config import get_settings
from app.integrations.telegram.callbacks import router as callback_router
from app.integrations.telegram.commands import router as command_router
from app.integrations.telegram.middleware import (
    WhitelistMiddleware,
    parse_allowed_ids,
)

log = logging.getLogger(__name__)


def build_bot(token: str) -> Bot:
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode="Markdown"),
    )


def build_dispatcher(allowed_raw: str) -> Dispatcher:
    allowed, allow_all = parse_allowed_ids(allowed_raw)
    middleware = WhitelistMiddleware(allowed, allow_all=allow_all)
    dp = Dispatcher()
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)
    dp.include_router(command_router)
    dp.include_router(callback_router)
    log.info(
        "bot.dispatcher.built allowed_ids=%s allow_all=%s",
        sorted(allowed) or "[]", allow_all,
    )
    return dp


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    settings = get_settings()
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        log.error("bot.startup.no_token — set TELEGRAM_BOT_TOKEN in .env")
        # Sleep instead of exit so docker doesn't restart-loop on a missing
        # secret in development.
        while True:
            await asyncio.sleep(3600)

    bot = build_bot(token)
    dp = build_dispatcher(settings.telegram_allowed_user_ids)
    log.info("bot.starting username-fetch")
    me = await bot.get_me()
    log.info("bot.started username=@%s id=%s", me.username, me.id)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
