"""
Avito -> Telegram Bridge
Forwards Avito messages to Telegram and allows replies
"""
import asyncio
import json
import time
import logging
from pathlib import Path
from datetime import datetime

import websocket
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configuration
CONFIG = {
    "telegram_token": "",  # Set your bot token here
    "telegram_chat_id": "",  # Set your chat ID here
    "avito_session_file": "avito_session_new.json",
}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class AvitoClient:
    """Avito WebSocket client"""

    def __init__(self, session_file):
        data = json.loads(Path(session_file).read_text())
        self.sessid = data["session_token"]
        self.device_id = data["session_data"]["device_id"]
        self.ws = None
        self.req_id = 0
        self.user_id = None
        self.connected = False
        self.channels = {}  # channelId -> user info

    def connect(self):
        ws_url = "wss://socket.avito.ru/socket?use_seq=true&app_name=android"
        headers = [
            f"Cookie: sessid={self.sessid}",
            f"X-Session: {self.sessid}",
            f"X-DeviceId: {self.device_id}",
            "X-App: avito",
            "X-Platform: android",
        ]

        self.ws = websocket.WebSocket()
        self.ws.connect(ws_url, header=headers)

        # Session init
        msg = self.ws.recv()
        data = json.loads(msg)
        if data.get("type") == "session":
            self.user_id = data["value"]["userId"]
            self.connected = True
            return True
        return False

    def send_rpc(self, method, params=None):
        self.req_id += 1
        msg = {
            "id": self.req_id,
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        self.ws.send(json.dumps(msg))

    def send_message(self, channel_id, text):
        """Send message to Avito chat"""
        import uuid
        self.send_rpc("avito.sendTextMessage.v2", {
            "channelId": channel_id,
            "randomId": str(uuid.uuid4()),
            "text": text,
            "initActionTimestamp": int(time.time() * 1000)
        })

    def recv(self, timeout=1):
        """Receive message with timeout"""
        self.ws.settimeout(timeout)
        try:
            msg = self.ws.recv()
            return json.loads(msg) if msg else None
        except:
            return None

    def ping(self):
        self.send_rpc("ping", {})


class AvitoTelegramBridge:
    """Bridge between Avito and Telegram"""

    def __init__(self, config):
        self.config = config
        self.avito = AvitoClient(config["avito_session_file"])
        self.bot = Bot(config["telegram_token"])
        self.chat_id = config["telegram_chat_id"]
        self.running = False
        self.last_channel = None  # For quick replies

    async def send_to_telegram(self, text, parse_mode=None):
        """Send message to Telegram"""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    def format_avito_message(self, data):
        """Format Avito message for Telegram"""
        v = data.get("value", {})
        body = v.get("body", {})
        msg_type = v.get("type", "unknown")
        channel_id = v.get("channelId", "")

        # Store channel for replies
        self.last_channel = channel_id

        text_parts = ["📩 *Новое сообщение Avito*\n"]

        if msg_type == "text":
            text_parts.append(f"💬 {body.get('text', '[пусто]')}")
        elif msg_type == "image":
            text_parts.append(f"🖼 Изображение: {body.get('imageId', '?')}")
        elif msg_type == "voice":
            text_parts.append(f"🎤 Голосовое сообщение")
        elif msg_type == "location":
            text_parts.append(f"📍 Локация: {body.get('title', '?')}")
        else:
            text_parts.append(f"[{msg_type}]")

        text_parts.append(f"\n\n_Channel: {channel_id[:30]}..._")

        return "\n".join(text_parts)

    async def avito_listener(self):
        """Listen for Avito messages"""
        logger.info("Starting Avito listener...")

        if not self.avito.connect():
            logger.error("Failed to connect to Avito")
            return

        logger.info(f"Connected to Avito. User ID: {self.avito.user_id}")
        await self.send_to_telegram("✅ Avito bridge подключен!")

        last_ping = time.time()

        while self.running:
            # Ping every 25 seconds
            if time.time() - last_ping > 25:
                self.avito.ping()
                last_ping = time.time()

            # Receive message
            data = self.avito.recv(timeout=1)
            if not data:
                continue

            msg_type = data.get("type") or data.get("type_v2", "")

            if msg_type in ["Message", "messenger.Message"]:
                text = self.format_avito_message(data)
                await self.send_to_telegram(text, parse_mode="Markdown")

            elif msg_type == "ChatTyping":
                v = data.get("value", {})
                channel = v.get("channelId", "")[:20]
                await self.send_to_telegram(f"⌨️ _Печатает в {channel}..._", parse_mode="Markdown")

            elif "result" in data and data.get("result") != "pong":
                logger.info(f"RPC result: {data}")

    async def handle_telegram_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle message from Telegram -> send to Avito"""
        if not self.last_channel:
            await update.message.reply_text("❌ Нет активного чата. Дождитесь сообщения от Avito.")
            return

        text = update.message.text
        self.avito.send_message(self.last_channel, text)
        await update.message.reply_text(f"✅ Отправлено в Avito")

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "🤖 *Avito Telegram Bridge*\n\n"
            "Этот бот пересылает сообщения из Avito.\n"
            "Чтобы ответить - просто напишите сообщение.",
            parse_mode="Markdown"
        )

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        status = "🟢 Подключен" if self.avito.connected else "🔴 Отключен"
        await update.message.reply_text(
            f"*Статус:* {status}\n"
            f"*User ID:* {self.avito.user_id}\n"
            f"*Последний чат:* {self.last_channel[:30] if self.last_channel else 'нет'}...",
            parse_mode="Markdown"
        )

    async def run(self):
        """Run the bridge"""
        self.running = True

        # Start Telegram bot
        app = Application.builder().token(self.config["telegram_token"]).build()

        app.add_handler(CommandHandler("start", self.handle_start))
        app.add_handler(CommandHandler("status", self.handle_status))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_telegram_message))

        # Start both
        async with app:
            await app.start()
            logger.info("Telegram bot started")

            # Run Avito listener
            await self.avito_listener()

            await app.stop()


def main():
    print("="*50)
    print("Avito -> Telegram Bridge")
    print("="*50)

    if not CONFIG["telegram_token"]:
        print("\n[!] Set telegram_token in CONFIG!")
        print("    1. Create bot via @BotFather")
        print("    2. Copy token to CONFIG['telegram_token']")
        return

    if not CONFIG["telegram_chat_id"]:
        print("\n[!] Set telegram_chat_id in CONFIG!")
        print("    1. Send /start to your bot")
        print("    2. Get chat_id from @userinfobot")
        print("    3. Copy to CONFIG['telegram_chat_id']")
        return

    bridge = AvitoTelegramBridge(CONFIG)
    asyncio.run(bridge.run())


if __name__ == "__main__":
    main()
