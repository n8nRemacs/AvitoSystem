"""TaskIQ tasks for the seller dialog workflow (Phase A).

Phase A exposes one task: ``start_seller_dialog(profile_id, listing_id)``.
It's enqueued from the listing-action HTTP endpoint when a user accepts a
lot. Logic:

  1. Create a SellerDialog row (stage=contact).
  2. Look up the listing's Avito item_id.
  3. Call xapi to create a messenger channel.
  4. Send the hardcoded greeting on that channel.
  5. Persist the outgoing message to messenger_messages with
     dialog_id linking it back.

If anything fails after step 1, the dialog is marked operator_mode=true
so a human can take over. We do NOT retry — Avito rate-limits aggressively
and we'd rather have a stuck dialog than a duplicate greeting.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Listing, MessengerMessage
from app.services.messenger_bot.dedup import ensure_chat_row
from app.services.seller_dialog import service as sd_service
from app.services.seller_dialog.constants import GREETING_TEMPLATE
from app.tasks.broker import broker

log = logging.getLogger(__name__)


async def _get_avito_item_id(session: AsyncSession, listing_id: uuid.UUID) -> str:
    """Look up Avito's item_id for our internal listing UUID."""
    stmt = select(Listing.avito_id).where(Listing.id == listing_id)
    avito_id = (await session.execute(stmt)).scalar_one()
    return str(avito_id)


async def _start_seller_dialog_impl(
    session: AsyncSession,
    xapi_client,  # XapiClient-shaped object with create_channel_by_item + send_text
    profile_id: uuid.UUID,
    listing_id: uuid.UUID,
) -> dict[str, Any]:
    """Pure-logic implementation, separated from broker wrapping for testability.

    The ``xapi_client`` argument is duck-typed: anything with awaitable
    ``create_channel_by_item(item_id) -> {"id": ...}`` and
    ``send_text(channel_id, text) -> {"id": ...}`` works. The real broker
    entrypoint below wires in a concrete client; tests pass an AsyncMock.
    """
    # Idempotency guard — re-clicks / replays should not re-greet the seller.
    existing = await sd_service.get_dialog_by_listing(
        session, profile_id=profile_id, listing_id=listing_id,
    )
    if existing is not None:
        log.info(
            "seller_dialog.start skip — dialog already exists listing=%s stage=%s",
            listing_id, existing.stage,
        )
        return {
            "dialog_id": str(existing.id),
            "channel_id": existing.channel_id,
            "skipped": True,
        }

    # Step 1: create dialog
    dialog = await sd_service.create_dialog(
        session,
        profile_id=profile_id,
        listing_id=listing_id,
        operator_mode=False,
    )
    await session.flush()

    # Step 2: avito item_id
    avito_item_id = await _get_avito_item_id(session, listing_id)

    # Step 3: create channel
    channel_resp = await xapi_client.create_channel_by_item(avito_item_id)
    channel_id = channel_resp["id"]
    await sd_service.set_channel_id(session, dialog.id, channel_id)

    # Ensure messenger_chats parent row exists before we INSERT a child
    # messenger_messages row (FK channel_id → messenger_chats.id).
    # ensure_chat_row opens its own session and commits — idempotent via
    # ON CONFLICT DO NOTHING.
    await ensure_chat_row(channel_id, item_id=int(avito_item_id))

    # Step 4: send greeting
    msg_resp = await xapi_client.send_text(channel_id, GREETING_TEMPLATE)
    msg_id = msg_resp["id"]

    # Step 5: persist outgoing message
    msg = MessengerMessage(
        id=msg_id,
        channel_id=channel_id,
        dialog_id=dialog.id,
        direction="out",
        author_id=None,
        text=GREETING_TEMPLATE,
        type="text",
        created_at=datetime.now(tz=timezone.utc),
        raw={"source": "seller_dialog.start"},
    )
    session.add(msg)

    await session.commit()

    log.info(
        "seller_dialog.start success listing=%s channel=%s msg=%s",
        listing_id, channel_id, msg_id,
    )
    return {
        "dialog_id": str(dialog.id),
        "channel_id": channel_id,
        "greeting_message_id": msg_id,
    }


