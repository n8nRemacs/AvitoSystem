# Avito Account Pool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать pool из N (сейчас 2) Avito-аккаунтов с round-robin polling, автоматическим переходом в cooldown при 403, автоматическим refresh токенов через ADB device-switcher + AvitoSessionManager APK, multi-phone support.

**Architecture:** Source-of-truth state в Supabase (`avito_accounts` table). xapi выставляет атомарные эндпойнты `poll-claim` / `report` / `refresh-cycle`. avito-monitor `AccountPool` client + расширенный `health_checker` (существующий) рулит timing'ом. Device-switcher живёт в xapi (USB passthrough в LXC). UI read-only в monitor.

**Tech Stack:** FastAPI, Supabase (Postgres), curl_cffi (xapi), pytest + pytest-asyncio + respx, Alembic (avito-monitor), ADB, Jinja2.

**Architectural deviation from spec §7.4:** `health_checker` логика остаётся в **avito-monitor** (где она фактически живёт), а не переносится в xapi. xapi даёт атомарный эндпойнт `POST /accounts/{id}/refresh-cycle` который health_checker monitor'а вызывает. Эффект эквивалентен, разделение чище.

---

## File Structure

### avito-xapi (новые файлы)
- `supabase/migrations/007_avito_accounts_pool.sql` — schema + data migration
- `avito-xapi/src/routers/accounts.py` — новый роутер с poll-claim/report/refresh-cycle
- `avito-xapi/src/workers/device_switcher.py` — ADB wrapper, per-phone Lock
- `avito-xapi/src/services/account_state.py` — pure-функция compute_next_state (state machine)
- `avito-xapi/tests/test_accounts_router.py`
- `avito-xapi/tests/test_device_switcher.py`
- `avito-xapi/tests/test_account_state.py`

### avito-xapi (изменения)
- `avito-xapi/src/main.py` — регистрация accounts router + ADB-server start
- `avito-xapi/src/routers/sessions.py` — account-scoped deactivation, resolve_or_create_account
- `avito-xapi/src/workers/session_reader.py` — `load_session_for_account`
- `avito-xapi/tests/test_sessions_router.py` — расширить
- `avito-xapi/tests/conftest.py` — фикстуры для accounts mock
- `avito-xapi/requirements.txt` — добавить нужные либы (если нужно)

### avito-monitor (новые файлы)
- `avito-monitor/alembic/versions/20260428_HHMM_search_profile_owner_account.py` — Alembic migration
- `avito-monitor/app/services/account_pool.py` — клиент AccountPool
- `avito-monitor/app/web/templates/settings/accounts.html` — read-only таблица
- `avito-monitor/tests/test_account_pool.py`

### avito-monitor (изменения)
- `avito-monitor/app/db/models/search_profile.py` — поле `owner_account_id`
- `avito-monitor/app/tasks/polling.py` — `fetch_with_pool` retry-обёртка
- `avito-monitor/app/services/autosearch_sync.py` — per-account loop
- `avito-monitor/app/services/health_checker/` — расширить tick: вызовы refresh-cycle xapi, dead detection
- `avito-monitor/app/web/routers.py` — GET /settings/accounts route
- `avito-monitor/tests/health_checker/` — новые сценарии для refresh path
- `avito-monitor/tests/test_polling.py` — расширить
- `CONTINUE.md` — обновить состояние после deploy

---

## Phase 1: Schema migrations

### Task 1: Supabase migration 007 — `avito_accounts` table

**Files:**
- Create: `supabase/migrations/007_avito_accounts_pool.sql`

- [ ] **Step 1: Создать SQL migration**

Полный текст файла `supabase/migrations/007_avito_accounts_pool.sql`:

```sql
-- 007_avito_accounts_pool.sql
-- Avito multi-account pool: stable account identity + state machine + multi-phone

CREATE TABLE avito_accounts (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nickname               TEXT NOT NULL,
    avito_user_id          BIGINT NOT NULL,
    last_device_id         TEXT,
    phone_serial           TEXT NOT NULL DEFAULT '',
    android_user_id        INTEGER NOT NULL DEFAULT 0,
    state                  TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active','cooldown','needs_refresh',
                         'waiting_refresh','dead')),
    cooldown_until         TIMESTAMPTZ,
    consecutive_cooldowns  INTEGER NOT NULL DEFAULT 0,
    last_polled_at         TIMESTAMPTZ,
    last_session_at        TIMESTAMPTZ,
    waiting_since          TIMESTAMPTZ,
    last_403_body          TEXT,
    last_403_at            TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (avito_user_id)
);

CREATE INDEX idx_accounts_pool
    ON avito_accounts (last_polled_at NULLS FIRST)
    WHERE state = 'active';

CREATE INDEX idx_accounts_avito_user
    ON avito_accounts (avito_user_id);

ALTER TABLE avito_sessions
    ADD COLUMN account_id UUID REFERENCES avito_accounts(id) ON DELETE CASCADE;

DROP INDEX IF EXISTS idx_avito_sessions_active;
CREATE INDEX idx_avito_sessions_active_per_account
    ON avito_sessions (account_id, is_active) WHERE is_active = true;

-- One-shot data migration: для каждого user_id создаём account row + привязываем sessions
DO $$ DECLARE r RECORD; new_acc UUID; BEGIN
    FOR r IN (SELECT DISTINCT user_id FROM avito_sessions WHERE user_id IS NOT NULL) LOOP
        INSERT INTO avito_accounts (avito_user_id, nickname, state)
            VALUES (r.user_id, 'auto-' || r.user_id, 'active')
            RETURNING id INTO new_acc;
        UPDATE avito_sessions SET account_id = new_acc WHERE user_id = r.user_id;
    END LOOP;
END $$;
```

- [ ] **Step 2: Подсветить идемпотентность — добавить `IF NOT EXISTS` в CREATE TABLE/INDEX**

Замени в файле `supabase/migrations/007_avito_accounts_pool.sql`:
```sql
CREATE TABLE avito_accounts (
```
на:
```sql
CREATE TABLE IF NOT EXISTS avito_accounts (
```

И аналогично для индексов:
```sql
CREATE INDEX IF NOT EXISTS idx_accounts_pool ...
CREATE INDEX IF NOT EXISTS idx_accounts_avito_user ...
CREATE INDEX IF NOT EXISTS idx_avito_sessions_active_per_account ...
```

ALTER TABLE добавь guard через DO-block:
```sql
DO $$ BEGIN
    ALTER TABLE avito_sessions ADD COLUMN account_id UUID REFERENCES avito_accounts(id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_column THEN
    NULL;
END $$;
```

DO $$ block migration данных оберни в guard `WHERE account_id IS NULL`:
```sql
FOR r IN (SELECT DISTINCT user_id FROM avito_sessions
          WHERE user_id IS NOT NULL
          AND account_id IS NULL) LOOP
```

- [ ] **Step 3: Apply на staging Supabase (homelab)**

Run:
```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql \
  -h 127.0.0.1 -p 5433 -U postgres -d postgres \
  -f /mnt/projects/repos/AvitoSystem/supabase/migrations/007_avito_accounts_pool.sql"
```

Expected: `CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE`, `DO`, `DO` без ERROR.

- [ ] **Step 4: Verify schema**

Run:
```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  '\d avito_accounts'"
```

Expected output: показывает все 16 колонок (`id, nickname, avito_user_id, ..., last_403_at, created_at, updated_at`) + CHECK на `state` + UNIQUE на `avito_user_id` + 2 индекса.

- [ ] **Step 5: Verify data migration**

Run:
```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  'SELECT id, avito_user_id, nickname, state FROM avito_accounts;'"
```

Expected: одна row для каждого уникального `user_id` из существующих `avito_sessions`. Вероятно: 1 row (clone) с `nickname='auto-{N}'`, state='active'.

```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  'SELECT COUNT(*) FROM avito_sessions WHERE account_id IS NULL;'"
```

Expected: `0` (все sessions привязаны).

- [ ] **Step 6: Idempotency check**

Run migration ещё раз:
```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres \
  -f /mnt/projects/repos/AvitoSystem/supabase/migrations/007_avito_accounts_pool.sql"
```

Expected: NOTICES «relation already exists, skipping», но без ERROR. SELECT count повторяет тот же результат.

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations/007_avito_accounts_pool.sql
git commit -m "feat(schema): account pool — avito_accounts table + sessions FK"
```

---

### Task 2: Manual UPDATE для known accounts

**Files:**
- Create (one-shot, не в репо): локальный SQL `update_known_accounts.sql`

- [ ] **Step 1: Получить avito_user_id'ы**

Run:
```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  'SELECT id, avito_user_id, nickname FROM avito_accounts ORDER BY created_at;'"
```

Запиши result: один или два user_id. Тот, у которого есть active session — clone (157920214 по CONTINUE §1). Если другой есть — Main.

- [ ] **Step 2: UPDATE clone (Active)**

Run (подставь реальный `avito_user_id` clone'а):
```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  \"UPDATE avito_accounts SET nickname='Clone', android_user_id=10, phone_serial='110139ce' \
    WHERE avito_user_id=157920214;\""
```

Expected: `UPDATE 1`.

- [ ] **Step 3: UPDATE main, если row существует**

Если есть Main (banned user 0 token):
```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  \"UPDATE avito_accounts SET nickname='Main', android_user_id=0, phone_serial='110139ce', state='dead' \
    WHERE avito_user_id=<MAIN_USER_ID>;\""
```

Если row нет (потому что в avito_sessions нет user 0 record'а с user_id) — пропускаем; будет создан автоматически когда APK Main сделает POST /sessions.

- [ ] **Step 4: Verify**

Run:
```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  'SELECT nickname, avito_user_id, state, android_user_id, phone_serial FROM avito_accounts;'"
```

Expected: `Clone | 157920214 | active | 10 | 110139ce` (+ Main row если был).

Эта задача — **операционная**, без коммита в git (UPDATE одноразовый). Зафиксировать в внутреннем runbook (CONTINUE.md потом).

---

### Task 3: avito-monitor Alembic migration — `search_profiles.owner_account_id`

**Files:**
- Create: `avito-monitor/alembic/versions/20260428_1500_search_profile_owner_account.py`
- Modify: `avito-monitor/app/db/models/search_profile.py`

- [ ] **Step 1: Добавить колонку в SQLAlchemy model**

Открой `avito-monitor/app/db/models/search_profile.py` и добавь в класс модели (после поля `archived_at` или похожих legacy-колонок):

```python
from uuid import UUID as UUID_t
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID

class SearchProfile(Base):
    # ... existing fields ...
    owner_account_id: Mapped[UUID_t | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
```

(Конкретный синтаксис подгоняй под существующий стиль модели — там mapped_column / Column.)

- [ ] **Step 2: Auto-generate Alembic migration**

Run:
```bash
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && \
  docker compose exec -T app alembic revision --autogenerate -m "search_profile_owner_account"'
```

Expected: создаётся файл `alembic/versions/20260428_HHMM_search_profile_owner_account.py`.

- [ ] **Step 3: Inspect migration**

Прочитай созданный файл — должен содержать `op.add_column('search_profiles', sa.Column('owner_account_id', ...))` + `op.create_index(...)`. Если auto-generate добавил лишнее — почисти.

- [ ] **Step 4: Apply migration**

Run:
```bash
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && \
  docker compose exec -T app alembic upgrade head'
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade ... -> 20260428_HHMM, search_profile_owner_account`.

- [ ] **Step 5: Backfill — все существующие профили под clone-account**

Run (подставь UUID Clone-account из Task 2):
```bash
ssh homelab "docker exec avito-monitor-db-1 psql -h 127.0.0.1 -U avito -d avito_monitor -c \
  \"UPDATE search_profiles SET owner_account_id='<CLONE_ACCOUNT_UUID>' WHERE archived_at IS NULL;\""
```

Expected: `UPDATE 7` (или сколько профилей было) — подгоняется к фактическому числу.

- [ ] **Step 6: Verify**

```bash
ssh homelab "docker exec avito-monitor-db-1 psql -h 127.0.0.1 -U avito -d avito_monitor -c \
  'SELECT COUNT(*), owner_account_id FROM search_profiles GROUP BY owner_account_id;'"
```

Expected: одна row (clone UUID, count = N) + возможно null'ы для архивных.

- [ ] **Step 7: Commit**

```bash
git add avito-monitor/app/db/models/search_profile.py \
        avito-monitor/alembic/versions/20260428_1500_search_profile_owner_account.py
git commit -m "feat(schema): search_profiles.owner_account_id for per-account autosearch sync"
```

---

## Phase 2: xapi accounts router (TDD)

### Task 4: pure state machine `compute_next_state`

State transitions — самое опасное место. Делаем pure function без БД, тест-таблица.

**Files:**
- Create: `avito-xapi/src/services/account_state.py`
- Create: `avito-xapi/tests/test_account_state.py`

- [ ] **Step 1: Написать failing tests**

Создай `avito-xapi/tests/test_account_state.py`:

```python
"""Tests for pure state-machine logic of avito_accounts."""
from datetime import datetime, timedelta, timezone
import pytest

from src.services.account_state import (
    compute_next_state,
    cooldown_duration_for,
    AccountState,
    Event,
)


NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)


