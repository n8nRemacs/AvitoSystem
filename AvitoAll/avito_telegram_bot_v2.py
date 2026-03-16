"""
Avito Messenger -> Telegram Bot Bridge v2
Stable version with watchdog, auto-reconnect, and health monitoring
"""
import json
import asyncio
import aiohttp
import logging
import signal
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, List
import base64

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('AvitoBot')

# === CONFIGURATION ===
TELEGRAM_BOT_TOKEN = "8244492730:AAErO55dU1We-UvJOK84aKYCMWXlONgh4z4"
SESSION_FILE = Path("avito_session_new.json")

# Timeouts
WS_RECV_TIMEOUT = 60  # seconds
PING_INTERVAL = 25  # seconds
HEALTH_CHECK_INTERVAL = 30  # seconds
RECONNECT_BASE_DELAY = 5  # seconds
RECONNECT_MAX_DELAY = 120  # seconds


@dataclass
class BotState:
    """Centralized bot state"""
    admin_chat_id: Optional[int] = None
    current_channel: Optional[str] = None
    channels_cache: List[dict] = field(default_factory=list)
    user_names: Dict[str, str] = field(default_factory=dict)

    # Health metrics
    ws_connected: bool = False
    last_ws_message: datetime = field(default_factory=datetime.now)
    last_ping_sent: datetime = field(default_factory=datetime.now)
    last_ping_recv: datetime = field(default_factory=datetime.now)
    reconnect_count: int = 0
    messages_forwarded: int = 0
    start_time: datetime = field(default_factory=datetime.now)


class AvitoSession:
    """Manages Avito session with auto-refresh"""

    def __init__(self):
        self.load()

    def load(self):
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        self.token = data["session_token"]
        self.refresh_token = data.get("refresh_token", "")
        self.device_id = data["session_data"]["device_id"]
        self.fingerprint = data["session_data"]["fingerprint"]
        self.remote_id = data["session_data"]["remote_device_id"]
        self.cookies = data["session_data"]["cookies"]
        self.user_hash = "4c48533419806d790635e8565693e5c2"
        self.user_id = 157920214
        self._parse_expiry()

    def _parse_expiry(self):
        """Parse JWT expiration time"""
        try:
            parts = self.token.split('.')
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
            self.expires_at = datetime.fromtimestamp(payload['exp'])
        except:
            self.expires_at = datetime.now() + timedelta(hours=24)

    def is_expired(self) -> bool:
        return datetime.now() >= self.expires_at

    def hours_until_expiry(self) -> float:
        return (self.expires_at - datetime.now()).total_seconds() / 3600

    def headers(self) -> dict:
        cookie_str = f"sessid={self.token}"
        for k, v in self.cookies.items():
            cookie_str += f"; {k}={v}"
        return {
            "Cookie": cookie_str,
            "X-Session": self.token,
            "X-DeviceId": self.device_id,
            "X-RemoteDeviceId": self.remote_id,
            "f": self.fingerprint,
            "X-App": "avito",
            "X-Platform": "android",
            "X-AppVersion": "215.1",
            "User-Agent": "AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
            "Content-Type": "application/json",
        }

    def ws_url(self) -> str:
        return f"wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={self.user_hash}"


