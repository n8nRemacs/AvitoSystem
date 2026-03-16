-- ============================================================
-- AvitoSystem SaaS Platform — Initial Migration
-- Supabase project: bkxpajeqrkutktmtmwui
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- Supervisors (partners / resellers)
-- ============================================================
CREATE TABLE supervisors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    email TEXT,
    is_active BOOLEAN DEFAULT true,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- Toolkits (feature sets that supervisors assign to tenants)
-- ============================================================
CREATE TABLE toolkits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supervisor_id UUID NOT NULL REFERENCES supervisors(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    features JSONB NOT NULL,
    limits JSONB DEFAULT '{}',
    price_monthly DECIMAL(10,2),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- Tenants (SaaS clients, belong to a supervisor)
-- ============================================================
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supervisor_id UUID NOT NULL REFERENCES supervisors(id) ON DELETE CASCADE,
    toolkit_id UUID REFERENCES toolkits(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    email TEXT,
    is_active BOOLEAN DEFAULT true,
    subscription_until TIMESTAMPTZ,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- API Keys (multiple per tenant)
-- ============================================================
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key_hash TEXT NOT NULL UNIQUE,
    name TEXT,
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- Avito Sessions (bound to tenant)
-- ============================================================
CREATE TABLE avito_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tokens JSONB NOT NULL,
    fingerprint TEXT,
    device_id TEXT,
    user_id BIGINT,
    source TEXT NOT NULL CHECK (source IN ('android', 'redroid', 'manual', 'farm', 'browser')),
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- Audit Log
-- ============================================================
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- Farm Devices (physical Android devices)
-- ============================================================
CREATE TABLE farm_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    model TEXT,
    serial TEXT UNIQUE,
    max_profiles INT DEFAULT 100,
    api_key_hash TEXT UNIQUE,
    status TEXT DEFAULT 'online' CHECK (status IN ('online', 'offline', 'maintenance')),
    last_heartbeat TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- Account Bindings (Avito account → Android profile → tenant)
-- ============================================================
CREATE TABLE account_bindings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    farm_device_id UUID NOT NULL REFERENCES farm_devices(id) ON DELETE CASCADE,
    android_profile_id INT NOT NULL,
    avito_user_id BIGINT,
    avito_login TEXT,
    fingerprint_hash TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'migrating')),
    last_refresh_at TIMESTAMPTZ,
    next_refresh_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(farm_device_id, android_profile_id)
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_tenant_id ON api_keys(tenant_id);
CREATE INDEX idx_avito_sessions_tenant_id ON avito_sessions(tenant_id);
CREATE INDEX idx_avito_sessions_active ON avito_sessions(tenant_id, is_active) WHERE is_active = true;
CREATE INDEX idx_audit_log_tenant_id ON audit_log(tenant_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
CREATE INDEX idx_tenants_supervisor_id ON tenants(supervisor_id);
CREATE INDEX idx_toolkits_supervisor_id ON toolkits(supervisor_id);
CREATE INDEX idx_account_bindings_tenant_id ON account_bindings(tenant_id);
CREATE INDEX idx_account_bindings_device_id ON account_bindings(farm_device_id);

-- ============================================================
-- Row Level Security (RLS)
-- ============================================================
ALTER TABLE supervisors ENABLE ROW LEVEL SECURITY;
ALTER TABLE toolkits ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE avito_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE farm_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE account_bindings ENABLE ROW LEVEL SECURITY;

-- Service role bypass (for backend access via service_role key)
-- The backend uses the service_role key which bypasses RLS by default in Supabase.
-- These policies are for anon/authenticated access if needed in the future.

-- Allow service role full access (implicit in Supabase when using service_role key)
-- For anon key, deny everything by default (no policies = deny all)

-- ============================================================
-- Updated_at trigger
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER supervisors_updated_at
    BEFORE UPDATE ON supervisors
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
