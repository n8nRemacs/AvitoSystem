# Server Migration + Manual Refresh Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move avito-monitor + avito-proxy off homelab onto a dedicated RU VPS (81.200.119.132, 1c/2GB/15GB Ubuntu 24.04), migrate Postgres to Supabase Cloud, switch refresh model from "automatic via APK monkey-scroll + ADB" to fully manual (user opens Avito-app twice/day), and remove the dead-code paths that automated refresh relied on. Result: homelab no longer required for runtime; only Supabase Cloud + the new VPS + the phone (with internet).

**Architecture:**
- **New VPS** runs everything: avito-monitor, avito-proxy (xapi minus token-bridge bits), Redis, Caddy reverse proxy with auto-TLS.
- **Supabase Cloud** (project `drwgozasaypgphkxyizt`, Frankfurt) replaces homelab self-hosted Postgres as the single source of truth.
- **Phone** runs AvitoSessionManager APK in user_0 + user_10. Both APK instances POST refreshed JWTs directly to the VPS over HTTPS. No ADB. No long-poll. No commands queue.
- **Manual refresh:** user opens Avito-app in user_0 each morning, in user_10 each evening. APK catches the refresh push via NotificationListener, reads SharedPrefs, POSTs `/api/v1/sessions`.
- **Alert model:** `account_tick.py` no longer triggers refresh. It only emits one-shot TG alerts when a per-account session goes stale (`expires_at < NOW()`), with an extra critical alert if both accounts stale simultaneously.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 async, TaskIQ + Redis, aiogram, Docker Compose, Caddy 2.x, Supabase Cloud (managed Postgres), Kotlin (APK config-only — no rebuild).

---

## Phase 0 — Prerequisites (user actions, must happen before plan starts)

These are not coding tasks — they unblock everything else. Confirm each is done before opening Phase 1.

- [ ] **P0.1** Beget edge firewall opened for inbound TCP 22, 80, 443 on 81.200.119.132. Verify from local machine: `Test-NetConnection -ComputerName 81.200.119.132 -Port 22` returns `TcpTestSucceeded: True`. Without this, Phase 6 onward blocks.
- [ ] **P0.2** Supabase Cloud project `drwgozasaypgphkxyizt` (Frankfurt) provisioned. Settings → Database password generated and saved offline. Verify via Settings → API page loads.
- [ ] **P0.3** Decision on hostname for the VPS. Pick one:
  - **Option A:** Use IP-only (`https://81.200.119.132`) — Caddy issues IP cert via Let's Encrypt (supported since 2025). Simplest.
  - **Option B:** Free DuckDNS subdomain (e.g., `avitosystem.duckdns.org`) → A-record → 81.200.119.132. Caddy issues domain cert via HTTP-01. Most reliable.
  - **Option C:** Owned domain. Same as B but using user's own domain.
  - Plan defaults to **Option B (DuckDNS)** because IP-cert support varies by validator. Replace `avitosystem.duckdns.org` with chosen hostname throughout if A or C picked.

---

## Phase 1 — Schema migration to Supabase Cloud

Apply existing migrations 001-008 to the fresh Cloud project. SQL only, no code change.

**Files:**
- Source: `supabase/migrations/001_init.sql` … `supabase/migrations/008_avito_accounts_multidevice.sql`
- Verify: Supabase Dashboard → SQL Editor

- [ ] **1.1 Concatenate migrations into a single file for review**

```bash
cd C:/Projects/Sync/AvitoSystem
cat supabase/migrations/001_init.sql \
    supabase/migrations/002_seed.sql \
    supabase/migrations/003_tenant_auth.sql \
    supabase/migrations/004_tenant_auth_seed.sql \
    supabase/migrations/005_avito_notifications.sql \
    supabase/migrations/006_avito_device_commands.sql \
    supabase/migrations/007_avito_accounts_pool.sql \
    supabase/migrations/008_avito_accounts_multidevice.sql \
    > /tmp/all_migrations.sql
wc -l /tmp/all_migrations.sql
```

Expected: ~500-1000 lines (depends on actual sizes).

- [ ] **1.2 Apply migrations one-by-one via Supabase SQL Editor**

For each file 001 → 008:
1. Open Supabase Dashboard → SQL Editor → New query
2. Paste full contents of the file
3. Click Run
4. Expected: green checkmark, "Success. No rows returned"
5. If any error: stop, report to plan author

**Note:** Do NOT use `\copy` or `psql`-specific commands. SQL Editor is plain Postgres — all our migrations should be vanilla SQL.

- [ ] **1.3 Verify schema parity**

In SQL Editor run:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema='public' ORDER BY table_name;
```

Expected output (must include all):
```
audit_log
avito_accounts
avito_device_commands
avito_listings
avito_listings_history
avito_notifications
avito_sessions
profile_listings
profile_market_stats
profile_runs
search_profiles
session_history
sub_intervals
tenants
tenant_features
user_listing_blacklists
```

(Adjust this list if the actual migration files differ — the source of truth is what 001-008 actually create.)

- [ ] **1.4 Verify constraint from migration 008**

```sql
SELECT conname FROM pg_constraint
WHERE conrelid = 'avito_accounts'::regclass
  AND conname = 'avito_accounts_user_device_uniq';
```
Expected: 1 row returned.

- [ ] **1.5 Commit no-op (schema migrations are tracked in git already, no new files)**

Skip — Phase 1 produces no source changes.

---

## Phase 2 — Data migration from homelab → Cloud

Copy live data for tables we want to preserve. Skip transient tables.

**Tables to migrate** (must keep): `tenants`, `tenant_features`, `search_profiles`, `avito_accounts`, `avito_sessions` (only `is_active=true` rows), `profile_listings`, `user_listing_blacklists`.

**Tables to skip** (rebuild themselves): `avito_listings`, `avito_listings_history`, `profile_runs`, `profile_market_stats`, `avito_notifications`, `avito_device_commands`, `audit_log`, `session_history`, `sub_intervals`.

- [ ] **2.1 Dump source tables from homelab**

Run on local machine:
```bash
HOMELAB_DB="postgresql://postgres:Mi31415926pSss%21@213.108.170.194:5433/postgres"
mkdir -p /tmp/avitomigrate

