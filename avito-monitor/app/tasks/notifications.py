"""Notification dispatch — Block 5 (real Telegram delivery).

Two cooperating tasks:

* :func:`send_notification(notification_id)` — renders the row's
  template, picks the provider for the row's ``channel`` and calls
  ``send()``. On transient errors the row stays PENDING and the next
  ``dispatch_pending`` tick will retry it; permanent errors flip it to
  FAILED with the provider's message recorded.

* :func:`dispatch_pending` — every 2 minutes: enqueue
  ``send_notification`` for every PENDING row. Skipped entirely while
  the runtime pause flag is on or while the silent window is active —
  in both cases rows accumulate and ship when the gate opens.

Telegram chat target comes from ``TELEGRAM_ALLOWED_USER_IDS`` (first
id in the CSV). Same convention the V2 reliability alerter uses, so
the bot, the alerter and these notifications all land in the same
chat without extra plumbing.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.config import get_settings
from app.db.base import get_sessionmaker
from app.db.models import Notification
from app.db.models.enums import NotificationStatus
from app.integrations.messenger import MessengerError, get_provider
from app.integrations.messenger.renderer import render
from app.services import runtime_state
from app.tasks.broker import broker

log = logging.getLogger(__name__)


def _telegram_chat_id() -> str | None:
    raw = (get_settings().telegram_allowed_user_ids or "").strip()
    if not raw:
        return None
    first = raw.split(",")[0].strip()
    return first or None


@broker.task(task_name="app.tasks.notifications.send_notification")
async def send_notification(notification_id: str) -> dict[str, str]:
    """Deliver one notification through the configured channel."""
    sessionmaker = get_sessionmaker()
    nid = uuid.UUID(notification_id)

    async with sessionmaker() as session:
        notif = await session.get(Notification, nid)
        if notif is None:
            log.warning("notifications.missing id=%s", notification_id)
            return {"status": "skipped", "reason": "missing"}

        if notif.status != NotificationStatus.PENDING.value:
            return {"status": "skipped", "reason": f"already {notif.status}"}

    # Resolve chat id per channel. Today only telegram has a real one;
    # max would derive its own when wired up.
    if notif.channel == "telegram":
        chat_id = _telegram_chat_id()
        if not chat_id:
            log.warning("notifications.no_chat_id id=%s", notification_id)
            return {"status": "skipped", "reason": "no_chat_id"}
    else:
        chat_id = ""  # max stub will raise inside send()

    message = render(notif, chat_id=chat_id)

    try:
        provider = get_provider(notif.channel)
        provider_msg_id = await provider.send(message)
    except MessengerError as exc:
        if exc.transient:
            async with sessionmaker() as session:
                await session.execute(
                    update(Notification)
                    .where(Notification.id == nid)
                    .values(
                        retry_count=Notification.retry_count + 1,
                        error_message=str(exc)[:500],
                    )
                )
                await session.commit()
            log.warning(
                "notifications.transient id=%s err=%s",
                notification_id, exc,
            )
            return {"status": "retry", "reason": str(exc)}
        async with sessionmaker() as session:
            await session.execute(
                update(Notification)
                .where(Notification.id == nid)
                .values(
                    status=NotificationStatus.FAILED.value,
                    error_message=str(exc)[:500],
                )
            )
            await session.commit()
        log.warning("notifications.failed id=%s err=%s", notification_id, exc)
        return {"status": "failed", "reason": str(exc)}
    except Exception as exc:  # pragma: no cover — last-resort
        log.exception("notifications.unexpected id=%s", notification_id)
        async with sessionmaker() as session:
            await session.execute(
                update(Notification)
                .where(Notification.id == nid)
                .values(
                    status=NotificationStatus.FAILED.value,
                    error_message=f"{type(exc).__name__}: {exc}"[:500],
                )
            )
            await session.commit()
        return {"status": "failed", "reason": "unexpected"}

    async with sessionmaker() as session:
        payload = dict(notif.payload or {})
        payload["_provider_message_id"] = provider_msg_id
        await session.execute(
            update(Notification)
            .where(Notification.id == nid)
            .values(
                status=NotificationStatus.SENT.value,
                sent_at=datetime.now(timezone.utc),
                payload=payload,
                error_message=None,
            )
        )
        await session.commit()

    log.info(
        "notifications.sent id=%s channel=%s type=%s",
        notification_id, notif.channel, notif.type,
    )
    return {"status": "sent", "notification_id": notification_id}


@broker.task(
    task_name="app.tasks.notifications.dispatch_pending",
    schedule=[{"cron": "*/2 * * * *"}],
)
async def dispatch_pending() -> dict[str, int]:
    """Every 2 minutes: enqueue ``send_notification`` for PENDING rows.

    Held back entirely when the system is paused or the silent window
    is active — rows pile up and ship on the next tick after the gate
    opens. Polling-style retry rather than reactive enqueueing so a
    worker crash mid-match never strands a notification.
    """
    if await runtime_state.is_paused():
        log.info("notifications.dispatch.paused")
        return {"enqueued": 0, "reason": "paused"}
    if await runtime_state.is_silent_now():
        log.info("notifications.dispatch.silent")
        return {"enqueued": 0, "reason": "silent"}

    sessionmaker = get_sessionmaker()
    enqueued = 0
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(Notification.id)
                .where(Notification.status == NotificationStatus.PENDING.value)
                .limit(500)
            )
        ).scalars().all()

    for row_id in rows:
        try:
            await send_notification.kiq(str(row_id))
            enqueued += 1
        except Exception:
            log.exception("notifications.dispatch.kiq_failed id=%s", row_id)

    if enqueued:
        log.info("notifications.dispatch.tick enqueued=%d", enqueued)
    return {"enqueued": enqueued}
