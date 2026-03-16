"""
Avito Client
WebSocket and HTTP client for Avito Messenger API
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
from aiohttp import WSMsgType

import sys
sys.path.insert(0, "..")
from shared.utils import (
    build_avito_headers, build_ws_url,
    extract_channel_info, extract_message_info,
    parse_jwt, RateLimiter
)
from shared.config import settings


class ConnectionState(str, Enum):
    """WebSocket connection state"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass
class AvitoSession:
    """Avito session data"""
    session_token: str
    fingerprint: str
    device_id: str
    user_id: int
    user_hash: str
    remote_device_id: Optional[str] = None
    user_agent: Optional[str] = None


@dataclass
class AvitoMessage:
    """Avito message"""
    id: str
    channel_id: str
    author_id: str
    text: str
    message_type: str = "text"
    created: int = 0
    is_incoming: bool = True


class AvitoClient:
    """
    Avito Messenger client

    Handles:
    - WebSocket connection for real-time messages
    - HTTP API for sending messages and getting chat list
    - Auto-reconnect with exponential backoff
    """

    BASE_URL = "https://api.avito.ru"
    MESSENGER_URL = "https://m.avito.ru"

    def __init__(
        self,
        session: AvitoSession,
        on_message: Optional[Callable[[AvitoMessage], None]] = None,
        on_connect: Optional[Callable[[], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None
    ):
        self.session = session
        self.on_message = on_message
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect

        self.state = ConnectionState.DISCONNECTED
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._ping_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._seq = 0  # Message sequence number

        self._rate_limiter = RateLimiter(max_calls=30, period_seconds=60)

    @property
    def headers(self) -> Dict[str, str]:
        """Get HTTP headers for API requests"""
        return build_avito_headers(
            session_token=self.session.session_token,
            fingerprint=self.session.fingerprint,
            device_id=self.session.device_id,
            remote_device_id=self.session.remote_device_id,
            user_agent=self.session.user_agent
        )

    async def start(self) -> None:
        """Start the client"""
        self._running = True
        self._http_session = aiohttp.ClientSession()
        await self._connect_ws()

    async def stop(self) -> None:
        """Stop the client"""
        self._running = False

        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._ws and not self._ws.closed:
            await self._ws.close()

        if self._http_session:
            await self._http_session.close()

        self.state = ConnectionState.DISCONNECTED

    async def _connect_ws(self) -> None:
        """Connect to WebSocket"""
        if not self._running:
            return

        self.state = ConnectionState.CONNECTING

        ws_url = build_ws_url(self.session.user_hash)

        try:
            self._ws = await self._http_session.ws_connect(
                ws_url,
                headers=self.headers,
                heartbeat=30.0,
                timeout=30.0
            )

            self.state = ConnectionState.CONNECTED
            self._reconnect_attempts = 0
            self._seq = 0

            print(f"WebSocket connected for user {self.session.user_id}")

            if self.on_connect:
                self.on_connect()

            # Start ping and receive tasks
            self._ping_task = asyncio.create_task(self._ping_loop())
            self._receive_task = asyncio.create_task(self._receive_loop())

        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.state = ConnectionState.DISCONNECTED
            await self._schedule_reconnect()

    async def _schedule_reconnect(self) -> None:
        """Schedule reconnection with exponential backoff"""
        if not self._running:
            return

        if self._reconnect_attempts >= self._max_reconnect_attempts:
            print("Max reconnection attempts reached")
            if self.on_disconnect:
                self.on_disconnect()
            return

        self.state = ConnectionState.RECONNECTING
        self._reconnect_attempts += 1

        # Exponential backoff: 1, 2, 4, 8, 16, 32, 60, 60...
        delay = min(60, 2 ** (self._reconnect_attempts - 1))
        print(f"Reconnecting in {delay}s (attempt {self._reconnect_attempts})")

        await asyncio.sleep(delay)
        await self._connect_ws()

    async def _ping_loop(self) -> None:
        """Send periodic pings to keep connection alive"""
        while self._running and self.state == ConnectionState.CONNECTED:
            try:
                await asyncio.sleep(25)

                if self._ws and not self._ws.closed:
                    ping_msg = {
                        "t": "ping",
                        "ts": int(time.time() * 1000)
                    }
                    await self._ws.send_json(ping_msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Ping error: {e}")
                break

    async def _receive_loop(self) -> None:
        """Receive and process WebSocket messages"""
        while self._running and self.state == ConnectionState.CONNECTED:
            try:
                msg = await self._ws.receive(timeout=60.0)

                if msg.type == WSMsgType.TEXT:
                    await self._handle_ws_message(json.loads(msg.data))

                elif msg.type == WSMsgType.CLOSED:
                    print("WebSocket closed by server")
                    break

                elif msg.type == WSMsgType.ERROR:
                    print(f"WebSocket error: {msg.data}")
                    break

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Receive error: {e}")
                break

        # Connection lost, try to reconnect
        if self._running:
            self.state = ConnectionState.DISCONNECTED
            if self.on_disconnect:
                self.on_disconnect()
            await self._schedule_reconnect()

    async def _handle_ws_message(self, data: Dict[str, Any]) -> None:
        """Handle incoming WebSocket message"""
        msg_type = data.get("t")

        if msg_type == "pong":
            # Ping response, ignore
            pass

        elif msg_type == "message":
            # New message
            payload = data.get("payload", {})
            message = payload.get("message", {})

            if message and self.on_message:
                msg_info = extract_message_info(message)

                avito_msg = AvitoMessage(
                    id=msg_info["id"],
                    channel_id=msg_info["channel_id"],
                    author_id=str(msg_info["author_id"]),
                    text=msg_info["text"],
                    message_type=msg_info["type"],
                    created=msg_info["created"],
                    is_incoming=str(msg_info["author_id"]) != str(self.session.user_id)
                )

                self.on_message(avito_msg)

        elif msg_type == "ack":
            # Acknowledgement of our message
            self._seq = data.get("seq", self._seq)

        elif msg_type == "typing":
            # User is typing, can be ignored or handled
            pass

        else:
            print(f"Unknown WS message type: {msg_type}")

    # ============== HTTP API Methods ==============

    async def get_channels(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get list of chat channels

        Returns list of channels with last message and user info
        """
        await self._rate_limiter.wait_if_needed()

        url = f"{self.MESSENGER_URL}/api/1/messenger/getChannels"
        params = {
            "limit": limit,
            "offset": offset
        }

        try:
            async with self._http_session.get(url, headers=self.headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    channels = data.get("channels", [])
                    return [extract_channel_info(ch) for ch in channels]
                else:
                    print(f"Get channels error: {resp.status}")
                    return []

        except Exception as e:
            print(f"Get channels exception: {e}")
            return []

    async def get_messages(
        self,
        channel_id: str,
        limit: int = 50,
        before_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get messages from channel

        Args:
            channel_id: Channel ID
            limit: Number of messages to fetch
            before_id: Get messages before this ID (for pagination)

        Returns list of messages
        """
        await self._rate_limiter.wait_if_needed()

        url = f"{self.MESSENGER_URL}/api/1/messenger/getMessages"
        params = {
            "channelId": channel_id,
            "limit": limit
        }

        if before_id:
            params["beforeId"] = before_id

        try:
            async with self._http_session.get(url, headers=self.headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    messages = data.get("messages", [])
                    return [extract_message_info(m) for m in messages]
                else:
                    print(f"Get messages error: {resp.status}")
                    return []

        except Exception as e:
            print(f"Get messages exception: {e}")
            return []

    async def send_message(self, channel_id: str, text: str) -> Optional[str]:
        """
        Send text message to channel

        Args:
            channel_id: Channel ID
            text: Message text

        Returns message ID if successful
        """
        await self._rate_limiter.wait_if_needed()

        url = f"{self.MESSENGER_URL}/api/1/messenger/sendMessage"

        payload = {
            "channelId": channel_id,
            "body": {
                "text": {
                    "text": text
                }
            }
        }

        try:
            async with self._http_session.post(url, headers=self.headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("id")
                else:
                    error_text = await resp.text()
                    print(f"Send message error: {resp.status} - {error_text}")
                    return None

        except Exception as e:
            print(f"Send message exception: {e}")
            return None

    async def mark_read(self, channel_id: str, message_id: str) -> bool:
        """
        Mark messages as read up to message_id

        Args:
            channel_id: Channel ID
            message_id: Last read message ID

        Returns True if successful
        """
        await self._rate_limiter.wait_if_needed()

        url = f"{self.MESSENGER_URL}/api/1/messenger/markRead"

        payload = {
            "channelId": channel_id,
            "messageId": message_id
        }

        try:
            async with self._http_session.post(url, headers=self.headers, json=payload) as resp:
                return resp.status == 200

        except Exception as e:
            print(f"Mark read exception: {e}")
            return False

    async def get_user_info(self) -> Optional[Dict[str, Any]]:
        """
        Get current user info

        Returns user profile data
        """
        await self._rate_limiter.wait_if_needed()

        url = f"{self.BASE_URL}/api/1/users/self"

        try:
            async with self._http_session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    print(f"Get user info error: {resp.status}")
                    return None

        except Exception as e:
            print(f"Get user info exception: {e}")
            return None

    async def send_typing(self, channel_id: str) -> bool:
        """
        Send typing indicator

        Args:
            channel_id: Channel ID

        Returns True if successful
        """
        if not self._ws or self._ws.closed:
            return False

        try:
            typing_msg = {
                "t": "typing",
                "payload": {
                    "channelId": channel_id
                }
            }
            await self._ws.send_json(typing_msg)
            return True

        except Exception as e:
            print(f"Send typing exception: {e}")
            return False


class AvitoClientPool:
    """
    Pool of Avito clients for managing multiple accounts

    Handles:
    - Creating and managing multiple AvitoClient instances
    - Routing messages to correct handlers
    - Health monitoring
    """

    def __init__(self):
        self.clients: Dict[str, AvitoClient] = {}  # user_id -> client
        self._message_handlers: Dict[str, Callable[[AvitoMessage], None]] = {}

    async def add_client(
        self,
        user_id: str,
        session: AvitoSession,
        message_handler: Optional[Callable[[AvitoMessage], None]] = None
    ) -> AvitoClient:
        """Add and start a new client"""
        if user_id in self.clients:
            await self.remove_client(user_id)

        client = AvitoClient(
            session=session,
            on_message=lambda msg: self._route_message(user_id, msg),
            on_connect=lambda: print(f"Client {user_id} connected"),
            on_disconnect=lambda: print(f"Client {user_id} disconnected")
        )

        if message_handler:
            self._message_handlers[user_id] = message_handler

        await client.start()
        self.clients[user_id] = client

        return client

    async def remove_client(self, user_id: str) -> None:
        """Stop and remove a client"""
        if user_id in self.clients:
            await self.clients[user_id].stop()
            del self.clients[user_id]

        if user_id in self._message_handlers:
            del self._message_handlers[user_id]

    def _route_message(self, user_id: str, message: AvitoMessage) -> None:
        """Route message to handler"""
        if user_id in self._message_handlers:
            self._message_handlers[user_id](message)

    def get_client(self, user_id: str) -> Optional[AvitoClient]:
        """Get client by user ID"""
        return self.clients.get(user_id)

    async def stop_all(self) -> None:
        """Stop all clients"""
        for client in self.clients.values():
            await client.stop()
        self.clients.clear()
        self._message_handlers.clear()

    def get_status(self) -> Dict[str, str]:
        """Get status of all clients"""
        return {
            user_id: client.state.value
            for user_id, client in self.clients.items()
        }