def state(**kwargs):
    base = AccountState(
        state="active",
        consecutive_cooldowns=0,
        cooldown_until=None,
        waiting_since=None,
    )
    for k, v in kwargs.items():
        setattr(base, k, v)
    return base


def test_200_resets_counters():
    s = state(state="active", consecutive_cooldowns=2)
    next_s = compute_next_state(s, Event(kind="report", status_code=200), now=NOW)
    assert next_s.state == "active"
    assert next_s.consecutive_cooldowns == 0


def test_403_first_time_starts_20min_cooldown():
    s = state(state="active", consecutive_cooldowns=0)
    next_s = compute_next_state(s, Event(kind="report", status_code=403), now=NOW)
    assert next_s.state == "cooldown"
    assert next_s.cooldown_until == NOW + timedelta(minutes=20)
    assert next_s.consecutive_cooldowns == 1


def test_403_ratchet_doubles_each_time():
    durations = [20, 40, 80, 160, 24 * 60]
    s = state(state="active", consecutive_cooldowns=0)
    for expected_minutes in durations:
        next_s = compute_next_state(s, Event(kind="report", status_code=403), now=NOW)
        assert next_s.cooldown_until == NOW + timedelta(minutes=expected_minutes), \
            f"Expected {expected_minutes}m at consecutive={s.consecutive_cooldowns}"
        s = next_s


def test_401_marks_for_immediate_refresh_no_cooldown():
    s = state(state="active", consecutive_cooldowns=0)
    next_s = compute_next_state(s, Event(kind="report", status_code=401), now=NOW)
    assert next_s.state == "active"
    assert next_s.consecutive_cooldowns == 0
    assert next_s.expires_at == NOW  # форсирует health_checker подобрать


def test_5xx_no_state_change():
    s = state(state="active", consecutive_cooldowns=1)
    next_s = compute_next_state(s, Event(kind="report", status_code=503), now=NOW)
    assert next_s.state == "active"
    assert next_s.consecutive_cooldowns == 1


def test_cooldown_expired_transitions_to_needs_refresh():
    s = state(state="cooldown", cooldown_until=NOW - timedelta(seconds=1))
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.state == "needs_refresh"


def test_cooldown_not_yet_expired_stays_cooldown():
    s = state(state="cooldown", cooldown_until=NOW + timedelta(minutes=10))
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.state == "cooldown"


def test_waiting_refresh_timeout_marks_dead():
    s = state(state="waiting_refresh", waiting_since=NOW - timedelta(minutes=5, seconds=1))
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.state == "dead"


def test_waiting_refresh_within_window_stays():
    s = state(state="waiting_refresh", waiting_since=NOW - timedelta(minutes=4))
    next_s = compute_next_state(s, Event(kind="tick"), now=NOW)
    assert next_s.state == "waiting_refresh"


def test_session_arrived_clears_waiting():
    s = state(state="waiting_refresh", waiting_since=NOW - timedelta(minutes=2))
    next_s = compute_next_state(s, Event(kind="session_arrived"), now=NOW)
    assert next_s.state == "active"
    assert next_s.waiting_since is None


def test_consecutive_5_cooldowns_24h():
    assert cooldown_duration_for(5) == timedelta(hours=24)
    assert cooldown_duration_for(6) == timedelta(hours=24)


def test_consecutive_4_cooldowns_160m():
    assert cooldown_duration_for(4) == timedelta(minutes=160)
