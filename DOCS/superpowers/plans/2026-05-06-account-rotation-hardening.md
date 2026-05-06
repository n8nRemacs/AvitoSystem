# Account Rotation Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать AccountPool устойчивым к протухшим токенам и owner-mismatch — фетч никогда не ходит в Avito с дохлым токеном и никогда не пытается достать чужой autosearch чужим аккаунтом.

**Architecture:** Три независимых фикса в 3 commit'ах:
- **A. Liveness predicate** в `POST /api/v1/accounts/poll-claim` — выдаём только сессии с `expires_at > NOW() + 5 min`.
- **B. Cooldown auto-recovery** в health-checker `account_tick` — раз в 30s переводим `state='cooldown'` с истёкшим `cooldown_until` обратно в `active` (если сессия свежая) или `needs_refresh` (если нет).
- **C. Owner-aware claim** — `poll-claim` принимает опциональный `account_id`; polling для autosearch-based профилей пинит claim к `profile.owner_account_id` без ретрая по другим аккаунтам.

После всех трёх фиксов:
- Pool никогда не выдаёт expired/stale-token аккаунт.
- `state='cooldown'` с истёкшим cooldown сам «расцветает» обратно (наша текущая ситуация: `14acfef4` со свежей сессией до 2026-05-07 07:57 UTC, но застрявший в cooldown).
- 7 search_profiles owned by Clone (`42c179db`, dead) → polling возвращает чистый «owner_unavailable» fail вместо retry-spam'а 403'ками.

