# MOCKS.md — Registry of Mock Data and Stubs

## Status Legend
- :red_circle: Mock — stub in use
- :yellow_circle: Partial — partially real data
- :green_circle: Real — real data

## Supabase

| What | Value | File | Status |
|------|-------|------|--------|
| Test supervisor | name="DevSupervisor", id=a000...0001 | 002_seed.sql | :red_circle: |
| Test toolkit | name="Avito Full Access", features=["avito.*"] | 002_seed.sql | :red_circle: |
| Test tenant | name="TestTenant", id=c000...0001 | 002_seed.sql | :red_circle: |
| Test API key | key="test_dev_key_123", hash=6096e7... | 002_seed.sql | :red_circle: |

## Avito Tokens

| What | Value | File | Status |
|------|-------|------|--------|
| Test JWT | eyJ... (expired, for unit tests) | tests/fixtures/mock_session.json | :red_circle: |
| Session JSON | mock_session.json | tests/fixtures/mock_session.json | :red_circle: |
| Fingerprint | A2.000...mock | tests/fixtures/mock_session.json | :red_circle: |
| Avito user_id | 99999999 | tests/fixtures/mock_session.json | :red_circle: |

## API Responses (mock for unit tests)

| What | File | Status |
|------|------|--------|
| get_channels response | tests/fixtures/channels.json | :red_circle: |
| get_messages response | tests/fixtures/messages.json | :red_circle: |
| search_items response | tests/fixtures/search.json | :red_circle: |
| call_history response | tests/fixtures/calls.json | :red_circle: |

## Configuration

| What | Dev Value | Prod Value | File |
|------|-----------|------------|------|
| SUPABASE_URL | https://bkxpajeqrkutktmtmwui.supabase.co | same | .env |
| SUPABASE_KEY | eyJ...anon | service_role key | .env |
| API_KEY | test_dev_key_123 | generate new | .env |
| CORS origins | http://localhost:3000 | https://avito.newlcd.ru | .env |

## Token Farm

| What | Value | File | Status |
|------|-------|------|--------|
| Test device | name="MockDevice" | 002_seed.sql | :red_circle: |
| Farm API key | farm_test_key_456 | .env | :red_circle: |

## Rules
- When creating any mock, immediately add a row to this file
- When replacing a mock with real data, change status to :green_circle:
- Before production deploy, all rows should be :green_circle: or :yellow_circle:
