"""DB-backed dedup checks for the messenger-bot.

Two questions per inbound event:

1. ``already_replied(channel_id)`` — did we already act on this channel? A row
   in ``chat_dialog_state`` (any state) means yes. This is the primary
   dedup key and survives restarts.
2. ``operator_already_replied(channel_id)`` — did a human operator already
   send a message in this chat (e.g. via APK directly)? Detected by any
   ``direction='out'`` row in ``messenger_messages`` for the channel.

Plus :func:`record_dialog_state` and :func:`record_outgoing_message` for the
"send was successful, now persist" half of the pipeline. Both are upsert-ish
to make ``/run-once`` repeatable from manual tests.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.base import get_sessionmaker
from app.db.models import ChatDialogState, MessengerChat, MessengerMessage

log = structlog.get_logger(__name__)


async def already_replied(channel_id: str) -> bool:
    """True iff a row exists in ``chat_dialog_state`` for this channel."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = select(func.count()).select_from(ChatDialogState).where(
            ChatDialogState.channel_id == channel_id
        )
        n = (await session.execute(stmt)).scalar() or 0
    return int(n) > 0


async def operator_already_replied(channel_id: str) -> bool:
    """True iff any ``direction='out'`` message exists for this channel."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = (
            select(func.count())
            .select_from(MessengerMessage)
            .where(MessengerMessage.channel_id == channel_id)
            .where(MessengerMessage.direction == "out")
        )
        n = (await session.execute(stmt)).scalar() or 0
    return int(n) > 0


async def ensure_chat_row(channel_id: str, *, item_id: int | None = None) -> None:
    """Make sure ``messenger_chats`` has a row for ``channel_id``.

    The dialog-state and message rows have FKs onto this table, so we upsert
    a minimal stub if it's missing. Real channel metadata is filled in by the
    activity-simulator and (later) by an inbound listing-cache job.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = pg_insert(MessengerChat).values(
            id=channel_id,
            item_id=item_id,
            updated_at=datetime.now(UTC),
        )
        # ON CONFLICT DO NOTHING — we don't want to clobber a richer row.
        stmt = stmt.on_conflict_do_nothing(index_elements=[MessengerChat.id])
        await session.execute(stmt)
        await session.commit()


async def record_dialog_state(
    channel_id: str,
    *,
    state: str,
    message_id: str | None,
    notes: dict[str, Any] | None = None,
) -> None:
    """Upsert one row into ``chat_dialog_state``.

    Pre-condition: ``messenger_chats`` row exists (FK). The caller is expected
    to ``ensure_chat_row`` first; the handler does this automatically.
    """
    sessionmaker = get_sessionmaker()
    now = datetime.now(UTC)
    async with sessionmaker() as session:
        stmt = pg_insert(ChatDialogState).values(
            channel_id=channel_id,
            state=state,
            bot_replied_at=now if state == "replied_with_template" else None,
            bot_reply_message_id=message_id,
            notes=notes,
            updated_at=now,
        )
        # If we somehow re-enter we still want last-write-wins behaviour for
        # the ``state``/``message_id`` columns so manual recovery is possible.
        stmt = stmt.on_conflict_do_update(
            index_elements=[ChatDialogState.channel_id],
            set_={
                "state": stmt.excluded.state,
                "bot_replied_at": stmt.excluded.bot_replied_at,
                "bot_reply_message_id": stmt.excluded.bot_reply_message_id,
                "notes": stmt.excluded.notes,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)
        await session.commit()


async def record_outgoing_message(
    channel_id: str,
    *,
    message_id: str,
    text: str,
) -> None:
    """Insert an ``out`` message row.

    Pre-condition: a ``messenger_chats`` row exists (FK). Idempotent on
    ``message_id`` PK conflict — re-running the same handler twice (e.g. on
    a debug retry) won't crash.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = pg_insert(MessengerMessage).values(
            id=message_id,
            channel_id=channel_id,
            direction="out",
            text=text,
            type="text",
            created_at=datetime.now(UTC),
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=[MessengerMessage.id])
        await session.execute(stmt)
        await session.commit()