**Tech Stack:** FastAPI + Pydantic v2 (xapi), Supabase Python SDK (storage layer mock'ается через `make_mock_sb` в тестах), pytest + pytest-asyncio (monitor), httpx (AccountPool client).

---

## File Structure

| Файл | Что делает |
|---|---|
| `avito-xapi/src/routers/accounts.py` | Расширяем `poll_claim()` — fresh-session predicate + опциональный `account_id` в payload |
| `avito-xapi/tests/test_accounts_router.py` | +4 теста: skip-stale-session, fresh-session-passes, claim-by-account-id, claim-by-account-id-409-stale |
| `avito-monitor/app/services/account_pool.py` | `claim_for_poll(account_id=None)` пробрасывает в xapi |
| `avito-monitor/app/services/health_checker/account_tick.py` | +функция `_recover_expired_cooldowns()` |
| `avito-monitor/tests/services/test_account_tick.py` | новый файл, покрывает recovery flow |
| `avito-monitor/app/tasks/polling.py` | `fetch_with_pool(required_owner=None)` + branch для autosearch-based профилей |
| `avito-monitor/tests/test_polling.py` | +2 теста: owner-binding, owner-binding-no-retry |

Изменения локализованы в 7 файлах, никаких миграций БД, никакого нового storage. Существующие колонки (`avito_accounts.state`, `cooldown_until`, `avito_sessions.expires_at`) уже всё что нужно.

---

## Task 1: Liveness predicate в `poll-claim`

**Files:**
- Modify: `avito-xapi/src/routers/accounts.py:44-115` (функция `poll_claim`)
- Test: `avito-xapi/tests/test_accounts_router.py` (добавить тесты в конец секции `poll_claim`)

**Что меняем.** Сейчас `poll_claim` после CAS делает `select avito_sessions WHERE account_id=... AND is_active=true LIMIT 1` и если нет строки → continue. Но если строка есть с `expires_at < NOW()` — она всё равно возвращается, и xapi отдаёт протухший session_token. Polling worker ловит 401, ретраит, в худшем случае snowball на всех LRU-active. Добавляем predicate `expires_at > NOW() + INTERVAL '5 min'` в session select. Если нет свежей — continue к следующему LRU-active.

5-минутный safety margin — чтобы между моментом claim'а и моментом удара в Avito токен не успел истечь (Avito polling tick ~60s, network roundtrip ~1s; 5 минут с запасом покрывает любую задержку).

- [ ] **Step 1: Добавить failing test для skip-stale-session**

В `avito-xapi/tests/test_accounts_router.py` после `test_poll_claim_picks_oldest_active`:

```python
def test_poll_claim_skips_account_with_stale_session(client, accounts_in_db):
    """Account with active session but expires_at < NOW()+5min must be skipped.

    Setup: two accounts, both state='active'. acc-1 (LRU) has session expiring
    in 1 minute (stale). acc-2 has fresh session (24h). poll_claim should pick
    acc-2 — never serve a stale token.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    stale_iso = (now + timedelta(minutes=1)).isoformat()
    fresh_iso = (now + timedelta(hours=24)).isoformat()

    # 1) SELECT active accounts ORDER BY last_polled_at — acc-1 first (LRU).
    accounts_in_db([
        {"id": "acc-1", "state": "active", "last_polled_at": "2026-05-06T10:00:00Z",
         "phone_serial": "S1", "android_user_id": 0, "nickname": "stale"},
    ])
    # 2) CAS update for acc-1 — succeeds.
    accounts_in_db([
        {"id": "acc-1", "state": "active", "last_polled_at": "2026-05-06T12:30:00Z"},
    ])
    # 3) SELECT session for acc-1 — has stale session.
    accounts_in_db([
        {"id": "sess-1", "account_id": "acc-1", "is_active": True,
         "expires_at": stale_iso,
         "device_id": "stale_dev", "fingerprint": "stale_fp",
         "tokens": {"session_token": "STALE_TOKEN"}},
    ])
    # 4) Loop continues: SELECT next LRU active — acc-2 (now LRU since acc-1 was bumped).
    accounts_in_db([
        {"id": "acc-2", "state": "active", "last_polled_at": "2026-05-06T11:00:00Z",
         "phone_serial": "S2", "android_user_id": 10, "nickname": "fresh"},
    ])
    # 5) CAS update for acc-2 — succeeds.
    accounts_in_db([
        {"id": "acc-2", "state": "active", "last_polled_at": "2026-05-06T12:30:01Z"},
    ])
    # 6) SELECT session for acc-2 — fresh.
    accounts_in_db([
        {"id": "sess-2", "account_id": "acc-2", "is_active": True,
         "expires_at": fresh_iso,
         "device_id": "fresh_dev", "fingerprint": "fresh_fp",
         "tokens": {"session_token": "FRESH_TOKEN"}},
    ])

    r = client.post("/api/v1/accounts/poll-claim",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] == "acc-2"
    assert body["session_token"] == "FRESH_TOKEN"


def test_poll_claim_409_when_all_sessions_stale(client, accounts_in_db):
    """If every active account has a stale session, return 409 pool_drained.

    poll_claim must not mark a stale account as 'active that just got polled'
    forever — but for this MVP fix we accept that LRU bump is irrelevant when
    pool is fully stale (caller will retry next tick anyway). Verifies the
    409 happens once we exhaust _CLAIM_MAX_ATTEMPTS=3 retries with stale
    sessions everywhere.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    stale_iso = (now + timedelta(minutes=1)).isoformat()

    # Pattern repeats 3 times (one per CAS attempt): pick LRU, CAS, fetch session (stale).
    for _ in range(3):
        accounts_in_db([
            {"id": "acc-1", "state": "active", "last_polled_at": "2026-05-06T10:00:00Z",
             "phone_serial": "S1", "android_user_id": 0, "nickname": "stale"},
        ])
        accounts_in_db([
            {"id": "acc-1", "state": "active", "last_polled_at": "2026-05-06T12:30:00Z"},
        ])
        accounts_in_db([
            {"id": "sess-1", "account_id": "acc-1", "is_active": True,
             "expires_at": stale_iso,
             "device_id": "x", "fingerprint": "x",
             "tokens": {"session_token": "STALE"}},
        ])

    r = client.post("/api/v1/accounts/poll-claim",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={})
    assert r.status_code == 503  # contention exhausted (we treat stale as miss)
```

- [ ] **Step 2: Запустить тесты — оба должны упасть**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py::test_poll_claim_skips_account_with_stale_session tests/test_accounts_router.py::test_poll_claim_409_when_all_sessions_stale -v
```

Expected: оба FAIL — текущий код не фильтрует по `expires_at`, вернёт acc-1 со stale-токеном (status_code=200 вместо 503/200-acc-2).

- [ ] **Step 3: Реализовать predicate в `poll_claim`**

В `avito-xapi/src/routers/accounts.py` найти блок `sess_res = (sb.table("avito_sessions")...)` (строки 92-99) и заменить на:

```python
        # Liveness predicate: session must NOT be near-expiry. 5 min margin
        # covers polling tick + Avito network roundtrip — never serve a token
        # that's about to die mid-request.
        from datetime import timedelta
        fresh_threshold = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        sess_res = (
            sb.table("avito_sessions")
            .select("*")
            .eq("account_id", acc["id"])
            .eq("is_active", True)
            .gt("expires_at", fresh_threshold)
            .limit(1)
            .execute()
        )
        if not sess_res.data:
            # Account either has no active session OR session is stale.
            # Skip — try next LRU.
            continue
```

(Перенести `from datetime import timedelta` в top-level import: уже есть `from datetime import datetime, timezone`, заменить на `from datetime import datetime, timedelta, timezone`.)

- [ ] **Step 4: Запустить тесты — должны пройти**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py -v
```

Expected: оба новых теста PASS, существующие `test_poll_claim_picks_oldest_active` / `test_poll_claim_returns_409_when_pool_drained` тоже PASS.

Если existing test упал на отсутствии `expires_at` в его mock-session — добавить `"expires_at": "2026-05-08T00:00:00Z"` (далёкое будущее) в session-fixture внутри теста.

- [ ] **Step 5: Commit**

```bash
git add avito-xapi/src/routers/accounts.py avito-xapi/tests/test_accounts_router.py
git commit -m "fix(xapi): poll_claim skips accounts with stale sessions

Add expires_at > NOW()+5min predicate so claim never returns a token
that's already expired (or will expire mid-request). Solves the
'state=active but token dead' edge case where polling worker would
ping Avito with a guaranteed-401 token and burn retries.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Cooldown auto-recovery в `account_tick`

**Files:**
- Modify: `avito-monitor/app/services/health_checker/account_tick.py`
- Create: `avito-monitor/tests/services/test_account_tick.py`

**Что делаем.** `account_tick_iteration` крутится в health-checker'е каждые 30s (см. `account_loop.py`). Сейчас он только шлёт TG-alerts на stale-сессии. Расширяем: перед alert-блоком вызываем `_recover_expired_cooldowns(accounts, pool, now)`. Логика:

```
for acc in accounts:
    if acc.state == 'cooldown' and acc.cooldown_until < now:
        if acc.expires_at and acc.expires_at > now + 5min:
            pool.patch_state(acc.id, 'active', reason='cooldown expired, session fresh')
        else:
            pool.patch_state(acc.id, 'needs_refresh', reason='cooldown expired, session stale')
```

Это решит проблему `14acfef4` (cooldown_until истёк 2026-05-05 10:16, сессия валидна до 2026-05-07) автоматом в течение 30 секунд после деплоя.

- [ ] **Step 1: Создать failing tests**

Создать `avito-monitor/tests/services/test_account_tick.py`:

```python
"""Tests for cooldown auto-recovery in account_tick."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.health_checker.account_tick import account_tick_iteration


def _make_pool(accounts: list[dict]):
    pool = MagicMock()
    pool.list_all_accounts = AsyncMock(return_value=accounts)
    pool.patch_state = AsyncMock()
    return pool


@pytest.mark.asyncio
async def test_recovers_cooldown_with_fresh_session_to_active():
    """Cooldown expired AND session still fresh → patch_state('active')."""
    now = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
    fresh = (now + timedelta(hours=12)).isoformat()
    cooldown_past = (now - timedelta(hours=24)).isoformat()

    pool = _make_pool([
        {"id": "acc-x", "nickname": "auto-431483569", "android_user_id": 0,
         "state": "cooldown", "cooldown_until": cooldown_past,
         "expires_at": fresh, "consecutive_cooldowns": 1},
    ])
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    pool.patch_state.assert_awaited_once()
    args, kwargs = pool.patch_state.call_args
    assert args[0] == "acc-x"
    assert args[1] == "active"


@pytest.mark.asyncio
async def test_recovers_cooldown_with_stale_session_to_needs_refresh():
    """Cooldown expired AND session stale → patch_state('needs_refresh')."""
    now = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
    stale = (now - timedelta(minutes=1)).isoformat()
    cooldown_past = (now - timedelta(hours=1)).isoformat()

    pool = _make_pool([
        {"id": "acc-y", "nickname": "Clone", "android_user_id": 10,
         "state": "cooldown", "cooldown_until": cooldown_past,
         "expires_at": stale, "consecutive_cooldowns": 2},
    ])
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    pool.patch_state.assert_awaited_once()
    args, _ = pool.patch_state.call_args
    assert args[0] == "acc-y"
    assert args[1] == "needs_refresh"


@pytest.mark.asyncio
async def test_does_not_recover_active_cooldown():
    """Cooldown still in future → no state change."""
    now = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
    cooldown_future = (now + timedelta(minutes=20)).isoformat()
    fresh = (now + timedelta(hours=12)).isoformat()

    pool = _make_pool([
        {"id": "acc-z", "nickname": "n", "android_user_id": 0,
         "state": "cooldown", "cooldown_until": cooldown_future,
         "expires_at": fresh, "consecutive_cooldowns": 1},
    ])
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    pool.patch_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_does_not_touch_active_or_dead_accounts():
    """state in (active, dead, needs_refresh, waiting_refresh) → no recovery."""
    now = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
    fresh = (now + timedelta(hours=12)).isoformat()

    pool = _make_pool([
        {"id": "a", "nickname": "n", "android_user_id": 0, "state": "active",
         "expires_at": fresh, "consecutive_cooldowns": 0},
        {"id": "b", "nickname": "n", "android_user_id": 0, "state": "dead",
         "expires_at": None, "consecutive_cooldowns": 5},
    ])
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    pool.patch_state.assert_not_awaited()
```

Также обеспечить наличие `__init__.py` в `avito-monitor/tests/services/` (создать пустой файл если его нет).

- [ ] **Step 2: Запустить — все 4 теста должны упасть**

```bash
cd avito-monitor && pytest tests/services/test_account_tick.py -v
```

Expected: все 4 FAIL. Первый и второй — потому что `account_tick_iteration` не вызывает `patch_state`. Третий и четвёртый PASS теоретически (no patch_state) — но на текущем коде они тоже могут упасть если другие части `account_tick_iteration` падают на отсутствующих ключах в mock-аккаунтах. Если PASS — fine, движемся дальше.

- [ ] **Step 3: Реализовать `_recover_expired_cooldowns`**

В `avito-monitor/app/services/health_checker/account_tick.py` после функции `_is_session_stale` (строка 28) добавить:

```python
def _is_session_fresh(acc: dict, *, now: datetime) -> bool:
    """True iff session has expires_at > now+5min (mirrors xapi liveness predicate)."""
    from datetime import timedelta
    exp = _parse_ts(acc.get("expires_at"))
    return exp is not None and exp > now + timedelta(minutes=5)


async def _recover_expired_cooldowns(accounts: list[dict], *, pool, now: datetime) -> None:
    """Auto-rebloom: cooldown with cooldown_until in past gets nudged forward.

    - Fresh session → 'active' (account is usable again).
    - Stale session → 'needs_refresh' (session must be refreshed before active).
    Other states are not touched.
    """
    for acc in accounts:
        if acc.get("state") != "cooldown":
            continue
        cd_until = _parse_ts(acc.get("cooldown_until"))
        if cd_until is None or cd_until >= now:
            continue
        next_state = "active" if _is_session_fresh(acc, now=now) else "needs_refresh"
        await pool.patch_state(
            acc["id"],
            next_state,
            reason=f"cooldown expired at {cd_until.isoformat()}, session "
                   f"{'fresh' if next_state == 'active' else 'stale'}",
        )
        log.info(
            "account_tick.recovered id=%s nickname=%s -> %s",
            acc["id"], acc.get("nickname"), next_state,
        )
```

И вызвать его в `account_tick_iteration` перед `_check_pool_health`:

```python
async def account_tick_iteration(*, pool: AccountPool, now: datetime, tg) -> None:
    accounts = await pool.list_all_accounts()
    await _recover_expired_cooldowns(accounts, pool=pool, now=now)
    # Re-fetch — recovery may have flipped some states; alerts must see latest.
    accounts = await pool.list_all_accounts()
    await _check_pool_health(accounts, now=now, tg=tg)
```

Также в test_does_not_touch_active_or_dead_accounts ожидается что `list_all_accounts` зовётся 2 раза — поправить mock или тест:

В тестах добавить `pool.list_all_accounts.assert_awaited()` (любое число раз) либо использовать `MagicMock` без assert на call count.

(Текущие тесты используют `AsyncMock(return_value=accounts)` — повторный вызов вернёт тот же список, тесты остаются валидными.)

Сигнатура `pool.patch_state` — в `app/services/account_pool.py:63` — `async def patch_state(self, account_id: str, state: str, reason: str | None = None)`. Совпадает.

- [ ] **Step 4: Запустить — должны пройти**

```bash
cd avito-monitor && pytest tests/services/test_account_tick.py -v
```

Expected: все 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/services/health_checker/account_tick.py avito-monitor/tests/services/test_account_tick.py avito-monitor/tests/services/__init__.py
git commit -m "feat(monitor): cooldown auto-recovery in account_tick

Every 30s tick re-blooms accounts whose cooldown_until expired:
- fresh session -> state='active' (immediate reuse)
- stale session -> state='needs_refresh' (waits for APK push)

Solves the case where a 403 inflicted cooldown, session refreshed via
APK push during cooldown window, but state stayed stuck at 'cooldown'
forever. Pool effectively held a live token hostage.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Owner-aware claim для autosearch-based профилей

**Files:**
- Modify: `avito-xapi/src/routers/accounts.py:44-115` (extend `poll_claim` payload)
- Modify: `avito-xapi/tests/test_accounts_router.py` (+тесты)
- Modify: `avito-monitor/app/services/account_pool.py` (extend `claim_for_poll` signature)
- Modify: `avito-monitor/app/tasks/polling.py` (branch на autosearch-based профили)
- Modify: `avito-monitor/tests/test_polling.py` (+тесты)

**Что делаем.** Avito subscription_id принадлежит конкретному Avito-юзеру. Сейчас polling для autosearch-based профилей делает `pool.claim_for_poll()` (any active LRU) → если pool вернёт чужой аккаунт → 403 от Avito → `fetch_with_pool` retries следующим аккаунтом → опять 403 → и т.д. Дыра.

Расширяем `POST /api/v1/accounts/poll-claim`: payload теперь `{"account_id": "..."}` (опц.). Если задан → fast-path: проверить state=active, fresh session, CAS update last_polled_at, вернуть. Иначе старый round-robin.

В polling.py: если профиль autosearch-based → передаём `required_owner=str(profile.owner_account_id)`, max_attempts=1 (нет смысла ретраить — никто другой autosearch не достанет).

- [ ] **Step 1: Failing test для xapi — claim by account_id success**

В `avito-xapi/tests/test_accounts_router.py` после Task 1 тестов добавить:

```python
def test_poll_claim_by_account_id_succeeds_when_active_and_fresh(client, accounts_in_db):
    """payload.account_id pinned: returns that specific account if active+fresh."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    fresh_iso = (now + timedelta(hours=12)).isoformat()

    # 1) SELECT specific account by id.
    accounts_in_db([
        {"id": "acc-target", "state": "active", "last_polled_at": "2026-05-06T08:00:00Z",
         "phone_serial": "S9", "android_user_id": 0, "nickname": "target"},
    ])
    # 2) CAS update for acc-target — succeeds.
    accounts_in_db([
        {"id": "acc-target", "state": "active", "last_polled_at": "2026-05-06T12:30:00Z"},
    ])
    # 3) SELECT session — fresh.
    accounts_in_db([
        {"id": "sess-t", "account_id": "acc-target", "is_active": True,
         "expires_at": fresh_iso,
         "device_id": "tdev", "fingerprint": "tfp",
         "tokens": {"session_token": "TARGET_TOKEN"}},
    ])

    r = client.post("/api/v1/accounts/poll-claim",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"account_id": "acc-target"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] == "acc-target"
    assert body["session_token"] == "TARGET_TOKEN"


def test_poll_claim_by_account_id_409_when_not_active(client, accounts_in_db):
    """Pinned account in cooldown → 409 with diagnostic."""
    accounts_in_db([
        {"id": "acc-dead", "state": "dead", "nickname": "Clone"},
    ])

    r = client.post("/api/v1/accounts/poll-claim",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"account_id": "acc-dead"})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["error"] == "owner_unavailable"
    assert body["detail"]["account_id"] == "acc-dead"
    assert body["detail"]["state"] == "dead"


