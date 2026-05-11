"""Notifications service — enqueue TG-ping rows for seller-dialog transitions."""
from __future__ import annotations

import uuid
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Notification, SearchProfile
from app.db.models.enums import NotificationStatus

log = logging.getLogger(__name__)


async def enqueue_tg_ping(
    session: AsyncSession,
    notif_type: str,
    dialog_id: uuid.UUID,
) -> None:
    """Persist a TG-ping notification row tied to a seller_dialog.

    Resolves user_id via the dialog's profile_id so the Notification FK
    constraint is satisfied.  Listing FK is left NULL — pings carry enough
    context in ``payload`` for the Jinja2 template to render.

    If the profile row is missing (race condition / bad data) we log and
    skip rather than crashing the caller's transaction.
    """
    # Import here to avoid circular imports (models → services → models).
    from app.db.models.seller_dialog import SellerDialog  # noqa: PLC0415

    dialog = await session.get(SellerDialog, dialog_id)
    if dialog is None:
        log.warning("enqueue_tg_ping: dialog %s not found, skipping ping %s", dialog_id, notif_type)
        return

    profile = await session.get(SearchProfile, dialog.profile_id)
    if profile is None:
        log.warning("enqueue_tg_ping: profile %s not found, skipping ping %s", dialog.profile_id, notif_type)
        return

    # Resolve listing for payload (avito_id / title / price for template)
    from app.db.models.listing import Listing  # noqa: PLC0415
    listing = await session.get(Listing, dialog.listing_id)

    from app.config import get_settings  # noqa: PLC0415
    settings = get_settings()
    kanban_url = f"{settings.app_base_url}/listings?tab=in_progress"

    payload: dict = {
        "dialog_id": str(dialog_id),
        "kanban_url": kanban_url,
    }
    if listing is not None:
        payload["avito_id"] = listing.avito_id
        payload["title"] = listing.title
        payload["price"] = float(listing.price) if listing.price is not None else None
        payload["url"] = listing.url

    notif = Notification(
        user_id=profile.user_id,
        profile_id=profile.id,
        related_listing_id=dialog.listing_id,
        type=notif_type,
        channel="telegram",
        payload=payload,
        status=NotificationStatus.PENDING.value,
    )
    session.add(notif)
    log.info(
        "enqueue_tg_ping: queued %s for dialog=%s listing=%s",
        notif_type, dialog_id, dialog.listing_id,
    )