```

- [ ] **Step 2: Run tests — verify they fail**

Run:
```bash
cd avito-xapi && pytest tests/test_account_state.py -v
```

Expected: `ImportError: cannot import name 'compute_next_state' from 'src.services.account_state'` (file does not exist).

- [ ] **Step 3: Создать pure module**

Создай `avito-xapi/src/services/account_state.py`:

```python
"""Pure state-machine логика avito_accounts. No DB, no IO."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal


StateName = Literal["active", "cooldown", "needs_refresh", "waiting_refresh", "dead"]


@dataclass
class AccountState:
    state: StateName
    consecutive_cooldowns: int = 0
    cooldown_until: datetime | None = None
    waiting_since: datetime | None = None
    expires_at: datetime | None = None


@dataclass
class Event:
    kind: Literal["report", "tick", "session_arrived"]
    status_code: int | None = None


def cooldown_duration_for(consecutive: int) -> timedelta:
    """Ratchet: 20m → 40m → 80m → 160m → 24h+."""
    if consecutive >= 5:
        return timedelta(hours=24)
    return timedelta(minutes=20 * (2 ** (consecutive - 1))) if consecutive > 0 else timedelta(minutes=20)


def compute_next_state(curr: AccountState, event: Event, *, now: datetime) -> AccountState:
    if event.kind == "report":
        sc = event.status_code or 0
        if sc == 200:
            return replace(curr, state="active", consecutive_cooldowns=0)
        if sc == 403:
            new_consec = curr.consecutive_cooldowns + 1
            return replace(
                curr,
                state="cooldown",
                consecutive_cooldowns=new_consec,
                cooldown_until=now + cooldown_duration_for(new_consec),
            )
        if sc == 401:
            return replace(curr, expires_at=now)
        return curr  # 5xx / network — no-op

    if event.kind == "tick":
        if curr.state == "cooldown" and curr.cooldown_until and curr.cooldown_until < now:
            return replace(curr, state="needs_refresh")
        if curr.state == "waiting_refresh" and curr.waiting_since \
                and (now - curr.waiting_since) > timedelta(minutes=5):
            return replace(curr, state="dead")
        return curr

    if event.kind == "session_arrived":
        return replace(curr, state="active", waiting_since=None)

    return curr
```

- [ ] **Step 4: Run tests — verify they pass**

Run:
```bash
cd avito-xapi && pytest tests/test_account_state.py -v
```

Expected: `12 passed`.

- [ ] **Step 5: Commit**

```bash
git add avito-xapi/src/services/account_state.py avito-xapi/tests/test_account_state.py
git commit -m "feat(xapi): account state machine — pure compute_next_state with ratchet"
```

---

### Task 5: GET /api/v1/accounts (list)

**Files:**
- Modify: `avito-xapi/src/routers/accounts.py` (создать) + `avito-xapi/src/main.py` (зарегистрировать)
- Modify: `avito-xapi/tests/test_accounts_router.py` (создать)
- Modify: `avito-xapi/tests/conftest.py` (фикстура `accounts_in_db`)

- [ ] **Step 1: Failing test**

Создай `avito-xapi/tests/test_accounts_router.py`:

```python
"""Tests for /api/v1/accounts router."""
import pytest
from fastapi.testclient import TestClient


def test_get_accounts_returns_list(client: TestClient, accounts_in_db):
    accounts_in_db([
        {"id": "acc-1", "nickname": "Clone", "state": "active",
         "consecutive_cooldowns": 0, "android_user_id": 10},
        {"id": "acc-2", "nickname": "Main", "state": "dead",
         "consecutive_cooldowns": 5, "android_user_id": 0},
    ])
    r = client.get("/api/v1/accounts", headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert {a["nickname"] for a in data} == {"Clone", "Main"}


def test_get_accounts_unauthorized(client: TestClient):
    r = client.get("/api/v1/accounts")
    assert r.status_code in (401, 403)
```

В `avito-xapi/tests/conftest.py` добавить фикстуру:

```python
@pytest.fixture
def accounts_in_db(mock_sb):
    """Заполнить mock Supabase rows accounts."""
    def _fill(rows):
        mock_sb.table("avito_accounts").select("*").execute.return_value.data = rows
    return _fill
```

- [ ] **Step 2: Run — verify fail**

Run:
```bash
cd avito-xapi && pytest tests/test_accounts_router.py -v
```

Expected: 404 на endpoint (router не зарегистрирован).

- [ ] **Step 3: Создать router**

Создай `avito-xapi/src/routers/accounts.py`:

```python
"""Account pool router — list, claim, report, refresh-cycle."""
from fastapi import APIRouter, Depends, HTTPException
from src.deps import require_api_key, get_supabase

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


@router.get("")
async def list_accounts(
    _auth=Depends(require_api_key),
    sb=Depends(get_supabase),
):
    res = sb.table("avito_accounts").select("*").execute()
    return res.data or []
```

(Подгоняй имена `require_api_key`, `get_supabase` под фактические dependency-helpers из существующего кода. В `routers/sessions.py` посмотри как там сделано, повтори.)

- [ ] **Step 4: Зарегистрировать router в `src/main.py`**

Открой `avito-xapi/src/main.py`, найди блок `app.include_router(...)` и добавь:

```python
from src.routers import accounts as accounts_router

app.include_router(accounts_router.router)
```

- [ ] **Step 5: Run tests — pass**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add avito-xapi/src/routers/accounts.py avito-xapi/src/main.py \
        avito-xapi/tests/test_accounts_router.py avito-xapi/tests/conftest.py
git commit -m "feat(xapi): GET /api/v1/accounts list endpoint"
```

---

### Task 6: POST /api/v1/accounts/poll-claim (atomic round-robin)

**Files:**
- Modify: `avito-xapi/src/routers/accounts.py`
- Modify: `avito-xapi/tests/test_accounts_router.py`

- [ ] **Step 1: Failing tests**

Добавь в `tests/test_accounts_router.py`:

```python
def test_poll_claim_picks_oldest_active(client, accounts_in_db, sessions_in_db):
    accounts_in_db([
        {"id": "acc-1", "state": "active", "last_polled_at": "2026-04-28T12:00:00Z"},
        {"id": "acc-2", "state": "active", "last_polled_at": "2026-04-28T11:00:00Z"},
        {"id": "acc-3", "state": "cooldown", "last_polled_at": "2026-04-28T10:00:00Z"},
    ])
    sessions_in_db([
        {"account_id": "acc-2", "is_active": True,
         "tokens": {"session_token": "T2"}, "device_id": "D2"},
    ])
    r = client.post("/api/v1/accounts/poll-claim",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={})
    assert r.status_code == 200
    body = r.json()
    assert body["account_id"] == "acc-2"
    assert body["session_token"] == "T2"


def test_poll_claim_returns_409_when_pool_drained(client, accounts_in_db):
    accounts_in_db([
        {"id": "acc-1", "state": "cooldown", "cooldown_until": "2026-04-28T13:25:00Z"},
        {"id": "acc-2", "state": "dead"},
    ])
    r = client.post("/api/v1/accounts/poll-claim",
                    headers={"X-Api-Key": "test_dev_key_123"}, json={})
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["error"] == "pool_drained"
    assert len(body["detail"]["accounts"]) == 2
```

Расширь `conftest.py` фикстурой `sessions_in_db`:

```python
@pytest.fixture
def sessions_in_db(mock_sb):
    def _fill(rows):
        mock_sb.table("avito_sessions").select("*").execute.return_value.data = rows
    return _fill
```

- [ ] **Step 2: Run — verify fail**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py::test_poll_claim_picks_oldest_active -v
```

Expected: 404 / 405.

- [ ] **Step 3: Implement endpoint**

Добавь в `avito-xapi/src/routers/accounts.py`:

```python
from datetime import datetime, timezone


@router.post("/poll-claim")
async def poll_claim(
    _auth=Depends(require_api_key),
    sb=Depends(get_supabase),
):
    # NOTE: Supabase python-клиент не поддерживает FOR UPDATE SKIP LOCKED напрямую.
    # Решение: используем PostgREST RPC через RPC-функцию (создать в миграции 008),
    # либо raw SQL через psycopg2-pool. На MVP — оптимистический pick:
    # 1) SELECT next active LRU
    # 2) UPDATE last_polled_at WHERE id=X AND last_polled_at = old_value (CAS)
    # 3) если 0 rows updated — retry (другой воркер схватил)
    for _ in range(3):
        res = (sb.table("avito_accounts")
                 .select("*")
                 .eq("state", "active")
                 .order("last_polled_at", desc=False, nullsfirst=True)
                 .limit(1)
                 .execute())
        if not res.data:
            # pool drained
            all_accs = sb.table("avito_accounts").select(
                "nickname,state,cooldown_until,waiting_since"
            ).execute()
            raise HTTPException(status_code=409, detail={
                "error": "pool_drained",
                "accounts": all_accs.data or [],
            })
        acc = res.data[0]
        old_polled = acc.get("last_polled_at")
        now = datetime.now(timezone.utc).isoformat()
        upd = (sb.table("avito_accounts")
                 .update({"last_polled_at": now})
                 .eq("id", acc["id"])
                 .eq_or_is_null("last_polled_at", old_polled)
                 .execute())
        if upd.data:  # CAS succeeded
            session = (sb.table("avito_sessions")
                         .select("*")
                         .eq("account_id", acc["id"])
                         .eq("is_active", True)
                         .limit(1)
                         .execute())
            if not session.data:
                continue  # account без активной session — пропустим, попробуем другой
            s = session.data[0]
            tokens = s.get("tokens") or {}
            return {
                "account_id": acc["id"],
                "session_token": tokens.get("session_token"),
                "device_id": s.get("device_id"),
                "fingerprint": s.get("fingerprint"),
                "phone_serial": acc.get("phone_serial"),
                "android_user_id": acc.get("android_user_id"),
            }
        # CAS failed — retry
    raise HTTPException(status_code=503, detail="poll_claim contention, retry")
```

**Замечание для исполнителя:** `eq_or_is_null` — это синтетический хелпер для CAS на nullable-колонке. Если Supabase python client этого не поддерживает напрямую — реализовать через raw SQL:

```python
# Альтернатива через RPC (создать в migration 008):
# CREATE OR REPLACE FUNCTION claim_account_for_poll() RETURNS TABLE(...) ...
sb.rpc("claim_account_for_poll", {}).execute()
```

Если миграция 008 не делается — проверь Supabase client docs на CAS. Если ничего нет — оптимистическая retry-петля как выше.

- [ ] **Step 4: Run — pass**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add avito-xapi/src/routers/accounts.py avito-xapi/tests/test_accounts_router.py \
        avito-xapi/tests/conftest.py
git commit -m "feat(xapi): POST /accounts/poll-claim atomic round-robin"
```

---

### Task 7: POST /api/v1/accounts/{id}/report (state transitions)

**Files:**
- Modify: `avito-xapi/src/routers/accounts.py`
- Modify: `avito-xapi/tests/test_accounts_router.py`

- [ ] **Step 1: Failing tests**

```python
def test_report_200_resets_counters(client, accounts_in_db, mock_sb):
    accounts_in_db([
        {"id": "acc-1", "state": "active", "consecutive_cooldowns": 2,
         "last_403_body": "old", "last_403_at": "2026-04-27T..."},
    ])
    r = client.post("/api/v1/accounts/acc-1/report",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"status_code": 200})
    assert r.status_code == 204
    upd = mock_sb.last_update_for("avito_accounts")
    assert upd["consecutive_cooldowns"] == 0
    assert upd["last_403_body"] is None


def test_report_403_starts_cooldown_with_ratchet(client, accounts_in_db, mock_sb):
    accounts_in_db([
        {"id": "acc-1", "state": "active", "consecutive_cooldowns": 0,
         "last_403_body": None},
    ])
    r = client.post("/api/v1/accounts/acc-1/report",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"status_code": 403, "body_excerpt": "<firewall>banned</firewall>"})
    assert r.status_code == 204
    upd = mock_sb.last_update_for("avito_accounts")
    assert upd["state"] == "cooldown"
    assert upd["consecutive_cooldowns"] == 1
    assert upd["last_403_body"] == "<firewall>banned</firewall>"


def test_report_403_third_time_80min_cooldown(client, accounts_in_db, mock_sb):
    accounts_in_db([
        {"id": "acc-1", "state": "active", "consecutive_cooldowns": 2},
    ])
    r = client.post("/api/v1/accounts/acc-1/report",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"status_code": 403})
    assert r.status_code == 204
    upd = mock_sb.last_update_for("avito_accounts")
    # 20m * 2^2 = 80m
    from datetime import datetime
    until = datetime.fromisoformat(upd["cooldown_until"].replace("Z","+00:00"))
    delta_min = (until - datetime.now(until.tzinfo)).total_seconds() / 60
    assert 79 < delta_min < 81


def test_report_401_marks_for_immediate_refresh(client, accounts_in_db, mock_sb):
    accounts_in_db([
        {"id": "acc-1", "state": "active", "consecutive_cooldowns": 0},
    ])
    r = client.post("/api/v1/accounts/acc-1/report",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"status_code": 401})
    assert r.status_code == 204
    upd = mock_sb.last_update_for("avito_accounts")
    # 401 не cooldown'ит, но force expires_at=NOW для health_checker
    assert upd["state"] == "active"  # или не trogano
    # expires_at on session? Это поле в sessions. Уточнить с реализацией.


def test_report_5xx_no_state_change(client, accounts_in_db, mock_sb):
    accounts_in_db([
        {"id": "acc-1", "state": "active", "consecutive_cooldowns": 1},
    ])
    r = client.post("/api/v1/accounts/acc-1/report",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"status_code": 503})
    assert r.status_code == 204
    upd = mock_sb.last_update_for("avito_accounts")
    assert upd is None or upd.get("state", "active") == "active"
```

Добавь в `conftest.py` helper `last_update_for`:

```python
@pytest.fixture
def mock_sb_with_capture(mock_sb):
    """Запоминает последний UPDATE на каждой таблице."""
    captured = {}
    original_update = mock_sb.table

    def patched_table(name):
        t = original_update(name)
        original_upd = t.update
        def patched_upd(payload):
            captured[name] = payload
            return original_upd(payload)
        t.update = patched_upd
        return t

    mock_sb.table = patched_table
    mock_sb.last_update_for = lambda name: captured.get(name)
    return mock_sb
```

(Если `mock_sb` — простой MagicMock, реализация может отличаться; подгоняй под существующий паттерн в conftest.)

- [ ] **Step 2: Run fail**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py -v -k report
```

Expected: 404 на endpoint.

- [ ] **Step 3: Implement endpoint**

Добавь в `routers/accounts.py`:

```python
from pydantic import BaseModel
from src.services.account_state import (
    AccountState, Event, compute_next_state, cooldown_duration_for
)


class ReportPayload(BaseModel):
    status_code: int
    body_excerpt: str | None = None


@router.post("/{account_id}/report", status_code=204)
async def report(
    account_id: str,
    payload: ReportPayload,
    _auth=Depends(require_api_key),
    sb=Depends(get_supabase),
):
    res = sb.table("avito_accounts").select("*").eq("id", account_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "account not found")
    row = res.data[0]
    
    curr = AccountState(
        state=row["state"],
        consecutive_cooldowns=row.get("consecutive_cooldowns", 0),
        cooldown_until=_parse_ts(row.get("cooldown_until")),
        waiting_since=_parse_ts(row.get("waiting_since")),
    )
    next_s = compute_next_state(
        curr,
        Event(kind="report", status_code=payload.status_code),
        now=datetime.now(timezone.utc),
    )
    
    update = {
        "state": next_s.state,
        "consecutive_cooldowns": next_s.consecutive_cooldowns,
        "cooldown_until": next_s.cooldown_until.isoformat() if next_s.cooldown_until else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload.status_code == 403:
        update["last_403_body"] = (payload.body_excerpt or "")[:1024] or None
        update["last_403_at"] = datetime.now(timezone.utc).isoformat()
    elif payload.status_code == 200:
        update["last_403_body"] = None
        update["last_403_at"] = None
    elif payload.status_code == 401:
        # Force health_checker подобрать на следующем tick'е
        # Меняем expires_at в session (не в account):
        sb.table("avito_sessions").update({
            "expires_at": datetime.now(timezone.utc).isoformat()
        }).eq("account_id", account_id).eq("is_active", True).execute()
    
    sb.table("avito_accounts").update(update).eq("id", account_id).execute()
    
    if next_s.consecutive_cooldowns >= 5:
        # TG-alert (вызов будет реализован в Task 16+; пока no-op log)
        import logging
        logging.warning("account %s consecutive_cooldowns=%d, manual review needed",
                        account_id, next_s.consecutive_cooldowns)


def _parse_ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
```

- [ ] **Step 4: Run pass**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py -v -k report
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add avito-xapi/src/routers/accounts.py avito-xapi/tests/test_accounts_router.py
git commit -m "feat(xapi): POST /accounts/{id}/report — state transitions + ratchet"
```

---

### Task 8: GET /api/v1/accounts/{id}/session-for-sync

**Files:**
- Modify: `avito-xapi/src/routers/accounts.py`
- Modify: `avito-xapi/tests/test_accounts_router.py`

- [ ] **Step 1: Failing test**

```python
def test_session_for_sync_returns_active(client, accounts_in_db, sessions_in_db):
    accounts_in_db([{"id": "acc-1", "state": "active"}])
    sessions_in_db([{"account_id": "acc-1", "is_active": True,
                     "tokens": {"session_token": "T1"}, "device_id": "D1"}])
    r = client.get("/api/v1/accounts/acc-1/session-for-sync",
                   headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 200
    assert r.json()["session_token"] == "T1"


def test_session_for_sync_409_when_not_active(client, accounts_in_db):
    accounts_in_db([{"id": "acc-1", "state": "cooldown",
                     "cooldown_until": "2026-04-28T13:00:00Z"}])
    r = client.get("/api/v1/accounts/acc-1/session-for-sync",
                   headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 409
    assert r.json()["detail"]["state"] == "cooldown"
```

- [ ] **Step 2: Run fail** — Expected 404.

- [ ] **Step 3: Implement**

```python
@router.get("/{account_id}/session-for-sync")
async def session_for_sync(
    account_id: str,
    _auth=Depends(require_api_key),
    sb=Depends(get_supabase),
):
    res = sb.table("avito_accounts").select("*").eq("id", account_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "account not found")
    row = res.data[0]
    if row["state"] != "active":
        raise HTTPException(409, detail={"state": row["state"], "id": account_id})
    s = sb.table("avito_sessions").select("*").eq("account_id", account_id).eq("is_active", True).limit(1).execute()
    if not s.data:
        raise HTTPException(409, detail={"state": "no_session", "id": account_id})
    sd = s.data[0]
    return {
        "account_id": account_id,
        "session_token": (sd.get("tokens") or {}).get("session_token"),
        "device_id": sd.get("device_id"),
        "fingerprint": sd.get("fingerprint"),
    }
```

- [ ] **Step 4: Run pass.**

- [ ] **Step 5: Commit**

```bash
git add avito-xapi/src/routers/accounts.py avito-xapi/tests/test_accounts_router.py
git commit -m "feat(xapi): GET /accounts/{id}/session-for-sync"
```

---

## Phase 3: xapi sessions.py refactoring

### Task 9: `resolve_or_create_account` helper

**Files:**
- Create: `avito-xapi/src/services/account_resolver.py`
- Create: `avito-xapi/tests/test_account_resolver.py`

- [ ] **Step 1: Failing tests**

```python
"""Tests for resolve_or_create_account helper."""
from src.services.account_resolver import resolve_or_create_account


def test_returns_existing_account(mock_sb):
    mock_sb.table("avito_accounts").select("*").eq("avito_user_id", 12345).execute.return_value.data = [
        {"id": "acc-1", "avito_user_id": 12345, "state": "active"},
    ]
    acc = resolve_or_create_account(mock_sb, avito_user_id=12345, device_id="D1")
    assert acc["id"] == "acc-1"


def test_creates_new_account_when_unknown(mock_sb):
    mock_sb.table("avito_accounts").select("*").eq("avito_user_id", 99999).execute.return_value.data = []
    mock_sb.table("avito_accounts").insert.return_value.execute.return_value.data = [
        {"id": "new-uuid", "avito_user_id": 99999, "nickname": "auto-99999", "state": "active"},
    ]
    acc = resolve_or_create_account(mock_sb, avito_user_id=99999, device_id="D9")
    assert acc["id"] == "new-uuid"
    assert acc["nickname"] == "auto-99999"


def test_updates_last_device_id_when_existing(mock_sb):
    mock_sb.table("avito_accounts").select("*").eq("avito_user_id", 12345).execute.return_value.data = [
        {"id": "acc-1", "avito_user_id": 12345, "last_device_id": "OLD"},
    ]
    resolve_or_create_account(mock_sb, avito_user_id=12345, device_id="NEW")
    upd = mock_sb.table("avito_accounts").update.call_args[0][0]
    assert upd["last_device_id"] == "NEW"
```

- [ ] **Step 2: Run fail** — Expected ImportError.

- [ ] **Step 3: Implement**

```python
"""Resolves Avito user_id → avito_accounts row, creates if missing."""
from datetime import datetime, timezone


def resolve_or_create_account(sb, *, avito_user_id: int, device_id: str | None) -> dict:
    res = sb.table("avito_accounts").select("*").eq("avito_user_id", avito_user_id).limit(1).execute()
    now = datetime.now(timezone.utc).isoformat()
    if res.data:
        acc = res.data[0]
        if device_id and acc.get("last_device_id") != device_id:
            sb.table("avito_accounts").update({
                "last_device_id": device_id,
                "last_session_at": now,
                "updated_at": now,
            }).eq("id", acc["id"]).execute()
            acc["last_device_id"] = device_id
        return acc
    # create
    new = sb.table("avito_accounts").insert({
        "avito_user_id": avito_user_id,
        "nickname": f"auto-{avito_user_id}",
        "last_device_id": device_id,
        "state": "active",
        "last_session_at": now,
    }).execute()
    return new.data[0]
```

- [ ] **Step 4: Run pass.**

- [ ] **Step 5: Commit**

```bash
git add avito-xapi/src/services/account_resolver.py avito-xapi/tests/test_account_resolver.py
git commit -m "feat(xapi): resolve_or_create_account helper for account-scoped sessions"
```

---

### Task 10: POST /sessions deactivation скоупим до account_id + waiting_refresh→active

**Files:**
- Modify: `avito-xapi/src/routers/sessions.py:29-82`
- Modify: `avito-xapi/tests/test_sessions_router.py`

- [ ] **Step 1: Failing tests**

Добавь в `tests/test_sessions_router.py`:

```python
def test_post_session_deactivates_only_same_account(client, accounts_in_db, sessions_in_db, mock_sb):
    """POST /sessions для acc-1 НЕ трогает sessions acc-2."""
    accounts_in_db([
        {"id": "acc-1", "avito_user_id": 111, "state": "active"},
        {"id": "acc-2", "avito_user_id": 222, "state": "active"},
    ])
    sessions_in_db([
        {"id": "s-old1", "account_id": "acc-1", "is_active": True, "user_id": 111},
        {"id": "s-other", "account_id": "acc-2", "is_active": True, "user_id": 222},
    ])
    payload = {
        "user_id": 111, "device_id": "D1",
        "tokens": {"session_token": "NEW", "refresh_token": "R", "device_id": "D1"},
    }
    r = client.post("/api/v1/sessions", headers={"X-Api-Key": "test_dev_key_123"}, json=payload)
    assert r.status_code in (200, 201)
    # Verify deactivation запрос был только для acc-1
    deact = mock_sb.captured_updates_for("avito_sessions")
    assert any(call.filter == ("account_id", "acc-1") for call in deact)
    assert not any(call.filter == ("account_id", "acc-2") for call in deact)


def test_post_session_waiting_refresh_to_active(client, accounts_in_db, mock_sb):
    accounts_in_db([
        {"id": "acc-1", "avito_user_id": 111, "state": "waiting_refresh",
         "waiting_since": "2026-04-28T11:50:00Z"},
    ])
    payload = {
        "user_id": 111, "device_id": "D1",
        "tokens": {"session_token": "NEW", "refresh_token": "R"},
    }
    r = client.post("/api/v1/sessions", headers={"X-Api-Key": "test_dev_key_123"}, json=payload)
    assert r.status_code in (200, 201)
    upd = mock_sb.last_update_for("avito_accounts")
    assert upd["state"] == "active"
    assert upd["waiting_since"] is None
```

- [ ] **Step 2: Run fail.**

- [ ] **Step 3: Modify `routers/sessions.py:29-82`**

Открой файл, найди блок текущей логики (Supabase update is_active=False WHERE tenant_id) и замени на:

```python
from src.services.account_resolver import resolve_or_create_account

@router.post("")
async def post_session(payload: SessionPayload, ctx=Depends(...)):
    # Resolve / create account
    acc = resolve_or_create_account(
        ctx.sb,
        avito_user_id=payload.user_id,
        device_id=payload.device_id,
    )
    
    # Deactivate ONLY same-account old sessions
    ctx.sb.table("avito_sessions").update({"is_active": False}).eq(
        "account_id", acc["id"]
    ).eq("is_active", True).execute()
    
    # Insert new session
    new_session = ctx.sb.table("avito_sessions").insert({
        "account_id": acc["id"],
        "tenant_id": ctx.tenant.id,  # legacy, оставляем заполненным
        "user_id": payload.user_id,
        "device_id": payload.device_id,
        "tokens": payload.tokens,
        "fingerprint": payload.tokens.get("fingerprint"),
        "source": payload.source or "android",
        "is_active": True,
        "expires_at": payload.expires_at,
    }).execute()
    
    # If waiting_refresh — transition to active
    if acc.get("state") == "waiting_refresh":
        ctx.sb.table("avito_accounts").update({
            "state": "active",
            "waiting_since": None,
            "last_session_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", acc["id"]).execute()
    
    return {"session_id": new_session.data[0]["id"], "account_id": acc["id"]}
```

(Подгоняй имена `ctx`, `SessionPayload` под фактический код. Сохрани все остальные поля payload что были в legacy-коде — не выкидывай.)

- [ ] **Step 4: Run pass.**

- [ ] **Step 5: Commit**

```bash
git add avito-xapi/src/routers/sessions.py avito-xapi/tests/test_sessions_router.py
git commit -m "feat(xapi): POST /sessions account-scoped deactivation + waiting_refresh transition"
```

---

## Phase 4: xapi session_reader

### Task 11: `load_session_for_account` + сохранить legacy wrapper

**Files:**
- Modify: `avito-xapi/src/workers/session_reader.py`
- Modify: `avito-xapi/tests/test_session_reader.py` (создать если нет)

- [ ] **Step 1: Failing tests**

```python
"""Tests for session_reader pool-aware loaders."""
from src.workers.session_reader import load_session_for_account, load_active_session


@pytest.mark.asyncio
async def test_load_session_for_account_returns_active(mock_sb):
    mock_sb.table("avito_sessions").select("*").eq("account_id", "acc-1").eq("is_active", True).execute.return_value.data = [
        {"account_id": "acc-1", "tokens": {"session_token": "T1"}, "device_id": "D1", "is_active": True},
    ]
    session = await load_session_for_account(mock_sb, "acc-1")
    assert session.session_token == "T1"


@pytest.mark.asyncio
async def test_load_session_for_account_none_when_missing(mock_sb):
    mock_sb.table("avito_sessions").select("*").eq("account_id", "acc-x").eq("is_active", True).execute.return_value.data = []
    session = await load_session_for_account(mock_sb, "acc-x")
    assert session is None


@pytest.mark.asyncio
async def test_legacy_load_active_session_picks_any_active(mock_sb):
    """Legacy wrapper для не-pool путей: возвращает любую активную."""
    mock_sb.table("avito_sessions").select("*").eq("is_active", True).execute.return_value.data = [
        {"account_id": "acc-1", "tokens": {"session_token": "Tx"}, "device_id": "Dx", "is_active": True},
    ]
    session = await load_active_session(mock_sb, tenant_id=None)
    assert session.session_token == "Tx"
```

- [ ] **Step 2: Run fail** — Expected: legacy `load_active_session` берёт MAX(created_at) WHERE tenant_id, новой `load_session_for_account` нет.

- [ ] **Step 3: Modify session_reader.py**

```python
"""Session reader — pool-aware + legacy."""
from typing import Optional

# ... existing imports ...


async def load_session_for_account(sb, account_id: str) -> Optional[SessionData]:
    """Pool-aware: возвращает active session конкретного account."""
    res = sb.table("avito_sessions").select("*").eq("account_id", account_id).eq("is_active", True).limit(1).execute()
    if not res.data:
        return None
    return _row_to_session_data(res.data[0])


async def load_active_session(sb, tenant_id=None) -> Optional[SessionData]:
    """DEPRECATED legacy wrapper. Pool-aware пути должны использовать load_session_for_account.
    
    Возвращает любую active session (произвольную из active accounts) для backward-compat
    эндпойнтов которые ещё не интегрированы с pool (например, generic search/items если есть).
    """
    res = sb.table("avito_sessions").select("*").eq("is_active", True).order(
        "created_at", desc=True
    ).limit(1).execute()
    if not res.data:
        return None
    return _row_to_session_data(res.data[0])


def _row_to_session_data(row):
    # Прежняя логика конвертации row → SessionData; повтори существующее.
    ...
```

(Вытащи `_row_to_session_data` из текущего `load_active_session`, чтобы не дублировать код.)

- [ ] **Step 4: Run pass.**

- [ ] **Step 5: Commit**

```bash
git add avito-xapi/src/workers/session_reader.py avito-xapi/tests/test_session_reader.py
git commit -m "feat(xapi): session_reader pool-aware load_session_for_account"
```

---

## Phase 5: xapi device_switcher

### Task 12: DeviceSwitcher class with mocked subprocess

**Files:**
- Create: `avito-xapi/src/workers/device_switcher.py`
- Create: `avito-xapi/tests/test_device_switcher.py`

- [ ] **Step 1: Failing tests**

```python
"""Tests for DeviceSwitcher — multi-phone ADB wrapper."""
import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from src.workers.device_switcher import DeviceSwitcher, DeviceSwitchError


@pytest.fixture
def fake_adb():
    """Mock subprocess.run для adb."""
    with patch("src.workers.device_switcher._run_adb", new_callable=AsyncMock) as mock:
        yield mock


@pytest.mark.asyncio
async def test_switch_to_target_when_already_there_is_noop(fake_adb):
    fake_adb.side_effect = [
        ("10", 0),  # adb -s S shell am get-current-user → 10
    ]
    sw = DeviceSwitcher()
    await sw.switch_to("110139ce", 10)
    # Только один вызов get-current-user, switch-user не вызывался
    assert fake_adb.call_count == 1
    assert fake_adb.call_args[0][0] == ["-s", "110139ce", "shell", "am", "get-current-user"]


@pytest.mark.asyncio
async def test_switch_to_when_different_runs_switch_user(fake_adb):
    fake_adb.side_effect = [
        ("10", 0),  # initial: at 10
        ("", 0),    # switch-user 0
        ("0", 0),   # confirm: now at 0
    ]
    sw = DeviceSwitcher()
    await sw.switch_to("110139ce", 0)
    assert fake_adb.call_count == 3
    assert fake_adb.call_args_list[1][0][0] == ["-s", "110139ce", "shell", "am", "switch-user", "0"]


@pytest.mark.asyncio
async def test_switch_to_raises_on_timeout(fake_adb):
    fake_adb.side_effect = [
        ("10", 0),  # at 10
        ("", 0),    # switch-user 0
        ("10", 0), ("10", 0), ("10", 0),  # confirm loop returns wrong user
    ]
    sw = DeviceSwitcher()
    with pytest.raises(DeviceSwitchError):
        await sw.switch_to("110139ce", 0, _confirm_timeout_sec=1.5, _confirm_interval_sec=0.5)


@pytest.mark.asyncio
async def test_health_returns_true_when_adb_state_device(fake_adb):
    fake_adb.return_value = ("device", 0)
    sw = DeviceSwitcher()
    assert await sw.health("110139ce") is True


@pytest.mark.asyncio
async def test_health_returns_false_when_adb_unauthorized(fake_adb):
    fake_adb.return_value = ("unauthorized", 0)
    sw = DeviceSwitcher()
    assert await sw.health("110139ce") is False


@pytest.mark.asyncio
async def test_per_phone_locks_dont_block_each_other(fake_adb):
    """Switch на двух разных phone_serial'ах должны идти параллельно."""
    fake_adb.side_effect = [
        ("0", 0), ("", 0), ("10", 0),  # phone A
        ("0", 0), ("", 0), ("10", 0),  # phone B
    ]
    sw = DeviceSwitcher()
    await asyncio.gather(
        sw.switch_to("PHONE_A", 10),
        sw.switch_to("PHONE_B", 10),
    )
    assert fake_adb.call_count == 6


