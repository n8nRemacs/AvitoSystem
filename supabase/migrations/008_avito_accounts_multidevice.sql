-- 008_avito_accounts_multidevice.sql
-- Allow multiple device_id rows per Avito user_id.
-- Pre-condition: 007_avito_accounts_pool.sql applied (avito_accounts table exists).
-- Idempotent.

DO $$
BEGIN
    -- The constraint name is auto-generated; PG names it <table>_<col>_key.
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'avito_accounts_avito_user_id_key'
    ) THEN
        ALTER TABLE avito_accounts DROP CONSTRAINT avito_accounts_avito_user_id_key;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'avito_accounts_user_device_uniq'
    ) THEN
        ALTER TABLE avito_accounts
            ADD CONSTRAINT avito_accounts_user_device_uniq
            UNIQUE (avito_user_id, last_device_id);
    END IF;
END $$;

-- NOTE: PostgreSQL UNIQUE allows multiple rows where any column is NULL.
-- Existing rows have last_device_id set. Future INSERT-without-device flows
-- (legacy auto-rows from 007 data migration) are not expected to recur — but
-- nothing currently breaks if they do, since the resolver only INSERTs with
-- device_id provided.
