"""
MCP Manager
Multi-account manager for Avito SmartFree

Orchestrates:
- Multiple Avito WebSocket connections
- Single Telegram bot
- Message routing between platforms
- Token refresh coordination with Token Farm
"""

import asyncio
from datetime import datetime
from typing import Dict, Optional, List, Any
from uuid import UUID
from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher
from aiogram.types import Message as TgMessage
import httpx

import sys
sys.path.insert(0, "..")
from shared.database import (
    get_db, init_db, close_db,
    AccountRepository, SessionRepository, TelegramUserRepository
)
from shared.models import Account, Session, AccountStatus, TelegramUser
from shared.config import settings
from shared.utils import parse_jwt

from avito_client import AvitoClient, AvitoSession, AvitoMessage, AvitoClientPool
from telegram_bot import create_bot, router


@dataclass
class AccountConnection:
    """Account connection state"""
    account_id: UUID
    user_id: int
    user_hash: str
    client: Optional[AvitoClient] = None
    connected: bool = False
    last_error: Optional[str] = None
    telegram_users: List[int] = field(default_factory=list)


class MCPManager:
    """
    Main MCP Manager

    Manages:
    - Pool of Avito clients (one per account)
    - Single Telegram bot
    - Message routing
    - Token Farm communication
    """

    def __init__(self):
        # Telegram
        self.bot: Optional[Bot] = None
        self.dispatcher: Optional[Dispatcher] = None

        # Avito
        self.avito_pool = AvitoClientPool()
        self.connections: Dict[str, AccountConnection] = {}  # account_id -> connection

        # Token Farm client
        self.farm_client: Optional[httpx.AsyncClient] = None

        # State
        self._running = False
        self._refresh_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the MCP Manager"""
        print("Starting MCP Manager...")

        # Initialize database
        await init_db()
        print("Database initialized")

        # Create Token Farm client
        if settings.farm_api_url:
            self.farm_client = httpx.AsyncClient(
                base_url=settings.farm_api_url,
                headers={"X-API-Key": settings.farm_api_key or ""},
                timeout=30.0
            )
            print(f"Token Farm client initialized: {settings.farm_api_url}")

        # Create and start Telegram bot
        self.bot, self.dispatcher = create_bot()

        # Register message handler for Avito forwarding
        router.message.register(
            self._handle_telegram_message,
            lambda m: m.text and not m.text.startswith("/")
        )

        # Load active accounts
        await self._load_accounts()
        print(f"Loaded {len(self.connections)} accounts")

        self._running = True

        # Start background tasks
        self._refresh_task = asyncio.create_task(self._token_refresh_loop())
        self._health_task = asyncio.create_task(self._health_check_loop())

        # Start bot polling (blocking)
        print("Starting Telegram bot polling...")
        await self.dispatcher.start_polling(self.bot)

    async def stop(self) -> None:
        """Stop the MCP Manager"""
        print("Stopping MCP Manager...")
        self._running = False

        # Stop background tasks
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        # Stop all Avito clients
        await self.avito_pool.stop_all()

        # Close farm client
        if self.farm_client:
            await self.farm_client.aclose()

        # Close database
        await close_db()

        print("MCP Manager stopped")

    async def _load_accounts(self) -> None:
        """Load active accounts from database"""
        db = await get_db()
        async with db.session() as session:
            repo = AccountRepository(session)
            session_repo = SessionRepository(session)
            tg_repo = TelegramUserRepository(session)

            accounts = await repo.get_all(status=AccountStatus.ACTIVE)

            for account in accounts:
                # Get active session
                active_session = await session_repo.get_active(account.id)
                if not active_session:
                    print(f"No active session for {account.phone}, skipping")
                    continue

                # Get linked Telegram users
                # This would need a query to find TG users linked to this account
                # For now, we'll connect on first message

                # Create connection
                await self._connect_account(account, active_session)

    async def _connect_account(self, account: Account, session: Session) -> None:
        """Connect an account to Avito"""
        try:
            # Parse JWT to get user info
            jwt_payload = parse_jwt(session.session_token)
            if not jwt_payload:
                print(f"Failed to parse JWT for {account.phone}")
                return

            # Create session object
            avito_session = AvitoSession(
                session_token=session.session_token,
                fingerprint=account.fingerprint or "",
                device_id=account.device_id,
                user_id=jwt_payload.user_id,
                user_hash=account.user_hash or "",
                remote_device_id=account.remote_device_id
            )

            # Create connection record
            connection = AccountConnection(
                account_id=account.id,
                user_id=jwt_payload.user_id,
                user_hash=account.user_hash or ""
            )

            # Add to pool with message handler
            client = await self.avito_pool.add_client(
                user_id=str(jwt_payload.user_id),
                session=avito_session,
                message_handler=lambda msg: asyncio.create_task(
                    self._handle_avito_message(str(account.id), msg)
                )
            )

            connection.client = client
            connection.connected = True
            self.connections[str(account.id)] = connection

            print(f"Connected account {account.phone}")

        except Exception as e:
            print(f"Failed to connect {account.phone}: {e}")

    async def _handle_avito_message(self, account_id: str, message: AvitoMessage) -> None:
        """
        Handle incoming Avito message

        Forwards message to all Telegram users linked to this account
        """
        if not message.is_incoming:
            # Our own message, ignore
            return

        print(f"New Avito message: {message.text[:50]}...")

        # Get connection
        connection = self.connections.get(account_id)
        if not connection:
            return

        # Find Telegram users linked to this account
        db = await get_db()
        async with db.session() as session:
            # Get all TG users with this account
            from sqlalchemy import select
            from shared.models import TelegramUser

            result = await session.execute(
                select(TelegramUser).where(
                    TelegramUser.account_id == UUID(account_id),
                    TelegramUser.notifications_enabled == True
                )
            )
            tg_users = list(result.scalars().all())

            for tg_user in tg_users:
                # Send notification
                try:
                    text = (
                        f"Новое сообщение Avito\n\n"
                        f"{message.text}\n\n"
                        f"Чат: {message.channel_id}"
                    )
                    await self.bot.send_message(tg_user.telegram_id, text)
                except Exception as e:
                    print(f"Failed to notify TG user {tg_user.telegram_id}: {e}")

    async def _handle_telegram_message(self, message: TgMessage) -> None:
        """
        Handle Telegram message for forwarding to Avito

        This is called when user sends a text message (not a command)
        """
        db = await get_db()
        async with db.session() as session:
            tg_repo = TelegramUserRepository(session)
            user = await tg_repo.get_by_telegram_id(message.from_user.id)

            if not user or not user.account_id or not user.selected_channel_id:
                return

            # Find connection
            connection = self.connections.get(str(user.account_id))
            if not connection or not connection.client:
                await message.answer("Соединение с Avito потеряно. Попробуйте позже.")
                return

            # Send message
            msg_id = await connection.client.send_message(
                channel_id=user.selected_channel_id,
                text=message.text
            )

            if msg_id:
                await message.answer("Сообщение отправлено")
            else:
                await message.answer("Ошибка отправки сообщения")

    async def _token_refresh_loop(self) -> None:
        """
        Periodically check for expiring tokens and refresh them

        Uses Token Farm API to refresh tokens
        """
        while self._running:
            try:
                await asyncio.sleep(60 * 15)  # Every 15 minutes

                db = await get_db()
                async with db.session() as session:
                    repo = AccountRepository(session)
                    expiring = await repo.get_expiring(hours=4)

                    for account in expiring:
                        await self._request_token_refresh(account.id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Token refresh loop error: {e}")

    async def _request_token_refresh(self, account_id: UUID) -> None:
        """Request token refresh from Token Farm"""
        if not self.farm_client:
            print("Token Farm not configured, cannot refresh")
            return

        try:
            response = await self.farm_client.post(
                f"/accounts/{account_id}/refresh",
                json={"force": False}
            )

            if response.status_code == 200:
                print(f"Token refresh requested for {account_id}")
            else:
                print(f"Token refresh failed: {response.status_code}")

        except Exception as e:
            print(f"Token refresh request error: {e}")

    async def _health_check_loop(self) -> None:
        """
        Periodically check connection health
        """
        while self._running:
            try:
                await asyncio.sleep(60)  # Every minute

                # Check Avito connections
                status = self.avito_pool.get_status()
                disconnected = [uid for uid, state in status.items() if state != "connected"]

                if disconnected:
                    print(f"Disconnected clients: {disconnected}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Health check error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get manager status"""
        return {
            "running": self._running,
            "accounts_total": len(self.connections),
            "accounts_connected": sum(1 for c in self.connections.values() if c.connected),
            "avito_status": self.avito_pool.get_status()
        }


async def main():
    """Main entry point"""
    manager = MCPManager()

    try:
        await manager.start()
    except KeyboardInterrupt:
        pass
    finally:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