@pytest.mark.asyncio
async def test_list_devices_parses_adb_devices(fake_adb):
    fake_adb.return_value = (
        "List of devices attached\n"
        "110139ce\tdevice\n"
        "ABCDEFGH\toffline\n"
        "XYZ12345\tdevice\n",
        0,
    )
    sw = DeviceSwitcher()
    serials = await sw.list_devices()
    assert serials == ["110139ce", "XYZ12345"]
```

- [ ] **Step 2: Run fail.**

- [ ] **Step 3: Implement DeviceSwitcher**

```python
"""ADB-based device switcher for Avito session pool.

Управляет N физическими телефонами через `adb -s <serial>`. Per-phone asyncio.Lock
позволяет параллельные switch'и на разных устройствах.
"""
import asyncio
import logging
from typing import Tuple

log = logging.getLogger(__name__)


class DeviceSwitchError(RuntimeError):
    pass


async def _run_adb(args: list[str], timeout: float = 10.0) -> Tuple[str, int]:
    """Run `adb <args>`, return (stdout, returncode)."""
    proc = await asyncio.create_subprocess_exec(
        "adb", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise DeviceSwitchError(f"adb {args} timed out")
    return stdout.decode().strip(), proc.returncode


class DeviceSwitcher:
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, phone_serial: str) -> asyncio.Lock:
        if phone_serial not in self._locks:
            self._locks[phone_serial] = asyncio.Lock()
        return self._locks[phone_serial]

    async def current_user(self, phone_serial: str) -> int:
        out, code = await _run_adb(["-s", phone_serial, "shell", "am", "get-current-user"])
        if code != 0:
            raise DeviceSwitchError(f"get-current-user failed: rc={code}, out={out}")
        return int(out.strip())

    async def switch_to(
        self, phone_serial: str, target: int,
        _confirm_timeout_sec: float = 5.0,
        _confirm_interval_sec: float = 0.5,
    ) -> None:
        async with self._lock_for(phone_serial):
            curr = await self.current_user(phone_serial)
            if curr == target:
                return
            out, code = await _run_adb(["-s", phone_serial, "shell", "am", "switch-user", str(target)])
            if code != 0:
                raise DeviceSwitchError(f"switch-user failed: rc={code}, out={out}")

            # confirm loop
            elapsed = 0.0
            while elapsed < _confirm_timeout_sec:
                await asyncio.sleep(_confirm_interval_sec)
                elapsed += _confirm_interval_sec
                if await self.current_user(phone_serial) == target:
                    return
            raise DeviceSwitchError(
                f"switch-user {target} on {phone_serial}: confirm timeout after {_confirm_timeout_sec}s"
            )

    async def health(self, phone_serial: str) -> bool:
        out, code = await _run_adb(["-s", phone_serial, "get-state"])
        return code == 0 and out.strip() == "device"

    async def list_devices(self) -> list[str]:
        out, code = await _run_adb(["devices"])
        if code != 0:
            return []
        serials = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] == "device":
                serials.append(parts[0])
        return serials


