-- ============================================================
-- AvitoSystem — Tenant Auth Migration
-- Adds self-service registration, OTP auth, JWT sessions,
-- sub-users, billing plans, and notifications.
-- ============================================================

-- ============================================================
-- Billing Plans
-- ============================================================
CREATE TABLE billing_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    price_monthly DECIMAL(10,2) NOT NULL DEFAULT 0,
    max_api_keys INT NOT NULL DEFAULT 1,
    max_sessions INT NOT NULL DEFAULT 1,
    max_sub_users INT NOT NULL DEFAULT 1,
    features JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE billing_plans ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- ALTER tenants: add billing_plan_id and phone
-- ============================================================
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS billing_plan_id UUID REFERENCES billing_plans(id) ON DELETE SET NULL;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS phone TEXT;

-- ============================================================
-- Tenant Users (phone-based auth)
-- ============================================================
CREATE TABLE tenant_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    phone TEXT NOT NULL UNIQUE,
    email TEXT,
    email_verified BOOLEAN DEFAULT false,
    phone_verified BOOLEAN DEFAULT false,
    name TEXT,
    avatar_url TEXT,
    role TEXT NOT NULL DEFAULT 'owner' CHECK (role IN ('owner', 'admin', 'manager', 'viewer')),
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tenant_users_tenant_id ON tenant_users(tenant_id);
CREATE INDEX idx_tenant_users_phone ON tenant_users(phone);
CREATE INDEX idx_tenant_users_email ON tenant_users(email) WHERE email IS NOT NULL;

ALTER TABLE tenant_users ENABLE ROW LEVEL SECURITY;

CREATE TRIGGER tenant_users_updated_at
    BEFORE UPDATE ON tenant_users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- Verification Codes (OTP for phone and email)
-- ============================================================
CREATE TABLE verification_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('phone', 'email')),
    code TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('sms', 'telegram', 'whatsapp', 'vk_max', 'email', 'console')),
    purpose TEXT NOT NULL CHECK (purpose IN ('register', 'login', 'verify_email', 'change_phone', 'change_email')),
    attempts INT DEFAULT 0,
    max_attempts INT DEFAULT 5,
    is_used BOOLEAN DEFAULT false,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_verification_codes_target ON verification_codes(target, purpose, is_used);
CREATE INDEX idx_verification_codes_expires ON verification_codes(expires_at);

ALTER TABLE verification_codes ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Refresh Tokens (JWT sessions)
-- ============================================================
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash TEXT NOT NULL UNIQUE,
    user_id UUID NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
    device_info JSONB DEFAULT '{}',
    is_revoked BOOLEAN DEFAULT false,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);

ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Tenant Invites (sub-user invitations)
-- ============================================================
CREATE TABLE tenant_invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    invited_by UUID NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
    phone TEXT,
    email TEXT,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin', 'manager', 'viewer')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'cancelled', 'expired')),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tenant_invites_tenant_id ON tenant_invites(tenant_id);
CREATE INDEX idx_tenant_invites_token_hash ON tenant_invites(token_hash);

ALTER TABLE tenant_invites ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Notification Preferences
-- ============================================================
CREATE TABLE notification_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
    channel TEXT NOT NULL CHECK (channel IN ('sms', 'telegram', 'whatsapp', 'vk_max', 'email')),
    event_type TEXT NOT NULL,
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, channel, event_type)
);

CREATE INDEX idx_notification_preferences_user_id ON notification_preferences(user_id);

ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Notification History
-- ============================================================
CREATE TABLE notification_history (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    event_type TEXT NOT NULL,
    title TEXT,
    body TEXT,
    is_read BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_notification_history_user_id ON notification_history(user_id, created_at DESC);

ALTER TABLE notification_history ENABLE ROW LEVEL SECURITY;
