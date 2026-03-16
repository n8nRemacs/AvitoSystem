"""
Async PostgreSQL database connection and utilities
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from .models import Base
from .config import settings


class Database:
    """Async database manager"""

    def __init__(self, url: Optional[str] = None):
        self.url = url or settings.database_url
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None

    async def connect(self) -> None:
        """Create database connection"""
        self.engine = create_async_engine(
            self.url,
            echo=settings.log_level == "DEBUG",
            poolclass=NullPool,  # For better async compatibility
            future=True
        )

        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False
        )

    async def disconnect(self) -> None:
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    async def create_tables(self) -> None:
        """Create all tables"""
        if not self.engine:
            await self.connect()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self) -> None:
        """Drop all tables (use with caution!)"""
        if not self.engine:
            await self.connect()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session context manager"""
        if not self.session_factory:
            await self.connect()

        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def health_check(self) -> bool:
        """Check database connection health"""
        try:
            async with self.session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


# Global database instance
_db: Optional[Database] = None


async def get_db() -> Database:
    """Get or create database instance"""
    global _db
    if _db is None:
        _db = Database()
        await _db.connect()
    return _db


async def init_db() -> None:
    """Initialize database and create tables"""
    db = await get_db()
    await db.create_tables()


async def close_db() -> None:
    """Close database connection"""
    global _db
    if _db:
        await _db.disconnect()
        _db = None


# Repository classes for common operations

from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from typing import List
from uuid import UUID

from .models import Account, Session, TelegramUser, Proxy, AccountStatus


class AccountRepository:
    """Repository for Account operations"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, phone: str, device_id: str, **kwargs) -> Account:
        """Create new account"""
        account = Account(phone=phone, device_id=device_id, **kwargs)
        self.session.add(account)
        await self.session.flush()
        return account

    async def get_by_id(self, account_id: UUID) -> Optional[Account]:
        """Get account by ID"""
        result = await self.session.execute(
            select(Account)
            .options(selectinload(Account.sessions))
            .where(Account.id == account_id)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Optional[Account]:
        """Get account by phone number"""
        result = await self.session.execute(
            select(Account).where(Account.phone == phone)
        )
        return result.scalar_one_or_none()

    async def get_all(self, status: Optional[AccountStatus] = None) -> List[Account]:
        """Get all accounts, optionally filtered by status"""
        query = select(Account).options(selectinload(Account.sessions))
        if status:
            query = query.where(Account.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_expiring(self, hours: int = 4) -> List[Account]:
        """Get accounts with tokens expiring within N hours"""
        threshold = datetime.utcnow() + timedelta(hours=hours)
        result = await self.session.execute(
            select(Account)
            .join(Session)
            .where(
                Account.status == AccountStatus.ACTIVE,
                Session.is_active == True,
                Session.expires_at < threshold
            )
            .options(selectinload(Account.sessions))
        )
        return list(result.scalars().all())

    async def update_status(self, account_id: UUID, status: AccountStatus, error: str = None) -> None:
        """Update account status"""
        await self.session.execute(
            update(Account)
            .where(Account.id == account_id)
            .values(status=status, error_message=error, updated_at=datetime.utcnow())
        )

    async def delete(self, account_id: UUID) -> None:
        """Delete account"""
        await self.session.execute(
            delete(Account).where(Account.id == account_id)
        )


class SessionRepository:
    """Repository for Session operations"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, account_id: UUID, session_token: str, expires_at: datetime, **kwargs) -> Session:
        """Create new session"""
        # Deactivate old sessions
        await self.session.execute(
            update(Session)
            .where(Session.account_id == account_id, Session.is_active == True)
            .values(is_active=False)
        )

        session = Session(
            account_id=account_id,
            session_token=session_token,
            expires_at=expires_at,
            **kwargs
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def get_active(self, account_id: UUID) -> Optional[Session]:
        """Get active session for account"""
        result = await self.session.execute(
            select(Session)
            .where(Session.account_id == account_id, Session.is_active == True)
            .order_by(Session.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def deactivate(self, session_id: UUID) -> None:
        """Deactivate session"""
        await self.session.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(is_active=False)
        )


class TelegramUserRepository:
    """Repository for TelegramUser operations"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, telegram_id: int, **kwargs) -> TelegramUser:
        """Create new telegram user"""
        user = TelegramUser(telegram_id=telegram_id, **kwargs)
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[TelegramUser]:
        """Get user by Telegram ID"""
        result = await self.session.execute(
            select(TelegramUser)
            .options(selectinload(TelegramUser.account))
            .where(TelegramUser.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, telegram_id: int, **kwargs) -> TelegramUser:
        """Get existing user or create new one"""
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            user = await self.create(telegram_id, **kwargs)
        return user

    async def link_account(self, telegram_id: int, account_id: UUID) -> None:
        """Link Telegram user to Avito account"""
        await self.session.execute(
            update(TelegramUser)
            .where(TelegramUser.telegram_id == telegram_id)
            .values(account_id=account_id)
        )

    async def update_selected_channel(self, telegram_id: int, channel_id: str) -> None:
        """Update selected channel for user"""
        await self.session.execute(
            update(TelegramUser)
            .where(TelegramUser.telegram_id == telegram_id)
            .values(selected_channel_id=channel_id, last_activity=datetime.utcnow())
        )


class ProxyRepository:
    """Repository for Proxy operations"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active(self, proxy_type: Optional[str] = None) -> List[Proxy]:
        """Get active proxies"""
        query = select(Proxy).where(Proxy.is_active == True, Proxy.is_healthy == True)
        if proxy_type:
            query = query.where(Proxy.proxy_type == proxy_type)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_random(self, proxy_type: str = "mobile") -> Optional[Proxy]:
        """Get random healthy proxy"""
        from sqlalchemy.sql.expression import func
        result = await self.session.execute(
            select(Proxy)
            .where(
                Proxy.is_active == True,
                Proxy.is_healthy == True,
                Proxy.proxy_type == proxy_type
            )
            .order_by(func.random())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_unhealthy(self, proxy_id: UUID) -> None:
        """Mark proxy as unhealthy"""
        await self.session.execute(
            update(Proxy)
            .where(Proxy.id == proxy_id)
            .values(is_healthy=False, error_count=Proxy.error_count + 1)
        )