class AvitoTelegramBridge:
    """Main bridge class with robust error handling"""

    def __init__(self):
        self.session = AvitoSession()
        self.state = BotState()
        self.http: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._shutdown = False
        self._ws_lock = asyncio.Lock()
        self._reconnect_delay = RECONNECT_BASE_DELAY

    async def start(self):
        """Start the bridge"""
        log.info("Starting Avito -> Telegram Bridge v2")

        # Setup signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                asyncio.get_event_loop().add_signal_handler(sig, self._signal_handler)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                signal.signal(sig, lambda s, f: self._signal_handler())

        self.http = aiohttp.ClientSession()

        # Load initial channels
        await self._load_channels()

        # Start all tasks
        tasks = [
            asyncio.create_task(self._websocket_loop(), name="websocket"),
            asyncio.create_task(self._telegram_loop(), name="telegram"),
            asyncio.create_task(self._ping_loop(), name="ping"),
            asyncio.create_task(self._watchdog_loop(), name="watchdog"),
        ]

        log.info("All tasks started. Send /start to bot.")

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            log.info("Tasks cancelled")
        finally:
            await self._cleanup()

    def _signal_handler(self):
        log.info("Shutdown signal received")
        self._shutdown = True

    async def _cleanup(self):
        """Clean shutdown"""
        if self.ws and not self.ws.closed:
            await self.ws.close()
        if self.http and not self.http.closed:
            await self.http.close()
        log.info("Cleanup complete")

    # === HTTP API ===

    async def _api_call(self, endpoint: str, payload: dict) -> dict:
        """Make Avito API call with error handling"""
        url = f"https://app.avito.ru/api/1/messenger/{endpoint}"
        try:
            async with self.http.post(url, headers=self.session.headers(), json=payload, timeout=15) as resp:
                data = await resp.json()
                return data.get("success", {})
        except Exception as e:
            log.error(f"API error ({endpoint}): {e}")
            return {}

    async def _load_channels(self):
        """Load channels and cache user names"""
        log.info("Loading channels...")
        result = await self._api_call("getChannels", {"category": 1, "filters": {}, "limit": 100})
        channels = result.get("channels", [])

        for ch in channels:
            for user in ch.get("users", []):
                if isinstance(user, dict):
                    uid = user.get("id", "")
                    name = user.get("name", "")
                    if uid and name:
                        self.state.user_names[uid] = name

        log.info(f"Cached {len(self.state.user_names)} users from {len(channels)} channels")

    async def get_channels(self, limit=15) -> List[dict]:
        result = await self._api_call("getChannels", {"category": 1, "filters": {}, "limit": limit})
        self.state.channels_cache = result.get("channels", [])
        return self.state.channels_cache

    async def get_messages(self, channel_id: str, limit=10) -> List[dict]:
        result = await self._api_call("getUserVisibleMessages", {"channelId": channel_id, "limit": limit})
        return result.get("messages", [])

    async def send_avito_message(self, channel_id: str, text: str) -> bool:
        import uuid
        result = await self._api_call("sendTextMessage", {
            "channelId": channel_id,
            "text": text,
            "idempotencyKey": str(uuid.uuid4()),
        })
        return bool(result)

    # === WebSocket ===

    async def _connect_ws(self):
        """Connect to Avito WebSocket"""
        async with self._ws_lock:
            if self.ws and not self.ws.closed:
                await self.ws.close()

            log.info("Connecting to WebSocket...")
            try:
                self.ws = await self.http.ws_connect(
                    self.session.ws_url(),
                    headers=self.session.headers(),
                    heartbeat=30,
                    timeout=15
                )

                # Read init message
                msg = await asyncio.wait_for(self.ws.receive(), timeout=10)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("type") == "session":
                        log.info(f"WebSocket connected! User: {data['value']['userId']}")
                        self.state.ws_connected = True
                        self.state.last_ws_message = datetime.now()
                        self._reconnect_delay = RECONNECT_BASE_DELAY
                        return True

            except Exception as e:
                log.error(f"WebSocket connect failed: {e}")

            self.state.ws_connected = False
            return False

    async def _websocket_loop(self):
        """Main WebSocket listening loop with auto-reconnect"""
        while not self._shutdown:
            try:
                # Connect if needed
                if not self.state.ws_connected or not self.ws or self.ws.closed:
                    if not await self._connect_ws():
                        await asyncio.sleep(self._reconnect_delay)
                        self._reconnect_delay = min(self._reconnect_delay * 2, RECONNECT_MAX_DELAY)
                        self.state.reconnect_count += 1
                        continue

                # Receive with timeout
                try:
                    msg = await asyncio.wait_for(self.ws.receive(), timeout=WS_RECV_TIMEOUT)
                except asyncio.TimeoutError:
                    log.warning("WebSocket recv timeout, will reconnect")
                    self.state.ws_connected = False
                    continue

                if msg.type == aiohttp.WSMsgType.TEXT:
                    self.state.last_ws_message = datetime.now()
                    await self._handle_ws_message(json.loads(msg.data))

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    log.warning("WebSocket closed by server")
                    self.state.ws_connected = False

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    log.error(f"WebSocket error: {self.ws.exception()}")
                    self.state.ws_connected = False

            except Exception as e:
                log.error(f"WebSocket loop error: {e}")
                self.state.ws_connected = False
                await asyncio.sleep(1)

    async def _handle_ws_message(self, data: dict):
        """Process incoming WebSocket message"""
        # Skip ping responses
        if data.get("id") == 999:
            self.state.last_ping_recv = datetime.now()
            return

        msg_type = data.get("type", "")

        if msg_type == "Message":
            value = data.get("value", {})
            from_uid = value.get("fromUid", "")

            # Skip own messages
            if from_uid == self.session.user_hash:
                return

            # Extract text
            body = value.get("body", {})
            txt_obj = body.get("text", {})
            if isinstance(txt_obj, dict):
                text = txt_obj.get("text", "")
            else:
                text = str(txt_obj) if txt_obj else ""

            if not text:
                if body.get("imageId"):
                    text = "[Image]"
                elif body.get("voiceId"):
                    text = "[Voice]"
                else:
                    text = "[Media]"

            sender = self.state.user_names.get(from_uid, from_uid[:8] + "...")
            log.info(f"MSG from {sender}: {text[:50]}")

            if self.state.admin_chat_id:
                await self._send_telegram(f"<b>{sender}</b>\n{text}")
                self.state.messages_forwarded += 1

    async def _ping_loop(self):
        """Send periodic pings to keep WebSocket alive"""
        while not self._shutdown:
            await asyncio.sleep(PING_INTERVAL)

            if self.state.ws_connected and self.ws and not self.ws.closed:
                try:
                    ping_msg = json.dumps({"id": 999, "jsonrpc": "2.0", "method": "ping", "params": {}})
                    await self.ws.send_str(ping_msg)
                    self.state.last_ping_sent = datetime.now()
                    log.debug("Ping sent")
                except Exception as e:
                    log.error(f"Ping failed: {e}")
                    self.state.ws_connected = False

    async def _watchdog_loop(self):
        """Monitor health and trigger reconnect if needed"""
        last_session_mtime = SESSION_FILE.stat().st_mtime if SESSION_FILE.exists() else 0

        while not self._shutdown:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

            now = datetime.now()

            # Check if session file was updated (token refreshed)
            if SESSION_FILE.exists():
                current_mtime = SESSION_FILE.stat().st_mtime
                if current_mtime > last_session_mtime:
                    log.info("Session file changed! Reloading...")
                    last_session_mtime = current_mtime
                    old_token = self.session.token[:20]
                    self.session.load()
                    new_token = self.session.token[:20]

                    if old_token != new_token:
                        log.info(f"Token updated! Old: {old_token}... New: {new_token}...")
                        if self.state.admin_chat_id:
                            await self._send_telegram(
                                f"Token refreshed!\n"
                                f"New expiry: {self.session.hours_until_expiry():.1f}h\n"
                                f"Reconnecting..."
                            )
                        # Force reconnect with new token
                        self.state.ws_connected = False
                    else:
                        log.info("Session file changed but token is the same")

            # Check if WebSocket is stale
            ws_age = (now - self.state.last_ws_message).total_seconds()
            if ws_age > WS_RECV_TIMEOUT * 2 and self.state.ws_connected:
                log.warning(f"WebSocket stale ({ws_age:.0f}s), forcing reconnect")
                self.state.ws_connected = False

            # Check session expiry
            hours_left = self.session.hours_until_expiry()
            if hours_left < 1:
                log.warning(f"Session expires in {hours_left:.1f}h!")
                if self.state.admin_chat_id:
                    await self._send_telegram(f"Session expires in {hours_left:.1f}h! Please refresh.")

            # Log health status
            log.debug(f"Health: ws={self.state.ws_connected}, reconnects={self.state.reconnect_count}, fwd={self.state.messages_forwarded}")

    # === Telegram ===

    async def _send_telegram(self, text: str, chat_id: int = None):
        """Send message to Telegram"""
        chat_id = chat_id or self.state.admin_chat_id
        if not chat_id:
            return

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            async with self.http.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML"
            }, timeout=10) as resp:
                if resp.status != 200:
                    log.error(f"Telegram send failed: {resp.status}")
        except Exception as e:
            log.error(f"Telegram error: {e}")

    async def _telegram_loop(self):
        """Handle Telegram bot commands"""
        offset = 0

        while not self._shutdown:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                async with self.http.get(url, params={"offset": offset, "timeout": 5}, timeout=15) as resp:
                    data = await resp.json()

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    await self._handle_telegram_update(update)

            except Exception as e:
                log.error(f"Telegram loop error: {e}")
                await asyncio.sleep(5)

            await asyncio.sleep(0.5)

    async def _handle_telegram_update(self, update: dict):
        """Process Telegram command"""
        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "")

        if not chat_id or not text:
            return

        log.info(f"TG command: {text}")

        if text == "/start":
            self.state.admin_chat_id = chat_id
            await self._send_telegram(
                "Avito Bridge v2 Active!\n\n"
                "/chats - list chats\n"
                "/select N - select chat\n"
                "/history - view messages\n"
                "/status - bot health",
                chat_id
            )

        elif text == "/status":
            uptime = datetime.now() - self.state.start_time
            hours_left = self.session.hours_until_expiry()
            status = (
                f"<b>Status:</b>\n"
                f"WS Connected: {'Yes' if self.state.ws_connected else 'No'}\n"
                f"Reconnects: {self.state.reconnect_count}\n"
                f"Messages forwarded: {self.state.messages_forwarded}\n"
                f"Uptime: {uptime}\n"
                f"Session expires: {hours_left:.1f}h"
            )
            await self._send_telegram(status, chat_id)

        elif text == "/chats":
            channels = await self.get_channels()
            msg_text = "<b>Chats:</b>\n\n"
            for i, ch in enumerate(channels):
                users = ch.get("users", [])
                name = users[0].get("name", "?") if users else "?"
                unread = ch.get("unreadCount", 0)
                mark = f" ({unread})" if unread else ""
                msg_text += f"{i}. {name}{mark}\n"
            await self._send_telegram(msg_text, chat_id)

        elif text.startswith("/select"):
            try:
                idx = int(text.split()[1])
                if self.state.channels_cache and 0 <= idx < len(self.state.channels_cache):
                    self.state.current_channel = self.state.channels_cache[idx].get("id")
                    users = self.state.channels_cache[idx].get("users", [])
                    name = users[0].get("name", "?") if users else "?"
                    await self._send_telegram(f"Selected: {name}", chat_id)
                else:
                    await self._send_telegram("Use /chats first", chat_id)
            except:
                await self._send_telegram("Usage: /select N", chat_id)

        elif text == "/history":
            if not self.state.current_channel:
                await self._send_telegram("Use /select N first", chat_id)
            else:
                messages = await self.get_messages(self.state.current_channel)
                msg_text = "<b>History:</b>\n\n"
                for m in reversed(messages):
                    body = m.get("body", {})
                    txt_obj = body.get("text", {})
                    txt = txt_obj.get("text", "[media]") if isinstance(txt_obj, dict) else str(txt_obj or "[media]")
                    author = m.get("authorId", "")
                    name = self.state.user_names.get(author, author[:8] + "...")
                    msg_text += f"<b>{name}:</b> {txt[:60]}\n\n"
                await self._send_telegram(msg_text, chat_id)

        elif text == "/reconnect":
            self.state.ws_connected = False
            await self._send_telegram("Forcing reconnect...", chat_id)

        elif not text.startswith("/"):
            if not self.state.current_channel:
                await self._send_telegram("Use /select N first", chat_id)
            else:
                if await self.send_avito_message(self.state.current_channel, text):
                    await self._send_telegram("Sent!", chat_id)
                else:
                    await self._send_telegram("Send failed", chat_id)


async def main():
    bridge = AvitoTelegramBridge()
    await bridge.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted")
