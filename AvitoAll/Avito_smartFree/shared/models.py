"""
Database models for Avito SmartFree
SQLAlchemy models with PostgreSQL
"""

from datetime import datetime
from typing import Optional
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean, DateTime,
    Text, JSON, ForeignKey, Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class AccountStatus(str, Enum):
    """Account status enum"""
    PENDING = "pending"           # Awaiting registration
    REGISTERING = "registering"   # Registration in progress
    ACTIVE = "active"             # Active and working
    REFRESHING = "refreshing"     # Token refresh in progress
    EXPIRED = "expired"           # Token expired, needs refresh
    BLOCKED = "blocked"           # Blocked by Avito
    ERROR = "error"               # Error state


class ProxyType(str, Enum):
    """Proxy type enum"""
    MOBILE = "mobile"
    RESIDENTIAL = "residential"
    DATACENTER = "datacenter"


class Account(Base):
    """Avito account model"""
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)

    # Avito identifiers
    user_id = Column(BigInteger, nullable=True, index=True)
    user_hash = Column(String(64), nullable=True)
    device_id = Column(String(32), nullable=False)
    remote_device_id = Column(Text, nullable=True)

    # Security
    fingerprint = Column(Text, nullable=True)  # Header 'f'

    # Device emulation settings
    device_model = Column(String(100), default="SM-G998B")
    device_brand = Column(String(50), default="samsung")
    android_version = Column(String(10), default="12")
    imei = Column(String(20), nullable=True)

    # Status
    status = Column(SQLEnum(AccountStatus), default=AccountStatus.PENDING, index=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_sync_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    sessions = relationship("Session", back_populates="account", cascade="all, delete-orphan")
    telegram_users = relationship("TelegramUser", back_populates="account")

    # Indexes
    __table_args__ = (
        Index('idx_accounts_status_updated', 'status', 'updated_at'),
    )

    def __repr__(self):
        return f"<Account {self.phone} ({self.status})>"


class Session(Base):
    """Avito session/token model"""
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)

    # Token data
    session_token = Column(Text, nullable=False)  # JWT
    refresh_token = Column(String(64), nullable=True)

    # Parsed from JWT
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)

    # Cookies
    cookies = Column(JSON, default=dict)

    # Status
    is_active = Column(Boolean, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    account = relationship("Account", back_populates="sessions")

    # Indexes
    __table_args__ = (
        Index('idx_sessions_active_expires', 'is_active', 'expires_at'),
    )

    @property
    def is_expired(self) -> bool:
        """Check if session is expired"""
        return datetime.utcnow() > self.expires_at.replace(tzinfo=None)

    @property
    def hours_until_expiry(self) -> float:
        """Get hours until expiration"""
        delta = self.expires_at.replace(tzinfo=None) - datetime.utcnow()
        return delta.total_seconds() / 3600

    def __repr__(self):
        return f"<Session {self.id} expires={self.expires_at}>"


class TelegramUser(Base):
    """Telegram user linked to Avito account"""
    __tablename__ = "telegram_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)

    # Linked account
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)

    # Currently selected chat
    selected_channel_id = Column(String(100), nullable=True)

    # Settings
    notifications_enabled = Column(Boolean, default=True)
    auto_reply_enabled = Column(Boolean, default=False)

    # Subscription
    is_active = Column(Boolean, default=True)
    subscription_expires = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    account = relationship("Account", back_populates="telegram_users")

    def __repr__(self):
        return f"<TelegramUser {self.telegram_id} ({self.username})>"


class Proxy(Base):
    """Proxy configuration"""
    __tablename__ = "proxies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Connection
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(100), nullable=True)
    password = Column(String(100), nullable=True)

    # Type
    proxy_type = Column(SQLEnum(ProxyType), default=ProxyType.MOBILE)
    protocol = Column(String(10), default="http")  # http, socks5

    # Location
    country = Column(String(10), default="RU")

    # Status
    is_active = Column(Boolean, default=True, index=True)
    is_healthy = Column(Boolean, default=True)
    last_check = Column(DateTime(timezone=True), nullable=True)
    error_count = Column(Integer, default=0)

    # Usage stats
    requests_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def url(self) -> str:
        """Get proxy URL"""
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.protocol}://{auth}{self.host}:{self.port}"

    def __repr__(self):
        return f"<Proxy {self.host}:{self.port} ({self.proxy_type})>"


class Message(Base):
    """Message cache for history"""
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Avito message data
    avito_message_id = Column(String(100), unique=True, nullable=False, index=True)
    channel_id = Column(String(100), nullable=False, index=True)

    # Account
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)

    # Message content
    author_id = Column(String(100), nullable=False)
    author_name = Column(String(255), nullable=True)
    text = Column(Text, nullable=True)
    message_type = Column(String(50), default="text")  # text, image, voice

    # Direction
    is_incoming = Column(Boolean, default=True)  # True = from Avito user, False = our reply

    # Telegram
    telegram_message_id = Column(BigInteger, nullable=True)

    # Timestamps
    avito_created_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index('idx_messages_channel_created', 'channel_id', 'avito_created_at'),
    )

    def __repr__(self):
        return f"<Message {self.avito_message_id}>"
