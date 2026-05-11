"""Per-dialog topic state helpers (pure DB, no LLM)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SellerDialogTopic, DialogTopic


async def init_dialog_topics(
    session: AsyncSession,
    *,
    dialog_id: uuid.UUID,
    topic_keys: list[str],
) -> None:
    """Insert one SellerDialogTopic per checked key with status='pending'.
    Priority equals position in the list."""
    for i, key in enumerate(topic_keys):
        session.add(SellerDialogTopic(
            id=uuid.uuid4(),
            dialog_id=dialog_id,
            topic_key=key,
            priority=i,
            status="pending",
        ))
    await session.flush()


async def pick_next_pending(
    session: AsyncSession, dialog_id: uuid.UUID,
) -> SellerDialogTopic | None:
    """Return the highest-priority pending topic or None."""
    stmt = (
        select(SellerDialogTopic)
        .where(
            SellerDialogTopic.dialog_id == dialog_id,
            SellerDialogTopic.status == "pending",
        )
        .order_by(SellerDialogTopic.priority)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_asked_topic(
    session: AsyncSession, dialog_id: uuid.UUID,
) -> SellerDialogTopic | None:
    """Return the topic currently awaiting an answer (status='asked', no answer)."""
    stmt = (
        select(SellerDialogTopic)
        .where(
            SellerDialogTopic.dialog_id == dialog_id,
            SellerDialogTopic.status == "asked",
            SellerDialogTopic.answer_text.is_(None),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def mark_asked(
    session: AsyncSession, topic_id: uuid.UUID, *,
    question_text: str, question_msg_id: str | None,
) -> None:
    await session.execute(
        update(SellerDialogTopic)
        .where(SellerDialogTopic.id == topic_id)
        .values(
            status="asked",
            question_text=question_text,
            question_msg_id=question_msg_id,
            asked_at=datetime.now(tz=timezone.utc),
        )
    )


async def mark_answered(
    session: AsyncSession, topic_id: uuid.UUID, *,
    answer_text: str, answer_msg_id: str | None = None,
) -> None:
    await session.execute(
        update(SellerDialogTopic)
        .where(SellerDialogTopic.id == topic_id)
        .values(
            status="answered",
            answer_text=answer_text,
            answer_msg_id=answer_msg_id,
            answered_at=datetime.now(tz=timezone.utc),
        )
    )


async def mark_skipped(
    session: AsyncSession, topic_id: uuid.UUID,
) -> None:
    await session.execute(
        update(SellerDialogTopic)
        .where(SellerDialogTopic.id == topic_id)
        .values(status="skipped", answered_at=datetime.now(tz=timezone.utc))
    )


async def increment_retry(
    session: AsyncSession, topic_id: uuid.UUID,
) -> int:
    """Increment retry_count and return new value."""
    res = await session.execute(
        update(SellerDialogTopic)
        .where(SellerDialogTopic.id == topic_id)
        .values(retry_count=SellerDialogTopic.retry_count + 1)
        .returning(SellerDialogTopic.retry_count)
    )
    return res.scalar_one()


async def all_open_topics(
    session: AsyncSession, dialog_id: uuid.UUID,
) -> list[dict]:
    """List open topics for context in parse_topic_answer (for side_topics)."""
    stmt = (
        select(SellerDialogTopic.topic_key, DialogTopic.title)
        .join(DialogTopic, DialogTopic.key == SellerDialogTopic.topic_key)
        .where(
            SellerDialogTopic.dialog_id == dialog_id,
            SellerDialogTopic.status.in_(("pending", "asked")),
        )
    )
    return [{"key": k, "title": t} for k, t in (await session.execute(stmt)).all()]


async def answered_topics(
    session: AsyncSession, dialog_id: uuid.UUID,
) -> list[tuple]:
    """Return list of (DialogTopic, answer_text) for all answered topics in priority order.
    Used by formulate_recap."""
    stmt = (
        select(DialogTopic, SellerDialogTopic.answer_text)
        .join(SellerDialogTopic, SellerDialogTopic.topic_key == DialogTopic.key)
        .where(
            SellerDialogTopic.dialog_id == dialog_id,
            SellerDialogTopic.status == "answered",
        )
        .order_by(SellerDialogTopic.priority)
    )
    return [(t, a) for t, a in (await session.execute(stmt)).all()]


async def count_open(session: AsyncSession, dialog_id: uuid.UUID) -> int:
    """Count topics still pending or asked (i.e. not done)."""
    stmt = select(SellerDialogTopic).where(
        SellerDialogTopic.dialog_id == dialog_id,
        SellerDialogTopic.status.in_(("pending", "asked")),
    )
    rows = (await session.execute(stmt)).scalars().all()
    return len(rows)
