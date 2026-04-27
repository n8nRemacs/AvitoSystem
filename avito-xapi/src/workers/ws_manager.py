"""WsManager — per-tenant WebSocket lifecycle and fan-out to SSE subscribers.

Bridge between sync WS recv_thread and async SSE generators via
loop.call_soon_threadsafe() → asyncio.Queue.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from src.workers.ws_client import AvitoWsClient
from src.workers.session_reader import SessionData, load_active_session

logger = logging.getLogger("xapi.ws_manager")

QUEUE_MAX = 256


class TenantConnection:
    """WsClient + subscriber queues for one tenant."""

    __slots__ = ("tenant_id", "client", "subscribers", "_loop")

    def __init__(self, tenant_id: str, client: AvitoWsClient, loop: asyncio.AbstractEventLoop):
        self.tenant_id = tenant_id
        self.client = client
        self.subscribers: list[asyncio.Queue] = []
        self._loop = loop

    def broadcast(self, event: dict[str, Any]) -> None:
        """Called from sync WS recv_thread — push event into every subscriber queue."""
        for q in self.subscribers[:]:
            try:
                self._loop.call_soon_threadsafe(q.put_nowait, event)
            except asyncio.QueueFull:
                logger.warning("Queue full for tenant %s, dropping event", self.tenant_id)
            except Exception:
                pass


class WsManager:
    """Singleton managing per-tenant WS connections and SSE fan-out."""

    def __init__(self):
        self._connections: dict[str, TenantConnection] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def init(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once at app startup with the running event loop."""
        self._loop = loop
        logger.info("WsManager initialized")

    async def subscribe(self, tenant_id: str) -> asyncio.Queue:
        """Subscribe to real-time events for a tenant.

        Auto-starts WS connection on first subscriber.
        Returns an asyncio.Queue that will receive event dicts.
        """
        if self._loop is None:
            raise RuntimeError("WsManager not initialized")

        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)

        if tenant_id not in self._connections:
            await self._start_connection(tenant_id)

        conn = self._connections[tenant_id]
        conn.subscribers.append(queue)
        logger.info("Subscriber added for tenant %s (total: %d)", tenant_id, len(conn.subscribers))
        return queue

    async def unsubscribe(self, tenant_id: str, queue: asyncio.Queue) -> None:
        """Remove subscriber. Auto-stops WS when no subscribers remain."""
        conn = self._connections.get(tenant_id)
        if not conn:
            return

        try:
            conn.subscribers.remove(queue)
        except ValueError:
            pass

        logger.info("Subscriber removed for tenant %s (remaining: %d)", tenant_id, len(conn.subscribers))

        if not conn.subscribers:
            await self._stop_connection(tenant_id)

    async def stop_all(self) -> None:
        """Shutdown: disconnect all WS connections."""
        tenant_ids = list(self._connections.keys())
        for tid in tenant_ids:
            await self._stop_connection(tid)
        logger.info("WsManager stopped all connections")

    def broadcast_to_tenant(
        self, tenant_id: str, event_name: str, payload: dict[str, Any]
    ) -> bool:
        """Inject an externally-sourced event into the tenant's SSE fan-out.

        Returns True when the event was queued for at least one SSE subscriber.
        Returns False when no SSE subscribers exist for that tenant — in that
        case the caller is expected to have persisted the event durably so it
        can be replayed via a catch-up query later.

        Used by the V2.1 NotificationListener pipeline: the notifications
        router calls this after persisting the row, so the messenger-bot can
        react in real-time without polling.
        """
        conn = self._connections.get(tenant_id)
        if not conn or not conn.subscribers:
            logger.info(
                "broadcast_to_tenant: no SSE subscribers for tenant %s, event=%s skipped",
                tenant_id, event_name,
            )
            return False
        event = {
            "event": event_name,
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        conn.broadcast(event)
        return True

    def get_status(self, tenant_id: str) -> dict[str, Any]:
        """Get connection status for a tenant."""
        conn = self._connections.get(tenant_id)
        if not conn:
            return {"connected": False, "subscribers": 0}
        return {
            "connected": conn.client.is_connected,
            "subscribers": len(conn.subscribers),
            "tenant_id": tenant_id,
        }

    def get_all_status(self) -> dict[str, Any]:
        """Get status of all active connections."""
        return {
            "total_connections": len(self._connections),
            "connections": {tid: self.get_status(tid) for tid in self._connections},
        }

    # ── Internal ─────────────────────────────────────

    async def _start_connection(self, tenant_id: str) -> None:
        """Load session and start WS connection for tenant."""
        session = load_active_session(tenant_id)
        if not session:
            raise ValueError(f"No active session for tenant {tenant_id}")

        # V2 reliability: re-fetch active session from DB on each reconnect
        # so we pick up freshly synced JWT (APK refreshes tokens every ~24h).
        client = AvitoWsClient(session, session_loader=lambda: load_active_session(tenant_id))
        conn = TenantConnection(tenant_id, client, self._loop)

        def _make_handler(event_type: str):
            def handler(data):
                event = {
                    "event": event_type,
                    "tenant_id": tenant_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": data or {},
                }
                conn.broadcast(event)
            return handler

        client.on("message", _make_handler("new_message"))
        client.on("typing", _make_handler("typing"))
        client.on("read", _make_handler("read"))
        client.on("disconnected", _make_handler("disconnected"))

        self._connections[tenant_id] = conn

        try:
            await client.connect()
            logger.info("WS connected for tenant %s", tenant_id)
        except Exception as e:
            del self._connections[tenant_id]
            raise ConnectionError(f"WS connect failed for tenant {tenant_id}: {e}")

    async def _stop_connection(self, tenant_id: str) -> None:
        """Stop WS connection and remove from registry."""
        conn = self._connections.pop(tenant_id, None)
        if not conn:
            return
        try:
            await conn.client.disconnect()
        except Exception as e:
            logger.warning("Error disconnecting tenant %s: %s", tenant_id, e)
        logger.info("WS disconnected for tenant %s", tenant_id)


# Singleton
ws_manager = WsManager()
