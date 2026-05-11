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

    async def create_channel_by_item(self, item_id: str) -> dict[str, Any]:
        call = await self._client.post(
            "/api/v1/messenger/channels/by-item",
            json_body={"item_id": item_id},
        )
        if not call.ok or not isinstance(call.body, dict):
            raise RuntimeError(
                f"xapi create_channel_by_item failed status={call.status_code} body={call.body!r}"
            )
        # xapi wraps in {"status":"ok","result":{...}}; some shapes nest "success" too.
        result = call.body.get("result") or call.body.get("success") or call.body
        return result if isinstance(result, dict) else {"id": result}

    async def send_text(self, channel_id: str, text: str) -> dict[str, Any]:
        call = await self._client.post(
            f"/api/v1/messenger/channels/{channel_id}/messages",
            json_body={"text": text},
        )
        if not call.ok or not isinstance(call.body, dict):
            raise RuntimeError(
                f"xapi send_text failed status={call.status_code} body={call.body!r}"
            )
        result = call.body.get("result") or call.body.get("success") or call.body
        return result if isinstance(result, dict) else {"id": result}


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
