"""Inline-button schema per notification type.

Callback-data layout: ``"<action>:<notification_id>:<extra>"``. The
bot's callback handler in ``app/integrations/telegram/callbacks.py``
splits on ":" with maxsplit=2. Keep ``action`` short — Telegram caps
callback_data at 64 bytes total.
"""
from __future__ import annotations

import uuid

from app.db.models.enums import NotificationType
from app.integrations.messenger.base import InlineButton


# Action codes (≤ 8 chars to leave room for UUID + extra).
ACTION_VIEWED = "viewed"
ACTION_HIDE = "hide"
ACTION_HIDE_SELLER = "hidesel"
ACTION_RECLASSIFY = "recheck"
ACTION_APPLY_BAND = "applyband"
ACTION_IGNORE = "ignore"


def _cb(action: str, notif_id: uuid.UUID, extra: str = "") -> str:
    suffix = f":{extra}" if extra else ""
    return f"{action}:{notif_id}{suffix}"


def buttons_for(
    notification_type: str,
    notification_id: uuid.UUID,
    *,
    listing_url: str | None = None,
    seller_id: str | None = None,
) -> list[list[InlineButton]]:
    """Return the inline-keyboard rows appropriate for this notification.

    Empty list = no keyboard. Each inner list is rendered as one row.
    """
    listing_types = {
        NotificationType.NEW_LISTING.value,
        NotificationType.PRICE_DROP_LISTING.value,
        NotificationType.PRICE_DROPPED_INTO_ALERT.value,
        NotificationType.HISTORICAL_LOW.value,
    }
    if notification_type in listing_types:
        rows: list[list[InlineButton]] = []
        if listing_url:
            rows.append([InlineButton.link("Открыть на Avito", listing_url)])
        action_row = [
            InlineButton.callback("✓ Просмотрено", _cb(ACTION_VIEWED, notification_id)),
            InlineButton.callback("❌ Скрыть", _cb(ACTION_HIDE, notification_id)),
        ]
        if seller_id:
            action_row.append(
                InlineButton.callback(
                    "🚫 Продавец",
                    _cb(ACTION_HIDE_SELLER, notification_id, seller_id),
                )
            )
        rows.append(action_row)
        rows.append(
            [
                InlineButton.callback(
                    "🔍 Повторный LLM",
                    _cb(ACTION_RECLASSIFY, notification_id),
                )
            ]
        )
        return rows

    market_types = {
        NotificationType.MARKET_TREND_DOWN.value,
        NotificationType.MARKET_TREND_UP.value,
        NotificationType.SUPPLY_SURGE.value,
        NotificationType.CONDITION_MIX_CHANGE.value,
    }
    if notification_type in market_types:
        return [
            [
                InlineButton.callback(
                    "Применить вилку", _cb(ACTION_APPLY_BAND, notification_id)
                ),
                InlineButton.callback(
                    "Игнорировать", _cb(ACTION_IGNORE, notification_id)
                ),
            ]
        ]

    if notification_type == NotificationType.ERROR.value:
        return []

    return []
