-- 007_avito_accounts_pool.sql
-- Avito multi-account pool: stable account identity + state machine + multi-phone.
-- Idempotent: можно безопасно re-applied.

CREATE TABLE IF NOT EXISTS avito_accounts (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nickname               TEXT NOT NULL,
    avito_user_id          BIGINT NOT NULL,
    last_device_id         TEXT,
    phone_serial           TEXT NOT NULL DEFAULT '',
    android_user_id        INTEGER NOT NULL DEFAULT 0,
    state                  TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active','cooldown','needs_refresh',
                         'waiting_refresh','dead')),
    cooldown_until         TIMESTAMPTZ,
    consecutive_cooldowns  INTEGER NOT NULL DEFAULT 0,
    last_polled_at         TIMESTAMPTZ,
    last_session_at        TIMESTAMPTZ,
    waiting_since          TIMESTAMPTZ,
    last_403_body          TEXT,
    last_403_at            TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (avito_user_id)
);

CREATE INDEX IF NOT EXISTS idx_accounts_pool
    ON avito_accounts (last_polled_at NULLS FIRST)
    WHERE state = 'active';

CREATE INDEX IF NOT EXISTS idx_accounts_avito_user
    ON avito_accounts (avito_user_id);

DO $$ BEGIN
    ALTER TABLE avito_sessions
        ADD COLUMN account_id UUID REFERENCES avito_accounts(id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_column THEN
    NULL;
END $$;

DROP INDEX IF EXISTS idx_avito_sessions_active;
CREATE INDEX IF NOT EXISTS idx_avito_sessions_active_per_account
    ON avito_sessions (account_id, is_active) WHERE is_active = true;

-- One-shot data migration: для каждого user_id создаём account row + привязываем sessions.
-- Защита от повторного применения: WHERE account_id IS NULL.
DO $$ DECLARE r RECORD; new_acc UUID; BEGIN
    FOR r IN (SELECT DISTINCT user_id FROM avito_sessions
              WHERE user_id IS NOT NULL
                AND account_id IS NULL) LOOP
        INSERT INTO avito_accounts (avito_user_id, nickname, state)
            VALUES (r.user_id, 'auto-' || r.user_id, 'active')
            ON CONFLICT (avito_user_id) DO UPDATE SET updated_at = NOW()
            RETURNING id INTO new_acc;
        UPDATE avito_sessions SET account_id = new_acc
            WHERE user_id = r.user_id AND account_id IS NULL;
    END LOOP;
END $$;
