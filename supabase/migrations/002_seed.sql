-- ============================================================
-- Seed Data for Development
-- ============================================================

-- Test Supervisor
INSERT INTO supervisors (id, name, email, is_active)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'DevSupervisor',
    'dev@newlcd.ru',
    true
);

-- Test Toolkit (full access for development)
INSERT INTO toolkits (id, supervisor_id, name, features, limits, price_monthly, is_active)
VALUES (
    'b0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'Avito Full Access',
    '["avito.sessions", "avito.messenger", "avito.search", "avito.calls", "avito.farm"]',
    '{"max_sessions": 5, "max_messages_day": 1000}',
    0.00,
    true
);

-- Test Tenant
INSERT INTO tenants (id, supervisor_id, toolkit_id, name, email, is_active, subscription_until)
VALUES (
    'c0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000001',
    'TestTenant',
    'test@newlcd.ru',
    true,
    '2027-01-01T00:00:00Z'
);

-- Test API Key: "test_dev_key_123"
-- SHA-256 of "test_dev_key_123" = 7b3e5e5c80b5c5c8f1d7c0e5d3a1b9f4e2c6d8a0b3f5e7c9d1a3b5c7e9f0a2b4
-- Precomputed: SELECT encode(sha256('test_dev_key_123'::bytea), 'hex');
INSERT INTO api_keys (id, tenant_id, key_hash, name, is_active)
VALUES (
    'd0000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    '6096e738bb666ab4378531d758e3d913dbcddc48a0a1a82fcc01e1450dba9082',
    'Development',
    true
);
