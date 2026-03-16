"""
Avito Messenger Client - Server-side implementation
Based on reverse engineering of Avito Android app

Similar to Baileys for WhatsApp - provides programmatic access to Avito messenger
"""

import asyncio
import json
import uuid
import time
import logging
import aiohttp
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AvitoMessenger")


class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    VOICE = "voice"
    SYSTEM = "system"


@dataclass
class AvitoSession:
    """Session data for Avito authentication"""
    sessid: str
    user_id: Optional[str] = None
    user_hash: Optional[str] = None
    device_id: Optional[str] = None

    def __post_init__(self):
        if not self.device_id:
            self.device_id = str(uuid.uuid4())


@dataclass
class Message:
    """Represents a messenger message"""
    id: str
    channel_id: str
    author_id: str
    author_name: str
    body_type: str
    text: Optional[str]
    created: int
    status: str


@dataclass
class Channel:
    """Represents a chat channel"""
    id: str
    title: str
    last_message: Optional[Message]
    unread_count: int
    item_id: Optional[str]
    participants: List[str] = field(default_factory=list)


class AvitoMessengerClient:
    """
    Avito Messenger WebSocket Client

    Usage:
        session = AvitoSession(sessid="your_session_token")
        client = AvitoMessengerClient(session)

        @client.on_message
        async def handle_message(message):
            print(f"New message: {message.text}")

        await client.connect()
    """

    # API Endpoints
    WS_URL = "wss://socket.avito.ru/messenger"
    HTTP_API = "https://app.avito.ru/api/1/messenger"

    # Headers for mobile API
    DEFAULT_HEADERS = {
        "User-Agent": "AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
        "X-App": "avito",
        "Origin": "https://www.avito.ru",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    def __init__(self, session: AvitoSession):
        self.session = session
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._request_id = 0
        self._seq = 0
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._event_handlers: Dict[str, List[Callable]] = {
            "message": [],
            "typing": [],
            "read": [],
            "connected": [],
            "disconnected": [],
            "error": [],
        }
        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._ping_task: Optional[asyncio.Task] = None

    # ============ Event System ============

    def on(self, event: str):
        """Decorator to register event handlers"""
        def decorator(func: Callable):
            self._event_handlers.setdefault(event, []).append(func)
            return func
        return decorator

    def on_message(self, func: Callable):
        """Decorator for message events"""
        self._event_handlers["message"].append(func)
        return func

    def on_typing(self, func: Callable):
        """Decorator for typing events"""
        self._event_handlers["typing"].append(func)
        return func

    async def _emit(self, event: str, *args, **kwargs):
        """Emit event to all registered handlers"""
        for handler in self._event_handlers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in event handler for {event}: {e}")

    # ============ Connection Management ============

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with session authentication"""
        headers = self.DEFAULT_HEADERS.copy()
        headers["Cookie"] = f"sessid={self.session.sessid}"
        headers["X-Session"] = self.session.sessid
        headers["X-DeviceId"] = self.session.device_id
        headers["X-Request-Id"] = str(uuid.uuid4())
        return headers

    def _get_ws_url(self) -> str:
        """Build WebSocket URL with query parameters"""
        params = {
            "seq": self._seq,
            "id_version": "v2",
        }
        if self.session.user_hash:
            params["my_hash_id"] = self.session.user_hash

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.WS_URL}?{query}"

    async def connect(self):
        """Establish WebSocket connection"""
        if self._running:
            logger.warning("Already connected")
            return

        self._http_session = aiohttp.ClientSession(headers=self._get_headers())

        # First, get user info via HTTP API
        await self._fetch_user_info()

        # Connect WebSocket
        await self._connect_ws()

    async def _fetch_user_info(self):
        """Fetch current user info from HTTP API"""
        try:
            async with self._http_session.post(
                f"{self.HTTP_API}/getChannels",
                json={"category": 0, "filters": {}, "limit": 1, "offsetTimestamp": None}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Extract user hash from response if available
                    if "result" in data and "myUserId" in data.get("result", {}):
                        self.session.user_hash = data["result"]["myUserId"]
                        logger.info(f"User hash: {self.session.user_hash}")
                else:
                    logger.warning(f"Failed to fetch user info: {resp.status}")
        except Exception as e:
            logger.error(f"Error fetching user info: {e}")

    async def _connect_ws(self):
        """Connect to WebSocket"""
        try:
            ws_url = self._get_ws_url()
            logger.info(f"Connecting to WebSocket...")

            self._ws = await self._http_session.ws_connect(
                ws_url,
                headers=self._get_headers(),
                heartbeat=30.0,
            )

            self._running = True
            self._reconnect_attempts = 0
            logger.info("WebSocket connected")

            await self._emit("connected")

            # Start ping task
            self._ping_task = asyncio.create_task(self._ping_loop())

            # Start message loop
            await self._message_loop()

        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            await self._emit("error", e)
            await self._handle_reconnect()

    async def _message_loop(self):
        """Main message receiving loop"""
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {msg.data}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("WebSocket closed")
                    break
        except Exception as e:
            logger.error(f"Message loop error: {e}")
        finally:
            self._running = False
            await self._emit("disconnected")
            await self._handle_reconnect()

    async def _handle_reconnect(self):
        """Handle reconnection logic"""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            return

        self._reconnect_attempts += 1
        wait_time = min(30, 2 ** self._reconnect_attempts)
        logger.info(f"Reconnecting in {wait_time}s (attempt {self._reconnect_attempts})")

        await asyncio.sleep(wait_time)
        await self._connect_ws()

    async def _ping_loop(self):
        """Send periodic ping to keep connection alive"""
        while self._running:
            try:
                await asyncio.sleep(25)
                if self._running and self._ws and not self._ws.closed:
                    await self._send_rpc("ping", {})
            except Exception as e:
                logger.error(f"Ping error: {e}")

    async def disconnect(self):
        """Close connection"""
        self._running = False

        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        if self._ws and not self._ws.closed:
            await self._ws.close()

        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

        logger.info("Disconnected")

    # ============ JSON-RPC Protocol ============

    def _next_request_id(self) -> str:
        """Generate unique request ID"""
        self._request_id += 1
        return f"req_{self._request_id}_{uuid.uuid4().hex[:8]}"

    async def _send_rpc(self, method: str, params: Dict[str, Any], wait_response: bool = True) -> Optional[Dict]:
        """Send JSON-RPC request"""
        if not self._ws or self._ws.closed:
            raise ConnectionError("WebSocket not connected")

        request_id = self._next_request_id()
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": request_id
        }

        logger.debug(f"Sending: {method}")
        await self._ws.send_json(message)

        if wait_response:
            future = asyncio.get_event_loop().create_future()
            self._pending_requests[request_id] = future

            try:
                result = await asyncio.wait_for(future, timeout=30.0)
                return result
            except asyncio.TimeoutError:
                logger.error(f"Request timeout: {method}")
                self._pending_requests.pop(request_id, None)
                return None

        return None

    async def _handle_message(self, data: str):
        """Handle incoming WebSocket message"""
        try:
            msg = json.loads(data)

            # Handle JSON-RPC response
            if "id" in msg and msg["id"] in self._pending_requests:
                future = self._pending_requests.pop(msg["id"])
                if "error" in msg:
                    future.set_exception(Exception(msg["error"].get("message", "Unknown error")))
                else:
                    future.set_result(msg.get("result"))
                return

            # Handle server push notifications
            if "method" in msg:
                await self._handle_notification(msg["method"], msg.get("params", {}))

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON: {data[:100]}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def _handle_notification(self, method: str, params: Dict):
        """Handle server-side notifications"""
        logger.debug(f"Notification: {method}")

        if method == "messenger.newMessage":
            message = self._parse_message(params.get("message", {}))
            if message:
                await self._emit("message", message)

        elif method == "messenger.typing":
            await self._emit("typing", params)

        elif method == "messenger.read":
            await self._emit("read", params)

        elif method == "messenger.updateSeq":
            self._seq = params.get("seq", self._seq)

    def _parse_message(self, data: Dict) -> Optional[Message]:
        """Parse message data into Message object"""
        try:
            body = data.get("body", {})
            author = data.get("author", {})

            return Message(
                id=data.get("id", ""),
                channel_id=data.get("channelId", ""),
                author_id=author.get("id", ""),
                author_name=author.get("name", ""),
                body_type=body.get("type", "text"),
                text=body.get("text"),
                created=data.get("created", 0),
                status=data.get("status", "sent")
            )
        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            return None

    # ============ Messenger API Methods ============

    async def get_channels(self, category: int = 0, limit: int = 20, offset_timestamp: int = None) -> List[Channel]:
        """
        Get list of chat channels

        Args:
            category: 0=all, 1=unread, 6=favorites
            limit: Number of channels to fetch
            offset_timestamp: Pagination timestamp
        """
        result = await self._send_rpc("avito.getChats.v5", {
            "category": category,
            "filters": {},
            "limit": limit,
            "offsetTimestamp": offset_timestamp
        })

        channels = []
        if result and "chats" in result:
            for chat in result["chats"]:
                channels.append(Channel(
                    id=chat.get("id", ""),
                    title=chat.get("title", ""),
                    last_message=self._parse_message(chat.get("lastMessage", {})),
                    unread_count=chat.get("unreadCount", 0),
                    item_id=chat.get("context", {}).get("itemId"),
                    participants=chat.get("participantIds", [])
                ))

        return channels

    async def get_channel_by_id(self, channel_id: str) -> Optional[Channel]:
        """Get specific channel by ID"""
        result = await self._send_rpc("avito.getChatById.v3", {
            "channelId": channel_id
        })

        if result and "chat" in result:
            chat = result["chat"]
            return Channel(
                id=chat.get("id", ""),
                title=chat.get("title", ""),
                last_message=self._parse_message(chat.get("lastMessage", {})),
                unread_count=chat.get("unreadCount", 0),
                item_id=chat.get("context", {}).get("itemId"),
                participants=chat.get("participantIds", [])
            )

        return None

    async def get_messages(self, channel_id: str, limit: int = 50, before: str = None, after: str = None) -> List[Message]:
        """
        Get message history for a channel

        Args:
            channel_id: Channel ID
            limit: Number of messages
            before: Get messages before this message ID
            after: Get messages after this message ID
        """
        result = await self._send_rpc("messenger.history.v2", {
            "channelId": channel_id,
            "limit": limit,
            "before": before,
            "after": after
        })

        messages = []
        if result and "messages" in result:
            for msg_data in result["messages"]:
                message = self._parse_message(msg_data)
                if message:
                    messages.append(message)

        return messages

    async def send_message(self, channel_id: str, text: str, quote_message_id: str = None) -> Optional[Message]:
        """
        Send a text message

        Args:
            channel_id: Target channel ID
            text: Message text
            quote_message_id: Optional message ID to quote/reply to
        """
        random_id = str(uuid.uuid4())

        result = await self._send_rpc("avito.sendTextMessage.v2", {
            "channelId": channel_id,
            "randomId": random_id,
            "text": text,
            "templates": [],
            "quoteMessageId": quote_message_id,
            "chunkIndex": None,
            "xHash": None,
            "initActionTimestamp": int(time.time() * 1000)
        })

        if result and "message" in result:
            return self._parse_message(result["message"])

        return None

    async def send_typing(self, channel_id: str, user_ids: List[str] = None):
        """Send typing indicator"""
        await self._send_rpc("messenger.sendTyping.v2", {
            "channelId": channel_id,
            "userIds": user_ids or [],
            "initActionTimestamp": int(time.time() * 1000)
        }, wait_response=False)

    async def read_chat(self, channel_id: str, last_message_time: int = None):
        """Mark channel as read"""
        if last_message_time is None:
            last_message_time = int(time.time() * 1000)

        await self._send_rpc("messenger.readChat", {
            "channelId": channel_id,
            "lastMessageTime": last_message_time
        })

    async def create_chat_by_item(self, item_id: str) -> Optional[Channel]:
        """Create chat for a listing/item"""
        result = await self._send_rpc("avito.chatCreateByItemId.v2", {
            "itemId": item_id,
            "source": None,
            "extra": None,
            "xHash": None
        })

        if result and "chat" in result:
            chat = result["chat"]
            return Channel(
                id=chat.get("id", ""),
                title=chat.get("title", ""),
                last_message=None,
                unread_count=0,
                item_id=item_id,
                participants=chat.get("participantIds", [])
            )

        return None

    async def create_chat_by_user(self, user_id: str) -> Optional[Channel]:
        """Create direct chat with user"""
        result = await self._send_rpc("messenger.chatCreateByUserId.v2", {
            "opponentId": user_id
        })

        if result and "chat" in result:
            chat = result["chat"]
            return Channel(
                id=chat.get("id", ""),
                title=chat.get("title", ""),
                last_message=None,
                unread_count=0,
                item_id=None,
                participants=[user_id]
            )

        return None

    async def get_users(self, channel_id: str, user_ids: List[str]) -> Dict[str, Dict]:
        """Get user information"""
        result = await self._send_rpc("messenger.getUsers.v2", {
            "channelId": channel_id,
            "userIds": user_ids
        })

        return result.get("users", {}) if result else {}

    # ============ HTTP API Methods ============

    async def http_get_channels(self, category: int = 0, limit: int = 20) -> List[Channel]:
        """Get channels via HTTP API (fallback)"""
        try:
            async with self._http_session.post(
                f"{self.HTTP_API}/getChannels",
                json={
                    "category": category,
                    "filters": {},
                    "limit": limit,
                    "offsetTimestamp": None
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    channels = []
                    for chat in data.get("result", {}).get("chats", []):
                        channels.append(Channel(
                            id=chat.get("id", ""),
                            title=chat.get("title", ""),
                            last_message=self._parse_message(chat.get("lastMessage", {})),
                            unread_count=chat.get("unreadCount", 0),
                            item_id=chat.get("context", {}).get("itemId"),
                            participants=chat.get("participantIds", [])
                        ))
                    return channels
        except Exception as e:
            logger.error(f"HTTP get_channels error: {e}")

        return []

    async def http_send_message(self, channel_id: str, text: str) -> bool:
        """Send message via HTTP API (fallback)"""
        try:
            async with self._http_session.post(
                f"{self.HTTP_API}/sendTextMessage",
                json={
                    "channelId": channel_id,
                    "text": text,
                    "idempotencyKey": str(uuid.uuid4()),
                    "chunkIndex": None,
                    "quoteMessageId": None,
                    "source": None,
                    "xHash": None
                }
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"HTTP send_message error: {e}")

        return False


# ============ Example Usage ============

async def main():
    """Example usage of AvitoMessengerClient"""

    # Create session with your sessid token
    # You can get this from browser cookies after logging in to avito.ru
    session = AvitoSession(
        sessid="YOUR_SESSION_TOKEN_HERE"
    )

    client = AvitoMessengerClient(session)

    # Register event handlers
    @client.on_message
    async def handle_new_message(message: Message):
        print(f"\n[New Message] {message.author_name}: {message.text}")

        # Auto-reply example (commented out)
        # if "hello" in message.text.lower():
        #     await client.send_message(message.channel_id, "Hi there!")

    @client.on("typing")
    async def handle_typing(data):
        print(f"[Typing] Someone is typing...")

    @client.on("connected")
    async def on_connected():
        print("[Connected] WebSocket connected!")

        # Fetch channels
        channels = await client.get_channels(limit=10)
        print(f"\nFound {len(channels)} channels:")
        for ch in channels:
            print(f"  - {ch.title} ({ch.id})")

    @client.on("disconnected")
    async def on_disconnected():
        print("[Disconnected] WebSocket disconnected")

    @client.on("error")
    async def on_error(error):
        print(f"[Error] {error}")

    try:
        # Connect and run
        await client.connect()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
