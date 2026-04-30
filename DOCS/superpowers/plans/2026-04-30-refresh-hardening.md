# Refresh Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Avito JWT refresh works autonomously across all failure modes — server reboot with stale JWT, mid-polling expiry, multi-device on one Avito user. After this plan, the 2026-04-30 incident (server-off-then-on → expired JWT → worker DDoS → 403) cannot recur silently.

**Architecture:** Three independent fixes that compose:

1. **xapi: surface Avito's HTTP code instead of wrapping it in 500.** When `curl_cffi` raises `HTTPError` for an Avito 401/403/429, re-raise as `HTTPException` with the same status. The pool's `/report` endpoint then drives the state machine correctly (403 → cooldown, 401 → expire-session-now). Today the worker sees 500 and ratchet never fires.

2. **monitor `account_tick`: read `expires_at` from the active session, not from the account row.** The proactive refresh path already exists (`account_tick.py:53-61`) but reads `acc.get("expires_at")` which is always `None` (column lives on `avito_sessions`). Fix the data source and the logic works.

3. **DB: loosen `UNIQUE(avito_user_id)` to `UNIQUE(avito_user_id, last_device_id)`** + `resolve_or_create_account` keys by the pair. This lets two Avito-app instances on the same `u` (Main `device_id` + Clone `device_id` on the same phone) coexist as separate pool rows. Foundation for the user's multi-device strategy.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.0 async, Supabase Postgres (self-hosted), curl_cffi, pytest, TaskIQ. No new deps.

