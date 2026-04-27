-- ============================================================
-- AvitoSystem — Device-Command channel (server → APK)
-- New table: avito_device_commands
-- ============================================================
-- Server-driven control of the Android session-manager APK. The phone
-- doesn't have a public IP, so APK long-polls
-- ``GET /api/v1/devices/me/commands?wait=60``. Anything pending for the
-- caller's tenant comes back; APK acks via
-- ``POST /api/v1/devices/me/commands/{id}/ack``.
--
-- Primary use case: refresh_token. The server sees a session whose JWT
-- exp is 60–180 s away and inserts a refresh_token command. APK opens
-- Avito (root ``monkey``), nudges it with a few ``input swipe``s,
-- watches SharedPrefs until the new token shows up, force-stops Avito,
-- and uploads the fresh session via the existing ``POST /api/v1/sessions``.
-- The server correlates "command #X created at T → fresh session sync
-- arrived at T+Δ with exp > prev exp" to mark the command done.
--
-- Commands are per-tenant, not per-device. If a tenant happens to have
-- multiple devices online, the first one to long-poll wins and the
-- others see nothing — fine for the personal-monitor case.

CREATE TABLE IF NOT EXISTS avito_device_commands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    command TEXT NOT NULL,
    -- launch_avito | refresh_token | read_session_now | restart_listener | …
    -- V1 only emits refresh_token; the column is text rather than enum
    -- so adding a new command later doesn't need a migration.

    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- command-specific args; for refresh_token we may pass:
    --   {"timeout_sec": 90, "scroll_interval_sec": 1.5}

    status TEXT NOT NULL DEFAULT 'pending',
    -- pending  — created, not yet picked up
    -- delivered — long-poll returned it; APK is acting on it
    -- done     — APK acked success
    -- failed   — APK acked failure (with reason in result.error)
    -- expired  — server gave up waiting for ack (e.g. APK offline)

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ,
    acked_at TIMESTAMPTZ,
    expire_at TIMESTAMPTZ,
    -- Hard deadline so a stranded "delivered" command doesn't block
    -- future ones forever. Server sweeps these to "expired" lazily.

    result JSONB,
    -- Filled at ack time. For refresh_token success:
    --   {"new_exp": 1714400000, "scrolls": 5, "elapsed_sec": 12}
    -- For failure:
    --   {"error": "screen_locked", "details": "..."}

    issued_by TEXT,
    -- Free-form tag describing who created the command:
    --   "health_checker:scenario_a", "manual:tg_admin", …
    --   Useful for audit + dedup grouping.

    CONSTRAINT avito_device_commands_status_chk CHECK (
        status IN ('pending', 'delivered', 'done', 'failed', 'expired')
    )
);

-- Long-poll picks the oldest pending row; APK ack flips status by id.
CREATE INDEX IF NOT EXISTS idx_avito_device_commands_tenant_status_created
    ON avito_device_commands (tenant_id, status, created_at);

-- Used by the dedup check before the admin endpoint inserts a new row:
-- "is there already an in-flight command of this kind in the cooldown
-- window?".
CREATE INDEX IF NOT EXISTS idx_avito_device_commands_tenant_command_created
    ON avito_device_commands (tenant_id, command, created_at);
