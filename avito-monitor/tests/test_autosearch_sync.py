"""Tests for autosearch_sync orchestration layer (Task 18).

These tests cover only the per-account loop in ``sync_all_autosearches``:
iteration, cooldown skip, and per-account exception handling.
The internal upsert logic inside ``_sync_for_account`` is NOT tested here.
"""
import pytest
from unittest.mock import AsyncMock

from app.services.account_pool import AccountNotAvailableError


@pytest.mark.asyncio
async def test_sync_iterates_active_accounts(monkeypatch):
    """sync_all_autosearches calls _sync_for_account once per active account."""
    pool = AsyncMock()
    pool.list_active_accounts.return_value = [
        {"id": "acc-1", "nickname": "Clone"},
        {"id": "acc-2", "nickname": "Other"},
    ]
    pool.claim_for_sync.side_effect = [
        {"session_token": "T1"},
        {"session_token": "T2"},
    ]

    sync_called_with = []

    async def fake_sync_for_account(acc, session):
        sync_called_with.append(acc["id"])

    from app.services import autosearch_sync as mod
    monkeypatch.setattr(mod, "_sync_for_account", fake_sync_for_account)

    await mod.sync_all_autosearches(pool)
    assert sync_called_with == ["acc-1", "acc-2"]


@pytest.mark.asyncio
async def test_sync_skips_unavailable_accounts(monkeypatch):
    """Accounts returning AccountNotAvailableError are skipped; others proceed."""
    pool = AsyncMock()
    pool.list_active_accounts.return_value = [
        {"id": "acc-1", "nickname": "Clone"},
        {"id": "acc-2", "nickname": "Other"},
    ]
    pool.claim_for_sync.side_effect = [
        AccountNotAvailableError("acc-1", "cooldown"),
        {"session_token": "T2"},
    ]

    sync_called_with = []

    async def fake_sync_for_account(acc, session):
        sync_called_with.append(acc["id"])

    from app.services import autosearch_sync as mod
    monkeypatch.setattr(mod, "_sync_for_account", fake_sync_for_account)

    await mod.sync_all_autosearches(pool)
    assert sync_called_with == ["acc-2"]  # acc-1 was skipped


@pytest.mark.asyncio
async def test_sync_handles_per_account_exception(monkeypatch):
    """If _sync_for_account raises for one account, the loop continues with the next."""
    pool = AsyncMock()
    pool.list_active_accounts.return_value = [
        {"id": "acc-1", "nickname": "Clone"},
        {"id": "acc-2", "nickname": "Other"},
    ]
    pool.claim_for_sync.side_effect = [
        {"session_token": "T1"},
        {"session_token": "T2"},
    ]

    visited = []

    async def fake_sync_for_account(acc, session):
        visited.append(acc["id"])
        if acc["id"] == "acc-1":
            raise RuntimeError("simulated failure on acc-1")

    from app.services import autosearch_sync as mod
    monkeypatch.setattr(mod, "_sync_for_account", fake_sync_for_account)

    # Should not raise — exception is caught, loop continues
    await mod.sync_all_autosearches(pool)
    assert visited == ["acc-1", "acc-2"]