for t in tenants tenant_features search_profiles avito_accounts user_listing_blacklists profile_listings; do
  pg_dump --data-only --no-owner --no-acl --column-inserts \
          -t "public.$t" "$HOMELAB_DB" \
          > "/tmp/avitomigrate/$t.sql"
  echo "$t: $(wc -l < /tmp/avitomigrate/$t.sql) lines"
done

# Sessions: only is_active=true
pg_dump --data-only --no-owner --no-acl --column-inserts \
        -t "public.avito_sessions" --where "is_active=true" "$HOMELAB_DB" \
        > /tmp/avitomigrate/avito_sessions.sql 2>/dev/null || \
  echo "WARNING: pg_dump --where unsupported, falling back to manual filter"
```

If `--where` not supported (older pg_dump), do:
```bash
PGPASSWORD='Mi31415926pSss!' psql -h 213.108.170.194 -p 5433 -U postgres -d postgres \
  -c "\copy (SELECT * FROM avito_sessions WHERE is_active=true) TO '/tmp/avitomigrate/avito_sessions.csv' WITH CSV HEADER"
```

Expected: 6-7 small `.sql` files (each typically 5-50 KB for personal-scale data).

- [ ] **2.2 Inspect dumps for sensitive data**

Run:
```bash
for f in /tmp/avitomigrate/*.sql; do
  echo "=== $f ==="; head -20 "$f"; echo
done
```

Manually verify: tokens look correct, no plaintext passwords leaked into INSERT statements (passwords should be hashed already in tenants table).

- [ ] **2.3 Apply dumps to Supabase Cloud via SQL Editor**

For each file, open in editor (e.g., VS Code), paste into Supabase SQL Editor, Run. **Apply in order:**
1. `tenants.sql`
2. `tenant_features.sql`
3. `search_profiles.sql`
4. `avito_accounts.sql`
5. `user_listing_blacklists.sql`
6. `profile_listings.sql`
7. `avito_sessions.sql`

After each: verify row count matches source via `SELECT COUNT(*) FROM <table>;` in Cloud SQL Editor.

- [ ] **2.4 Reset sequences (if any auto-increment columns)**

Most tables use UUIDs, but if any have `SERIAL` or `BIGSERIAL`, reset:
```sql
SELECT setval(pg_get_serial_sequence(table_name, column_name),
              (SELECT MAX(column_name::bigint) FROM table_name))
-- repeat per table; only run if MAX returns non-null
```

In our schema, only check is needed — most use UUID DEFAULT. Skip if no sequences.

- [ ] **2.5 Commit migration scripts to git for audit trail**

```bash
cd C:/Projects/Sync/AvitoSystem
mkdir -p ops/migration-2026-05-02
cp /tmp/avitomigrate/*.sql ops/migration-2026-05-02/
echo "*.sql" > ops/migration-2026-05-02/.gitignore  # tokens are sensitive — NEVER commit
# Instead, just commit the README documenting what was migrated:
cat > ops/migration-2026-05-02/README.md <<EOF
# Data migration 2026-05-02 — homelab Supabase → Cloud Supabase

Tables migrated (data preserved):
- tenants, tenant_features, search_profiles
- avito_accounts (Main + Clone rows)
- avito_sessions (is_active=true only)
- user_listing_blacklists, profile_listings

Tables skipped (rebuilt by service):
- avito_listings, avito_listings_history (re-fetched on next polling tick)
- profile_runs, profile_market_stats (recomputed)
- avito_notifications (history only, not critical)
- avito_device_commands (no longer used after refactor)
- audit_log, session_history, sub_intervals (informational)

Source DB dumps NOT committed — they contain JWT tokens.
EOF
git add ops/migration-2026-05-02/.gitignore ops/migration-2026-05-02/README.md
git commit -m "docs(ops): record 2026-05-02 data migration to Cloud Supabase"
```

---

## Phase 3 — xapi refactor: remove dead code paths (TDD)

Delete components that the new manual-refresh model doesn't need: `device_switcher`, `/refresh-cycle`, `/devices/me/commands` long-poll endpoints, related models. Keep `/api/v1/sessions`, `/api/v1/accounts/poll-claim|report|session-for-sync|state`, `/api/v1/search/*`, `/api/v1/messenger/*`, `/api/v1/subscriptions/*`.

**Files affected:**
- Delete: `avito-xapi/src/workers/device_switcher.py`
- Delete: `avito-xapi/src/routers/device_commands.py`
- Delete: `avito-xapi/src/models/device_command.py`
- Modify: `avito-xapi/src/routers/accounts.py` (remove refresh-cycle endpoint, lines 226-312)
- Modify: `avito-xapi/src/main.py` (remove device_commands router include)
- Delete tests: any test file under `avito-xapi/tests/` that targets the above

### Task 3.1: Locate and inventory tests for code being removed

- [ ] **Step 1: Inventory test files referencing the removable components**

```bash
cd C:/Projects/Sync/AvitoSystem/avito-xapi
grep -rln "device_switcher\|refresh_cycle\|device_commands\|DeviceCommand" tests/ 2>/dev/null > /tmp/xapi_to_delete_tests.txt
cat /tmp/xapi_to_delete_tests.txt
```

Expected output: a list of test files (typically `tests/test_device_switcher.py`, `tests/test_refresh_cycle.py`, etc.).

- [ ] **Step 2: Write down a regression test that MUST still pass after deletion**

This is the safety harness — make sure removing dead code didn't break what we keep.

Create `avito-xapi/tests/test_xapi_surface_after_refactor.py`:

```python
"""Pin-down test: xapi keeps these endpoints after Phase 3 refactor."""
from fastapi.testclient import TestClient

EXPECTED_ROUTES = {
    "POST /api/v1/sessions",
    "GET /api/v1/sessions/current",
    "DELETE /api/v1/sessions",
    "GET /api/v1/sessions/history",
    "GET /api/v1/sessions/token-details",
    "GET /api/v1/sessions/alerts",
    "GET /api/v1/accounts",
    "POST /api/v1/accounts/poll-claim",
    "POST /api/v1/accounts/{account_id}/report",
    "GET /api/v1/accounts/{account_id}/session-for-sync",
    "PATCH /api/v1/accounts/{account_id}/state",
}

REMOVED_ROUTES = {
    "POST /api/v1/accounts/{account_id}/refresh-cycle",
    "GET /api/v1/devices/me/commands",
    "POST /api/v1/devices/me/commands",
    "POST /api/v1/devices/me/commands/{command_id}/ack",
}


def test_expected_routes_present(client: TestClient):
    """All endpoints we keep must exist in the FastAPI app."""
    routes = {f"{m} {r.path}" for r in client.app.routes for m in r.methods or []}
    missing = EXPECTED_ROUTES - routes
    assert not missing, f"Missing routes after refactor: {missing}"


def test_removed_routes_absent(client: TestClient):
    """All endpoints we removed must NOT exist."""
    routes = {f"{m} {r.path}" for r in client.app.routes for m in r.methods or []}
    leftover = REMOVED_ROUTES & routes
    assert not leftover, f"Should-be-removed routes still present: {leftover}"
```

- [ ] **Step 3: Run regression test now (it should FAIL on `removed_routes_absent`)**

```bash
cd C:/Projects/Sync/AvitoSystem/avito-xapi
pytest tests/test_xapi_surface_after_refactor.py -v
```

Expected: `test_expected_routes_present` PASSES (we haven't broken anything yet), `test_removed_routes_absent` FAILS (the routes still exist). This proves the test discriminates.

- [ ] **Step 4: Commit the safety harness**

```bash
git add tests/test_xapi_surface_after_refactor.py
git commit -m "test(xapi): pin down route surface before refresh-cycle refactor"
```

### Task 3.2: Remove `device_switcher.py` and its tests

- [ ] **Step 1: Delete the module**

```bash
cd C:/Projects/Sync/AvitoSystem/avito-xapi
rm src/workers/device_switcher.py
ls src/workers/  # verify file is gone
```

- [ ] **Step 2: Delete tests of device_switcher**

```bash
rm -f tests/test_device_switcher.py tests/workers/test_device_switcher.py 2>/dev/null
grep -l "device_switcher" tests/ -r 2>/dev/null
```

If grep returns any files, edit each and delete the lines that reference `device_switcher`. If a test file becomes empty after that, delete the file.

- [ ] **Step 3: Verify no remaining import of `device_switcher`**

```bash
grep -rn "device_switcher\|DeviceSwitcher\|DeviceSwitchError" src/ tests/
```
Expected: no matches.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(xapi): remove device_switcher (manual-refresh model)"
```

### Task 3.3: Remove `/refresh-cycle` endpoint from `accounts.py`

- [ ] **Step 1: Open `avito-xapi/src/routers/accounts.py` and delete lines 226-312**

The block to remove starts at the comment `# ----- Refresh-cycle endpoint -----` (around line 226) and includes the constants `_REFRESH_WARMUP_SEC`, `_REFRESH_CMD_EXPIRE_SEC`, and the `@router.post("/{account_id}/refresh-cycle", ...)` function definition.

Specifically delete (use Edit tool with this exact match, adjust if line numbers shifted):
```python
# ---------------------------------------------------------------------------
# Refresh-cycle endpoint
# ---------------------------------------------------------------------------

_REFRESH_WARMUP_SEC = 8
_REFRESH_CMD_EXPIRE_SEC = 120


@router.post("/{account_id}/refresh-cycle", status_code=202)
async def refresh_cycle(account_id: str):
    """..."""
    # full function body — delete entire block ending before the next "# ---" separator
```

Also delete the `from src.workers.device_switcher import ...` import at the top of the file (already broken since module was deleted).

- [ ] **Step 2: Verify accounts.py still parses**

```bash
cd C:/Projects/Sync/AvitoSystem/avito-xapi
python -c "from src.routers.accounts import router; print('OK', len(router.routes))"
```
Expected: `OK <number>` where number is now smaller than before.

- [ ] **Step 3: Run regression test from Task 3.1**

```bash
pytest tests/test_xapi_surface_after_refactor.py::test_removed_routes_absent -v
```
Expected: at least the refresh-cycle line is no longer in the leftover set. (May still fail because of /devices endpoints — fix in Task 3.4.)

- [ ] **Step 4: Commit**

```bash
git add src/routers/accounts.py
git commit -m "refactor(xapi): remove /refresh-cycle endpoint (manual model)"
```

### Task 3.4: Remove `device_commands` router

- [ ] **Step 1: Delete the router file and model**

```bash
rm src/routers/device_commands.py
rm src/models/device_command.py
```

- [ ] **Step 2: Remove router include from `src/main.py`**

Find the line that includes the device_commands router (likely):
```python
from src.routers import device_commands as device_commands_router
app.include_router(device_commands_router.router)
```

Remove both lines via Edit tool. If only one line (combined import + include), remove that one.

- [ ] **Step 3: Remove any model export from `src/models/__init__.py`**

```bash
grep -n "device_command\|DeviceCommand" src/models/__init__.py
```
If found, remove those lines.

- [ ] **Step 4: Search-and-destroy any leftover reference**

```bash
grep -rn "device_commands\|DeviceCommand" src/ tests/ 2>&1 | grep -v "test_xapi_surface_after_refactor"
```
Expected: empty. (The only remaining reference should be the regression test's REMOVED_ROUTES set, which is intentional.)

- [ ] **Step 5: Verify xapi boots**

```bash
python -c "from src.main import app; print('routes:', len(app.routes))"
```
Expected: prints route count without error.

- [ ] **Step 6: Run full regression test**

```bash
pytest tests/test_xapi_surface_after_refactor.py -v
```
Expected: BOTH tests pass.

- [ ] **Step 7: Run entire xapi test suite**

```bash
pytest -x --tb=short 2>&1 | tail -30
```
Expected: green or only test failures from deleted modules' tests (which we should have already deleted in Task 3.2 — but if any leak through, delete them now).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(xapi): remove device_commands router (APK no longer long-polls)"
```

### Task 3.5: Drop unused DB table reference in code

The `avito_device_commands` table still exists in the schema (migration 006), but no code reads/writes it anymore. We won't drop the table — leave it as historical record. Just verify no code accesses it.

- [ ] **Step 1: Grep for any remaining table reference**

```bash
grep -rn 'avito_device_commands' src/ ../avito-monitor/app/
```

If `avito-monitor/app/` has any reference, remove it as part of Phase 4. If `avito-xapi/src/` has any leftover, remove it now.

- [ ] **Step 2: No commit needed if grep was clean.**

---

## Phase 4 — avito-monitor refactor: remove proactive trigger, add one-stale alert (TDD)

**Files affected:**
- Modify: `avito-monitor/app/services/health_checker/account_tick.py` — remove `pool.trigger_refresh_cycle` calls, add `_check_pool_health` for one-stale alerts
- Modify: `avito-monitor/app/services/account_pool.py` — remove `trigger_refresh_cycle` method
- Test: `avito-monitor/tests/services/health_checker/test_account_tick_alerts.py` (new)

### Task 4.1: Write failing test for one-stale alert

- [ ] **Step 1: Create test file**

`avito-monitor/tests/services/health_checker/test_account_tick_alerts.py`:

```python
"""Tests for one-stale alert logic in account_tick after Phase 4 refactor."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.services.health_checker.account_tick import (
    account_tick_iteration,
    _alerted_stale_accounts,
)


def _account(*, id, nickname, expires_at, state="active", android_user_id=0):
    return {
        "id": id,
        "nickname": nickname,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "state": state,
        "android_user_id": android_user_id,
        "consecutive_cooldowns": 0,
    }


@pytest.fixture(autouse=True)
def reset_alert_state():
    _alerted_stale_accounts.clear()
    yield
    _alerted_stale_accounts.clear()


@pytest.mark.asyncio
async def test_no_alert_when_both_fresh():
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now + timedelta(hours=10), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now + timedelta(hours=8), android_user_id=10),
    ]
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    tg.assert_not_called()
    assert "trigger_refresh_cycle" not in str(pool.method_calls)


@pytest.mark.asyncio
async def test_one_stale_emits_alert_once():
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now - timedelta(minutes=5), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now + timedelta(hours=10), android_user_id=10),
    ]
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)
    await account_tick_iteration(pool=pool, now=now + timedelta(seconds=30), tg=tg)
    await account_tick_iteration(pool=pool, now=now + timedelta(minutes=5), tg=tg)

    # Idempotent: only one TG message emitted total despite 3 ticks
    assert tg.call_count == 1
    msg = tg.call_args.args[0]
    assert "Main" in msg
    assert "user_0" in msg


@pytest.mark.asyncio
async def test_alert_resets_when_account_recovers():
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    tg = AsyncMock()

    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now - timedelta(minutes=5), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now + timedelta(hours=10), android_user_id=10),
    ]
    await account_tick_iteration(pool=pool, now=now, tg=tg)
    assert tg.call_count == 1

    # Main recovers
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now + timedelta(hours=23), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now + timedelta(hours=10), android_user_id=10),
    ]
    await account_tick_iteration(pool=pool, now=now + timedelta(minutes=10), tg=tg)
    assert tg.call_count == 1  # no new alert during recovery

    # Main goes stale AGAIN (different cycle) — new alert allowed
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now - timedelta(minutes=1), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now + timedelta(hours=10), android_user_id=10),
    ]
    await account_tick_iteration(pool=pool, now=now + timedelta(hours=24), tg=tg)
    assert tg.call_count == 2


@pytest.mark.asyncio
async def test_both_stale_emits_critical_alert():
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now - timedelta(minutes=5), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now - timedelta(minutes=3), android_user_id=10),
    ]
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    # Three alerts total: per-account stale (Main, Clone) + critical pool-down
    assert tg.call_count == 3
    messages = " ".join(c.args[0] for c in tg.call_args_list)
    assert "Polling DOWN" in messages or "DOWN" in messages
    assert "Main" in messages
    assert "Clone" in messages


@pytest.mark.asyncio
async def test_no_proactive_refresh_call():
    """Phase 4: account_tick must NOT call trigger_refresh_cycle anywhere."""
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now + timedelta(minutes=10), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now - timedelta(minutes=5),
                 android_user_id=10, state="cooldown"),
    ]
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    # Assert that trigger_refresh_cycle was never called regardless of state
    pool.trigger_refresh_cycle.assert_not_called()
```

- [ ] **Step 2: Run tests — they should fail because the implementation hasn't changed yet**

```bash
cd C:/Projects/Sync/AvitoSystem/avito-monitor
pytest tests/services/health_checker/test_account_tick_alerts.py -v
```
Expected: at minimum `test_no_proactive_refresh_call` FAILS (current code calls trigger_refresh_cycle).

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/services/health_checker/test_account_tick_alerts.py
git commit -m "test(monitor): add failing tests for one-stale alert + no-proactive-refresh"
```

### Task 4.2: Rewrite `account_tick.py`

- [ ] **Step 1: Replace contents of `app/services/health_checker/account_tick.py`**

```python
"""Per-tick проверка состояний accounts pool. Запускается из существующего
health_checker scheduler'а каждые 30 секунд.

После Phase 4 (manual refresh model): NO proactive refresh triggers.
Only emits TG alerts on session stale (one-shot, idempotent)."""
import logging
from datetime import datetime, timezone

from app.services.account_pool import AccountPool

log = logging.getLogger(__name__)

# Module-level alert state. Idempotency: emit once per fresh→stale transition.
# Reset entry when account becomes fresh again.
# Special key 'pool_dead' tracks the both-stale critical alert.
_alerted_stale_accounts: set[str] = set()


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _is_session_stale(acc: dict, *, now: datetime) -> bool:
    exp = _parse_ts(acc.get("expires_at"))
    return exp is None or exp < now


async def account_tick_iteration(*, pool: AccountPool, now: datetime, tg) -> None:
    accounts = await pool.list_all_accounts()
    await _check_pool_health(accounts, now=now, tg=tg)


async def _check_pool_health(accounts: list[dict], *, now: datetime, tg) -> None:
    stale = [a for a in accounts if _is_session_stale(a, now=now)]
    fresh_ids = {a["id"] for a in accounts if not _is_session_stale(a, now=now)}

    # Per-account "one stale" alert (idempotent)
    for acc in stale:
        aid = acc["id"]
        if aid in _alerted_stale_accounts:
            continue
        nickname = acc.get("nickname") or aid[:8]
        user_id = acc.get("android_user_id", 0)
        other = "Clone" if nickname == "Main" or "Main" in nickname else "Main"
        await tg(
            f"📩 Аккаунт {nickname} протух (last refresh устарел). "
            f"Polling работает на {other}. Открой Avito-app в user_{user_id} "
            f"для восстановления safety net."
        )
        _alerted_stale_accounts.add(aid)

    # Reset alert state for accounts that became fresh again
    _alerted_stale_accounts.intersection_update(
        {x for x in _alerted_stale_accounts if x not in fresh_ids}
        | {"pool_dead"}  # preserve pool_dead key, handled separately below
    )
    for fid in fresh_ids:
        _alerted_stale_accounts.discard(fid)

    # Pool-wide critical alert: both stale
    if len(accounts) >= 2 and len(stale) == len(accounts):
        if "pool_dead" not in _alerted_stale_accounts:
            await tg(
                "🚨 Polling DOWN — все аккаунты протухли. "
                "Срочно открой Avito-app на phone'е (оба пользователя)."
            )
            _alerted_stale_accounts.add("pool_dead")
    else:
        _alerted_stale_accounts.discard("pool_dead")
```

- [ ] **Step 2: Run the test suite for this file**

```bash
cd C:/Projects/Sync/AvitoSystem/avito-monitor
pytest tests/services/health_checker/test_account_tick_alerts.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 3: Run wider monitor test suite**

```bash
pytest -x --tb=short 2>&1 | tail -30
```

Expected: green or only failures in tests that exercised the now-deleted `trigger_refresh_cycle` flow. If any such test exists, delete it (it tested removed behavior).

- [ ] **Step 4: Commit**

```bash
git add app/services/health_checker/account_tick.py
git commit -m "refactor(monitor): replace proactive refresh with one-stale TG alerts"
```

### Task 4.3: Remove `trigger_refresh_cycle` from `account_pool.py`

- [ ] **Step 1: Edit `avito-monitor/app/services/account_pool.py` — delete the method**

Locate (around line 63):
```python
    async def trigger_refresh_cycle(self, account_id: str) -> dict:
        """Используется monitor health_checker для запуска refresh."""
        resp = await self.xapi.post(f"/api/v1/accounts/{account_id}/refresh-cycle")
        resp.raise_for_status()
        return resp.json()
```

Delete this entire method.

- [ ] **Step 2: Verify no remaining caller**

```bash
cd C:/Projects/Sync/AvitoSystem/avito-monitor
grep -rn "trigger_refresh_cycle" app/ tests/
```
Expected: no matches.

- [ ] **Step 3: Run smoke test of pool client**

```bash
python -c "from app.services.account_pool import AccountPool; print(dir(AccountPool))" \
  | tr ',' '\n' | grep -E "^\s*'[^_]" | head -10
```
Expected: lists remaining methods (`claim_for_poll`, `report`, `claim_for_sync`, `list_active_accounts`, `list_all_accounts`, `patch_state`) — no `trigger_refresh_cycle`.

- [ ] **Step 4: Commit**

```bash
git add app/services/account_pool.py
git commit -m "refactor(monitor): drop AccountPool.trigger_refresh_cycle"
```

### Task 4.4: Update `DOCS/REFERENCE/02-auth-and-tokens.md` to reflect new model

- [ ] **Step 1: Edit `DOCS/REFERENCE/02-auth-and-tokens.md` §D.2 and §D.3**

Replace existing §D.2 contents with:
```markdown
### D.2 Health-checker (one-stale alerts only, no automatic refresh)

После Phase 4 (manual refresh model) `account_tick.py` НЕ триггерит refresh.
Раз в 30 сек проверяет всех аккаунтов и эмитит TG-alert один раз на переход
fresh → stale:

- 1 stale: «📩 Аккаунт X протух, polling на Y, обнови Avito-app в user_N»
- Все stale: «🚨 Polling DOWN, открой Avito-app на phone'е»

Stale = `expires_at IS NULL OR expires_at < NOW()`. Reset alert state когда
аккаунт снова становится fresh.

Источник: `avito-monitor/app/services/health_checker/account_tick.py`.
```

Replace existing §D.3 contents with:
```markdown
### D.3 Refresh Flow (manual)

```
[Юзер вручную, утром user_0 / вечером user_10:]
1. Открыть Avito-app в нужном Android-user'е на 60-90 сек.
2. Avito-app сам решает refresh (по своей внутренней логике near-expiry).
3. Avito-app пишет новый JWT в SharedPrefs + emits push о login/refresh.

[На phone'е автоматически:]
4. AvitoSessionManager APK ловит push через NotificationListener.
5. APK читает SharedPrefs через root.
6. APK POST https://<server>/api/v1/sessions с новым session_token + всем pack'ом.

[На сервере (xapi /sessions):]
7. resolve_or_create_account(payload.u, payload.device_id) → account row.
8. Деактивирует прежнюю активную сессию аккаунта.
9. INSERT новую avito_sessions с expires_at из JWT exp.
10. Если account.state == 'waiting_refresh' → 'active'. (Для 'dead' state
    — патчится вручную через PATCH /accounts/{id}/state.)

Backup путь: register_clone_session.py (manual ADB-extract + POST) если
APK сломался.
```

Источник: `avito-xapi/src/routers/sessions.py:30-106`.
```

Also: remove §H («refresh-cycle endpoint» — больше не существует).

- [ ] **Step 2: Update doc header date**

```markdown
**Компилировано:** 2026-04-28. **Refresh Hardening update:** 2026-04-30 (D.2/D.3/E/G/H/I).
**Manual refresh model:** 2026-05-02 (D.2/D.3 переписаны, refresh-cycle удалён).
```

- [ ] **Step 3: Commit**

```bash
git add DOCS/REFERENCE/02-auth-and-tokens.md
git commit -m "docs: rewrite D.2/D.3 for manual refresh model (Phase 4)"
```

---

## Phase 5 — Server deployment artifacts (compose, Caddy, env)

Build all the deployment files. Apply via jump host so we don't need edge open yet.

**Files to create on the server (81.200.119.132):**
- `/opt/avito-system/docker-compose.yml`
- `/opt/avito-system/.env`
- `/opt/avito-system/Caddyfile`
- `/opt/avito-system/data/` (directory for redis persistence)

### Task 5.1: Author `docker-compose.yml`

- [ ] **Step 1: Create the compose file in repo**

`ops/server/docker-compose.yml`:
```yaml
services:
  caddy:
    image: caddy:2.8-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - avito-monitor
      - avito-xapi
    mem_limit: 80m

  avito-xapi:
    image: ghcr.io/n8nremacs/avito-xapi:latest  # or build context, see notes
    restart: unless-stopped
    environment:
      DATABASE_URL: ${DATABASE_URL}
      AVITO_XAPI_API_KEY: ${AVITO_XAPI_API_KEY}
      RATE_LIMIT_RPS: "1.0"
      RATE_LIMIT_BURST: "3"
      LOG_LEVEL: INFO
    expose:
      - "8080"
    depends_on:
      - redis
    mem_limit: 256m

  avito-monitor:
    image: ghcr.io/n8nremacs/avito-monitor:latest  # or build context
    restart: unless-stopped
    environment:
      DATABASE_URL: ${DATABASE_URL}
      XAPI_URL: http://avito-xapi:8080
      XAPI_API_KEY: ${AVITO_XAPI_API_KEY}
      REDIS_URL: redis://redis:6379/0
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
      TG_BOT_TOKEN: ${TG_BOT_TOKEN}
      TG_CHAT_ID: ${TG_CHAT_ID}
      LOG_LEVEL: INFO
    expose:
      - "8000"
    depends_on:
      - redis
      - avito-xapi
    mem_limit: 480m

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --maxmemory 64mb --maxmemory-policy allkeys-lru --appendonly no
    volumes:
      - ./data/redis:/data
    expose:
      - "6379"
    mem_limit: 96m

volumes:
  caddy_data:
  caddy_config:
```

**Note about images:** if there's no published GHCR image, use `build:` blocks with `context: ../../avito-xapi` and `context: ../../avito-monitor`. The plan assumes you'll do an initial `docker compose build` on the server.

- [ ] **Step 2: Author `Caddyfile`**

`ops/server/Caddyfile` (assuming Phase 0 Option B — DuckDNS hostname `avitosystem.duckdns.org`):
```
avitosystem.duckdns.org {
    encode zstd gzip

    # Public sessions endpoint (APK posts here from phone)
    handle /api/v1/sessions* {
        reverse_proxy avito-xapi:8080
    }

    # Internal-ish xapi endpoints — should be auth'd by API key middleware,
    # but keep public route exposed since avito-monitor calls them too.
    handle /api/v1/accounts* {
        reverse_proxy avito-xapi:8080
    }
    handle /api/v1/search* {
        reverse_proxy avito-xapi:8080
    }
    handle /api/v1/messenger* {
        reverse_proxy avito-xapi:8080
    }
    handle /api/v1/subscriptions* {
        reverse_proxy avito-xapi:8080
    }

    # Avito-monitor dashboard + bot webhook
    handle {
        reverse_proxy avito-monitor:8000
    }

    # Logs
    log {
        output file /data/access.log {
            roll_size 10mb
            roll_keep 5
        }
    }
}
```

**If Phase 0 Option A (IP-only):** Replace `avitosystem.duckdns.org` with `81.200.119.132` and add `tls internal` directive — this gives self-signed cert which APK won't trust without manual cert install. Better to go with B.

- [ ] **Step 3: Author `.env.template`**

`ops/server/.env.template`:
```bash
# Supabase Cloud — Frankfurt (drwgozasaypgphkxyizt)
# Use POOLED connection string (port 6543, transaction mode) for app traffic.
DATABASE_URL=postgresql://postgres.drwgozasaypgphkxyizt:<DB_PASSWORD>@aws-0-eu-central-1.pooler.supabase.com:6543/postgres

# xapi internal API key — generate fresh, share with APK serverApiKey via PrefsManager
AVITO_XAPI_API_KEY=<generate-with-openssl-rand-hex-32>

# OpenRouter LLM key — read from c:/Projects/Sync/AvitoSystem/.env (rotated 2026-04-29)
OPENROUTER_API_KEY=<value>

# Telegram bot — see CLAUDE.md global, ZipMobile bot
TG_BOT_TOKEN=<value>
TG_CHAT_ID=<your-chat-id>

# Domain Caddy serves (must match Caddyfile)
DOMAIN=avitosystem.duckdns.org
```

- [ ] **Step 4: Add `.env` to `.gitignore` if not already**

```bash
cd C:/Projects/Sync/AvitoSystem
grep -q "ops/server/.env$" .gitignore || echo "ops/server/.env" >> .gitignore
```

- [ ] **Step 5: Commit deployment files**

```bash
git add ops/server/docker-compose.yml ops/server/Caddyfile ops/server/.env.template .gitignore
git commit -m "feat(ops): add server deployment artifacts (compose, Caddy, env template)"
```

### Task 5.2: Smoke-test compose locally (in jump-host context)

- [ ] **Step 1: Copy compose files to server**

```bash
scp -J root@155.212.217.226 -r ops/server/ root@81.200.119.132:/opt/avito-system/
```

- [ ] **Step 2: Validate compose syntax remotely**

```bash
ssh -J root@155.212.217.226 root@81.200.119.132 \
  "cd /opt/avito-system && docker compose config --quiet && echo 'compose-syntax-OK'"
```
Expected: `compose-syntax-OK` printed (any error = stop and fix the YAML).

- [ ] **Step 3: Build images on the server (or pull if pre-built)**

If using build-context approach, copy source dirs too. For initial bootstrap I recommend build-on-server:

```bash
# Copy entire repo to server (or just avito-xapi + avito-monitor)
rsync -avz -e "ssh -J root@155.212.217.226" \
  --exclude '.git' --exclude '__pycache__' --exclude 'node_modules' \
  --exclude '*.pyc' --exclude '.venv' --exclude 'AvitoAll' \
  C:/Projects/Sync/AvitoSystem/ root@81.200.119.132:/opt/avito-system/repo/

# Adjust docker-compose.yml `image:` lines to `build: ../repo/avito-xapi` etc.
```

This step's exact mechanics depend on which Dockerfile already exists. Verify each Dockerfile builds standalone before chaining into compose.

- [ ] **Step 4: Don't `up -d` yet — Phase 6 needs DNS + edge open first.**

---

## Phase 6 — Edge open + DNS + first deploy

Requires Phase 0.1 (Beget firewall) + Phase 0.3 (DuckDNS or domain) done.

### Task 6.1: Verify edge is open

- [ ] **Step 1: From local PowerShell**

```powershell
Test-NetConnection -ComputerName 81.200.119.132 -Port 22 -InformationLevel Quiet
Test-NetConnection -ComputerName 81.200.119.132 -Port 80 -InformationLevel Quiet
Test-NetConnection -ComputerName 81.200.119.132 -Port 443 -InformationLevel Quiet
```
Expected: all three return `True`. If any returns `False`, escalate Beget ticket — STOP, don't proceed.

- [ ] **Step 2: Direct SSH (no jump host)**

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 root@81.200.119.132 "uptime; docker version --format '{{.Server.Version}}'"
```
Expected: prints uptime + Docker version. If hangs/refuses — re-verify Step 1.

### Task 6.2: Configure DuckDNS (if Phase 0 Option B)

- [ ] **Step 1: Register `avitosystem.duckdns.org` at https://www.duckdns.org**, point to `81.200.119.132`. Save the DuckDNS token (will use for keep-updated cron, optional).
- [ ] **Step 2: Verify DNS resolution**

```bash
nslookup avitosystem.duckdns.org 1.1.1.1
```
Expected: A record `81.200.119.132`.

- [ ] **Step 3: Verify HTTP reachability via hostname**

```bash
curl -v http://avitosystem.duckdns.org/ 2>&1 | head -10
```

Expected: connection succeeds (probably 502 since no service yet — that's fine, means Caddy is wired but compose isn't up).

### Task 6.3: First deploy

- [ ] **Step 1: Edit `.env` on server with real secrets**

```bash
ssh root@81.200.119.132 'nano /opt/avito-system/.env'  # interactive
```
Fill in:
- `DATABASE_URL` (Supabase Pooled URI, port 6543)
- `AVITO_XAPI_API_KEY` — generate via `openssl rand -hex 32` on the server
- `OPENROUTER_API_KEY` — copy from `C:/Projects/Sync/AvitoSystem/.env`
- `TG_BOT_TOKEN`, `TG_CHAT_ID` — copy from `C:/Projects/Sync/CLAUDE.md`
- `DOMAIN=avitosystem.duckdns.org`

- [ ] **Step 2: First `docker compose up -d`**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose up -d --build 2>&1 | tail -30'
```
Expected: 4 containers `Created` and `Started`: `caddy`, `avito-xapi`, `avito-monitor`, `redis`.

- [ ] **Step 3: Verify containers healthy**

```bash
ssh root@81.200.119.132 'docker compose -f /opt/avito-system/docker-compose.yml ps'
```
Expected: all four `Up` (avito-monitor may take 30-60s for first boot).

- [ ] **Step 4: Verify Caddy issued TLS cert**

```bash
ssh root@81.200.119.132 'docker logs avito-system-caddy-1 2>&1 | grep -E "certificate|certificate_obtained|ok" | tail -5'
```
Expected: Let's Encrypt-related success log within 1-2 minutes of first up.

- [ ] **Step 5: External smoke test**

```bash
curl -v https://avitosystem.duckdns.org/health 2>&1 | tail -10
```
Expected: 200 OK with JSON `{"status":"ok",...}` (avito-monitor's standard health endpoint).

- [ ] **Step 6: Verify avito-xapi reachable internally**

```bash
ssh root@81.200.119.132 'curl -sH "X-Api-Key: $(grep AVITO_XAPI_API_KEY /opt/avito-system/.env | cut -d= -f2)" \
  http://localhost/api/v1/accounts | python3 -m json.tool | head -20'
```
Expected: JSON list with accounts (Main + Clone migrated from homelab). If 401 — API key mismatch. If empty — verify Phase 2 data migration ran.

- [ ] **Step 7: Commit final deployment artifacts (in case any tweaks made in Step 1)**

Nothing committed if `.env` is gitignored (it should be). The `.env.template` is the only committed artifact.

---

## Phase 7 — APK URL repoint (user actions on phone)

Manual UI changes in the AvitoSessionManager APK. No code change.

### Task 7.1: Repoint user_0 APK

- [ ] **Step 1** (user) — Switch phone to user_0 (Main). Open AvitoSessionManager app.
- [ ] **Step 2** (user) — Open Settings within the app (gear icon or menu). Find `Server URL` field.
- [ ] **Step 3** (user) — Replace current value (likely `http://213.108.170.194:8080` — homelab) with `https://avitosystem.duckdns.org`. **No port suffix** — Caddy handles 443 automatically.
- [ ] **Step 4** (user) — Find `Server API Key` field. Replace with the value of `AVITO_XAPI_API_KEY` from server `.env`. Get this value via:
```bash
ssh root@81.200.119.132 'grep AVITO_XAPI_API_KEY /opt/avito-system/.env'
```
Type it into APK Settings.
- [ ] **Step 5** (user) — Find `Auto Launch Avito` toggle, turn it **OFF**. (This was the monkey-scroll behavior we don't want anymore.)
- [ ] **Step 6** (user) — Save settings. App should show new URL on main screen.
- [ ] **Step 7** (user) — Tap "Sync now" or equivalent. APK should attempt POST and report success.

Verify on server side:
```bash
ssh root@81.200.119.132 \
  'curl -sH "X-Api-Key: $(grep AVITO_XAPI_API_KEY /opt/avito-system/.env | cut -d= -f2)" \
   https://localhost/api/v1/sessions/current -k'
```

### Task 7.2: Repoint user_10 APK

- [ ] **Step 1** (user) — Switch phone to user_10 (Clone via lock-screen → switch user).
- [ ] **Step 2-7** — Repeat 7.1 steps in user_10's APK.

### Task 7.3: First end-to-end manual refresh test

- [ ] **Step 1** (user) — In user_10, open Avito-app. Wait 60-90 sec.
- [ ] **Step 2** — Verify on server:
```bash
ssh root@81.200.119.132 'docker logs avito-system-avito-xapi-1 --since=2m 2>&1 | grep -i "POST.*sessions"'
```
Expected: a POST to `/api/v1/sessions` from APK in user_10 within 10-30 sec.

- [ ] **Step 3** — Verify in DB:
Open Supabase SQL Editor:
```sql
SELECT account_id, expires_at, created_at FROM avito_sessions
WHERE is_active=true ORDER BY created_at DESC LIMIT 3;
```
Expected: a fresh row with `created_at` matching when user opened Avito-app.

- [ ] **Step 4** — Verify polling resumes:
```bash
ssh root@81.200.119.132 'docker logs avito-system-avito-monitor-1 --since=2m 2>&1 | grep -E "poll-claim|fetch_with_pool" | tail -5'
```
Expected: claim succeeds, listings fetched.

---

## Phase 8 — Cutover and homelab decommission

### Task 8.1: Stop polling on homelab

- [ ] **Step 1** — Stop avito-monitor on homelab:
```bash
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && docker compose stop'
```

- [ ] **Step 2** — Verify only one polling instance is now running (the new server's). Check Telegram chat — should still receive notifications, but their `source` field will indicate new server.

### Task 8.2: Stop xapi on homelab

- [ ] **Step 1** — Stop xapi on homelab:
```bash
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-xapi && docker compose stop'
```
APK no longer points at homelab, so this won't break anything.

- [ ] **Step 2** — Optional: `docker compose down` to remove containers entirely. Don't delete images yet — keep them as rollback path for 30 days.

### Task 8.3: Update `CONTINUE.md` to reflect new state

- [ ] **Step 1** — Edit `CONTINUE.md` § 1 (current state) — replace homelab references:

Replace:
```markdown
**Дата:** 2026-04-30 19:30 UTC. **Refresh Hardening shipped в `main`** ...
```

With:
```markdown
**Дата:** 2026-05-02. **Server Migration shipped — homelab decommissioned as middleware.**

avito-monitor + avito-proxy + Caddy/TLS на новом VPS (81.200.119.132, RU).
DB на Supabase Cloud (drwgozasaypgphkxyizt, Frankfurt).
APK на phone'е POSTит /sessions напрямую на сервер.
Refresh — manual: утро user_0, вечер user_10. Health-checker эмитит only
one-stale alerts, не триггерит refresh.

Removed: device_switcher, /refresh-cycle, /devices/me/commands, monkey-scroll.
```

- [ ] **Step 2** — Update CONTINUE.md § 2 backlog: remove the "second Avito account" item (it was tied to ADB pool), unless still relevant. Keep "captcha/IP-ban detection" if still applicable.

- [ ] **Step 3** — Commit:
```bash
git add CONTINUE.md
git commit -m "docs: cutover to dedicated server + manual refresh model (2026-05-02)"
```

### Task 8.4: 7-day soak observation

This is operational, not a code task. Watch for one week:
- Are TG alerts firing correctly when user forgets to open Avito-app?
- Does manual refresh consistently produce fresh sessions on each open?
- Any unexpected errors in `docker logs avito-system-avito-monitor-1`?

If issues arise — rollback path: `ssh homelab; docker compose up -d` resurrects old infra; APK Settings can be reverted to homelab URL within 1 min.

---

## Self-review — gaps and consistency check

After writing the full plan, ran the spec coverage check:

- ✅ **Spec point 1** (Supabase Cloud migration of schema+data from homelab): Phases 1-2 cover both schema (via SQL Editor) and data (selective table dump+restore).
- ✅ **Spec point 2** (xapi refactor — remove device_switcher / refresh-cycle / device-commands long-poll / monkey-scroll): Phase 3, broken into 5 tasks with TDD safety harness. Note: the **monkey-scroll logic** lives in the APK (`AvitoSessionManager`), not xapi. Cleanup in xapi is correct (remove the cmd-issuing endpoint). The phone-side disabling is handled via APK Settings UI in Phase 7 (`autoLaunchAvito = OFF`).
- ✅ **Spec point 3** (avito-monitor + avito-proxy deploy on 81.200.119.132): Phase 5 (artifacts) + Phase 6 (deploy).
- ✅ **Spec point 4** (Caddy + auto-TLS via Let's Encrypt): Phase 5.1 Caddyfile with HTTP-01 via DuckDNS hostname; Phase 6.3 Step 4 verifies cert issued.
- ✅ **Spec point 5** (APK URL repoint via Settings UI in user_0 and user_10, autoLaunchAvito=false): Phase 7, both users covered, autoLaunchAvito explicitly toggled off.
- ✅ **Spec point 6** (one-stale alert logic in account_tick replacing proactive-refresh): Phase 4 (TDD), tests cover all 4 cases (both fresh / one stale / recovery / both stale).
- ✅ **Spec point 7** (homelab decommission as middleware, only Supabase remains optional): Phase 8 stops both services on homelab. Note: Phase 7 already moves DB load to Cloud, so by Phase 8 homelab is fully out of the runtime loop. The "only Supabase remains" is moot since user is migrating Supabase to Cloud too.

**Placeholder scan:** none. All steps contain concrete code/commands. The closest to placeholder is `<DB_PASSWORD>` in `.env.template` — that's correct (it's a literal placeholder for user secret value, intentional).

**Type consistency:** all method signatures match across tasks (`account_tick_iteration`, `_check_pool_health`, `_alerted_stale_accounts`). The set is module-level, persisted across ticks via Python interpreter lifetime (resets on container restart — acceptable for personal V1 since restart is rare and false-positive at restart is benign).

**Known caveat:** Phase 2 data migration assumes pg_dump can connect to homelab (213.108.170.194:5433) with the password. If homelab DB isn't reachable from local machine without VPN, run pg_dump on homelab itself: `ssh homelab 'PGPASSWORD=... pg_dump ... > /tmp/dump.sql'` then `scp` back to local then upload to Supabase via SQL Editor.

---

## Plan complete — execution choice

Plan saved to `DOCS/superpowers/plans/2026-05-02-server-migration.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Good for code-heavy phases (3, 4).

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Good for ops-heavy phases (1, 2, 6, 7) where each task has a verify step.

**My recommendation:** mixed — Phase 1 (schema migration) and Phase 7 (APK UI changes) you do yourself in Supabase Dashboard / on the phone (manual UI work, can't subagent that). Phases 2, 3, 4, 5, 6, 8 — subagent-driven so I can hand each to a fresh agent with the spec they need.

Which approach?
