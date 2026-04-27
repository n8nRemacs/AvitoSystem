"""Inline-button callback handlers."""
from __future__ import annotations

import logging
import uuid

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy import update

from app.db.base import get_sessionmaker
from app.db.models import Notification, ProfileListing, SearchProfile
from app.db.models.enums import UserAction
from app.integrations.messenger.buttons import (
    ACTION_APPLY_BAND,
    ACTION_HIDE,
    ACTION_HIDE_SELLER,
    ACTION_IGNORE,
    ACTION_RECLASSIFY,
    ACTION_VIEWED,
)

log = logging.getLogger(__name__)
router = Router(name="callbacks")


def _parse(data: str) -> tuple[str, str, str]:
    """Split ``"action:notif_id:extra"`` with maxsplit=2."""
    parts = data.split(":", 2)
    while len(parts) < 3:
        parts.append("")
    return parts[0], parts[1], parts[2]


async def _set_user_action(notif_id: uuid.UUID, action: str) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        notif = await session.get(Notification, notif_id)
        if notif is None or notif.related_listing_id is None or notif.profile_id is None:
            return
        await session.execute(
            update(ProfileListing)
            .where(
                ProfileListing.profile_id == notif.profile_id,
                ProfileListing.listing_id == notif.related_listing_id,
            )
            .values(user_action=action)
        )
        await session.commit()


async def _block_seller(profile_id: uuid.UUID, seller_id: str) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        profile = await session.get(SearchProfile, profile_id)
        if profile is None:
            return
        blocked = list(profile.blocked_sellers or [])
        if seller_id in blocked:
            return
        blocked.append(seller_id)
        profile.blocked_sellers = blocked
        await session.commit()


@router.callback_query()
async def on_callback(query: CallbackQuery) -> None:
    data = query.data or ""
    action, notif_id_raw, extra = _parse(data)
    try:
        notif_id = uuid.UUID(notif_id_raw)
    except ValueError:
        await query.answer("Битая кнопка.", show_alert=True)
        return

    log.info(
        "bot.callback action=%s notif_id=%s extra=%s user=%s",
        action, notif_id, extra,
        query.from_user.id if query.from_user else "?",
    )

    if action == ACTION_VIEWED:
        await _set_user_action(notif_id, UserAction.VIEWED.value)
        await query.answer("✓ Помечено как просмотренное")
    elif action == ACTION_HIDE:
        await _set_user_action(notif_id, UserAction.HIDDEN.value)
        await query.answer("Скрыто")
    elif action == ACTION_HIDE_SELLER:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            notif = await session.get(Notification, notif_id)
            profile_id = notif.profile_id if notif else None
        if profile_id and extra:
            await _block_seller(profile_id, extra)
            await query.answer(f"Продавец {extra} в чёрном списке")
        else:
            await query.answer("Не удалось — нет продавца", show_alert=True)
    elif action == ACTION_RECLASSIFY:
        # Re-enqueue stage-1 LLM for this listing.
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            notif = await session.get(Notification, notif_id)
        if notif and notif.related_listing_id and notif.profile_id:
            try:
                from app.tasks.analysis import analyze_listing

                await analyze_listing.kiq(
                    str(notif.related_listing_id), str(notif.profile_id)
                )
                await query.answer("LLM повторно поставлен в очередь")
            except Exception:
                log.exception("bot.callback.reclassify.kiq_failed")
                await query.answer("Не удалось поставить в очередь", show_alert=True)
        else:
            await query.answer("Лот не найден", show_alert=True)
    elif action == ACTION_APPLY_BAND:
        await query.answer("Авто-вилка появится в Block 7", show_alert=True)
    elif action == ACTION_IGNORE:
        await query.answer("Принято")
    else:
        await query.answer(f"Неизвестное действие: {action}", show_alert=True)
