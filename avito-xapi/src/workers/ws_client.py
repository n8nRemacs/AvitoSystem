"""
WebSocket JSON-RPC client for Avito real-time messaging.

Uses curl_cffi for TLS fingerprint impersonation (Chrome 120) to bypass QRATOR.
WebSocket runs in a background thread; async methods bridge to the event loop.

Protocol: JSON-RPC 2.0 over wss://socket.avito.ru/socket
Server push events: messenger.newMessage, messenger.typing, messenger.read, messenger.updateSeq
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from concurrent.futures import Future
from typing import Any, Callable

from curl_cffi import requests as curl_requests

from src.workers.session_reader import SessionData

logger = logging.getLogger("xapi.ws")

PING_ID = 999
PING_INTERVAL = 25  # seconds
RECONNECT_MAX_ATTEMPTS = 999_999  # de facto infinite — V2 reliability
RECONNECT_MAX_DELAY = 30  # seconds


class AvitoWsClient:
    """WebSocket client for Avito socket.avito.ru (JSON-RPC 2.0).

    Uses curl_cffi's ws_connect() with Chrome 120 TLS impersonation.
    Connection and receive loop run in a daemon thread.
    """

    WS_URL = "wss://socket.avito.ru/socket"
    APP_VERSION = "215.1"

    def __init__(self, session_data: SessionData, session_loader: Callable | None = None):
        # session_loader(): SessionData — optional callback to re-fetch a fresh
        # session from DB before each reconnect (V2 reliability: token refresh).
        self.session_data = session_data
        self._session_loader = session_loader
        self._ws = None
        self._session = curl_requests.Session(impersonate="chrome120")
        self._msg_id = 0
        self._seq = 0
        self._running = False
        self._connected = asyncio.Event()
        self._user_id: str | None = None

        # Request/response correlation
        self._pending: dict[int, Future] = {}
        self._lock = threading.Lock()

        # Event handlers: event_name → list of callbacks
        self._handlers: dict[str, list[Callable]] = {
            "message": [],
            "typing": [],
            "read": [],
            "connected": [],
            "disconnected": [],
        }

        # Background threads
        self._recv_thread: threading.Thread | None = None
        self._ping_thread: threading.Thread | None = None

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    @property
    def ws_url(self) -> str:
        user_hash = self.session_data.user_hash or ""
        params = f"use_seq=true&app_name=android&id_version=v2&my_hash_id={user_hash}"
        if self._seq > 0:
            params += f"&seq={self._seq}"
        return f"{self.WS_URL}?{params}"

    def _headers(self) -> dict[str, str]:
        """Build WebSocket connection headers matching Avito's mobile app."""
        sd = self.session_data
        cookie_parts = [f"sessid={sd.session_token}"]
        if sd.cookies:
            for k, v in sd.cookies.items():
                cookie_parts.append(f"{k}={v}")

        return {
            "User-Agent": f"AVITO {self.APP_VERSION} (OnePlus LE2115; Android 14; ru)",
            "X-Session": sd.session_token,
            "X-DeviceId": sd.device_id or "",
            "X-RemoteDeviceId": sd.remote_device_id or "",
            "f": sd.fingerprint or "",
            "X-App": "avito",
            "X-Platform": "android",
            "X-AppVersion": self.APP_VERSION,
            "Cookie": "; ".join(cookie_parts),
            "X-Date": str(int(time.time())),
            "AT-v": "1",
            "Schema-Check": "0",
        }

    def _build_rpc(self, method: str, params: dict[str, Any] | None = None) -> str:
        """Build JSON-RPC 2.0 message."""
        return json.dumps({
            "id": self._next_id(),
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        })

    # ── Event system ──────────────────────────────────

    def on(self, event: str, handler: Callable) -> None:
        """Register event handler. Events: message, typing, read, connected, disconnected."""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

    def _emit(self, event: str, data: Any = None) -> None:
        """Emit event to all registered handlers."""
        for handler in self._handlers.get(event, []):
            try:
                handler(data)
            except Exception as e:
                logger.error("Event handler error (%s): %s", event, e)

    # ── Connection management ─────────────────────────

    async def connect(self) -> dict[str, Any]:
        """Connect to Avito WebSocket. Returns initial session data.

        Launches background threads for receiving and ping.
        """
        self._running = True
        self._connected.clear()

        loop = asyncio.get_event_loop()

        # Connect in thread to not block the event loop
        init_future = loop.run_in_executor(None, self._connect_sync)
        init_data = await init_future

        if init_data:
            self._connected.set()
            self._emit("connected", init_data)

            # Start receive and ping threads
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()

            self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
            self._ping_thread.start()

        return init_data or {}

    def _connect_sync(self) -> dict[str, Any] | None:
        """Synchronous WebSocket connect via curl_cffi."""
        try:
            url = self.ws_url
            headers = self._headers()
            logger.info("Connecting WS to %s", url.split("?")[0])

            self._ws = self._session.ws_connect(url, headers=headers)

            # Read initial session message.
            # curl_cffi ws.recv() may return:
            #   - tuple (data, frame_info)  — newer versions
            #   - list[bytes]               — legacy
            #   - bytes / str               — single frame
            frames = self._ws.recv()
            if frames:
                if isinstance(frames, (tuple, list)):
                    raw = frames[0]
                else:
                    raw = frames
                init_msg = json.loads(raw)
                logger.info("WS connected. Init: type=%s", init_msg.get("type"))

                # Extract userId and seq from session init
                value = init_msg.get("value", {})
                self._user_id = value.get("userId")
                self._seq = value.get("seq", 0)

                return init_msg

            logger.warning("WS connected but no init message received")
            return None

        except Exception as e:
            logger.error("WS connect failed: %s", e)
            self._ws = None
            return None

    async def disconnect(self) -> None:
        """Disconnect WebSocket and stop background threads."""
        self._running = False
        self._connected.clear()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._emit("disconnected")
        logger.info("WS disconnected")

    @property
    def is_connected(self) -> bool:
        return self._running and self._ws is not None

    # ── Background loops ──────────────────────────────

    def _recv_loop(self) -> None:
        """Background thread: receive and dispatch messages."""
        while self._running and self._ws:
            try:
                frames = self._ws.recv()
                if not frames:
                    continue

                if isinstance(frames, (tuple, list)):
                    raw = frames[0]
                else:
                    raw = frames
                data = json.loads(raw)
                self._handle_message(data)

            except json.JSONDecodeError:
                continue
            except Exception as e:
                if self._running:
                    logger.error("WS recv error: %s", e)
                    self._try_reconnect()
                break

    def _ping_loop(self) -> None:
        """Background thread: send ping every 25 seconds."""
        while self._running:
            time.sleep(PING_INTERVAL)
            if not self._running or not self._ws:
                break
            try:
                ping_msg = json.dumps({
                    "id": PING_ID,
                    "jsonrpc": "2.0",
                    "method": "ping",
                    "params": {},
                })
                with self._lock:
                    self._ws.send(ping_msg.encode())
                logger.debug("WS ping sent")
            except Exception as e:
                logger.warning("WS ping failed: %s", e)

    def _try_reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff (V2: ~infinite + token refresh)."""
        for attempt in range(RECONNECT_MAX_ATTEMPTS):
            if not self._running:
                return

            delay = min(2 ** min(attempt, 5), RECONNECT_MAX_DELAY)
            logger.info("WS reconnecting in %ds (attempt %d)", delay, attempt + 1)
            time.sleep(delay)

            # V2 token refresh: pull a fresh active session from DB before each retry
            if self._session_loader is not None:
                try:
                    fresh = self._session_loader()
                    if fresh is not None:
                        self.session_data = fresh
                except Exception as e:
                    logger.warning("session_loader failed (will retry with cached): %s", e)

            result = self._connect_sync()
            if result:
                logger.info("WS reconnected successfully (attempt %d)", attempt + 1)
                return

        logger.error("WS reconnect failed after %d attempts", RECONNECT_MAX_ATTEMPTS)
        self._running = False
        self._emit("disconnected")

    # ── Message handling ──────────────────────────────

    def _handle_message(self, data: dict[str, Any]) -> None:
        """Route incoming WS message to appropriate handler."""

        # Skip ping responses
        if data.get("id") == PING_ID:
            return

        # JSON-RPC response (has "id" matching a pending request)
        msg_id = data.get("id")
        if msg_id is not None and msg_id in self._pending:
            future = self._pending.pop(msg_id)
            if "error" in data:
                future.set_exception(
                    Exception(data["error"].get("message", str(data["error"])))
                )
            else:
                future.set_result(data.get("result"))
            return

        # Server push notification (JSON-RPC method call from server)
        method = data.get("method")
        if method:
            params = data.get("params", {})
            self._handle_notification(method, params)
            return

        # Legacy push event (type-based)
        msg_type = data.get("type", "")
        if msg_type in ("Message", "messenger.Message"):
            self._handle_push_message(data.get("value", {}))
        elif msg_type in ("ChatTyping", "messenger.ChatTyping"):
            self._emit("typing", data.get("value", {}))
        elif msg_type in ("ChatRead", "messenger.ChatRead"):
            self._emit("read", data.get("value", {}))
        elif msg_type == "session":
            # Session init on reconnect
            value = data.get("value", {})
            self._seq = value.get("seq", self._seq)

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle JSON-RPC server push notifications."""
        if method == "messenger.newMessage":
            message = params.get("message", params)
            self._handle_push_message(message)
        elif method == "messenger.typing":
            self._emit("typing", params)
        elif method == "messenger.read":
            self._emit("read", params)
        elif method == "messenger.updateSeq":
            self._seq = params.get("seq", self._seq)
        else:
            logger.debug("Unhandled WS notification: %s", method)

    def _handle_push_message(self, value: dict[str, Any]) -> None:
        """Normalize and emit an incoming message."""
        body = value.get("body", {})
        text_obj = body.get("text", {})
        text = text_obj.get("text", "") if isinstance(text_obj, dict) else str(text_obj or "")

        normalized = {
            "channel_id": value.get("channelId", ""),
            "message_id": value.get("id", ""),
            "author_id": value.get("fromUid") or value.get("authorId", ""),
            "text": text,
            "created_at": value.get("createdAt"),
            "type": value.get("type", "text"),
        }

        # Detect media types
        if body.get("image"):
            normalized["type"] = "image"
            normalized["media"] = body["image"]
        elif body.get("voice"):
            normalized["type"] = "voice"
            normalized["media"] = body["voice"]

        self._emit("message", normalized)

    # ── RPC methods (async) ───────────────────────────

    async def _send_rpc(self, method: str, params: dict[str, Any] | None = None,
                        timeout: float = 10.0) -> Any:
        """Send JSON-RPC request and wait for response."""
        if not self._ws:
            raise ConnectionError("WebSocket not connected")

        msg_id = self._next_id()
        future: Future = Future()
        self._pending[msg_id] = future

        rpc_msg = json.dumps({
            "id": msg_id,
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        })

        with self._lock:
            self._ws.send(rpc_msg.encode())

        # Wait for response in thread to not block event loop
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, future.result, timeout),
                timeout=timeout + 1,
            )
            return result
        except TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"WS RPC timeout for {method}")

    async def ping(self) -> None:
        """Send ping (done automatically by ping thread, but can be called manually)."""
        await self._send_rpc("ping", timeout=5.0)

    async def get_chats(self, limit: int = 30, category: int = 1,
                        offset_timestamp: int | None = None) -> dict[str, Any]:
        """Get chat channels via WS (avito.getChats.v5)."""
        params: dict[str, Any] = {
            "limit": limit,
            "category": category,
            "filters": {"excludeTags": ["p", "s"]},
        }
        if offset_timestamp:
            params["offsetTimestamp"] = offset_timestamp

        result = await self._send_rpc("avito.getChats.v5", params)
        return result if isinstance(result, dict) else {}

    async def get_chat_by_id(self, channel_id: str) -> dict[str, Any]:
        """Get specific chat by ID (avito.getChatById.v3)."""
        result = await self._send_rpc("avito.getChatById.v3", {"channelId": channel_id})
        return result if isinstance(result, dict) else {}

    async def get_messages(self, channel_id: str, limit: int = 50) -> dict[str, Any]:
        """Get message history (messenger.history.v2)."""
        result = await self._send_rpc("messenger.history.v2", {
            "channelId": channel_id,
            "limit": limit,
        })
        return result if isinstance(result, dict) else {}

    async def send_text_message(self, channel_id: str, text: str) -> dict[str, Any]:
        """Send text message (avito.sendTextMessage.v2)."""
        result = await self._send_rpc("avito.sendTextMessage.v2", {
            "channelId": channel_id,
            "text": text,
            "randomId": str(uuid.uuid4()),
        })
        return result if isinstance(result, dict) else {}

    async def send_typing(self, channel_id: str) -> None:
        """Send typing indicator (messenger.sendTyping.v2)."""
        await self._send_rpc("messenger.sendTyping.v2", {
            "channelId": channel_id,
            "userIds": [],
            "initActionTimestamp": int(time.time() * 1000),
        }, timeout=5.0)

    async def mark_read(self, channel_id: str, last_message_time: int | None = None) -> None:
        """Mark chat as read (messenger.readChat)."""
        params: dict[str, Any] = {"channelId": channel_id}
        if last_message_time:
            params["lastMessageTime"] = last_message_time
        await self._send_rpc("messenger.readChat", params, timeout=5.0)

    async def create_channel_by_item(self, item_id: str) -> dict[str, Any]:
        """Create chat by listing ID (avito.chatCreateByItemId.v2)."""
        result = await self._send_rpc("avito.chatCreateByItemId.v2", {"itemId": item_id})
        return result if isinstance(result, dict) else {}

    async def create_channel_by_user(self, user_id: str) -> dict[str, Any]:
        """Create direct chat by user ID (messenger.chatCreateByUserId.v2)."""
        result = await self._send_rpc("messenger.chatCreateByUserId.v2", {"opponentId": user_id})
        return result if isinstance(result, dict) else {}

    async def get_unread_count(self) -> int:
        """Get unread message count (messenger.getUnreadCount.v1)."""
        result = await self._send_rpc("messenger.getUnreadCount.v1")
        if isinstance(result, dict):
            return result.get("unreadCount", 0)
        return 0

    async def get_users(self, channel_id: str, user_ids: list[str]) -> dict[str, Any]:
        """Get user info for a channel (messenger.getUsers.v2)."""
        result = await self._send_rpc("messenger.getUsers.v2", {
            "channelId": channel_id,
            "userIds": user_ids,
        })
        return result if isinstance(result, dict) else {}
