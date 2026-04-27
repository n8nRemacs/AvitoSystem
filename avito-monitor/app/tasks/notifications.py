"""Notification dispatch task — stub until Block 5.

For V1 the LLM match step (``app.tasks.analysis.match_listing``) writes
``Notification(status=PENDING)`` rows directly. Block 5 (Telegram bot
via aiogram) will replace this stub with real Telegram/Max delivery
through the pluggable :class:`MessengerProvider`.

Until then we keep the pipeline unblocked: this task simply logs the
intent and marks the notification ``sent`` so the dashboard counters
move and we can validate end-to-end flow without sending anything.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import update

from app.db.base import get_sessionmaker
from app.db.models import Notification
from app.db.models.enums import NotificationStatus
from app.tasks.broker import broker

log = logging.getLogger(__name__)


@broker.task(task_name="app.tasks.notifications.send_notification")
async def send_notification(notification_id: str) -> dict[str, str]:
    """Pretend to deliver a notification. Real impl arrives in Block 5."""
    sessionmaker = get_sessionmaker()
    nid = uuid.UUID(notification_id)

    async with sessionmaker() as session:
        notif = await session.get(Notification, nid)
        if notif is None:
            log.warning("notifications.stub.missing id=%s", notification_id)
            return {"status": "skipped", "reason": "missing"}

        if notif.status != NotificationStatus.PENDING.value:
            return {"status": "skipped", "reason": f"already {notif.status}"}

        # In Block 5 this is where TelegramProvider.send() goes.
        log.info(
            "notifications.stub.send id=%s type=%s channel=%s",
            notification_id, notif.type, notif.channel,
        )

        await session.execute(
            update(Notification)
            .where(Notification.id == nid)
            .values(
                status=NotificationStatus.SENT.value,
                sent_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    return {"status": "sent", "notification_id": notification_id}


@broker.task(
    task_name="app.tasks.notifications.dispatch_pending",
    schedule=[{"cron": "*/2 * * * *"}],
)
async def dispatch_pending() -> dict[str, int]:
    """Every 2 minutes: enqueue ``send_notification`` for every PENDING row.

    Done as a polling sweep rather than reactive enqueueing so a worker
    crash mid-match never strands a notification — the next sweep picks
    it up. Acceptable as long as the volume stays in the low hundreds /
    day; revisit when we cross 10k/day.
    """
    from sqlalchemy import select

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