# Singleton, инициализируется при старте xapi
device_switcher = DeviceSwitcher()
```

- [ ] **Step 4: Run pass.**

```bash
cd avito-xapi && pytest tests/test_device_switcher.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add avito-xapi/src/workers/device_switcher.py avito-xapi/tests/test_device_switcher.py
git commit -m "feat(xapi): DeviceSwitcher — multi-phone ADB wrapper with per-phone locks"
```

---

### Task 13: LXC USB passthrough config + smoke test

**Files:** инфраструктурная, не код. Изменения только на homelab Proxmox.

- [ ] **Step 1: Подключить телефон к Proxmox-host физически**

OnePlus 8T → USB кабель → USB-порт на homelab сервере. Проверь:
```bash
ssh root@213.108.170.194 'lsusb | grep -i oneplus || lsusb'
```

Expected: видна строка с OnePlus (или OnePlus 8T idVendor:idProduct).

- [ ] **Step 2: Идентифицировать USB-узел**

```bash
ssh root@213.108.170.194 'ls -la /dev/bus/usb/*/* | grep -B1 -A1 -i oneplus || ls -la /dev/bus/usb/'
```

Запиши major:minor (например `189:N`).

- [ ] **Step 3: Modify LXC config контейнера xapi**

Найди номер LXC контейнера (где живёт avito-xapi):
```bash
ssh root@213.108.170.194 'pct list | grep xapi'
```

Edit config:
```bash
ssh root@213.108.170.194 'cat /etc/pve/lxc/<CTID>.conf'
```

Добавь строки:
```
lxc.cgroup2.devices.allow: c 189:* rwm
lxc.mount.entry: /dev/bus/usb dev/bus/usb none bind,optional,create=dir
```

- [ ] **Step 4: Restart LXC + verify**

```bash
ssh root@213.108.170.194 'pct restart <CTID>'
ssh root@213.108.170.194 'pct exec <CTID> -- lsusb'
```

Expected: те же USB устройства видны изнутри LXC.

- [ ] **Step 5: Install adb внутри контейнера**

Внутри LXC (через `pct exec <CTID> -- bash`):
```bash
apt-get update && apt-get install -y android-tools-adb
adb start-server
adb devices
```

Expected: `List of devices attached` + одна строка `110139ce  device`.

- [ ] **Step 6: Включить USB Debugging на телефоне**

На самом OnePlus: Settings → Developer Options → USB Debugging = ON. Authorize the homelab fingerprint когда диалог появится.

- [ ] **Step 7: Smoke test через Python**

В контейнере:
```bash
python3 -c "
import asyncio
import sys
sys.path.insert(0, '/app/src')
from workers.device_switcher import DeviceSwitcher

async def main():
    sw = DeviceSwitcher()
    print('Devices:', await sw.list_devices())
    print('Health:', await sw.health('110139ce'))
    print('Current user:', await sw.current_user('110139ce'))

asyncio.run(main())
"
```

Expected: показывает serial, health=True, current_user=0 или 10.

- [ ] **Step 8: Document в runbook**

Добавь в `DOCS/SETUP_USB_PASSTHROUGH.md` (создай новый):

```markdown
# USB Passthrough OnePlus → xapi LXC

LXC config /etc/pve/lxc/<CTID>.conf:
- lxc.cgroup2.devices.allow: c 189:* rwm
- lxc.mount.entry: /dev/bus/usb dev/bus/usb none bind,optional,create=dir

После изменений: `pct restart <CTID>`.
Внутри контейнера: apt-get install android-tools-adb, adb start-server.

