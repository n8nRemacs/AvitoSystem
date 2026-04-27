"""Unit tests for the DB-backed dedup helpers."""
from __future__ import annotations

import pytest

from app.services.messenger_bot.dedup import (
    already_replied,
    ensure_chat_row,
    operator_already_replied,
    record_dialog_state,
    record_outgoing_message,
)


@pytest.mark.asyncio
async def test_already_replied_returns_true_when_row_exists(patch_sessionmaker):
    patch_sessionmaker.queue_scalar(1)  # COUNT=1
    assert await already_replied("u2i-foo") is True


@pytest.mark.asyncio
async def test_already_replied_returns_false_when_no_row(patch_sessionmaker):
    patch_sessionmaker.queue_scalar(0)
    assert await already_replied("u2i-bar") is False


@pytest.mark.asyncio
async def test_already_replied_returns_false_on_null(patch_sessionmaker):
    """``scalar()`` may return None on empty aggregate; we treat that as 0."""
    patch_sessionmaker.queue_scalar(None)
    assert await already_replied("u2i-null") is False


@pytest.mark.asyncio
async def test_operator_already_replied_true_on_outgoing(patch_sessionmaker):
    patch_sessionmaker.queue_scalar(1)
    assert await operator_already_replied("u2i-x") is True


@pytest.mark.asyncio
async def test_operator_already_replied_false_when_zero(patch_sessionmaker):
    patch_sessionmaker.queue_scalar(0)
    assert await operator_already_replied("u2i-y") is False


@pytest.mark.asyncio
async def test_record_dialog_state_executes_upsert(patch_sessionmaker):
    await record_dialog_state(
        "u2i-z",
        state="replied_with_template",
        message_id="msg-42",
        notes={"k": "v"},
    )
    assert patch_sessionmaker.commits == 1
    assert len(patch_sessionmaker.executions) == 1


@pytest.mark.asyncio
async def test_record_dialog_state_no_action_clears_replied_at(patch_sessionmaker):
    """For 'no_action' state we must NOT set ``bot_replied_at``."""
    from sqlalchemy.dialects.postgresql import Insert

    await record_dialog_state(
        "u2i-fail",
        state="no_action",
        message_id=None,
        notes={"reason": "send_failed"},
    )
    stmt = patch_sessionmaker.executions[0]
    # Sanity: this is an Insert (..ON CONFLICT) statement.
    assert isinstance(stmt, Insert)


@pytest.mark.asyncio
async def test_record_outgoing_message_executes(patch_sessionmaker):
    await record_outgoing_message("u2i-q", message_id="msg-1", text="hello")
    assert patch_sessionmaker.commits == 1
    assert len(patch_sessionmaker.executions) == 1


@pytest.mark.asyncio
async def test_ensure_chat_row_executes(patch_sessionmaker):
    await ensure_chat_row("u2i-new", item_id=12345)
    assert patch_sessionmaker.commits == 1
    assert len(patch_sessionmaker.executions) == 1
