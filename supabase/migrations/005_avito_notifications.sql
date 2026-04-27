-- ============================================================
-- AvitoSystem — V2.1 Notification Interception
-- New table: avito_notifications
-- ============================================================
-- Stores Android FCM notifications intercepted by NotificationListenerService
-- on the phone (AvitoSessionManager APK), forwarded via xapi.
-- Used as a third channel (in addition to WS push and REST polling) to detect
-- new chat messages even when xapi↔Avito WS link is broken.

CREATE TABLE IF NOT EXISTS avito_notifications (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Where the notification came from
    source TEXT NOT NULL DEFAULT 'android_notification',
    package_name TEXT,

    -- Android-side identifiers (best-effort; may be reused by Android over time)
    notification_id INT,
    tag TEXT,

    -- Parsed content
    title TEXT,
    body TEXT,            -- Notification.EXTRA_TEXT / preview
    big_text TEXT,        -- Notification.EXTRA_BIG_TEXT (full message if available)
    sub_text TEXT,        -- channel/category context

    -- Full extras blob for debugging / future parsing
    extras JSONB,

    -- Timestamps
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),  -- when xapi accepted it
    posted_at TIMESTAMPTZ,                           -- sbn.postTime from Android (may differ on slow networks)

    -- Pipeline flags
    processed BOOLEAN DEFAULT false,
    processed_at TIMESTAMPTZ,
    process_result JSONB
);

CREATE INDEX IF NOT EXISTS idx_avito_notifications_tenant_received
    ON avito_notifications (tenant_id, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_avito_notifications_unprocessed
    ON avito_notifications (tenant_id, received_at DESC)
    WHERE processed = false;

-- RLS: backend uses service_role key which bypasses RLS by default; mirror
-- the rest of the schema for symmetry.
ALTER TABLE avito_notifications ENABLE ROW LEVEL SECURITY;
