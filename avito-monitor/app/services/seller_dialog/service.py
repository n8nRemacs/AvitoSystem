"""CRUD operations for SellerDialog rows.

Single responsibility — no Avito API calls, no LLM, no HTTP. Pure DB.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SellerDialog
from app.services.seller_dialog.constants import STAGE_CONTACT


async def create_dialog(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    listing_id: uuid.UUID,
    operator_mode: bool = False,
) -> SellerDialog:
    """Insert a new dialog row at stage=contact. Caller commits."""
    sd = SellerDialog(
        profile_id=profile_id,
        listing_id=listing_id,
        stage=STAGE_CONTACT,
        operator_mode=operator_mode,
    )
    session.add(sd)
    await session.flush()
    return sd


async def get_dialog_by_listing(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    listing_id: uuid.UUID,
) -> SellerDialog | None:
    stmt = select(SellerDialog).where(
        SellerDialog.profile_id == profile_id,
        SellerDialog.listing_id == listing_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_dialog_by_channel(
    session: AsyncSession, channel_id: str
) -> SellerDialog | None:
    stmt = select(SellerDialog).where(SellerDialog.channel_id == channel_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def set_stage(
    session: AsyncSession,
    dialog_id: uuid.UUID,
    new_stage: str,
) -> None:
    """Transition to a new stage, update last_event_at to now()."""
    await session.execute(
        update(SellerDialog)
        .where(SellerDialog.id == dialog_id)
        .values(
            stage=new_stage,
            last_event_at=datetime.now(tz=timezone.utc),
        )
    )


async def set_operator_mode(
    session: AsyncSession,
    dialog_id: uuid.UUID,
    operator_mode: bool,
) -> None:
    await session.execute(
        update(SellerDialog)
        .where(SellerDialog.id == dialog_id)
        .values(operator_mode=operator_mode)
    )


async def set_channel_id(
    session: AsyncSession,
    dialog_id: uuid.UUID,
    channel_id: str,
) -> None:
    await session.execute(
        update(SellerDialog)
        .where(SellerDialog.id == dialog_id)
        .values(channel_id=channel_id)
    )


async def close_dialog(
    session: AsyncSession,
    dialog_id: uuid.UUID,
    *,
    reason: str,
) -> None:
    """Mark a dialog closed.

    Sets ``closed_at=now()``, ``closed_reason=reason``, and bumps
    ``last_event_at=now()`` so the kanban's recency sort still works.
    Idempotent — re-closing already-closed rows is a no-op write (caller
    typically pre-checks via ``get_dialog_by_listing`` and skips if
    ``closed_at`` is already set). Caller commits.
    """
    now = datetime.now(tz=timezone.utc)
    await session.execute(
        update(SellerDialog)
        .where(SellerDialog.id == dialog_id)
        .values(
            closed_at=now,
            closed_reason=reason,
            last_event_at=now,
        )
    )


async def get_dialog(session: AsyncSession, dialog_id: uuid.UUID) -> SellerDialog | None:
    return await session.get(SellerDialog, dialog_id)


async def set_recap(
    session: AsyncSession, dialog_id: uuid.UUID, *,
    text: str, msg_id: str | None, status: str,
) -> None:
    await session.execute(
        update(SellerDialog)
        .where(SellerDialog.id == dialog_id)
        .values(
            recap_text=text,
            recap_msg_id=msg_id,
            recap_status=status,
            last_event_at=datetime.now(tz=timezone.utc),
        )
    )


async def set_recap_status(
    session: AsyncSession, dialog_id: uuid.UUID, status: str,
) -> None:
    await session.execute(
        update(SellerDialog)
        .where(SellerDialog.id == dialog_id)
        .values(recap_status=status,
                last_event_at=datetime.now(tz=timezone.utc))
    )
