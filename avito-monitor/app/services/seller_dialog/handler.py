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
from app.services.dialog_topics import state as topic_state
from app.services.llm_analyzer import detect_yes_selling, parse_seller_agreement, parse_topic_answer
from app.services.messenger_bot.dedup import ensure_chat_row
from app.services.notifications import enqueue_tg_ping
from app.services.seller_dialog import service as sd_service
from app.services.seller_dialog.constants import (
    STAGE_QUESTIONS,
    RECAP_PENDING_ANSWER,
    RECAP_CONFIRMED,
)
from app.services.seller_dialog.service import (
    get_dialog_by_channel,
    set_stage,
)
from app.services.seller_dialog.transitions import next_stage_on_seller_reply
from app.tasks.seller_dialog_tasks import dialog_tick_questions

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

    # Ensure messenger_chats parent row exists — required by FK on
    # messenger_messages.channel_id. item_id unknown here (SSE payload
    # doesn't carry it); ensure_chat_row leaves it NULL on first insert.
    await ensure_chat_row(channel_id)

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

    # ── Stage QUESTIONS branch ──────────────────────────────────────────
    if dialog.stage == STAGE_QUESTIONS:
        # If recap awaits answer — classify seller's reply
        if dialog.recap_status == RECAP_PENDING_ANSWER:
            ag = await parse_seller_agreement(text or "")
            if ag["agreement"] == "yes":
                await sd_service.set_recap_status(session, dialog.id, RECAP_CONFIRMED)
                await session.commit()
                await enqueue_tg_ping(session, "seller_dialog_ready_to_negotiate", dialog.id)
            elif ag["agreement"] == "no":
                # Disputed — operator takes over
                from app.services.seller_dialog.service import set_operator_mode
                await set_operator_mode(session, dialog.id, True)
                await session.commit()
            # unclear → silently store msg + wait; operator may step in
            return

        # Otherwise — match inbound to current asked topic
        asked = await topic_state.get_asked_topic(session, dialog.id)
        if asked is None:
            return  # spam / out-of-band
        open_topics = await topic_state.all_open_topics(session, dialog.id)
        parsed = await parse_topic_answer(asked, text or "", open_topics=open_topics)
        if parsed["status"] == "answered":
            await topic_state.mark_answered(
                session, asked.id,
                answer_text=parsed["extracted"] or text or "",
                answer_msg_id=message_id,
            )
            for st in parsed["side_topics"]:
                # Find target by topic_key + dialog
                from sqlalchemy import select
                from app.db.models import SellerDialogTopic as SDT
                target = (await session.execute(
                    select(SDT).where(
                        SDT.dialog_id == dialog.id,
                        SDT.topic_key == st["topic_key"],
                        SDT.status.in_(("pending", "asked")),
                    )
                )).scalar_one_or_none()
                if target:
                    await topic_state.mark_answered(
                        session, target.id,
                        answer_text=st.get("extracted") or "",
                        answer_msg_id=message_id,
                    )
        else:  # unclear or off_topic
            new_retry = await topic_state.increment_retry(session, asked.id)
            if new_retry >= 2:
                await topic_state.mark_skipped(session, asked.id)
        await session.commit()
        await dialog_tick_questions.kiq(str(dialog.id))
        return

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