def test_poll_claim_by_account_id_409_when_session_stale(client, accounts_in_db):
    """Pinned account active but session stale → 409 owner_unavailable."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    stale_iso = (now + timedelta(minutes=1)).isoformat()

    # 1) SELECT acc-target.
    accounts_in_db([
        {"id": "acc-target", "state": "active",
         "last_polled_at": "2026-05-06T08:00:00Z", "nickname": "target"},
    ])
    # 2) CAS update succeeds.
    accounts_in_db([
        {"id": "acc-target", "state": "active",
         "last_polled_at": "2026-05-06T12:30:00Z"},
    ])
    # 3) SELECT session — stale (gt-filter empty).
    accounts_in_db([])

    r = client.post("/api/v1/accounts/poll-claim",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"account_id": "acc-target"})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["error"] == "owner_unavailable"
    assert body["detail"]["state"] == "session_stale"
```

- [ ] **Step 2: Запустить — все 3 теста должны упасть**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py -k "by_account_id" -v
```

Expected: 3 FAIL — payload.account_id игнорируется текущим кодом.

- [ ] **Step 3: Реализовать `account_id` branch в `poll_claim`**

В `avito-xapi/src/routers/accounts.py` заменить сигнатуру и тело `poll_claim`:

```python
class PollClaimPayload(BaseModel):
    account_id: str | None = None


@router.post("/poll-claim")
async def poll_claim(payload: PollClaimPayload | None = None):
    """Atomic claim of an active account.

    Two modes:
    1. Round-robin (payload omitted or account_id=None): LRU active +
       optimistic CAS on last_polled_at. Skips accounts with stale sessions.
    2. Pinned (payload.account_id set): claim a specific account, used by
       polling for autosearch-based profiles where the Avito subscription_id
       is owned by a specific Avito user — wrong owner = guaranteed 403.
       Returns 409 owner_unavailable if account is not active, has no session,
       or session is stale.
    """
    sb = get_supabase()
    payload = payload or PollClaimPayload()

    if payload.account_id is not None:
        return await _poll_claim_pinned(sb, payload.account_id)

    return await _poll_claim_lru(sb)


async def _poll_claim_pinned(sb, account_id: str):
    from datetime import timedelta

    res = sb.table("avito_accounts").select("*").eq("id", account_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, detail={"error": "owner_unavailable",
                                          "account_id": account_id,
                                          "state": "not_found"})
    acc = res.data[0]
    if acc["state"] != "active":
        raise HTTPException(409, detail={"error": "owner_unavailable",
                                          "account_id": account_id,
                                          "state": acc["state"]})

    # CAS to bump last_polled_at — same idempotency guarantee as LRU mode.
    old_polled = acc.get("last_polled_at")
    now_iso = datetime.now(timezone.utc).isoformat()
    upd = sb.table("avito_accounts").update({"last_polled_at": now_iso}).eq("id", acc["id"])
    if old_polled is None:
        upd = upd.is_("last_polled_at", None)
    else:
        upd = upd.eq("last_polled_at", old_polled)
    cas_res = upd.execute()
    if not cas_res.data:
        # Concurrent claim won — caller should retry next tick.
        raise HTTPException(503, detail="poll_claim concurrent contention, retry")

    fresh_threshold = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    sess_res = (
        sb.table("avito_sessions")
        .select("*")
        .eq("account_id", acc["id"])
        .eq("is_active", True)
        .gt("expires_at", fresh_threshold)
        .limit(1)
        .execute()
    )
    if not sess_res.data:
        raise HTTPException(409, detail={"error": "owner_unavailable",
                                          "account_id": account_id,
                                          "state": "session_stale"})

    s = sess_res.data[0]
    tokens = s.get("tokens") or {}
    return {
        "account_id": acc["id"],
        "session_token": tokens.get("session_token"),
        "device_id": s.get("device_id"),
        "fingerprint": s.get("fingerprint"),
        "phone_serial": acc.get("phone_serial"),
        "android_user_id": acc.get("android_user_id"),
    }


async def _poll_claim_lru(sb):
    """Original round-robin claim — extracted from old poll_claim body unchanged."""
    from datetime import timedelta

    for _ in range(_CLAIM_MAX_ATTEMPTS):
        lru_res = (
            sb.table("avito_accounts")
            .select("*")
            .eq("state", "active")
            .order("last_polled_at", nullsfirst=True)
            .limit(1)
            .execute()
        )
        if not lru_res.data:
            diag = (
                sb.table("avito_accounts")
                .select("nickname,state,cooldown_until,waiting_since")
                .execute()
            )
            raise HTTPException(
                status_code=409,
                detail={"error": "pool_drained", "accounts": diag.data or []},
            )

        acc = lru_res.data[0]
        old_polled = acc.get("last_polled_at")
        now_iso = datetime.now(timezone.utc).isoformat()

        upd = sb.table("avito_accounts").update({"last_polled_at": now_iso}).eq("id", acc["id"])
        if old_polled is None:
            upd = upd.is_("last_polled_at", None)
        else:
            upd = upd.eq("last_polled_at", old_polled)
        cas_res = upd.execute()

        if not cas_res.data:
            continue

        fresh_threshold = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        sess_res = (
            sb.table("avito_sessions")
            .select("*")
            .eq("account_id", acc["id"])
            .eq("is_active", True)
            .gt("expires_at", fresh_threshold)
            .limit(1)
            .execute()
        )
        if not sess_res.data:
            continue

        s = sess_res.data[0]
        tokens = s.get("tokens") or {}
        return {
            "account_id": acc["id"],
            "session_token": tokens.get("session_token"),
            "device_id": s.get("device_id"),
            "fingerprint": s.get("fingerprint"),
            "phone_serial": acc.get("phone_serial"),
            "android_user_id": acc.get("android_user_id"),
        }

    raise HTTPException(status_code=503, detail="poll_claim contention exhausted, retry")
```

NB: после этого Task 1 fresh-predicate уже встроен в `_poll_claim_lru` — и в `_poll_claim_pinned`. Тесты Task 1 продолжат работать (роутер код одинаков).

- [ ] **Step 4: Запустить все xapi-accounts тесты**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py -v
```

Expected: всё PASS, включая Task 1 + Task 3 тесты.

- [ ] **Step 5: Расширить `AccountPool.claim_for_poll`**

В `avito-monitor/app/services/account_pool.py:27-33` заменить:

```python
    @asynccontextmanager
    async def claim_for_poll(self, account_id: str | None = None):
        """Claim an account for polling.

        - account_id=None → round-robin LRU (default)
        - account_id set → pin to that specific account, raises NoAvailableAccountError
          if it's not active+fresh (Avito owner-binding for autosearch profiles).
        """
        body: dict = {}
        if account_id is not None:
            body["account_id"] = account_id
        resp = await self.xapi.post("/api/v1/accounts/poll-claim", json=body)
        if resp.status_code == 409:
            raise NoAvailableAccountError(resp.json().get("detail", {}))
        resp.raise_for_status()
        yield resp.json()
```

- [ ] **Step 6: Failing test для polling owner-binding**

В `avito-monitor/tests/test_polling.py` добавить (импорт уже есть):

```python
from contextlib import asynccontextmanager


@pytest.mark.asyncio
async def test_owner_binding_calls_pool_with_account_id():
    """fetch_with_pool with required_owner='X' passes account_id='X' into pool.claim_for_poll."""
    pool = MagicMock()
    pool.report = AsyncMock()
    captured: dict = {}

    @asynccontextmanager
    async def fake_claim(account_id=None):
        captured["account_id"] = account_id
        yield {"account_id": account_id or "fallback"}

    pool.claim_for_poll = fake_claim
    fetcher = AsyncMock(return_value={"items": []})

    result = await fetch_with_pool(
        fetcher_fn=fetcher, pool=pool, required_owner="acc-pinned"
    )

    assert result == {"items": []}
    assert captured["account_id"] == "acc-pinned"


@pytest.mark.asyncio
async def test_owner_binding_no_retry_on_403():
    """With required_owner set, 403 must NOT trigger retry — wrong owner = forever wrong."""
    pool = MagicMock()
    pool.report = AsyncMock()
    call_count = {"n": 0}

    @asynccontextmanager
    async def fake_claim(account_id=None):
        call_count["n"] += 1
        yield {"account_id": account_id}

    pool.claim_for_poll = fake_claim
    fetcher = AsyncMock(side_effect=XapiError("forbidden", status_code=403))

    with pytest.raises(XapiError) as excinfo:
        await fetch_with_pool(
            fetcher_fn=fetcher, pool=pool,
            required_owner="acc-x", max_attempts=2,
        )

    assert excinfo.value.status_code == 403
    # only one claim attempt — never retried with another account
    assert call_count["n"] == 1
    assert fetcher.await_count == 1
```

- [ ] **Step 7: Запустить — должны упасть**

```bash
cd avito-monitor && pytest tests/test_polling.py -k "owner_binding" -v
```

Expected: 2 FAIL — `fetch_with_pool` не принимает `required_owner` и не пробрасывает в `claim_for_poll`.

- [ ] **Step 8: Реализовать `required_owner` в `fetch_with_pool`**

В `avito-monitor/app/tasks/polling.py:179-223` заменить сигнатуру и логику ретрая:

```python
async def fetch_with_pool(
    *,
    fetcher_fn,
    pool: AccountPool,
    max_attempts: int = 2,
    required_owner: str | None = None,
):
    """Wraps fetcher_fn(account_claim) → result, with retry on 403/401/5xx.

    fetcher_fn receives the account claim dict and returns the fetch result,
    or raises XapiError on HTTP errors.

    required_owner: if set, every claim is pinned to this account_id (Avito
    autosearch ownership). 4xx errors are NOT retried — wrong owner can't
    fetch the subscription regardless of which token we try, so retry is
    pure noise. We still fall through to the raise at the bottom.

    Returns None if the pool is fully drained (NoAvailableAccountError on the
    very first claim attempt).  Re-raises the last XapiError once max_attempts
    are exhausted.

    After every attempt (success or failure) pool.report() is called so the
    xapi account state machine stays up to date.
    """
    last_error: Exception | None = None
    effective_attempts = 1 if required_owner else max_attempts
    for attempt in range(effective_attempts):
        try:
            async with pool.claim_for_poll(account_id=required_owner) as acc:
                try:
                    result = await fetcher_fn(acc)
                except XapiError as exc:
                    body = getattr(exc, "detail", None)
                    body_str = str(body) if body is not None else None
                    await pool.report(acc["account_id"], exc.status_code or 0, body_str)
                    if exc.status_code in (401, 403) and attempt < effective_attempts - 1:
                        last_error = exc
                        continue
                    if exc.status_code is not None and exc.status_code >= 500 and attempt < effective_attempts - 1:
                        last_error = exc
                        await asyncio.sleep(5)
                        continue
                    raise
                else:
                    await pool.report(acc["account_id"], 200)
                    return result
        except NoAvailableAccountError:
            log.warning("fetch_with_pool: pool drained — skipping (required_owner=%s)",
                        required_owner)
            return None
    if last_error is not None:
        raise last_error
    raise RuntimeError("fetch_with_pool exhausted without error")  # pragma: no cover
```

И в `poll_profile` (около строки 277) заменить вызов:

```python
    # --- fetch via account pool ---
    pool = get_account_pool()

    # Owner-binding for autosearch-based profiles: Avito subscription_id is
    # owned by a specific Avito user, so pinning the claim to that account is
    # mandatory (rotation across accounts can't recover from owner mismatch).
    required_owner: str | None = None
    if (
        profile.import_source == "autosearch_sync"
        and profile.avito_autosearch_id
        and profile.owner_account_id
    ):
        required_owner = str(profile.owner_account_id)

    async def _fetcher(acc: dict):
        async with AvitoMcpClient(account_id=acc["account_id"]) as mcp:
            if (
                profile.import_source == "autosearch_sync"
                and profile.avito_autosearch_id
            ):
                return await mcp.fetch_subscription_items(
                    int(profile.avito_autosearch_id)
                )
            return await mcp.fetch_search_page(profile.avito_search_url)

    try:
        page = await fetch_with_pool(
            fetcher_fn=_fetcher, pool=pool, required_owner=required_owner,
        )
    except Exception as exc:
        ...  # unchanged
```

Дополнительно: существующий test fixture `make_pool` в `test_polling.py` использует `claim_for_poll` без аргументов. Чтобы не сломать старые тесты — обновить fake:

```python
def make_pool(accounts: list[dict]):
    """Build a mock pool that yields the given accounts in order via claim_for_poll."""
    pool = MagicMock()
    pool.report = AsyncMock()
    queue = list(accounts)

    @asynccontextmanager
    async def fake_claim(account_id=None):
        if not queue:
            raise NoAvailableAccountError({"error": "pool_drained", "accounts": []})
        acc = queue.pop(0)
        yield acc

    pool.claim_for_poll = fake_claim
    return pool
```

- [ ] **Step 9: Запустить ВСЕ тесты polling**

```bash
cd avito-monitor && pytest tests/test_polling.py -v
```

Expected: все PASS, включая 5 старых + 2 новых owner-binding теста.

- [ ] **Step 10: Smoke test — собрать оба сервиса**

```bash
cd avito-xapi && python -c "from src.main import app; print('xapi import ok')"
cd ../avito-monitor && python -c "from app.tasks.polling import fetch_with_pool, poll_profile; print('monitor import ok')"
```

Expected: оба `import ok` без traceback.

- [ ] **Step 11: Commit**

```bash
git add avito-xapi/src/routers/accounts.py avito-xapi/tests/test_accounts_router.py avito-monitor/app/services/account_pool.py avito-monitor/app/tasks/polling.py avito-monitor/tests/test_polling.py
git commit -m "feat(pool): owner-aware claim for autosearch-based profiles

- xapi POST /accounts/poll-claim accepts optional payload.account_id
  to pin claim to a specific owner. Returns 409 owner_unavailable when
  pinned account is not active+fresh.
- monitor AccountPool.claim_for_poll(account_id=None) propagates.
- polling fetch_with_pool(required_owner=X) — for autosearch-based
  profiles, pins to profile.owner_account_id and disables retry: wrong
  Avito user can't fetch the subscription regardless of token.

Solves the case where 7 search_profiles owned by a dead account would
spam the pool with 403s and burn through all live tokens trying to
fetch autosearches that don't belong to them.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Финальная верификация

После всех 3 коммитов:

- [ ] **Запустить все тесты xapi и monitor**

```bash
cd avito-xapi && pytest tests/test_accounts_router.py -v
cd ../avito-monitor && pytest tests/services/test_account_tick.py tests/test_polling.py -v
```

Expected: всё PASS.

- [ ] **Деплой на VPS**

```bash
# 1. Sync xapi
cd avito-xapi && tar -czf - --exclude __pycache__ --exclude .git . | ssh root@81.200.119.132 'cd /opt/avito-system/repo/avito-xapi && tar -xzf -'
# 2. Sync monitor
cd ../avito-monitor && tar -czf - --exclude __pycache__ --exclude .git . | ssh root@81.200.119.132 'cd /opt/avito-system/repo/avito-monitor && tar -xzf -'
# 3. Rebuild + restart relevant services
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose build avito-xapi avito-monitor health-checker && docker compose up -d --force-recreate --no-deps avito-xapi avito-monitor health-checker'
```

- [ ] **Проверить что 14acfef4 ожил автоматом (через 30-60s после деплоя health-checker)**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose exec -T avito-monitor python -c "
import asyncio, os, asyncpg
async def main():
    url = os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\",\"postgresql://\")
    conn = await asyncpg.connect(url, statement_cache_size=0)
    r = await conn.fetchrow(\"SELECT state, cooldown_until FROM avito_accounts WHERE id=\$1\", \"14acfef4-c774-408e-a558-3927b4ac2c3b\")
    print(dict(r))
    await conn.close()
asyncio.run(main())
"'
```

Expected: `state='active'`. Если `state='needs_refresh'` — значит после Task 2 свежесть сессии оценилась как stale (вряд ли, expires_at 2026-05-07 > now+5min), либо `cooldown_until` уже nullified.

- [ ] **Health-checker logs — recovery должен залогироваться**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose logs --tail=200 health-checker | grep account_tick.recovered'
```

Expected: строка вида `account_tick.recovered id=14acfef4... -> active`.

---

## Что эта работа НЕ делает (out of scope)

- **Не пересоздаёт subscription_id для search_profiles owned by dead Clone.** После A+B+C polling для них корректно вернёт `owner_unavailable` и пометит ProfileRun=failed. Чтобы оживить эти 7 профилей — отдельная задача (либо warm-up `157920214` через Avito-app, либо пересоздать поиски под живым `431483569` через autosearch_sync).
- **Не меняет state machine** в `account_state.py`. Tick там по-прежнему cooldown→needs_refresh без учёта свежести. Recovery теперь живёт в health-checker'е, не в чистой state-машине.
- **Не вводит «pool warm-up» оповещение в TG**, когда `_poll_claim_pinned` отвечает 409. Health-checker scenario A/B уже отлавливает stale через свой механизм; добавлять отдельный canary избыточно.

---

## Self-review

**Spec coverage:**
- A (liveness predicate) → Task 1, 2 теста + код в `accounts.py`. ✅
- B (cooldown auto-recovery) → Task 2, 4 теста + код в `account_tick.py`. ✅
- C (owner-aware claim) → Task 3, 3 xapi-теста + 2 monitor-теста + код в xapi `accounts.py` + monitor `account_pool.py` + monitor `polling.py`. ✅

**Placeholder scan:** Все шаги содержат полный код, точные команды, ожидаемые результаты. Имена `_recover_expired_cooldowns`, `_poll_claim_pinned`, `_poll_claim_lru`, `required_owner` используются единообразно во всех таскахах.

**Type consistency:**
- `pool.patch_state(account_id: str, state: str, reason: str | None)` — sig неизменна, тесты Task 2 и существующий код совпадают.
- `claim_for_poll(account_id=None)` — Task 3 расширяет, Task 1/2 продолжают работать.
- `fetch_with_pool` keyword-only args — `required_owner` добавлен последним, не ломает существующих вызовов.
- `PollClaimPayload(account_id: str | None = None)` — body опциональный, старый клиент шлёт `{}` и получит LRU-режим как и раньше.
