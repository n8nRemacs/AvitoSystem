"""Inbound SSE handler for seller-dialog channels.

Called from the existing messenger_bot.handler.handle_event() after it
checks whether the inbound's channel belongs to a SellerDialog (rather
than a reliability-flow chat). We get the channel_id + message metadata
and run:

  1. Persist incoming message with dialog_id link.
  2. If operator_mode=True — that's it, operator handles it.
  3. Otherwise dispatch a stage-specific reaction:
       contact + yes-selling → set stage=questions_setup + TG-ping operator
       (TG-ping is added in Phase E; for now we just transition the stage)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MessengerMessage
from app.services.llm_analyzer import detect_yes_selling
from app.services.seller_dialog.service import (
    get_dialog_by_channel,
    set_stage,
)
from app.services.seller_dialog.transitions import next_stage_on_seller_reply

log = logging.getLogger(__name__)


async def handle_seller_inbound(
    *,
    session: AsyncSession,
    channel_id: str,
    message_id: str,
    author_id: str | None,
    text: str | None,
) -> None:
    """Process one inbound message for a known seller-dialog channel.

    Caller (messenger_bot.handler) must have already confirmed via
    get_dialog_by_channel() that this channel belongs to seller-dialog flow.
    """
    dialog = await get_dialog_by_channel(session, channel_id)
    if dialog is None:
        log.warning("seller_dialog.handler called for unknown channel %s", channel_id)
        return

    # Step 1: persist the inbound (idempotent on PK)
    msg = MessengerMessage(
        id=message_id,
        channel_id=channel_id,
        dialog_id=dialog.id,
        direction="in",
        author_id=author_id,
        text=text,
        type="text",
        created_at=datetime.now(tz=timezone.utc),
        raw=None,
    )
    session.add(msg)

    if dialog.operator_mode:
        log.info(
            "seller_dialog.handler op-mode dialog=%s — stored msg, no LLM",
            dialog.id,
        )
        await session.commit()
        return

    # Step 2: run stage-specific LLM check
    yes_selling = False
    if text:
        yes_selling = await detect_yes_selling(text)

    new_stage = next_stage_on_seller_reply(
        current_stage=dialog.stage,
        llm_yes_selling=yes_selling,
    )

    if new_stage is not None:
        await set_stage(session, dialog.id, new_stage)
        log.info(
            "seller_dialog.handler transition dialog=%s %s → %s",
            dialog.id, dialog.stage, new_stage,
        )

    await session.commit()
