-- ============================================================
-- AvitoSystem — Tenant Auth Seed Data
-- ============================================================

-- Billing Plans
INSERT INTO billing_plans (id, name, price_monthly, max_api_keys, max_sessions, max_sub_users, features) VALUES
    ('e0000000-0000-0000-0000-000000000001', 'free', 0, 1, 1, 1, '{"support": "community", "analytics": false}'),
    ('e0000000-0000-0000-0000-000000000002', 'starter', 990, 3, 5, 3, '{"support": "email", "analytics": true}'),
    ('e0000000-0000-0000-0000-000000000003', 'pro', 2990, 10, 20, 10, '{"support": "priority", "analytics": true, "webhooks": true}')
ON CONFLICT (name) DO NOTHING;

-- Assign free plan to existing test tenant
UPDATE tenants SET billing_plan_id = 'e0000000-0000-0000-0000-000000000001'
WHERE id = 'c0000000-0000-0000-0000-000000000001' AND billing_plan_id IS NULL;

-- Test tenant user (owner of TestTenant)
INSERT INTO tenant_users (id, tenant_id, phone, email, email_verified, phone_verified, name, role) VALUES
    ('f0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001', '+79991234567', 'test@example.com', true, true, 'Test Owner', 'owner')
ON CONFLICT (phone) DO NOTHING;