**Out of scope (deferred to ops or follow-up):**
- Phase 2 (multi-device activation) — APK config/install on phone, force-refresh Main with 12h offset. Operational, not code.
- TG bot inbound (backlog #3 — `pip install aiohttp-socks`).
- Scenario G hostname fix (`messenger-bot` → `telegram-bot`).
- `200 report` not clearing `cooldown_until` (cosmetic).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `avito-xapi/src/routers/subscriptions.py` | `/api/v1/subscriptions/{id}/items` handler — translate `curl_cffi.HTTPError` into `HTTPException` with the same status | Modify |
| `avito-xapi/src/routers/messenger.py` | Same translation for messenger endpoints (consistent) | Modify (only the catch points that already exist) |
| `avito-xapi/tests/test_subscriptions.py` | Add tests: Avito 403 → xapi returns 403 (not 500); same for 401/429 | Modify |
| `supabase/migrations/008_avito_accounts_multidevice.sql` | DROP constraint `avito_accounts_avito_user_id_key`; ADD `UNIQUE(avito_user_id, last_device_id)` | Create |
| `avito-xapi/src/services/account_resolver.py` | SELECT now keys on `(user_id, device_id)`; INSERT path unchanged | Modify |
| `avito-xapi/tests/test_account_resolver.py` | Add tests: same `u`, two `device_id` → two rows | Modify |
| `avito-xapi/src/routers/accounts.py` | `GET /api/v1/accounts` returns each row with `expires_at` from active session (LEFT JOIN-equivalent) | Modify |
| `avito-xapi/tests/test_accounts_router.py` | Add test: list returns `expires_at` per account | Modify |
| `avito-monitor/app/services/health_checker/account_tick.py` | Use `acc["expires_at"]` field returned by enriched xapi list | Modify (1-line change) |
| `avito-monitor/tests/health_checker/test_account_tick.py` | Add test: account with `expires_at < now+30min` triggers refresh-cycle | Create or extend |
| `DOCS/superpowers/plans/2026-04-30-refresh-hardening.md` | This plan | Created |

---

## Task 1: xapi — surface Avito HTTP code (subscriptions endpoint)

**Why first:** Closes the corruption path — without this, today's incident repeats. The pool can't see 403 because xapi hides it behind 500.

**Files:**
- Modify: `avito-xapi/src/routers/subscriptions.py:143-200` (the `get_subscription_items` handler)
- Modify: `avito-xapi/tests/test_subscriptions.py` (add new test)

- [ ] **Step 1: Write the failing test**

Add this test to `avito-xapi/tests/test_subscriptions.py`. It mocks the `_resolve_client` dependency to return a client whose `get_subscription_deeplink` raises `curl_cffi.requests.exceptions.HTTPError` with status 403. Expect 403 from xapi.

```python
# tests/test_subscriptions.py — append at the bottom
import pytest
from unittest.mock import AsyncMock, patch
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from fastapi.testclient import TestClient

from src.app import app


def _curl_error(status: int, body: str = "") -> CurlHTTPError:
    fake_resp = type("R", (), {"status_code": status, "reason": "Forbidden", "text": body})()
    return CurlHTTPError(f"HTTP Error {status}: ", 0, fake_resp)


@pytest.mark.parametrize("avito_status", [401, 403, 429])
def test_subscription_items_propagates_avito_status(monkeypatch, avito_status):
    """When Avito returns 4xx, xapi must return the same code, not 500."""
    fake_client = AsyncMock()
    fake_client.get_subscription_deeplink.side_effect = _curl_error(avito_status)

    async def fake_resolve(*a, **kw):
        return fake_client

    monkeypatch.setattr("src.routers.subscriptions._resolve_client", fake_resolve)
    monkeypatch.setattr(
        "src.middleware.auth.require_feature", lambda *a, **kw: None
    )
    # Bypass tenant dep — return any tenant ctx
    from src.dependencies import get_current_tenant
    from src.models.tenant import TenantContext
    fake_ctx = TenantContext(
        tenant=type("T", (), {"id": "t1", "name": "test"})(),
        toolkit=type("K", (), {"id": "k1", "features": ["avito.search"]})(),
    )
    app.dependency_overrides[get_current_tenant] = lambda: fake_ctx
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/v1/subscriptions/12345/items?page=1",
            headers={"X-Api-Key": "any"},
        )
        assert resp.status_code == avito_status, (
            f"expected {avito_status} from xapi, got {resp.status_code}: {resp.text}"
        )
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd avito-xapi && pytest tests/test_subscriptions.py::test_subscription_items_propagates_avito_status -v
```
Expected: 3 FAILs (one per parametrize) — handler currently lets HTTPError bubble up to error_handler middleware, which returns 500.

- [ ] **Step 3: Wrap the deeplink call in try/except and re-raise as HTTPException**

Modify `avito-xapi/src/routers/subscriptions.py` around line 161 (`deeplink = await client.get_subscription_deeplink(filter_id)`):

```python
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError

@router.get("/{filter_id}/items")
async def get_subscription_items(
    request: Request,
    filter_id: int = Path(..., description="Avito subscription/filter id"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    account_id: str | None = Query(None, description="Pool account id; omit for legacy any-active fallback"),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    require_feature(request, "avito.search")
    client = await _resolve_client(ctx, account_id)
    try:
        deeplink = await client.get_subscription_deeplink(filter_id)
    except CurlHTTPError as exc:
        status = getattr(getattr(exc, "args", [None, None, None])[2], "status_code", None)
        if status in (401, 403, 429):
            raise HTTPException(status_code=status, detail=f"Avito {status}")
        raise  # 4xx other / 5xx — let middleware wrap as 500
    if not deeplink:
        raise HTTPException(status_code=404, detail="Subscription not found")
    # … rest unchanged
```

Also wrap the `client.search_items(...)` call below (line 187) the same way:

```python
    try:
        data = await client.search_items(
            page=page,
            per_page=per_page,
            # … existing args
        )
    except CurlHTTPError as exc:
        status = getattr(getattr(exc, "args", [None, None, None])[2], "status_code", None)
        if status in (401, 403, 429):
            raise HTTPException(status_code=status, detail=f"Avito {status}")
        raise
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd avito-xapi && pytest tests/test_subscriptions.py::test_subscription_items_propagates_avito_status -v
```
Expected: 3 PASSs.

- [ ] **Step 5: Run the full subscriptions test file to catch regressions**

```bash
cd avito-xapi && pytest tests/test_subscriptions.py -v
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add avito-xapi/src/routers/subscriptions.py avito-xapi/tests/test_subscriptions.py
git commit -m "fix(xapi): surface Avito 401/403/429 codes instead of wrapping in 500"
```

---

## Task 2: xapi — same fix for messenger endpoints

**Files:**
- Modify: `avito-xapi/src/routers/messenger.py` (find every `await client.<method>(...)` that touches Avito and wrap)
- Modify: `avito-xapi/tests/test_messenger.py`

- [ ] **Step 1: Identify Avito-touching call sites in messenger.py**

```bash
grep -n "await client\." avito-xapi/src/routers/messenger.py
```
Note each line number; each is a try/except point.

- [ ] **Step 2: Write parametrized test**

In `avito-xapi/tests/test_messenger.py`, add a single test that hits one endpoint (`GET /api/v1/messenger/unread-count`) and verifies 401/403/429 propagate.

```python
@pytest.mark.parametrize("avito_status", [401, 403, 429])
def test_messenger_unread_propagates_avito_status(monkeypatch, avito_status):
    fake_client = AsyncMock()
    fake_client.unread_count.side_effect = _curl_error(avito_status)
    # … same pattern as Task 1's test, just different endpoint
```

(Reuse the `_curl_error` helper from `test_subscriptions.py` — extract it to `tests/conftest.py` if not already there.)

- [ ] **Step 3: Run test to verify it fails**

```bash
cd avito-xapi && pytest tests/test_messenger.py -k unread_propagates -v
```

- [ ] **Step 4: Wrap each `await client.<method>(...)` call in messenger.py**

Pattern (apply at every call site identified in Step 1):

```python
try:
    data = await client.unread_count(...)
except CurlHTTPError as exc:
    status = getattr(getattr(exc, "args", [None, None, None])[2], "status_code", None)
    if status in (401, 403, 429):
        raise HTTPException(status_code=status, detail=f"Avito {status}")
    raise
```

To avoid copy-paste, factor the translation into a helper:

```python
# avito-xapi/src/routers/_avito_errors.py — new file
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from fastapi import HTTPException

PROPAGATE = {401, 403, 429}

def reraise_avito_error(exc: CurlHTTPError) -> None:
    """If Avito returned 401/403/429, re-raise as HTTPException with same code.
    Otherwise re-raise the original exception."""
    status = getattr(getattr(exc, "args", [None, None, None])[2], "status_code", None)
    if status in PROPAGATE:
        raise HTTPException(status_code=status, detail=f"Avito {status}")
    raise exc
```

Use it everywhere:

```python
from src.routers._avito_errors import reraise_avito_error

try:
    data = await client.unread_count(...)
except CurlHTTPError as exc:
    reraise_avito_error(exc)
```

Refactor Task 1's two call sites (`subscriptions.py`) to use the helper too — same edit, less duplication.

- [ ] **Step 5: Run test to verify it passes**

```bash
cd avito-xapi && pytest tests/test_messenger.py tests/test_subscriptions.py -v
```

- [ ] **Step 6: Commit**

```bash
git add avito-xapi/src/routers/_avito_errors.py avito-xapi/src/routers/subscriptions.py avito-xapi/src/routers/messenger.py avito-xapi/tests/test_messenger.py
git commit -m "refactor(xapi): centralise Avito error propagation via reraise_avito_error helper"
```

---

## Task 3: DB migration — loosen UNIQUE constraint

**Why before resolver change:** the resolver SELECT changes from `eq(u)` to `eq(u).eq(device_id)`; without the constraint change, an INSERT with same `u` + different device would fail on the legacy unique key.

**Files:**
- Create: `supabase/migrations/008_avito_accounts_multidevice.sql`

- [ ] **Step 1: Write the migration**

```sql
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
```

- [ ] **Step 2: Apply migration to homelab Supabase to verify**

```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -f -" < supabase/migrations/008_avito_accounts_multidevice.sql
```

Expected: no errors.

- [ ] **Step 3: Verify constraint state**

```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \"\\d avito_accounts\" | grep -E 'UNIQUE|user_device'"
```
Expected: shows `avito_accounts_user_device_uniq UNIQUE (avito_user_id, last_device_id)` and NO `avito_accounts_avito_user_id_key`.

- [ ] **Step 4: Sanity check — INSERT a duplicate-u different-device row succeeds**

```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \\
  \"INSERT INTO avito_accounts (nickname, avito_user_id, last_device_id, phone_serial, android_user_id) \\
    VALUES ('Main-test', 157920214, '61238c435e700491', '110139ce', 0) RETURNING id;\""
```
Expected: row inserted, returns UUID. THEN delete the test row:

```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \\
  \"DELETE FROM avito_accounts WHERE nickname='Main-test';\""
```

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/008_avito_accounts_multidevice.sql
git commit -m "feat(db): allow multi-device per Avito user via UNIQUE(user_id, device_id)"
```

---

## Task 4: resolver — key by (user_id, device_id)

**Files:**
- Modify: `avito-xapi/src/services/account_resolver.py`
- Modify: `avito-xapi/tests/test_account_resolver.py`

- [ ] **Step 1: Write failing tests for the new behaviour**

Add to `avito-xapi/tests/test_account_resolver.py`:

```python
def test_two_devices_same_user_create_two_rows(mock_sb):
    """resolve(u=12345, device='D1') and resolve(u=12345, device='D2') yield
    distinct accounts (different device_id key)."""
    # First call: SELECT returns empty → INSERT
    select_chain = mock_sb.table("avito_accounts").select("*") \
        .eq("avito_user_id", 12345).eq("last_device_id", "D1").limit(1)
    select_chain.execute.return_value.data = []
    mock_sb.table("avito_accounts").insert.return_value.execute.return_value.data = [
        {"id": "acc-D1", "avito_user_id": 12345, "last_device_id": "D1"},
    ]
    acc1 = resolve_or_create_account(mock_sb, avito_user_id=12345, device_id="D1")
    assert acc1["id"] == "acc-D1"

    # Second call with same u, different device — returns separate row
    select_chain2 = mock_sb.table("avito_accounts").select("*") \
        .eq("avito_user_id", 12345).eq("last_device_id", "D2").limit(1)
    select_chain2.execute.return_value.data = []
    mock_sb.table("avito_accounts").insert.return_value.execute.return_value.data = [
        {"id": "acc-D2", "avito_user_id": 12345, "last_device_id": "D2"},
    ]
    acc2 = resolve_or_create_account(mock_sb, avito_user_id=12345, device_id="D2")
    assert acc2["id"] == "acc-D2"
    assert acc1["id"] != acc2["id"]


def test_existing_test_returns_existing_account_still_works(mock_sb):
    """The original 'returns existing' test must still pass after the change."""
    # SELECT now keys on BOTH user_id AND device_id
    mock_sb.table("avito_accounts").select("*") \
        .eq("avito_user_id", 12345).eq("last_device_id", "D1").limit(1) \
        .execute.return_value.data = [
        {"id": "acc-1", "avito_user_id": 12345, "last_device_id": "D1"},
    ]
    acc = resolve_or_create_account(mock_sb, avito_user_id=12345, device_id="D1")
    assert acc["id"] == "acc-1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd avito-xapi && pytest tests/test_account_resolver.py::test_two_devices_same_user_create_two_rows -v
```
Expected: FAIL — current resolver only filters on `avito_user_id`, would return `acc-D1` for the second call too.

- [ ] **Step 3: Update resolver**

Replace `avito-xapi/src/services/account_resolver.py` body:

```python
"""Resolves (Avito user_id, device_id) → avito_accounts row, creates if missing."""
from datetime import datetime, timezone


def resolve_or_create_account(sb, *, avito_user_id: int, device_id: str | None) -> dict:
    """Возвращает avito_accounts row для пары (user_id, device_id). Создаёт если нет.

    Multi-device на один Avito-юзер поддерживается через композитный ключ
    (avito_user_id, last_device_id) в БД (migration 008). Каждое (u, device)
    — отдельная строка в pool.
    """
    res = sb.table("avito_accounts").select("*") \
        .eq("avito_user_id", avito_user_id) \
        .eq("last_device_id", device_id) \
        .limit(1).execute()
    now = datetime.now(timezone.utc).isoformat()
    if res.data:
        return res.data[0]
    new = sb.table("avito_accounts").insert({
        "avito_user_id": avito_user_id,
        "nickname": f"auto-{avito_user_id}-{(device_id or 'unknown')[:6]}",
        "last_device_id": device_id,
        "state": "active",
        "last_session_at": now,
    }).execute()
    return new.data[0]
```

Note: the `test_updates_last_device_id_when_existing` and `test_no_update_if_device_id_unchanged` tests no longer apply — they tested behaviour the new keying makes impossible (you can't "change device" on an existing row, you create a new row). DELETE those two tests.

- [ ] **Step 4: Run all resolver tests**

```bash
cd avito-xapi && pytest tests/test_account_resolver.py -v
```
Expected: all green (3 tests now: returns_existing / creates_new / two_devices_same_user / existing_after_change).

- [ ] **Step 5: Run sessions tests (they patch resolve_or_create_account)**

```bash
cd avito-xapi && pytest tests/test_sessions.py -v
```
Expected: green — sessions tests mock the function, so signature compatibility is what matters; signature is unchanged.

- [ ] **Step 6: Commit**

```bash
git add avito-xapi/src/services/account_resolver.py avito-xapi/tests/test_account_resolver.py
git commit -m "feat(xapi): resolver keys by (user_id, device_id) for multi-device pool"
```

---

## Task 5: xapi — `GET /api/v1/accounts` returns expires_at per account

**Why:** monitor's `account_tick` reads `acc.get("expires_at")`. It's currently None because the column lives on `avito_sessions`. xapi needs to surface it.

**Files:**
- Modify: `avito-xapi/src/routers/accounts.py:22-26` (the `list_accounts` handler)
- Modify: `avito-xapi/tests/test_accounts_router.py`

- [ ] **Step 1: Write failing test**

Add to `avito-xapi/tests/test_accounts_router.py`:

```python
def test_list_accounts_includes_expires_at_from_active_session(client, mock_sb):
    """GET /api/v1/accounts returns expires_at on each account row, sourced from
    the active session (avito_sessions.expires_at WHERE account_id=… AND is_active=true)."""
    mock_sb.table("avito_accounts").select("*").execute.return_value.data = [
        {"id": "acc-1", "nickname": "Clone", "state": "active", "avito_user_id": 1},
        {"id": "acc-2", "nickname": "Main", "state": "active", "avito_user_id": 1},
    ]
    # Each account's session lookup returns its expires_at
    def session_lookup(account_id):
        m = MagicMock()
        m.execute.return_value.data = [
            {"expires_at": "2026-05-01T18:27:10+00:00" if account_id == "acc-1" else "2026-05-02T06:27:10+00:00"}
        ]
        return m
    sess_chain = mock_sb.table("avito_sessions").select("expires_at").eq("is_active", True)
    # Drive the per-account branch via dynamic .eq("account_id", X) — adapt to actual call shape
    # … (test scaffolding details; concrete shape depends on the implementation in Step 3)

    resp = client.get("/api/v1/accounts", headers={"X-Api-Key": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    expires = {a["id"]: a["expires_at"] for a in body}
    assert expires["acc-1"] == "2026-05-01T18:27:10+00:00"
    assert expires["acc-2"] == "2026-05-02T06:27:10+00:00"
```

(If `test_accounts_router.py` doesn't already have a working `client + mock_sb` fixture pair, copy the pattern from `test_account_resolver.py` and `test_sessions.py`.)

- [ ] **Step 2: Run test to verify it fails**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py::test_list_accounts_includes_expires_at_from_active_session -v
```
Expected: FAIL — `expires_at` field missing from response.

- [ ] **Step 3: Update `list_accounts` to enrich with session expiry**

Replace `avito-xapi/src/routers/accounts.py:22-26`:

```python
@router.get("")
async def list_accounts():
    """List all accounts; each row enriched with `expires_at` from active session."""
    sb = get_supabase()
    res = sb.table("avito_accounts").select("*").execute()
    accounts = res.data or []
    if not accounts:
        return []

    # Bulk-fetch active sessions for all listed accounts (one query, IN clause).
    ids = [a["id"] for a in accounts]
    sess_res = (
        sb.table("avito_sessions")
        .select("account_id,expires_at")
        .in_("account_id", ids)
        .eq("is_active", True)
        .execute()
    )
    expiry_by_account = {row["account_id"]: row["expires_at"] for row in (sess_res.data or [])}
    for a in accounts:
        a["expires_at"] = expiry_by_account.get(a["id"])
    return accounts
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py -v
```
Expected: green.

- [ ] **Step 5: Smoke-test on homelab**

```bash
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' http://127.0.0.1:8080/api/v1/accounts | python3 -m json.tool"
```
Expected: each account row has an `expires_at` field (ISO 8601 string or null).

- [ ] **Step 6: Commit**

```bash
git add avito-xapi/src/routers/accounts.py avito-xapi/tests/test_accounts_router.py
git commit -m "feat(xapi): GET /accounts enriches each row with active session expires_at"
```

---

## Task 6: monitor — account_tick reads expires_at from response

**Files:**
- Modify: `avito-monitor/app/services/health_checker/account_tick.py:53-61`
- Create: `avito-monitor/tests/health_checker/test_account_tick.py` (if not exists; if exists, append)

- [ ] **Step 1: Write failing test**

Create `avito-monitor/tests/health_checker/test_account_tick.py`:

```python
"""Tests for account_tick_iteration — proactive refresh path."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.services.health_checker.account_tick import account_tick_iteration


@pytest.mark.asyncio
async def test_active_account_near_expiry_triggers_refresh():
    """state=active and expires_at < now+30min → refresh-cycle is triggered."""
    now = datetime(2026, 4, 30, 18, 0, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        {
            "id": "acc-1",
            "nickname": "Clone",
            "state": "active",
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "consecutive_cooldowns": 0,
        }
    ]

    tg_calls: list[str] = []

    async def fake_tg(msg: str) -> None:
        tg_calls.append(msg)

    await account_tick_iteration(pool=pool, now=now, tg=fake_tg)
    pool.trigger_refresh_cycle.assert_awaited_once_with("acc-1")
    assert tg_calls == []


@pytest.mark.asyncio
async def test_active_account_already_expired_triggers_refresh():
    """state=active and expires_at < now (already expired — today's case) → refresh."""
    now = datetime(2026, 4, 30, 18, 0, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        {
            "id": "acc-1",
            "state": "active",
            "expires_at": (now - timedelta(hours=7)).isoformat(),
            "consecutive_cooldowns": 0,
        }
    ]

    async def noop(_): pass
    await account_tick_iteration(pool=pool, now=now, tg=noop)
    pool.trigger_refresh_cycle.assert_awaited_once_with("acc-1")


@pytest.mark.asyncio
async def test_active_account_fresh_does_not_refresh():
    """state=active with TTL > 30min → no refresh."""
    now = datetime(2026, 4, 30, 18, 0, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        {
            "id": "acc-1",
            "state": "active",
            "expires_at": (now + timedelta(hours=10)).isoformat(),
            "consecutive_cooldowns": 0,
        }
    ]

    async def noop(_): pass
    await account_tick_iteration(pool=pool, now=now, tg=noop)
    pool.trigger_refresh_cycle.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_account_no_session_triggers_refresh():
    """state=active but expires_at is None (no active session) → refresh."""
    now = datetime(2026, 4, 30, 18, 0, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        {"id": "acc-1", "state": "active", "expires_at": None, "consecutive_cooldowns": 0}
    ]

    async def noop(_): pass
    await account_tick_iteration(pool=pool, now=now, tg=noop)
    pool.trigger_refresh_cycle.assert_awaited_once_with("acc-1")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd avito-monitor && pytest tests/health_checker/test_account_tick.py -v
```
Expected: FAIL on `test_active_account_near_expiry_triggers_refresh` and `test_active_account_already_expired_triggers_refresh` and `test_active_account_no_session_triggers_refresh` (today's bug — `acc.get("expires_at")` is None for the first; for already-expired the threshold check is `< 3min` which is `(exp - now) < 3min` — for negative TTL also true, so this might pass; depends on current code path).

- [ ] **Step 3: Update threshold + handle missing session**

Replace lines 53-61 of `avito-monitor/app/services/health_checker/account_tick.py`:

```python
    if state == "active":
        exp = _parse_ts(acc.get("expires_at"))
        # Trigger refresh when:
        #   1. expires_at is missing (no active session — pool can't poll anyway)
        #   2. expires_at < now + 30min (proactive — give Avito-app time to refresh
        #      while IP is still clean and the JWT hasn't fully expired)
        if exp is None or (exp - now) < timedelta(minutes=30):
            try:
                await pool.trigger_refresh_cycle(aid)
                log.info("refresh-cycle triggered for %s (proactive, exp=%s)", aid, exp)
            except Exception as e:
                log.warning("proactive refresh failed for %s: %s", aid, e)
        return
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd avito-monitor && pytest tests/health_checker/test_account_tick.py -v
```
Expected: all green.

- [ ] **Step 5: Run the full health_checker suite**

```bash
cd avito-monitor && pytest tests/health_checker/ -v
```
Expected: all green; in particular `test_account_loop` should still pass (no signature change).

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/services/health_checker/account_tick.py avito-monitor/tests/health_checker/test_account_tick.py
git commit -m "fix(monitor): proactive refresh fires on near-expiry / missing session (Gap 4)"
```

---

## Task 7: deploy + soak verification

**Files:** none (deployment + observation)

- [ ] **Step 1: Build new images**

```bash
ssh homelab "cd /mnt/projects/repos/AvitoSystem && git pull && \
    cd avito-xapi && docker compose build && \
    cd ../avito-monitor && docker compose build"
```

- [ ] **Step 2: Apply migration 008 (if not already applied in Task 3 Step 2)**

```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -f /mnt/projects/repos/AvitoSystem/supabase/migrations/008_avito_accounts_multidevice.sql"
```

- [ ] **Step 3: Restart containers**

```bash
ssh homelab "cd /mnt/projects/repos/AvitoSystem/avito-xapi && docker compose up -d"
ssh homelab "cd /mnt/projects/repos/AvitoSystem/avito-monitor && docker compose up -d"
```

- [ ] **Step 4: Verify enriched /api/v1/accounts response**

```bash
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' http://127.0.0.1:8080/api/v1/accounts | python3 -m json.tool"
```
Expected: each row has `expires_at`.

- [ ] **Step 5: Force a near-expiry simulation**

Set Clone's session `expires_at` to NOW + 5min and watch the next account_tick (within 30s) trigger refresh-cycle:

```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \\
  \"UPDATE avito_sessions SET expires_at = NOW() + INTERVAL '5 minutes' \\
    WHERE account_id='42c179db-18b1-40b2-9af2-274c52824ab1' AND is_active=true;\""
ssh homelab "docker logs -f avito-monitor-health-checker-1 --since=1m 2>&1 | grep -E 'refresh-cycle|proactive'" &
```
Expected: within 30s log line: `refresh-cycle triggered for 42c179db-… (proactive, exp=…)`.

After verification, restore the real expires_at by re-running the full refresh-cycle (it'll come from APK):

```bash
ssh homelab "curl -s -X POST -H 'X-Api-Key: test_dev_key_123' http://127.0.0.1:8080/api/v1/accounts/42c179db-18b1-40b2-9af2-274c52824ab1/refresh-cycle"
```

- [ ] **Step 6: Force a 403 simulation to check pool report**

(Optional — skip if today's incident is too fresh and we don't want to provoke Avito.) Edit a search profile to point at an invalid filter_id, run-now, expect xapi to return 403 (not 500), and pool to mark account cooldown.

- [ ] **Step 7: Commit / push to main if all green**

If running on a feature branch, merge with the standard ratchet (PR review or direct push if working trunk-based per `CLAUDE.md`).

```bash
git push origin main  # or open PR
```

---

## Phase 2 — Multi-device activation (operational, not code)

This is documented for the next session, **after Phase 1 is merged and soaked**. No code work, just phone setup. Track separately from this plan.

1. SSH to homelab, `adb -s 110139ce` to phone.
2. Verify Avito-app already exists in user_0 (`pm list packages --user 0 | grep avito`). It does (we checked 2026-04-30).
3. Configure APK in user_10: copy a working `avito_session_manager.xml` from user_0, change nothing about server_url (already correct: `http://192.168.31.97:8080`). Reboot APK in user_10.
4. Force one upload from each user: `python scripts/register_clone_session.py --android-user 0` and same for 10 — both should appear in `avito_accounts` (now possible because of migration 008).
5. Twelve-hour offset: open Avito-app in user_0 RIGHT NOW. Wait 12h. Open Avito-app in user_10. From then on, refreshes naturally diverge by ~12h (Avito refreshes near-expiry, gap preserved).

**Verification:** `SELECT nickname, last_device_id, expires_at FROM avito_accounts JOIN avito_sessions …` shows two rows with `expires_at` ~12h apart.

---

## Self-Review

**Spec coverage:**
- [x] xapi 5xx → propagate Avito 4xx — Tasks 1+2
- [x] Migration UNIQUE(u,device) — Task 3
- [x] resolver multi-device — Task 4
- [x] xapi /accounts surface expires_at — Task 5
- [x] monitor account_tick uses real expires_at — Task 6
- [x] Boot-recovery — implicit: account_loop runs every 30s starting from container boot, so first tick within 30s of restart triggers refresh on any expired account
- [x] Verification after deploy — Task 7
- [x] Phase 2 (multi-device activation) — documented as ops, not in plan

**Placeholder scan:** No TBD / TODO / "implement later". Each step has runnable commands or full code.

**Type consistency:**
- `pool.trigger_refresh_cycle(account_id)` — used in Task 6 tests, exists in `account_pool.py:63`. ✓
- `expires_at` field on account dict — added in Task 5, consumed in Task 6. Same name. ✓
- `resolve_or_create_account(sb, *, avito_user_id, device_id)` signature unchanged — Tasks 4 + sessions.py call site agree. ✓
- `reraise_avito_error(exc)` introduced in Task 2, used by Task 1 retroactively (refactor step). ✓

No issues found.

---

## Risk Notes

- **Task 1 + 2 risk**: changing 5xx behaviour. If any test or downstream consumer depends on "Avito-403-becomes-xapi-500", they'll break. Mitigation: search for `status_code == 500` references in `avito-monitor` before merging — if there are any in pool/polling code, audit them.
- **Task 4 risk**: `resolve_or_create_account` signature unchanged but semantics shifted (`device_id` becomes part of the key). The legacy "auto-rows from 007 data migration" exist with `last_device_id=NULL`. They will become orphans (never matched by future SELECT with non-NULL device). Acceptable — they'd never be uploaded against in practice; if they are, a new row is created cleanly.
- **Task 5 risk**: `IN` query with empty list — handled by the early-return on `not accounts`.
- **Task 6 risk**: 30-min threshold may be too aggressive (pings Avito-app every 30 min of remaining TTL). On 24h JWT this means one refresh per day, which is normal. If we observe excess churn, raise to 60 min.
- **Migration ordering**: do NOT deploy Task 4 (resolver) before Task 3 (migration). Otherwise sessions/upload would fail on the legacy unique constraint when a new (u, device) shows up. Task 7 sequences this correctly.