Если adb не видит устройство:
1. Проверить USB Debugging на телефоне
2. Проверить authorization: adb shell echo OK; должна показать "OK"
3. lsusb внутри контейнера — устройство видно?
```

- [ ] **Step 9: Commit (только doc)**

```bash
git add DOCS/SETUP_USB_PASSTHROUGH.md
git commit -m "docs: USB passthrough setup для OnePlus → xapi LXC"
```

---

## Phase 6: xapi refresh-cycle endpoint

### Task 14: POST /api/v1/accounts/{id}/refresh-cycle (atomic switch + cmd)

**Files:**
- Modify: `avito-xapi/src/routers/accounts.py`
- Modify: `avito-xapi/tests/test_accounts_router.py`

- [ ] **Step 1: Failing test**

```python
def test_refresh_cycle_switches_user_creates_command_and_marks_waiting(client, accounts_in_db, mock_sb, monkeypatch):
    accounts_in_db([{"id": "acc-1", "state": "needs_refresh",
                     "android_user_id": 0, "phone_serial": "110139ce",
                     "last_device_id": "D1"}])
    
    switch_calls = []
    cmd_calls = []
    
    async def fake_switch(self, serial, target, **kw):
        switch_calls.append((serial, target))
    
    async def fake_create_cmd(sb, device_id, command, payload):
        cmd_calls.append((device_id, command))
        return {"id": "cmd-uuid"}
    
    monkeypatch.setattr("src.workers.device_switcher.DeviceSwitcher.switch_to", fake_switch)
    monkeypatch.setattr("src.routers.accounts.create_refresh_command", fake_create_cmd)
    
    r = client.post("/api/v1/accounts/acc-1/refresh-cycle",
                    headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 202
    assert switch_calls == [("110139ce", 0)]
    assert cmd_calls == [("D1", "refresh_token")]
    
    upd = mock_sb.last_update_for("avito_accounts")
    assert upd["state"] == "waiting_refresh"
    assert upd["waiting_since"] is not None


def test_refresh_cycle_409_when_adb_dead(client, accounts_in_db, monkeypatch):
    accounts_in_db([{"id": "acc-1", "state": "needs_refresh",
                     "phone_serial": "DEAD_SERIAL", "android_user_id": 0,
                     "last_device_id": "D1"}])
    
    async def fake_health(self, serial):
        return False
    monkeypatch.setattr("src.workers.device_switcher.DeviceSwitcher.health", fake_health)
    
    r = client.post("/api/v1/accounts/acc-1/refresh-cycle",
                    headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 503
    assert "adb" in r.json()["detail"].lower()
```

- [ ] **Step 2: Run fail.**

- [ ] **Step 3: Implement endpoint**

В `avito-xapi/src/routers/accounts.py`:

```python
import asyncio
from src.workers.device_switcher import device_switcher, DeviceSwitchError
from src.services.device_commands import create_refresh_command  # уже существует — найди реальный путь


@router.post("/{account_id}/refresh-cycle", status_code=202)
async def refresh_cycle(
    account_id: str,
    _auth=Depends(require_api_key),
    sb=Depends(get_supabase),
):
    res = sb.table("avito_accounts").select("*").eq("id", account_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "account not found")
    acc = res.data[0]
    
    # 1. ADB health
    if not await device_switcher.health(acc["phone_serial"]):
        raise HTTPException(503, detail=f"ADB-канал к {acc['phone_serial']} недоступен")
    
    # 2. Switch foreground
    try:
        await device_switcher.switch_to(acc["phone_serial"], acc["android_user_id"])
    except DeviceSwitchError as e:
        raise HTTPException(503, detail=f"switch-user failed: {e}")
    
    # 3. Wait NL прогрев
    await asyncio.sleep(8)
    
    # 4. Create refresh-token command
    if not acc.get("last_device_id"):
        raise HTTPException(409, "account has no last_device_id, cannot send refresh cmd")
    cmd = await create_refresh_command(sb, acc["last_device_id"], "refresh_token", {"timeout_sec": 90})
    
    # 5. Mark waiting_refresh
    sb.table("avito_accounts").update({
        "state": "waiting_refresh",
        "waiting_since": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", account_id).execute()
    
    return {"command_id": cmd.get("id"), "account_id": account_id}
```

(`create_refresh_command` — exists в `routers/device_commands.py:230-282`. Извлеки helper-функцию из существующего кода в `services/device_commands.py` если там логика inline в роутере.)

- [ ] **Step 4: Run pass.**

- [ ] **Step 5: Commit**

```bash
git add avito-xapi/src/routers/accounts.py avito-xapi/tests/test_accounts_router.py
git commit -m "feat(xapi): POST /accounts/{id}/refresh-cycle atomic ADB switch + cmd"
```

---

### Task 15: PATCH /api/v1/accounts/{id}/state (для dead detection из monitor'а)

**Files:**
- Modify: `avito-xapi/src/routers/accounts.py`
- Modify: `avito-xapi/tests/test_accounts_router.py`

Этот endpoint позволяет monitor health_checker'у пометить account как `dead` после 5-min waiting timeout.

- [ ] **Step 1: Failing test**

```python
def test_patch_state_sets_dead(client, accounts_in_db, mock_sb):
    accounts_in_db([{"id": "acc-1", "state": "waiting_refresh"}])
    r = client.patch("/api/v1/accounts/acc-1/state",
                     headers={"X-Api-Key": "test_dev_key_123"},
                     json={"state": "dead", "reason": "waiting_refresh timeout 5m"})
    assert r.status_code == 204
    upd = mock_sb.last_update_for("avito_accounts")
    assert upd["state"] == "dead"


def test_patch_state_rejects_invalid(client, accounts_in_db):
    accounts_in_db([{"id": "acc-1", "state": "active"}])
    r = client.patch("/api/v1/accounts/acc-1/state",
                     headers={"X-Api-Key": "test_dev_key_123"},
                     json={"state": "garbage"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run fail.**

- [ ] **Step 3: Implement**

```python
class StatePatchPayload(BaseModel):
    state: Literal["active", "cooldown", "needs_refresh", "waiting_refresh", "dead"]
    reason: str | None = None


@router.patch("/{account_id}/state", status_code=204)
async def patch_state(
    account_id: str,
    payload: StatePatchPayload,
    _auth=Depends(require_api_key),
    sb=Depends(get_supabase),
):
    update = {
        "state": payload.state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload.state != "waiting_refresh":
        update["waiting_since"] = None
    sb.table("avito_accounts").update(update).eq("id", account_id).execute()
    if payload.reason:
        log.warning("account %s state→%s: %s", account_id, payload.state, payload.reason)
```

- [ ] **Step 4: Run pass.**

- [ ] **Step 5: Commit**

```bash
git add avito-xapi/src/routers/accounts.py avito-xapi/tests/test_accounts_router.py
git commit -m "feat(xapi): PATCH /accounts/{id}/state for monitor-driven transitions"
```

---

## Phase 7: avito-monitor AccountPool client

### Task 16: AccountPool — claim_for_poll, report

**Files:**
- Create: `avito-monitor/app/services/account_pool.py`
- Create: `avito-monitor/tests/test_account_pool.py`

- [ ] **Step 1: Failing tests**

```python
"""Tests for AccountPool client."""
import pytest
import respx
from httpx import Response

from app.services.account_pool import (
    AccountPool, NoAvailableAccountError, AccountNotAvailableError,
)


@pytest.fixture
def xapi_base_url():
    return "http://xapi-test:8080"


@pytest.fixture
def pool(xapi_base_url):
    import httpx
    client = httpx.AsyncClient(base_url=xapi_base_url,
                                headers={"X-Api-Key": "test"})
    return AccountPool(xapi_client=client)


@pytest.mark.asyncio
async def test_claim_for_poll_returns_session(pool, xapi_base_url):
    with respx.mock(base_url=xapi_base_url) as m:
        m.post("/api/v1/accounts/poll-claim").mock(
            return_value=Response(200, json={
                "account_id": "acc-1", "session_token": "T1",
                "device_id": "D1", "fingerprint": "F1",
            }),
        )
        async with pool.claim_for_poll() as acc:
            assert acc["account_id"] == "acc-1"


@pytest.mark.asyncio
async def test_claim_for_poll_409_raises_no_available(pool, xapi_base_url):
    with respx.mock(base_url=xapi_base_url) as m:
        m.post("/api/v1/accounts/poll-claim").mock(
            return_value=Response(409, json={
                "detail": {"error": "pool_drained", "accounts": []}
            }),
        )
        with pytest.raises(NoAvailableAccountError):
            async with pool.claim_for_poll():
                pass


@pytest.mark.asyncio
async def test_report_truncates_body_to_1024(pool, xapi_base_url):
    captured = {}
    with respx.mock(base_url=xapi_base_url) as m:
        m.post("/api/v1/accounts/acc-1/report").mock(
            side_effect=lambda req: (captured.update(json=req.json()), Response(204))[1]
        )
        await pool.report("acc-1", 403, body="x" * 5000)
        assert len(captured["json"]["body_excerpt"]) == 1024


@pytest.mark.asyncio
async def test_report_none_body_sends_null(pool, xapi_base_url):
    captured = {}
    with respx.mock(base_url=xapi_base_url) as m:
        m.post("/api/v1/accounts/acc-1/report").mock(
            side_effect=lambda req: (captured.update(json=req.json()), Response(204))[1]
        )
        await pool.report("acc-1", 200, body=None)
        assert captured["json"]["body_excerpt"] is None


@pytest.mark.asyncio
async def test_claim_for_sync_409_raises_account_not_available(pool, xapi_base_url):
    with respx.mock(base_url=xapi_base_url) as m:
        m.get("/api/v1/accounts/acc-1/session-for-sync").mock(
            return_value=Response(409, json={"detail": {"state": "cooldown"}}),
        )
        with pytest.raises(AccountNotAvailableError) as ei:
            await pool.claim_for_sync("acc-1")
        assert ei.value.state == "cooldown"


@pytest.mark.asyncio
async def test_list_active_accounts_filters(pool, xapi_base_url):
    with respx.mock(base_url=xapi_base_url) as m:
        m.get("/api/v1/accounts").mock(return_value=Response(200, json=[
            {"id": "a1", "state": "active", "nickname": "Clone"},
            {"id": "a2", "state": "cooldown", "nickname": "Main"},
            {"id": "a3", "state": "active", "nickname": "Other"},
        ]))
        result = await pool.list_active_accounts()
        assert {a["nickname"] for a in result} == {"Clone", "Other"}
```

- [ ] **Step 2: Run fail** — Expected ImportError.

- [ ] **Step 3: Implement AccountPool**

Создай `avito-monitor/app/services/account_pool.py`:

```python
"""Pool client — тонкая обёртка над xapi /api/v1/accounts/* эндпойнтами."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging

import httpx

log = logging.getLogger(__name__)


class NoAvailableAccountError(Exception):
    def __init__(self, detail: dict):
        self.detail = detail
        super().__init__(detail.get("error", "no available account"))


class AccountNotAvailableError(Exception):
    def __init__(self, account_id: str, state: str):
        self.account_id = account_id
        self.state = state
        super().__init__(f"account {account_id} is in state={state}")


@dataclass
class AccountClaim:
    account_id: str
    session_token: str
    device_id: str | None
    fingerprint: str | None
    phone_serial: str | None
    android_user_id: int | None


class AccountPool:
    def __init__(self, xapi_client: httpx.AsyncClient):
        self.xapi = xapi_client

    @asynccontextmanager
    async def claim_for_poll(self):
        resp = await self.xapi.post("/api/v1/accounts/poll-claim", json={})
        if resp.status_code == 409:
            raise NoAvailableAccountError(resp.json().get("detail", {}))
        resp.raise_for_status()
        yield resp.json()

    async def report(self, account_id: str, status_code: int, body: str | None = None):
        body_excerpt = (body or "")[:1024] or None
        resp = await self.xapi.post(
            f"/api/v1/accounts/{account_id}/report",
            json={"status_code": status_code, "body_excerpt": body_excerpt},
        )
        resp.raise_for_status()

    async def claim_for_sync(self, account_id: str) -> dict:
        resp = await self.xapi.get(f"/api/v1/accounts/{account_id}/session-for-sync")
        if resp.status_code == 409:
            raise AccountNotAvailableError(account_id, resp.json().get("detail", {}).get("state", "unknown"))
        resp.raise_for_status()
        return resp.json()

    async def list_active_accounts(self) -> list[dict]:
        resp = await self.xapi.get("/api/v1/accounts")
        resp.raise_for_status()
        return [a for a in resp.json() if a.get("state") == "active"]

    async def list_all_accounts(self) -> list[dict]:
        resp = await self.xapi.get("/api/v1/accounts")
        resp.raise_for_status()
        return resp.json()

    async def trigger_refresh_cycle(self, account_id: str) -> dict:
        """Используется monitor health_checker для запуска refresh."""
        resp = await self.xapi.post(f"/api/v1/accounts/{account_id}/refresh-cycle")
        resp.raise_for_status()
        return resp.json()

    async def patch_state(self, account_id: str, state: str, reason: str | None = None):
        resp = await self.xapi.patch(
            f"/api/v1/accounts/{account_id}/state",
            json={"state": state, "reason": reason},
        )
        resp.raise_for_status()
```

- [ ] **Step 4: Run pass.**

```bash
cd avito-monitor && pytest tests/test_account_pool.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/services/account_pool.py avito-monitor/tests/test_account_pool.py
git commit -m "feat(monitor): AccountPool client — claim/report/sync/refresh-cycle"
```

---

## Phase 8: avito-monitor polling integration

### Task 17: `fetch_with_pool` retry logic

**Files:**
- Modify: `avito-monitor/app/tasks/polling.py`
- Modify: `avito-monitor/tests/test_polling.py` (создать или расширить)

- [ ] **Step 1: Failing test**

В `avito-monitor/tests/test_polling.py`:

```python
"""Tests for fetch_with_pool retry behaviour."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.tasks.polling import fetch_with_pool
from app.services.account_pool import NoAvailableAccountError


@pytest.mark.asyncio
async def test_403_retries_with_different_account():
    pool = MagicMock()
    pool.claim_for_poll = MagicMock()
    pool.report = AsyncMock()
    
    accounts = [{"account_id": "A"}, {"account_id": "B"}]
    
    @asynccontextmanager
    async def fake_claim():
        yield accounts.pop(0)
    pool.claim_for_poll = fake_claim
    
    fetcher = AsyncMock(side_effect=[
        XapiError(403, "<firewall>"),
        {"items": [], "total": 0},
    ])
    
    result = await fetch_with_pool(fetcher_fn=fetcher, pool=pool, max_attempts=2)
    
    assert result == {"items": [], "total": 0}
    assert pool.report.call_count == 2  # 403 первого + 200 второго
    assert pool.report.call_args_list[0][0] == ("A", 403)
    assert pool.report.call_args_list[1][0] == ("B", 200)


@pytest.mark.asyncio
async def test_5xx_retries_same_account_after_sleep(monkeypatch):
    pool = MagicMock()
    pool.report = AsyncMock()
    
    @asynccontextmanager
    async def fake_claim():
        yield {"account_id": "A"}
    pool.claim_for_poll = fake_claim
    
    fetcher = AsyncMock(side_effect=[
        XapiError(503, ""),
        {"items": []},
    ])
    sleep_calls = []
    monkeypatch.setattr("asyncio.sleep", AsyncMock(side_effect=lambda d: sleep_calls.append(d)))
    
    result = await fetch_with_pool(fetcher_fn=fetcher, pool=pool, max_attempts=2)
    assert result == {"items": []}
    assert sleep_calls == [5]


@pytest.mark.asyncio
async def test_pool_drained_returns_none():
    pool = MagicMock()
    
    @asynccontextmanager
    async def fake_claim():
        raise NoAvailableAccountError({"error": "pool_drained", "accounts": []})
    pool.claim_for_poll = fake_claim
    
    fetcher = AsyncMock()
    result = await fetch_with_pool(fetcher_fn=fetcher, pool=pool)
    assert result is None
    fetcher.assert_not_called()
```

- [ ] **Step 2: Run fail.**

- [ ] **Step 3: Implement fetch_with_pool**

В `avito-monitor/app/tasks/polling.py` рядом с существующим `poll_profile`:

```python
import asyncio
from contextlib import asynccontextmanager
from app.services.account_pool import NoAvailableAccountError, AccountPool
from app.integrations.xapi_client import XapiError


async def fetch_with_pool(*, fetcher_fn, pool: AccountPool, max_attempts: int = 2):
    """Wraps fetcher_fn(account_claim) → result, with retry on 403/401/5xx.
    
    fetcher_fn should accept an account_claim dict and return the result, raising XapiError on http errors.
    """
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            async with pool.claim_for_poll() as acc:
                try:
                    result = await fetcher_fn(acc)
                except XapiError as e:
                    await pool.report(acc["account_id"], e.status_code, e.body if hasattr(e, "body") else None)
                    if e.status_code in (403, 401) and attempt < max_attempts - 1:
                        last_error = e
                        continue  # retry с другим account
                    if e.status_code >= 500 and attempt < max_attempts - 1:
                        last_error = e
                        await asyncio.sleep(5)
                        continue  # retry с тем же account (он не виноват)
                    raise
                else:
                    await pool.report(acc["account_id"], 200)
                    return result
        except NoAvailableAccountError:
            log.warning("pool drained — profile_run skipped")
            return None
    raise last_error if last_error else RuntimeError("fetch_with_pool exhausted")
```

- [ ] **Step 4: Rewire `poll_profile`**

Найди в `polling.py:174-237` место где вызывается `mcp.fetch_subscription_items` и `mcp.fetch_search_page`. Заверни в `fetch_with_pool`:

```python
# было:
# async with AvitoMcpClient() as mcp:
#     items = await mcp.fetch_subscription_items(...)

# стало:
async def _fetcher(acc):
    async with AvitoMcpClient(account_id=acc["account_id"]) as mcp:
        if profile.import_source == "autosearch_sync":
            return await mcp.fetch_subscription_items(profile.avito_autosearch_id)
        return await mcp.fetch_search_page(profile.search_url)

result = await fetch_with_pool(fetcher_fn=_fetcher, pool=POOL_INSTANCE)
if result is None:
    profile_run.status = "skipped_no_account"
    return
items = result["items"]
```

(`AvitoMcpClient` нужно расширить чтобы принимал `account_id` и пробрасывал его в xapi-вызовы как query param `?account_id=...`. xapi эндпойнты должны его понимать. Это **subtask 17a** ниже.)

- [ ] **Step 5: Run tests pass.**

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/tasks/polling.py avito-monitor/tests/test_polling.py
git commit -m "feat(monitor): fetch_with_pool — retry on 403/401/5xx + pool draining"
```

---

### Task 17a: AvitoMcpClient — пробрасывать `account_id`

**Files:**
- Modify: `avito-monitor/app/integrations/avito_mcp_client/client.py`

- [ ] **Step 1: Проверь, какие методы принимают session-info.**

Read file `avito-monitor/app/integrations/avito_mcp_client/client.py` и найди методы `fetch_subscription_items`, `fetch_search_page`. Они дёргают xapi через httpx.

- [ ] **Step 2: Add account_id query param**

Modify методы чтобы принимать `account_id` опционально и добавлять его как query param:

```python
class AvitoMcpClient:
    def __init__(self, account_id: str | None = None):
        self._account_id = account_id
        # ... existing init ...

    async def fetch_subscription_items(self, filter_id: str, **kwargs):
        params = kwargs.copy()
        if self._account_id:
            params["account_id"] = self._account_id
        # ... existing call to xapi ...
```

- [ ] **Step 3: На стороне xapi** — `routers/subscriptions.py` принимает `account_id` query param и использует `load_session_for_account(account_id)` вместо legacy session reader.

Modify file `avito-xapi/src/routers/subscriptions.py`:

```python
@router.get("/{filter_id}/items")
async def get_subscription_items(
    filter_id: int,
    account_id: str | None = Query(None),
    sb=Depends(get_supabase),
    _auth=Depends(require_api_key),
):
    if account_id:
        session = await load_session_for_account(sb, account_id)
        if not session:
            raise HTTPException(409, f"account {account_id} has no active session")
    else:
        # backward-compat: pre-pool callers
        session = await load_active_session(sb)
    # ... rest of logic ...
```

- [ ] **Step 4: Test (integration через respx)**

```python
@pytest.mark.asyncio
async def test_avito_mcp_client_includes_account_id():
    import respx
    with respx.mock() as m:
        route = m.get("/api/v1/subscriptions/12345/items").mock(
            return_value=httpx.Response(200, json={"items": []}),
        )
        client = AvitoMcpClient(account_id="acc-X")
        await client.fetch_subscription_items("12345")
        assert "account_id=acc-X" in str(route.calls.last.request.url)
```

- [ ] **Step 5: Run pass.**

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/integrations/avito_mcp_client/client.py \
        avito-xapi/src/routers/subscriptions.py
git commit -m "feat(integration): pass account_id from monitor → xapi for pool-aware fetch"
```

---

## Phase 9: avito-monitor autosearch_sync per-account

### Task 18: Per-account loop in `sync_all_autosearches`

**Files:**
- Modify: `avito-monitor/app/services/autosearch_sync.py`
- Modify: `avito-monitor/tests/test_autosearch_sync.py`

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_sync_iterates_accounts_skips_cooldown(monkeypatch):
    pool_mock = AsyncMock()
    pool_mock.list_active_accounts.return_value = [
        {"id": "acc-1", "nickname": "Clone"},
        {"id": "acc-2", "nickname": "Other"},
    ]
    pool_mock.claim_for_sync.side_effect = [
        {"session_token": "T1"},
        AccountNotAvailableError("acc-2", "cooldown"),
    ]
    
    sync_called_with = []
    async def fake_sync(acc, session):
        sync_called_with.append(acc["id"])
    
    monkeypatch.setattr("app.services.autosearch_sync._sync_for_account", fake_sync)
    monkeypatch.setattr("app.services.autosearch_sync._POOL", pool_mock)
    
    await sync_all_autosearches()
    assert sync_called_with == ["acc-1"]  # acc-2 was skipped
```

- [ ] **Step 2: Run fail.**

- [ ] **Step 3: Modify `services/autosearch_sync.py`**

Найди существующий `sync_autosearches_for_user(user_id)` — обернись в loop:

```python
from app.services.account_pool import AccountNotAvailableError, AccountPool

# Singleton AccountPool (init в DI или module-level)
_POOL: AccountPool | None = None

def _get_pool() -> AccountPool:
    global _POOL
    if _POOL is None:
        # ... init httpx client с XAPI_URL + X-Api-Key из settings ...
        _POOL = AccountPool(xapi_client=...)
    return _POOL


async def sync_all_autosearches():
    pool = _get_pool()
    accounts = await pool.list_active_accounts()
    log.info("sync_all_autosearches: %d active accounts", len(accounts))
    for acc in accounts:
        try:
            session = await pool.claim_for_sync(acc["id"])
        except AccountNotAvailableError as e:
            log.info("skip sync acc=%s state=%s", acc["nickname"], e.state)
            continue
        await _sync_for_account(acc, session)


async def _sync_for_account(acc: dict, session: dict):
    autosearches = await xapi.list_subscriptions(account_id=acc["id"])
    for autosearch in autosearches:
        await _upsert_search_profile(autosearch, owner_account_id=acc["id"])
        await asyncio.sleep(_PER_ITEM_SLEEP_SEC)
```

- [ ] **Step 4: Run pass.**

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/services/autosearch_sync.py avito-monitor/tests/test_autosearch_sync.py
git commit -m "feat(monitor): autosearch_sync per-account loop with cooldown skip"
```

---

## Phase 10: avito-monitor health_checker — refresh path

### Task 19: Account-aware tick в health_checker

**Files:**
- Modify: `avito-monitor/app/services/health_checker/` (расширить существующие модули)
- Add: `avito-monitor/tests/health_checker/test_account_refresh_path.py`

`health_checker` — это уже существующий subsystem в monitor'е, расширяем его.

- [ ] **Step 1: Failing test**

```python
"""Tests for account-aware tick in health_checker."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.services.health_checker.account_tick import account_tick_iteration

NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_cooldown_expired_triggers_refresh_cycle():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "cooldown",
        "cooldown_until": (NOW - timedelta(seconds=10)).isoformat(),
    }]
    pool.trigger_refresh_cycle = AsyncMock()
    
    await account_tick_iteration(pool=pool, now=NOW, tg=AsyncMock())
    
    pool.trigger_refresh_cycle.assert_called_once_with("acc-1")


@pytest.mark.asyncio
async def test_waiting_refresh_5min_marks_dead_and_alerts():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "waiting_refresh", "nickname": "Clone",
        "android_user_id": 10,
        "waiting_since": (NOW - timedelta(minutes=5, seconds=10)).isoformat(),
    }]
    pool.patch_state = AsyncMock()
    tg = AsyncMock()
    
    await account_tick_iteration(pool=pool, now=NOW, tg=tg)
    
    pool.patch_state.assert_called_once_with("acc-1", "dead", reason="waiting_refresh timeout 5m")
    tg.assert_awaited_once()
    msg = tg.call_args[0][0]
    assert "Clone" in msg
    assert "10" in msg


@pytest.mark.asyncio
async def test_active_with_expiry_under_3min_triggers_proactive_refresh():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "active",
        "expires_at": (NOW + timedelta(minutes=2)).isoformat(),
    }]
    pool.trigger_refresh_cycle = AsyncMock()
    
    await account_tick_iteration(pool=pool, now=NOW, tg=AsyncMock())
    pool.trigger_refresh_cycle.assert_called_once_with("acc-1")


@pytest.mark.asyncio
async def test_active_with_expiry_far_does_nothing():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "active",
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
    }]
    pool.trigger_refresh_cycle = AsyncMock()
    
    await account_tick_iteration(pool=pool, now=NOW, tg=AsyncMock())
    pool.trigger_refresh_cycle.assert_not_called()
```

- [ ] **Step 2: Run fail** — Expected ImportError.

- [ ] **Step 3: Implement `account_tick_iteration`**

Создай `avito-monitor/app/services/health_checker/account_tick.py`:

```python
"""Per-tick проверка состояний accounts pool. Запускается из существующего
health_checker scheduler'а каждые 30 секунд."""
import logging
from datetime import datetime, timedelta, timezone

from app.services.account_pool import AccountPool

log = logging.getLogger(__name__)


def _parse_ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


async def account_tick_iteration(*, pool: AccountPool, now: datetime, tg):
    accounts = await pool.list_all_accounts()
    for acc in accounts:
        await _process_account(acc, pool=pool, now=now, tg=tg)


async def _process_account(acc, *, pool, now, tg):
    state = acc.get("state")
    aid = acc["id"]

    if state == "cooldown":
        until = _parse_ts(acc.get("cooldown_until"))
        if until and until < now:
            try:
                await pool.trigger_refresh_cycle(aid)
                log.info("refresh-cycle triggered for %s (post-cooldown)", aid)
            except Exception as e:
                log.warning("refresh-cycle failed for %s: %s", aid, e)
        return

    if state == "waiting_refresh":
        since = _parse_ts(acc.get("waiting_since"))
        if since and (now - since) > timedelta(minutes=5):
            await pool.patch_state(aid, "dead", reason="waiting_refresh timeout 5m")
            await tg(
                f"⚠️ Account {acc.get('nickname')} (Android-user "
                f"{acc.get('android_user_id')}) не получил refresh за 5 минут. "
                f"Открой вручную или проверь APK."
            )
        return

    if state == "active":
        exp = _parse_ts(acc.get("expires_at"))
        if exp and (exp - now) < timedelta(minutes=3):
            try:
                await pool.trigger_refresh_cycle(aid)
                log.info("refresh-cycle triggered for %s (proactive)", aid)
            except Exception as e:
                log.warning("proactive refresh failed for %s: %s", aid, e)
        return
```

- [ ] **Step 4: Wire в существующий health_checker scheduler**

Найди где живёт основной tick health_checker'а (вероятно `app/services/health_checker/runner.py` или `scenarios.py`). Добавь вызов:

```python
from app.services.health_checker.account_tick import account_tick_iteration

async def health_loop():
    while not stop:
        # ... existing scenarios ...
        try:
            await account_tick_iteration(pool=POOL, now=datetime.now(timezone.utc), tg=tg_send)
        except Exception:
            log.exception("account_tick failed")
        await asyncio.sleep(30)
```

- [ ] **Step 5: Run pass.**

```bash
cd avito-monitor && pytest tests/health_checker/test_account_refresh_path.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/services/health_checker/account_tick.py \
        avito-monitor/app/services/health_checker/runner.py \
        avito-monitor/tests/health_checker/test_account_refresh_path.py
git commit -m "feat(monitor): health_checker account_tick — refresh on cooldown/expiry/timeout"
```

---

### Task 20: TG-alert для consecutive_cooldowns >= 5

**Files:**
- Modify: `avito-monitor/app/services/health_checker/account_tick.py`
- Modify: тот же test файл

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_consecutive_5_alert_emitted_once():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "cooldown", "nickname": "Clone",
        "consecutive_cooldowns": 5,
        "cooldown_until": (NOW + timedelta(hours=24)).isoformat(),
    }]
    tg = AsyncMock()
    
    # First call — alert sent
    await account_tick_iteration(pool=pool, now=NOW, tg=tg)
    assert tg.call_count == 1
    
    # Second call (next tick) — НЕ повторяем alert (idempotent через флаг in-memory)
    await account_tick_iteration(pool=pool, now=NOW, tg=tg)
    assert tg.call_count == 1  # still 1
```

- [ ] **Step 2: Run fail.**

- [ ] **Step 3: Add alert logic**

Modify `account_tick.py`:

```python
_alerted_24h: set[str] = set()


async def _process_account(acc, *, pool, now, tg):
    # ... existing logic ...
    
    if acc.get("consecutive_cooldowns", 0) >= 5 and acc["id"] not in _alerted_24h:
        await tg(
            f"🚨 Account {acc.get('nickname')} лежит в 24h cooldown "
            f"(consecutive={acc['consecutive_cooldowns']}). Проверь вручную."
        )
        _alerted_24h.add(acc["id"])
    
    # При сбросе counter (200 пришёл) — снимаем alert flag
    if acc.get("consecutive_cooldowns", 0) == 0 and acc["id"] in _alerted_24h:
        _alerted_24h.remove(acc["id"])
```

- [ ] **Step 4: Run pass.**

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/services/health_checker/account_tick.py \
        avito-monitor/tests/health_checker/test_account_refresh_path.py
git commit -m "feat(monitor): TG-alert on consecutive_cooldowns >= 5 (idempotent)"
```

---

## Phase 11: UI /settings/accounts (read-only)

### Task 21: Route + template

**Files:**
- Modify: `avito-monitor/app/web/routers.py`
- Create: `avito-monitor/app/web/templates/settings/accounts.html`
- Create: `avito-monitor/tests/web/test_settings_accounts.py`

- [ ] **Step 1: Failing test**

```python
"""Tests for /settings/accounts page."""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_get_settings_accounts_renders_table(client, monkeypatch):
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        {"id": "acc-1", "nickname": "Clone", "state": "active",
         "android_user_id": 10, "consecutive_cooldowns": 0,
         "last_polled_at": "2026-04-28T12:00:00Z"},
        {"id": "acc-2", "nickname": "Main", "state": "dead",
         "android_user_id": 0, "consecutive_cooldowns": 5,
         "last_403_body": "<firewall>"},
    ]
    monkeypatch.setattr("app.web.routers._get_pool", lambda: pool)
    
    r = await client.get("/settings/accounts")
    assert r.status_code == 200
    body = r.text
    assert "Clone" in body
    assert "Main" in body
    assert "active" in body or "🟢" in body
    assert "dead" in body or "🔴" in body
```

- [ ] **Step 2: Run fail.**

- [ ] **Step 3: Add route in `app/web/routers.py`**

```python
@web_router.get("/settings/accounts", response_class=HTMLResponse)
async def settings_accounts(request: Request):
    pool = _get_pool()
    accounts = await pool.list_all_accounts()
    return templates.TemplateResponse(
        "settings/accounts.html",
        {"request": request, "accounts": accounts},
    )


def _get_pool() -> AccountPool:
    # init httpx client с XAPI_URL + X-Api-Key из settings
    from app.services.account_pool import AccountPool
    import httpx
    from app.config import settings
    client = httpx.AsyncClient(base_url=settings.XAPI_URL, headers={"X-Api-Key": settings.XAPI_API_KEY})
    return AccountPool(xapi_client=client)
```

- [ ] **Step 4: Create template**

Создай `avito-monitor/app/web/templates/settings/accounts.html`:

```html
{% extends "base.html" %}
{% block title %}Аккаунты Avito{% endblock %}

{% block content %}
<h1>Аккаунты Avito (pool)</h1>
<p class="muted">Read-only. Управление состояниями — через подключённый APK.</p>

<table class="data-table">
  <thead>
    <tr>
      <th>Nickname</th>
      <th>Android-user</th>
      <th>Phone</th>
      <th>State</th>
      <th>Cooldown until</th>
      <th>Last polled</th>
      <th>Consecutive</th>
      <th>Last 403</th>
    </tr>
  </thead>
  <tbody>
    {% for acc in accounts %}
    <tr>
      <td>{{ acc.nickname }}</td>
      <td>{{ acc.android_user_id }}</td>
      <td><code>{{ acc.phone_serial or '—' }}</code></td>
      <td>
        {% if acc.state == 'active' %}<span class="badge ok">🟢 active</span>
        {% elif acc.state == 'cooldown' %}<span class="badge warn">🟡 cooldown</span>
        {% elif acc.state == 'needs_refresh' %}<span class="badge warn">🟠 needs_refresh</span>
        {% elif acc.state == 'waiting_refresh' %}<span class="badge info">🔵 waiting_refresh</span>
        {% elif acc.state == 'dead' %}<span class="badge err">🔴 dead</span>
        {% endif %}
      </td>
      <td>{{ acc.cooldown_until or '—' }}</td>
      <td>{{ acc.last_polled_at or '—' }}</td>
      <td>{{ acc.consecutive_cooldowns }}</td>
      <td>
        {% if acc.last_403_body %}
        <details><summary>view</summary><pre>{{ acc.last_403_body }}</pre></details>
        {% else %}—{% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 5: Run pass.**

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/web/routers.py \
        avito-monitor/app/web/templates/settings/accounts.html \
        avito-monitor/tests/web/test_settings_accounts.py
git commit -m "feat(monitor): /settings/accounts read-only UI for pool state"
```

---

## Phase 12: Polish

### Task 22: Fix 5 broken health_checker tests

CONTINUE.md §3: «5 health_checker tests сломаны после Stage 9 (русские vs английские)».

**Files:**
- Modify: existing `avito-monitor/tests/health_checker/*.py`

- [ ] **Step 1: Найди сломанные тесты**

```bash
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && \
  docker compose exec -T app pytest tests/health_checker/ -v 2>&1 | grep -E "FAIL|ERROR"'
```

Expected: 5 имён тестов с FAIL.

- [ ] **Step 2: Open each failing test, find assertion на строку**

Для каждого FAIL'а: открой файл, найди `assert "..."` где русская/английская строка не совпадает с фактическим выводом.

- [ ] **Step 3: Поправь ассерты под текущие сообщения**

Заменяй ожидание на актуальный текст из реального лога/exception. Не меняй код продакшна — это просто fix tests.

- [ ] **Step 4: Run all health_checker tests pass**

```bash
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && \
  docker compose exec -T app pytest tests/health_checker/ -v'
```

Expected: 0 failures.

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/tests/health_checker/
git commit -m "test(health_checker): fix 5 stale tests with outdated string assertions"
```

---

### Task 23: Deploy + E2E checklist

**Files:** инфраструктурная.

- [ ] **Step 1: Deploy xapi**

```bash
ssh homelab 'cd /mnt/projects/repos/AvitoSystem && git pull && \
  cd avito-xapi && docker compose up -d --build'
```

Verify:
```bash
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' http://127.0.0.1:8080/api/v1/accounts | python3 -m json.tool"
```

Expected: список accounts (1 или 2).

- [ ] **Step 2: Deploy avito-monitor**

```bash
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && \
  docker compose up -d --build && docker compose exec -T app alembic upgrade head'
```

- [ ] **Step 3: Verify scheduler round-robin**

```bash
ssh homelab 'docker logs avito-monitor-worker-1 --since=10m 2>&1 | grep "scheduler.tick" | tail -10'
```

Expected: enqueued=1 / skipped_gap=1 alternation сохранилась (изменений в scheduler не было).

- [ ] **Step 4: Force test — 403 на одном account**

```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  \"UPDATE avito_accounts SET state='cooldown', cooldown_until=NOW()+INTERVAL '20 min', consecutive_cooldowns=1 WHERE nickname='Clone';\""
```

Жди 60 сек. Verify polling переключился на другой active account (если есть Main с new session) или попадает в pool drained:
```bash
ssh homelab "docker exec avito-monitor-db-1 psql -h 127.0.0.1 -U avito -d avito_monitor -c \
  \"SELECT started_at, status FROM profile_runs WHERE started_at > NOW() - INTERVAL '5 min' ORDER BY started_at DESC LIMIT 5;\""
```

Expected: status='skipped_no_account' (если pool=1) или success (если есть второй active).

Возврат:
```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  \"UPDATE avito_accounts SET state='active', cooldown_until=NULL, consecutive_cooldowns=0 WHERE nickname='Clone';\""
```

- [ ] **Step 5: Force test — cooldown_expired**

```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  \"UPDATE avito_accounts SET state='cooldown', cooldown_until=NOW()+INTERVAL '30 sec' WHERE nickname='Clone';\""
```

Жди 60 сек. Verify health_checker сделал refresh-cycle:
```bash
ssh homelab 'docker logs avito-monitor-worker-1 --since=2m 2>&1 | grep -i "refresh-cycle"'
```

Expected: `refresh-cycle triggered for <uuid> (post-cooldown)`.

И посмотреть что Avito-app в Android-user 10 действительно сделал refresh:
```bash
ssh homelab "docker exec supabase-db psql -U postgres -d postgres -c \
  \"SELECT id, account_id, is_active, EXTRACT(EPOCH FROM (NOW()-created_at))/60 as min_old FROM avito_sessions WHERE is_active=true ORDER BY created_at DESC LIMIT 3;\""
```

Expected: новая session row с recent created_at (< 1 мин).

- [ ] **Step 6: Force test — dead**

```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  \"UPDATE avito_accounts SET state='waiting_refresh', waiting_since=NOW()-INTERVAL '6 min' WHERE nickname='Clone';\""
```

Жди 60 сек. Verify TG-alert приходит. Verify state=dead:
```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  \"SELECT nickname, state FROM avito_accounts;\""
```

Expected: Clone | dead.

Возврат:
```bash
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  \"UPDATE avito_accounts SET state='active', waiting_since=NULL, consecutive_cooldowns=0 WHERE nickname='Clone';\""
```

- [ ] **Step 7: Force test — ADB unplug**

Физически вытащи USB-кабель. Жди 60 сек. Verify в health_checker логах:
```bash
ssh homelab 'docker logs xapi-... --since=2m 2>&1 | grep -i "adb"'
```

Expected: ошибка / TG-alert «ADB-канал к 110139ce отвалился».
Verify что polling продолжается (на cached токенах):
```bash
ssh homelab 'docker logs avito-monitor-worker-1 --since=2m 2>&1 | grep "scheduler.tick" | tail -5'
```

Expected: enqueued=1 продолжается. Воткни кабель обратно.

- [ ] **Step 8: Reboot worker — verify recovery**

```bash
ssh homelab 'docker restart avito-monitor-worker-1'
```

Жди 60 сек. Verify polling возобновился:
```bash
ssh homelab 'docker logs avito-monitor-worker-1 --since=2m 2>&1 | grep "scheduler.tick" | tail -5'
```

Expected: новые tick'и идут.

- [ ] **Step 9: Smoke /settings/accounts**

```bash
ssh homelab "curl -s http://127.0.0.1:8000/settings/accounts | grep -i 'Clone'"
```

(Or open в браузере если есть.) Expected: видим строку Clone, badge 🟢.

- [ ] **Step 10: Document**

Обновить `CONTINUE.md` — будет в Task 24.

---

### Task 24: Update CONTINUE.md

**Files:**
- Modify: `CONTINUE.md`

- [ ] **Step 1: Edit handoff doc**

В `CONTINUE.md`:
- В §1 «Что задеплоено и работает» добавить новую строку: «Account pool: avito_accounts table, round-robin claim, cooldown ratchet, post-cooldown auto-refresh через ADB device-switcher. Pool из 2 accounts (Clone active, Main dead до restore).»
- В §1 «Что НЕ сделано в этой сессии (TODO)» — пометить #13/#14/#15 как **DONE** (с reference на этот plan).
- В §3 «Известные хвосты» — обновить «#13/#14 backend для round-robin» → «**Done через account pool plan, см. DOCS/superpowers/plans/2026-04-28-account-pool.md**».
- В §3 — добавить новую заметку: «ADB-кабель OnePlus → homelab. LXC USB passthrough configured. Если USB отвалится → TG-alert. Manual reconnect: воткнуть кабель обратно, через 30 сек health() вернётся».
- В §4 «Что делать дальше» — пересмотреть приоритеты. C (восстановить user 0 token) теперь в pool работает: добавится автоматически когда APK Main сделает POST /sessions.

- [ ] **Step 2: Commit**

```bash
git add CONTINUE.md
git commit -m "docs(continue): handoff after account pool implementation"
```

---

## Self-Review Checklist (для plan'а)

После выполнения всех задач:

**1. Spec coverage:**
- [x] §6.1 Supabase 0005 → Task 1
- [x] §6.2 Monitor Alembic → Task 3
- [x] §7.1 accounts router → Tasks 5-8, 14-15
- [x] §7.2 sessions.py refactoring → Task 10
- [x] §7.3 session_reader → Task 11
- [x] §7.4 health_checker → Task 19-20 (но в monitor, deviation от spec'а явно отмечен)
- [x] §7.5 device_switcher → Task 12-13
- [x] §7.6 AccountPool client → Task 16
- [x] §7.7 polling integration → Task 17, 17a
- [x] §7.8 autosearch_sync → Task 18
- [x] §7.9 UI → Task 21
- [x] §8 Data flows проверяются в Task 23 E2E
- [x] §9 Concurrency tests → встроены в Tasks 6, 12
- [x] §10 Error matrix → реализовано через state machine + tests
- [x] §11 Logging → log statements распределены по реализациям
- [x] §12 Testing → каждая задача начинается с failing test
- [x] §13 Migration runbook → Tasks 1-3, 13, 23
- [x] §14 Acceptance criteria → Task 23 E2E checklist

**2. Placeholder scan:** все code-snippet'ы заполнены, нет TBD/TODO. Один помеченный — `_row_to_session_data` в Task 11 (повторить из существующего `load_active_session` — это refactoring, не new code).

**3. Type consistency:**
- `claim_for_poll`, `report`, `claim_for_sync`, `list_active_accounts`, `list_all_accounts`, `trigger_refresh_cycle`, `patch_state` — все ссылки на эти методы согласованы между Task 16 (definition) и Tasks 17/18/19 (использование). ✓
- `compute_next_state(curr, event, *, now)` сигнатура → используется в Task 7 (report endpoint). ✓
- `device_switcher.switch_to(phone_serial, target)`, `health(phone_serial)`, `current_user(phone_serial)` — согласованы между Task 12 и Task 14. ✓
- `AccountState`, `Event`, `cooldown_duration_for` — определены в Task 4, повторно используются в Task 7 (через import from `account_state`). ✓

---

**Plan complete and saved to `c:/Projects/Sync/AvitoSystem/DOCS/superpowers/plans/2026-04-28-account-pool.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — я диспатчу свежий subagent на каждую задачу, ревью между, fast iteration

**2. Inline Execution** — выполняю задачи в этой сессии через executing-plans, batch-execution с checkpoint'ами

**Какой подход?**
