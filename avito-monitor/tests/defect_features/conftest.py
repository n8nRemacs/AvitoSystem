"""Fixtures for defect_features tests — in-memory async SQLite session.

We cannot use Base.metadata.create_all because models use
sqlalchemy.dialects.postgresql.JSONB which SQLite's DDL compiler cannot render.
Instead we issue raw CREATE TABLE DDL that is SQLite-compatible, covering only
the tables required by these tests.
"""
import uuid
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Raw SQLite DDL for only the tables needed by these tests.
# JSONB → TEXT, UUID → TEXT, Postgres-specific defaults stripped.
_DDL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id          TEXT PRIMARY KEY,
        username    TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        is_active   INTEGER NOT NULL DEFAULT 1,
        is_admin    INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_profiles (
        id                  TEXT PRIMARY KEY,
        user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name                TEXT NOT NULL,
        avito_search_url    TEXT NOT NULL,
        parsed_brand        TEXT,
        parsed_model        TEXT,
        parsed_category     TEXT,
        region_slug         TEXT,
        only_with_delivery  INTEGER,
        sort                INTEGER,
        search_min_price    INTEGER,
        search_max_price    INTEGER,
        alert_min_price     INTEGER,
        alert_max_price     INTEGER,
        custom_criteria     TEXT,
        allowed_conditions  TEXT NOT NULL DEFAULT '["working"]',
        llm_classify_model  TEXT,
        llm_match_model     TEXT,
        analyze_photos      INTEGER NOT NULL DEFAULT 0,
        evaluate_strategy   TEXT NOT NULL DEFAULT 'per_criterion',
        confidence_threshold REAL NOT NULL DEFAULT 0.7,
        criteria_set_hash   TEXT,
        bucket_routing      TEXT,
        poll_interval_minutes INTEGER NOT NULL DEFAULT 15,
        active_hours        TEXT,
        is_active           INTEGER NOT NULL DEFAULT 1,
        blocked_sellers     TEXT NOT NULL DEFAULT '[]',
        notification_settings TEXT NOT NULL DEFAULT '{}',
        notification_channels TEXT NOT NULL DEFAULT '["telegram"]',
        avito_autosearch_id TEXT,
        import_source       TEXT NOT NULL DEFAULT 'manual_url',
        archived_at         TEXT,
        last_synced_at      TEXT,
        last_full_poll_at   TEXT,
        search_params       TEXT,
        owner_account_id    TEXT,
        created_at          TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS listings (
        id                      TEXT PRIMARY KEY,
        avito_id                INTEGER NOT NULL UNIQUE,
        title                   TEXT NOT NULL,
        price                   REAL,
        initial_price           REAL,
        last_price_change_at    TEXT,
        currency                TEXT NOT NULL DEFAULT 'RUB',
        region                  TEXT,
        url                     TEXT,
        description             TEXT,
        images                  TEXT NOT NULL DEFAULT '[]',
        parameters              TEXT NOT NULL DEFAULT '{}',
        seller_id               TEXT,
        seller_type             TEXT DEFAULT 'private',
        seller_info             TEXT NOT NULL DEFAULT '{}',
        condition_class         TEXT NOT NULL DEFAULT 'unknown',
        condition_confidence    REAL,
        condition_reasoning     TEXT,
        avito_created_at        TEXT,
        avito_updated_at        TEXT,
        first_seen_at           TEXT,
        last_seen_at            TEXT,
        status                  TEXT NOT NULL DEFAULT 'active',
        reservation_status      TEXT NOT NULL DEFAULT 'active',
        reservation_changed_at  TEXT,
        reserved_at_price       REAL,
        raw_data                TEXT,
        created_at              TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS listing_features (
        id          TEXT PRIMARY KEY,
        listing_id  TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
        feature_key TEXT NOT NULL,
        state       TEXT NOT NULL,
        confidence  REAL,
        source      TEXT NOT NULL,
        evidence    TEXT,
        parsed_at   TEXT NOT NULL DEFAULT (datetime('now')),
        CONSTRAINT uq_listing_features_listing_key UNIQUE (listing_id, feature_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS profile_feature_rules (
        id          TEXT PRIMARY KEY,
        profile_id  TEXT NOT NULL REFERENCES search_profiles(id) ON DELETE CASCADE,
        feature_key TEXT NOT NULL,
        rule        TEXT NOT NULL,
        updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
        CONSTRAINT uq_profile_feature_rules_profile_key UNIQUE (profile_id, feature_key)
    )
    """,
]


@pytest_asyncio.fixture
async def db_session():
    """Each test gets a fresh in-memory async SQLite with hand-written DDL
    that avoids JSONB/PostgreSQL-specific types."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for stmt in _DDL:
            await conn.execute(text(stmt))
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def sample_listing_id(db_session: AsyncSession):
    """A minimal Listing row that the FK can hang on."""
    from app.db.models import Listing
    lst = Listing(
        avito_id=123456789,
        title="iPhone 12 PM 256gb",
        url="https://avito.ru/123456789",
        images=[],
        parameters={},
        seller_info={},
    )
    db_session.add(lst)
    await db_session.commit()
    return lst.id


@pytest_asyncio.fixture
async def sample_profile_id(db_session: AsyncSession):
    """A User + SearchProfile row. SearchProfile has a NOT NULL FK to users."""
    from app.db.models import User, SearchProfile
    user = User(
        username="testuser",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$test",
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    await db_session.flush()  # populate user.id before FK reference

    sp = SearchProfile(
        name="iPhone 12 PM",
        user_id=user.id,
        avito_search_url="https://www.avito.ru/moskva/telefony/iphone-ASgBAgICAUSQEPAQ",
    )
    db_session.add(sp)
    await db_session.commit()
    return sp.id
