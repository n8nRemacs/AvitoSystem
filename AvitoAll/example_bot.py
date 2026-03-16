"""
Example Avito Messenger Bot
Demonstrates usage of AvitoMessengerClient and AvitoSessionManager
"""

import asyncio
import logging
from avito_messenger_client import AvitoMessengerClient, AvitoSession, Message, Channel
from avito_session_manager import AvitoSessionManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AvitoBot")


class AvitoBot:
    """Simple Avito Messenger Bot"""

    def __init__(self, session_file: str = "avito_session.json"):
        self.session_manager = AvitoSessionManager(session_file)
        self.client: AvitoMessengerClient = None
        self.running = False

    async def start(self):
        """Start the bot"""
        # Load or create session
        if not self.session_manager.load_session():
            logger.error("No session found. Run session_manager first to authenticate.")
            return False

        # Validate session
        async with self.session_manager:
            if not await self.session_manager.validate_session():
                logger.error("Session is invalid or expired. Re-authenticate.")
                return False

        # Create client
        session = AvitoSession(
            sessid=self.session_manager.session.sessid,
            user_id=self.session_manager.session.user_id,
            user_hash=self.session_manager.session.user_hash,
            device_id=self.session_manager.session.device_id
        )
        self.client = AvitoMessengerClient(session)

        # Register handlers
        self._register_handlers()

        # Connect
        self.running = True
        logger.info("Starting bot...")
        await self.client.connect()

    def _register_handlers(self):
        """Register event handlers"""

        @self.client.on_message
        async def on_message(message: Message):
            await self._handle_message(message)

        @self.client.on("connected")
        async def on_connected():
            logger.info("Bot connected to Avito Messenger!")
            await self._on_ready()

        @self.client.on("disconnected")
        async def on_disconnected():
            logger.warning("Bot disconnected from Avito Messenger")

        @self.client.on("error")
        async def on_error(error):
            logger.error(f"Bot error: {error}")

    async def _on_ready(self):
        """Called when bot is ready"""
        # Get channel list
        channels = await self.client.get_channels(limit=5)
        logger.info(f"Found {len(channels)} channels:")
        for ch in channels:
            logger.info(f"  - {ch.title} (unread: {ch.unread_count})")

    async def _handle_message(self, message: Message):
        """Handle incoming messages"""
        # Skip own messages
        if message.author_id == self.session_manager.session.user_hash:
            return

        logger.info(f"New message from {message.author_name}: {message.text}")

        # Simple command handling
        text = (message.text or "").lower().strip()

        if text == "/help":
            await self.client.send_message(
                message.channel_id,
                "Available commands:\n"
                "/help - Show this help\n"
                "/ping - Check bot status\n"
                "/info - Get channel info"
            )

        elif text == "/ping":
            await self.client.send_message(message.channel_id, "Pong!")

        elif text == "/info":
            channel = await self.client.get_channel_by_id(message.channel_id)
            if channel:
                await self.client.send_message(
                    message.channel_id,
                    f"Channel: {channel.title}\n"
                    f"ID: {channel.id}\n"
                    f"Item: {channel.item_id or 'N/A'}"
                )

        # Auto-reply example (disabled by default)
        # elif "hello" in text or "hi" in text:
        #     await self.client.send_message(message.channel_id, "Hello! How can I help?")

    async def stop(self):
        """Stop the bot"""
        self.running = False
        if self.client:
            await self.client.disconnect()
        logger.info("Bot stopped")


# ============ Simple Usage Examples ============

async def example_list_chats():
    """Example: List all chats"""
    manager = AvitoSessionManager()

    if not manager.load_session():
        print("No session found")
        return

    session = AvitoSession(
        sessid=manager.session.sessid,
        device_id=manager.session.device_id
    )

    client = AvitoMessengerClient(session)

    # Initialize HTTP session for API calls
    import aiohttp
    client._http_session = aiohttp.ClientSession(headers=client._get_headers())

    channels = await client.http_get_channels(limit=20)

    print(f"\n=== Your Chats ({len(channels)}) ===\n")
    for ch in channels:
        unread = f"[{ch.unread_count} unread]" if ch.unread_count else ""
        print(f"- {ch.title} {unread}")
        print(f"  ID: {ch.id}")
        if ch.last_message:
            print(f"  Last: {ch.last_message.text[:50]}..." if ch.last_message.text and len(ch.last_message.text) > 50 else f"  Last: {ch.last_message.text}")
        print()

    await client.disconnect()


async def example_send_message():
    """Example: Send a message to a channel"""
    manager = AvitoSessionManager()

    if not manager.load_session():
        print("No session found")
        return

    channel_id = input("Enter channel ID: ").strip()
    text = input("Enter message: ").strip()

    session = AvitoSession(
        sessid=manager.session.sessid,
        device_id=manager.session.device_id
    )

    client = AvitoMessengerClient(session)

    # Initialize HTTP session
    import aiohttp
    client._http_session = aiohttp.ClientSession(headers=client._get_headers())

    success = await client.http_send_message(channel_id, text)

    if success:
        print("Message sent!")
    else:
        print("Failed to send message")

    await client.disconnect()


async def example_monitor_chats():
    """Example: Monitor chats for new messages (WebSocket)"""
    manager = AvitoSessionManager()

    if not manager.load_session():
        print("No session found")
        return

    session = AvitoSession(
        sessid=manager.session.sessid,
        user_hash=manager.session.user_hash,
        device_id=manager.session.device_id
    )

    client = AvitoMessengerClient(session)

    @client.on_message
    async def on_message(message: Message):
        print(f"\n[{message.author_name}]: {message.text}")

    @client.on("connected")
    async def on_connected():
        print("Connected! Monitoring messages... (Ctrl+C to stop)")

    try:
        await client.connect()
    except KeyboardInterrupt:
        pass
    finally:
        await client.disconnect()


# ============ Main Entry Point ============

async def main():
    """Main entry point"""
    print("\n=== Avito Messenger Bot Examples ===\n")
    print("1. Run bot (auto-reply)")
    print("2. List chats")
    print("3. Send message")
    print("4. Monitor messages")
    print("5. Setup session (login)")

    choice = input("\nSelect option (1-5): ").strip()

    if choice == "1":
        bot = AvitoBot()
        try:
            await bot.start()
        except KeyboardInterrupt:
            await bot.stop()

    elif choice == "2":
        await example_list_chats()

    elif choice == "3":
        await example_send_message()

    elif choice == "4":
        await example_monitor_chats()

    elif choice == "5":
        from avito_session_manager import interactive_login
        await interactive_login()


if __name__ == "__main__":
    asyncio.run(main())