class _XapiMessengerAdapter:
    """Duck-typed adapter wrapping the generic XapiClient to expose the two
    methods _start_seller_dialog_impl expects.

    Avito-monitor doesn't yet have a typed messenger client; the existing
    XapiClient (in health_checker/xapi_client.py) is a generic GET/POST
    wrapper. avito-xapi exposes:
      - POST /api/v1/messenger/channels/by-item        body={item_id} → {result: {id, ...}}
      - POST /api/v1/messenger/channels/{id}/messages  body={text}    → {result: {id, ...}}
    """

    def __init__(self, client):
        self._client = client

    @staticmethod
    def _unwrap_result(call) -> dict[str, Any]:
        """Pull the inner result dict out of the xapi envelope and raise on
        Avito-side errors that xapi proxied as HTTP 200.

        Wire shape: ``{"status":"ok","result":{...}}`` on success. On
        Avito-side rejection xapi still answers HTTP 200 but with
        ``result.error = {"code": ..., "message": ...}`` (seen e.g. for
        unpublished lots: ``Forbidden because item do not support create
        channel``). Treat such payloads as failures.
        """
        if not call.ok or not isinstance(call.body, dict):
            raise RuntimeError(
                f"xapi call failed status={call.status_code} body={call.body!r}"
            )
        result = call.body.get("result") or call.body.get("success") or call.body
        if isinstance(result, dict) and isinstance(result.get("error"), dict):
            err = result["error"]
            raise RuntimeError(
                f"avito rejected: code={err.get('code')} message={err.get('message')!r}"
            )
        if not isinstance(result, dict):
            return {"id": result}
        return result

    async def create_channel_by_item(self, item_id: str) -> dict[str, Any]:
        call = await self._client.post(
            "/api/v1/messenger/channels/by-item",
            json_body={"item_id": item_id},
        )
        result = self._unwrap_result(call)
        # xapi shape: result = {"channel": {"id": "u2i-...", "authorId": ..., ...}}.
        # Peel the inner channel so callers can do channel_resp["id"].
        if isinstance(result, dict) and isinstance(result.get("channel"), dict):
            return result["channel"]
        return result

    async def send_text(self, channel_id: str, text: str) -> dict[str, Any]:
        call = await self._client.post(
            f"/api/v1/messenger/channels/{channel_id}/messages",
            json_body={"text": text},
        )
        result = self._unwrap_result(call)
        # xapi shape: result = {"message": {"id": "...", "channelId": "...", ...}}.
        # Peel so callers can do msg_resp["id"].
        if isinstance(result, dict) and isinstance(result.get("message"), dict):
            return result["message"]
        return result


@broker.task(task_name="app.tasks.seller_dialog_tasks.start_seller_dialog")
async def start_seller_dialog(profile_id: str, listing_id: str) -> dict[str, Any]:
    """TaskIQ entrypoint — opens its own DB session + xapi client.

    Wraps the generic XapiClient (used elsewhere in the messenger bot) with
    a small adapter that exposes the typed messenger methods
    ``_start_seller_dialog_impl`` expects.
    """
    from app.db.base import get_sessionmaker
    from app.services.messenger_bot.runner import make_xapi_client

    sessionmaker = get_sessionmaker()
    xapi_raw = make_xapi_client()
    xapi = _XapiMessengerAdapter(xapi_raw)
    async with sessionmaker() as session:
        try:
            return await _start_seller_dialog_impl(
                session=session,
                xapi_client=xapi,
                profile_id=uuid.UUID(profile_id),
                listing_id=uuid.UUID(listing_id),
            )
        except Exception:
            log.exception(
                "seller_dialog.start failed listing=%s — switching to operator_mode",
                listing_id,
            )
            # Mark the (possibly created) dialog as operator_mode for human takeover.
            try:
                dlg = await sd_service.get_dialog_by_listing(
                    session,
                    profile_id=uuid.UUID(profile_id),
                    listing_id=uuid.UUID(listing_id),
                )
                if dlg:
                    await sd_service.set_operator_mode(session, dlg.id, True)
                    await session.commit()
            except Exception:
                log.exception("seller_dialog.start cleanup also failed")
            raise


