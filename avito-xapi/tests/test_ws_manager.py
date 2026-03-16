"""Tests for WsManager — per-tenant WS lifecycle and fan-out."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.workers.ws_manager import WsManager, TenantConnection, QUEUE_MAX


@pytest.fixture
def loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def manager(loop):
    mgr = WsManager()
    mgr.init(loop)
    return mgr


def _make_mock_session():
    return MagicMock(
        id="s1",
        tenant_id="tenant-1",
        session_token="tok",
        refresh_token=None,
        device_id="dev",
        fingerprint="fp",
        remote_device_id="rdev",
        user_hash="hash",
        user_id=99999999,
        cookies=None,
        source="android",
        is_active=True,
        expires_at=None,
        created_at="2024-01-01",
    )


# ── TenantConnection tests ──────────────────────────

def test_broadcast_puts_event_in_queues(loop):
    client = MagicMock()
    conn = TenantConnection("t1", client, loop)

    q1 = asyncio.Queue(maxsize=QUEUE_MAX)
    q2 = asyncio.Queue(maxsize=QUEUE_MAX)
    conn.subscribers = [q1, q2]

    event = {"event": "new_message", "payload": {"text": "hi"}}
    conn.broadcast(event)

    # Run pending callbacks
    loop.run_until_complete(asyncio.sleep(0))

    assert not q1.empty()
    assert not q2.empty()
    assert q1.get_nowait() == event
    assert q2.get_nowait() == event


def test_broadcast_handles_full_queue(loop):
    """Full queue → event dropped, no exception."""
    client = MagicMock()
    conn = TenantConnection("t1", client, loop)

    q = asyncio.Queue(maxsize=1)
    conn.subscribers = [q]

    # Fill the queue
    loop.call_soon(q.put_nowait, {"event": "filler"})
    loop.run_until_complete(asyncio.sleep(0))

    # This should not raise
    conn.broadcast({"event": "new_message"})
    loop.run_until_complete(asyncio.sleep(0))

    # Queue still has 1 item (the filler)
    assert q.qsize() == 1


# ── WsManager tests ─────────────────────────────────

def test_init_sets_loop(loop):
    mgr = WsManager()
    mgr.init(loop)
    assert mgr._loop is loop


@pytest.mark.asyncio
async def test_subscribe_starts_ws():
    """First subscribe auto-starts WS connection."""
    mgr = WsManager()
    mgr.init(asyncio.get_running_loop())

    mock_session = _make_mock_session()
    mock_client = MagicMock()
    mock_client.connect = AsyncMock(return_value={})
    mock_client.is_connected = True
    mock_client.on = MagicMock()

    with patch("src.workers.ws_manager.load_active_session", return_value=mock_session), \
         patch("src.workers.ws_manager.AvitoWsClient", return_value=mock_client):
        queue = await mgr.subscribe("tenant-1")

    assert isinstance(queue, asyncio.Queue)
    assert "tenant-1" in mgr._connections
    assert len(mgr._connections["tenant-1"].subscribers) == 1
    mock_client.connect.assert_awaited_once()

    # Cleanup
    await mgr.stop_all()


@pytest.mark.asyncio
async def test_subscribe_no_session_raises():
    """subscribe() raises ValueError when no active session."""
    mgr = WsManager()
    mgr.init(asyncio.get_running_loop())

    with patch("src.workers.ws_manager.load_active_session", return_value=None):
        with pytest.raises(ValueError, match="No active session"):
            await mgr.subscribe("tenant-missing")


@pytest.mark.asyncio
async def test_unsubscribe_stops_ws_when_empty():
    """Last unsubscribe auto-stops WS connection."""
    mgr = WsManager()
    mgr.init(asyncio.get_running_loop())

    mock_session = _make_mock_session()
    mock_client = MagicMock()
    mock_client.connect = AsyncMock(return_value={})
    mock_client.disconnect = AsyncMock()
    mock_client.is_connected = True
    mock_client.on = MagicMock()

    with patch("src.workers.ws_manager.load_active_session", return_value=mock_session), \
         patch("src.workers.ws_manager.AvitoWsClient", return_value=mock_client):
        queue = await mgr.subscribe("tenant-1")

    await mgr.unsubscribe("tenant-1", queue)
    assert "tenant-1" not in mgr._connections
    mock_client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_multiple_subscribers_share_connection():
    """Two subscribers → one WS connection, two queues."""
    mgr = WsManager()
    mgr.init(asyncio.get_running_loop())

    mock_session = _make_mock_session()
    mock_client = MagicMock()
    mock_client.connect = AsyncMock(return_value={})
    mock_client.disconnect = AsyncMock()
    mock_client.is_connected = True
    mock_client.on = MagicMock()

    with patch("src.workers.ws_manager.load_active_session", return_value=mock_session), \
         patch("src.workers.ws_manager.AvitoWsClient", return_value=mock_client):
        q1 = await mgr.subscribe("tenant-1")
        q2 = await mgr.subscribe("tenant-1")

    # Only one connect call
    assert mock_client.connect.await_count == 1
    assert len(mgr._connections["tenant-1"].subscribers) == 2

    # Unsubscribe first — WS stays alive
    await mgr.unsubscribe("tenant-1", q1)
    assert "tenant-1" in mgr._connections

    # Unsubscribe second — WS stops
    await mgr.unsubscribe("tenant-1", q2)
    assert "tenant-1" not in mgr._connections


@pytest.mark.asyncio
async def test_get_status_no_connection():
    mgr = WsManager()
    mgr.init(asyncio.get_running_loop())
    status = mgr.get_status("nonexistent")
    assert status["connected"] is False
    assert status["subscribers"] == 0


@pytest.mark.asyncio
async def test_get_status_with_connection():
    mgr = WsManager()
    mgr.init(asyncio.get_running_loop())

    mock_session = _make_mock_session()
    mock_client = MagicMock()
    mock_client.connect = AsyncMock(return_value={})
    mock_client.is_connected = True
    mock_client.on = MagicMock()

    with patch("src.workers.ws_manager.load_active_session", return_value=mock_session), \
         patch("src.workers.ws_manager.AvitoWsClient", return_value=mock_client):
        await mgr.subscribe("tenant-1")

    status = mgr.get_status("tenant-1")
    assert status["connected"] is True
    assert status["subscribers"] == 1

    await mgr.stop_all()


@pytest.mark.asyncio
async def test_stop_all():
    """stop_all disconnects every tenant."""
    mgr = WsManager()
    mgr.init(asyncio.get_running_loop())

    mock_session = _make_mock_session()
    mock_client = MagicMock()
    mock_client.connect = AsyncMock(return_value={})
    mock_client.disconnect = AsyncMock()
    mock_client.is_connected = True
    mock_client.on = MagicMock()

    with patch("src.workers.ws_manager.load_active_session", return_value=mock_session), \
         patch("src.workers.ws_manager.AvitoWsClient", return_value=mock_client):
        await mgr.subscribe("tenant-1")

    await mgr.stop_all()
    assert len(mgr._connections) == 0
    mock_client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_failure_raises():
    """WS connect failure → ConnectionError, no dangling entry."""
    mgr = WsManager()
    mgr.init(asyncio.get_running_loop())

    mock_session = _make_mock_session()
    mock_client = MagicMock()
    mock_client.connect = AsyncMock(side_effect=Exception("Connection refused"))
    mock_client.on = MagicMock()

    with patch("src.workers.ws_manager.load_active_session", return_value=mock_session), \
         patch("src.workers.ws_manager.AvitoWsClient", return_value=mock_client):
        with pytest.raises(ConnectionError, match="WS connect failed"):
            await mgr.subscribe("tenant-1")

    assert "tenant-1" not in mgr._connections