# ---------------------------- Phase B ---------------------------------------
import asyncio
from app.services.dialog_topics import state as topic_state
from app.services.seller_dialog.constants import OPENING_LINE, RECAP_PENDING_ANSWER
from app.services.llm_analyzer import formulate_question, formulate_recap


async def has_started_questions(session, dialog_id) -> bool:
    """True if at least one topic was already asked/answered/skipped."""
    from sqlalchemy import select, func
    from app.db.models import SellerDialogTopic
    res = await session.execute(
        select(func.count())
        .select_from(SellerDialogTopic)
        .where(
            SellerDialogTopic.dialog_id == dialog_id,
            SellerDialogTopic.status.in_(("asked", "answered", "skipped")),
        )
    )
    return (res.scalar() or 0) > 0


async def _dialog_tick_questions_impl(session, xapi, dialog_id):
    """Pure-logic implementation, separated for testability."""
    dialog = await sd_service.get_dialog(session, dialog_id)
    if dialog is None or dialog.stage != "questions" or dialog.operator_mode:
        return

    # 1. If a topic is currently awaiting an answer — wait.
    asked = await topic_state.get_asked_topic(session, dialog_id)
    if asked is not None:
        return

    # 2. If first tick — send opening line first.
    if not await has_started_questions(session, dialog_id):
        await xapi.send_text(dialog.channel_id, OPENING_LINE)
        # Optional persist into messenger_messages happens via send wrapper if used;
        # else skip — opening is a courtesy, not part of state.
        await asyncio.sleep(3)

    # 3. Pick next pending topic.
    next_topic = await topic_state.pick_next_pending(session, dialog_id)
    if next_topic is not None:
        # Load full topic metadata for the LLM
        from sqlalchemy import select
        from app.db.models import DialogTopic
        topic_meta = (await session.execute(
            select(DialogTopic).where(DialogTopic.key == next_topic.topic_key)
        )).scalar_one()
        history_tail = []  # could be filled from messenger_messages — keep MVP simple
        question = await formulate_question(topic_meta, history_tail)
        send_resp = await xapi.send_text(dialog.channel_id, question)
        await topic_state.mark_asked(
            session, next_topic.id,
            question_text=question,
            question_msg_id=send_resp.get("id") if isinstance(send_resp, dict) else None,
        )
        await session.commit()
        return

    # 4. All topics done — formulate recap if not yet sent.
    if dialog.recap_status is None:
        answered = await topic_state.answered_topics(session, dialog_id)
        recap = await formulate_recap(answered)
        send_resp = await xapi.send_text(dialog.channel_id, recap)
        await sd_service.set_recap(
            session, dialog_id,
            text=recap,
            msg_id=send_resp.get("id") if isinstance(send_resp, dict) else None,
            status=RECAP_PENDING_ANSWER,
        )
        await session.commit()
        return

    # 5. recap is sent — waiting for seller's reply, nothing to do.


@broker.task(task_name="app.tasks.seller_dialog_tasks.dialog_tick_questions")
async def dialog_tick_questions(dialog_id: str) -> dict:
    """TaskIQ entrypoint for the questions stage state machine tick."""
    from app.db.base import get_sessionmaker
    from app.services.messenger_bot.runner import make_xapi_client

    sessionmaker = get_sessionmaker()
    xapi_raw = make_xapi_client()
    xapi = _XapiMessengerAdapter(xapi_raw)
    async with sessionmaker() as session:
        try:
            await _dialog_tick_questions_impl(session, xapi, uuid.UUID(dialog_id))
        except Exception:
            log.exception("dialog_tick_questions failed dialog=%s — operator_mode", dialog_id)
            try:
                await sd_service.set_operator_mode(session, uuid.UUID(dialog_id), True)
                await session.commit()
            except Exception:
                log.exception("operator_mode cleanup also failed")
            raise
    return {"dialog_id": dialog_id, "ok": True}
