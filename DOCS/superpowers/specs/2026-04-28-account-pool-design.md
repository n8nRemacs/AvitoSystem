# Avito Account Pool — Design Spec

**Дата:** 2026-04-28
**Статус:** Design approved, ready for implementation plan
**Связанные документы:** `CONTINUE.md` §1 хвосты #13/#14/#15, `DOCS/DECISIONS.md` ADR-011

---

## 1. Цель

Pool из N (сейчас 2) Avito-аккаунтов с round-robin распределением polling-нагрузки, автоматическим переходом в cooldown при бане одного из аккаунтов, и автоматическим refresh токенов через AvitoSessionManager APK + ADB-управляемое переключение Android-юзеров.

Сейчас система работает как pool-of-1: `xapi.session_reader` берёт `MAX(created_at) WHERE is_active=true`, любой ban токена → пауза всей системы. Цель — сделать систему устойчивой к временным банам отдельных аккаунтов и к expiry токенов.

## 2. Non-goals (V1)

- Multi-tenancy. Single-user/single-tenant система.
- Автоматический re-login после полного logout (когда `refresh_token` тоже мёртв) — оставляем как `state=dead` + ручной TG-alert.
- ADB-reconnection daemon — рассчитываем на стабильный USB-кабель.
- "Карусель прогрева" NL (периодическое переключение foreground без необходимости) — V1.5+.
- Capture polling rate-limit-aware retry (уже работает в xapi `rate_limiter`).
- Multi-host worker'ы / distributed locks — у нас один worker process в одном LXC.
- V2 messenger'ный flow (общение по объявлениям) — owner_account_id уже в схеме, но используется только sync'ом.

## 2.1 — Терминология

В этом спеке два разных «refresh_token» — важно различать:

| Термин | Где живёт | Кто использует |
|---|---|---|
| **Avito-app refresh_token** | SharedPreferences Avito-app в `/data/user/N/com.avito.android/...` | Avito-app сам, при `POST /token/refresh` к Avito-серверам. Это и есть путь которым обновляется access_token после bans. |
| **наш `tokens.refresh_token`** в `avito_sessions.tokens` | Supabase | Хранится для записи и manual debugging. **Сами не используем для refresh** — Avito-app всё делает сам со своей копией. |

Когда в спеке написано «refresh_token мёртв» — речь об Avito-app копии. Полный logout Avito-сервера → Avito-app не может обновиться → нужен ручной re-login (`state=dead`).

## 3. Принятые решения

| # | Вопрос | Решение |
|---|---|---|
| D1 | Scope pool | N (2-5), сейчас фактически 2; UI read-only в `/settings/accounts` |
| D2 | Что считать «баном» | Голый факт: 403 от Avito → cooldown, тело в лог. Остальное (401/5xx/network) НЕ cooldown |
| D3 | Cooldown ratchet | 20м → 40м → 80м → 160м → 24ч + TG-alert; счётчик сбрасывается на 200 |
| D4 | После cooldown | Обязательный refresh (токен протух — эмпирически подтверждено), не возврат в active напрямую |
| D5 | Refresh triggers | 3 триггера: proactive (expires_at < NOW+3m), reactive (401), post-cooldown |
| D6 | Polling distribution | Free-floating round-robin LRU между active accounts (owner-агностично) |
| D7 | Sync autosearches | Per-account loop: каждый pull'ит свои `/5/subscriptions`, search_profiles.owner_account_id (для V2 messenger'а) |
| D8 | Identity ladder | Avito user_id (BIGINT) → одна row в `avito_accounts`. Multiple history sessions FK на account |
| D9 | DB scheme | Подход 1 — отдельная таблица `avito_accounts`, sessions ссылается через `account_id` FK |
| D10 | ADB transport | USB-кабель напрямую в homelab + LXC passthrough (★★★★★ надёжность) |
| D11 | Frozen-NL fix | `device_switcher` через ADB перед refresh-командой (`am switch-user N`, ждём 8 сек, NL прогревается) |
| D12 | Multi-tenant | OUT — single-tenant, `tenant_id` остаётся как legacy в `avito_sessions`, новой логикой игнорируется |
| D13 | `android_user_id` provisioning | Manual SQL UPDATE после регистрации сессии (5 сек работы на аккаунт). APK auto-detect — V1.5+ |
| D14 | `last_403_body` storage | Один TEXT-поле, overwrite-only. Аналитика по статистике банов — V1.5+ |

## 4. Architecture overview

```
┌──────────────────────────────────────────────────────────────┐
│ avito-xapi (LXC, USB passthrough к OnePlus 8T)                │
│  ┌─────────────────────┐    ┌────────────────────────────┐   │
│  │ avito_accounts      │ ←─ │ avito_sessions             │   │
│  │  • state            │ FK │  • account_id (NEW)        │   │
│  │  • cooldown_until   │    │  • is_active (per-account) │   │
│  │  • last_polled_at   │    │  • tokens, expires_at      │   │
│  │  • android_user_id  │    └────────────────────────────┘   │
│  │  • last_device_id   │                                      │
│  │  • last_403_body    │                                      │
│  └─────────────────────┘                                      │
│                                                               │
│  Новые эндпойнты для monitor:                                 │
│   POST /api/v1/accounts/poll-claim                            │
│   POST /api/v1/accounts/{id}/report                           │
│   GET  /api/v1/accounts                                       │
│   GET  /api/v1/accounts/{id}/session-for-sync                 │
│                                                               │
│  health_checker (расширен):                                   │
│   • account.state=cooldown ∧ expired → needs_refresh          │
│   • state=active ∧ expires_at < NOW+3m → refresh path         │
│   • state=waiting_refresh > 5m → dead + TG-alert              │
│                                                               │
│  device_switcher (новый):                                     │
│   • adb shell am switch-user N (singleton asyncio.Lock)       │
│   • adb get-state, adb shell am get-current-user              │
│                                                               │
│  Изменения в POST /sessions:                                  │
│   • resolve_or_create_account(payload.user_id, device_id)     │
│   • deactivation скоупим до account_id (не tenant_id)         │
│   • account.state=waiting_refresh → 'active' атомарно         │
└──────────────────────────────────────────────────────────────┘
                       ↑ HTTP X-Api-Key
                       │
┌──────────────────────────────────────────────────────────────┐
│ avito-monitor (отдельная Postgres)                            │
│                                                               │
│  AccountPool client (тонкий, ~150 строк):                     │
│    async with pool.claim_for_poll() as acc:                   │
│        result = await xapi.fetch(...)                          │
│        await pool.report(acc.id, result.status)               │
│                                                               │
│  scheduler.py — без изменений                                 │
│  polling.py — оборачивает fetch в claim_for_poll              │
│  autosearch_sync.py — итерирует по pool.list_active_accounts  │
│  search_profiles.owner_account_id (UUID, no FK, cross-DB)     │
│  /settings/accounts — read-only таблица состояний             │
└──────────────────────────────────────────────────────────────┘
```

## 5. State machine аккаунта

```
                  (POST /sessions)
                       │
                       ▼
     ┌────────────────► active ◄───────────────┐
     │                  │                       │
     │              (403 report)             (POST /sessions
     │                  │                    после refresh)
     │                  ▼                       │
     │              cooldown                    │
     │                  │                       │
     │           (cooldown_until < NOW)         │
     │                  ▼                       │
     │             needs_refresh                │
     │                  │                       │
     │     (device_switch + send refresh cmd)   │
     │                  │                       │
     │                  ▼                       │
     │           waiting_refresh ───────────────┘
     │                  │
     │             (5 min timeout)
     │                  ▼
     │                dead
     │                  │
     │       (manual: TG-alert,
     │        user открыл Android-user
     │        вручную)
     └──────────── (POST /sessions
                    через ручной разогрев)

Также: state=active, expires_at < NOW+3min → waiting_refresh (proactive)
       state=active, 401 на запросе → waiting_refresh (reactive fallback)
```

## 6. DB schema

### 6.1 — Supabase migration 0005

```sql
CREATE TABLE avito_accounts (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nickname               TEXT NOT NULL,
    avito_user_id          BIGINT NOT NULL,
    last_device_id         TEXT,
    android_user_id        INTEGER NOT NULL DEFAULT 0,
    state                  TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active','cooldown','needs_refresh',
                         'waiting_refresh','dead')),
    cooldown_until         TIMESTAMPTZ,
    consecutive_cooldowns  INTEGER NOT NULL DEFAULT 0,
    last_polled_at         TIMESTAMPTZ,
    last_session_at        TIMESTAMPTZ,
    waiting_since          TIMESTAMPTZ,        -- старт waiting_refresh
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

DROP INDEX idx_avito_sessions_active;
CREATE INDEX idx_avito_sessions_active_per_account
    ON avito_sessions (account_id, is_active) WHERE is_active = true;

-- Migration данных (one-shot)
DO $$ DECLARE r RECORD; new_acc UUID; BEGIN
    FOR r IN (SELECT DISTINCT user_id FROM avito_sessions
              WHERE user_id IS NOT NULL) LOOP
        INSERT INTO avito_accounts (avito_user_id, nickname, state)
            VALUES (r.user_id, 'auto-' || r.user_id, 'active')
            RETURNING id INTO new_acc;
        UPDATE avito_sessions SET account_id = new_acc
            WHERE user_id = r.user_id;
    END LOOP;
END $$;
```

После migration — два ручных UPDATE для known аккаунтов. Сначала смотрим что
авто-создалось:
```sql
SELECT id, avito_user_id, nickname, state FROM avito_accounts;
-- → берём avito_user_id у clone (active) и main (banned)
```
Затем:
```sql
UPDATE avito_accounts SET nickname='Clone',
                          android_user_id=10
    WHERE avito_user_id=<clone-user-id>;
UPDATE avito_accounts SET nickname='Main',
                          android_user_id=0,
                          state='dead'   -- сейчас banned
    WHERE avito_user_id=<main-user-id>;
```

### 6.2 — avito-monitor migration Alembic 0005

```sql
ALTER TABLE search_profiles ADD COLUMN owner_account_id UUID;
-- БЕЗ FK constraint — Supabase в другой БД
CREATE INDEX idx_search_profiles_owner
    ON search_profiles (owner_account_id) WHERE archived_at IS NULL;

-- Backfill: все существующие профили → clone-account
UPDATE search_profiles SET owner_account_id = '<clone-account-uuid>';
```

## 7. Компоненты и interfaces

### 7.1 — `avito-xapi/src/routers/accounts.py` (новый)

```python
GET  /api/v1/accounts
  → list[{id, nickname, state, cooldown_until, last_polled_at,
          consecutive_cooldowns, expires_at, android_user_id}]

POST /api/v1/accounts/poll-claim   body: {}
  → 200 {account_id, session_token, device_id, fingerprint, ...}
  → 409 {error: "pool_drained", earliest_recovery: ts,
         accounts: [{nickname, state, until|since}]}
  Транзакция:
    BEGIN;
    SELECT * FROM avito_accounts WHERE state='active'
      ORDER BY last_polled_at NULLS FIRST LIMIT 1
      FOR UPDATE SKIP LOCKED;
    UPDATE avito_accounts SET last_polled_at=NOW WHERE id=...;
    COMMIT;

POST /api/v1/accounts/{id}/report   body: {status_code, body_excerpt?}
  status=200 → consecutive_cooldowns=0, last_403_*=NULL
  status=403 → state='cooldown',
               cooldown_until = NOW + ratchet(consecutive_cooldowns),
               consecutive_cooldowns += 1,
               last_403_body=body[:1024], last_403_at=NOW;
               consecutive ≥ 5 → TG-alert «account 24h»
  status=401 → flag в БД: SET expires_at = NOW (форсирует health_checker
               подхватить acc на следующем 30-сек tick'е и запустить
               refresh path как для proactive). Не cooldown.
  иное → no-op

GET  /api/v1/accounts/{id}/session-for-sync
  → 200 {session_token, ...}  если state='active'
  → 409 {state: ...}            иначе
```

### 7.2 — `avito-xapi/src/routers/sessions.py` — изменения

```diff
  POST /api/v1/sessions:
- # Деактивирует все active в тенанте
- sb.table("avito_sessions").update({"is_active": False})
-     .eq("tenant_id", ctx.tenant.id).eq("is_active", True).execute()

+ account = resolve_or_create_account(payload.user_id, payload.device_id)
+ sb.table("avito_sessions").update({"is_active": False})
+     .eq("account_id", account.id).eq("is_active", True).execute()
+ sb.table("avito_sessions").insert({
+     "account_id": account.id, ...
+ }).execute()
+ if account.state == 'waiting_refresh':
+     sb.table("avito_accounts").update({
+         "state": "active", "waiting_since": None,
+         "last_session_at": NOW
+     }).eq("id", account.id).execute()
```

### 7.3 — `avito-xapi/src/workers/session_reader.py`

```diff
+ async def load_session_for_account(account_id: UUID) -> SessionData | None:
+     """Используется для всех новых pool-aware вызовов."""
+     ...

  async def load_active_session(tenant_id: str) -> SessionData | None:
-     # Старая логика MAX(created_at) WHERE is_active=true
+     # DEPRECATED: thin wrapper для существующих не-pool эндпойнтов
+     # (search/items без account_id). Возвращает любую active session
+     # любого active account.
      ...
```

### 7.4 — `avito-xapi/src/workers/health_checker.py` — расширение

```python
async def health_loop():
    while True:
        accounts = await db.fetch_accounts_needing_attention()
        # WHERE state='active' AND expires_at < NOW+3min
        # OR (state='cooldown' AND cooldown_until < NOW)
        # OR (state='waiting_refresh' AND waiting_since < NOW-5min)

        for acc in accounts:
            await process_account(acc)
        await asyncio.sleep(30)


async def process_account(acc):
    # cooldown expired → needs_refresh (токен протух)
    if acc.state == 'cooldown' and acc.cooldown_until < now():
        await db.update_account(acc.id, state='needs_refresh')
        acc.state = 'needs_refresh'

    # active/needs_refresh с expiry < 3m → запускаем refresh path
    if acc.state in ('active', 'needs_refresh') and \
       (acc.expires_at < now() + timedelta(minutes=3) or acc.state == 'needs_refresh'):

        if not await device_switcher.health():
            await tg_alert("ADB-канал отвалился")
            return

        await device_switcher.switch_to(acc.android_user_id)
        await asyncio.sleep(8)

        await create_refresh_command(acc.last_device_id)
        await db.update_account(acc.id,
            state='waiting_refresh',
            waiting_since=now())

    # waiting timeout → dead
    if acc.state == 'waiting_refresh' and \
       acc.waiting_since < now() - timedelta(minutes=5):
        await db.update_account(acc.id, state='dead')
        await tg_alert(
            f"Account {acc.nickname} (Android-user {acc.android_user_id}) "
            f"не получил refresh за 5 минут. Открой вручную или проверь APK."
        )
```

### 7.5 — `avito-xapi/src/workers/device_switcher.py` (новый)

```python
class DeviceSwitcher:
    _lock = asyncio.Lock()

    async def current_user(self) -> int:
        # adb shell am get-current-user

    async def switch_to(self, target: int) -> None:
        async with self._lock:
            if await self.current_user() == target:
                return
            # adb shell am switch-user {target}
            # ждать current_user() == target до 5 сек
            # raises DeviceSwitchError при таймауте

    async def health(self) -> bool:
        # adb get-state == 'device'
```

ADB-сервер запускается в LXC контейнере как fork-процесс при старте xapi:
```bash
adb start-server
```

LXC config (Proxmox): cgroup devices.allow для USB-узла + bind-mount `/dev/bus/usb`.

### 7.6 — `avito-monitor/app/services/account_pool.py` (новый)

```python
class AccountPool:
    def __init__(self, xapi_client): ...

    @asynccontextmanager
    async def claim_for_poll(self):
        resp = await self.xapi.post('/accounts/poll-claim')
        if resp.status_code == 409:
            raise NoAvailableAccountError(resp.json())
        try:
            yield resp.json()
        finally:
            pass  # report() вызывается явно

    async def report(self, account_id: str, status_code: int,
                     body: str | None = None):
        await self.xapi.post(f'/accounts/{account_id}/report',
            json={'status_code': status_code,
                  'body_excerpt': (body or '')[:1024] or None})

    async def claim_for_sync(self, account_id: str):
        resp = await self.xapi.get(f'/accounts/{account_id}/session-for-sync')
        if resp.status_code == 409:
            raise AccountNotAvailableError(account_id, resp.json()['state'])
        return resp.json()

    async def list_active_accounts(self) -> list[Account]:
        resp = await self.xapi.get('/accounts')
        return [a for a in resp.json() if a['state'] == 'active']
```

### 7.7 — `avito-monitor/app/tasks/polling.py:174-237`

```python
async def fetch_with_pool(profile, mcp):
    for attempt in range(2):  # one retry для 403/401 (другим account); 5xx (тем же)
        try:
            async with pool.claim_for_poll() as acc:
                try:
                    result = await mcp.fetch_subscription_items(
                        profile.avito_autosearch_id,
                        account_id=acc['account_id'])
                except XapiError as e:
                    await pool.report(acc['account_id'], e.status_code, e.body)
                    if e.status_code in (403, 401) and attempt == 0:
                        continue  # retry с другим account
                    if e.status_code >= 500 and attempt == 0:
                        await asyncio.sleep(5)
                        continue  # retry с тем же account (он не виноват)
                    raise
                else:
                    await pool.report(acc['account_id'], 200)
                    return result
        except NoAvailableAccountError:
            log.warning("pool drained, profile_run skipped")
            return None

    return None
```

### 7.8 — `avito-monitor/app/services/autosearch_sync.py:46-78`

```python
async def sync_all_autosearches():
    for acc in await pool.list_active_accounts():
        try:
            session = await pool.claim_for_sync(acc.id)
        except AccountNotAvailableError as e:
            log.info("skip sync", account=acc.nickname, state=e.state)
            continue
        await sync_for_account(acc, session)


async def sync_for_account(acc, session):
    autosearches = await xapi.list_subscriptions(account_id=acc.id)
    for autosearch in autosearches:
        await upsert_search_profile(autosearch, owner_account_id=acc.id)
        await asyncio.sleep(_PER_ITEM_SLEEP_SEC)
```

### 7.9 — UI `/settings/accounts` (read-only)

`avito-monitor/app/web/templates/settings/accounts.html`:

| Столбец | Источник |
|---|---|
| Nickname | `accounts.nickname` |
| Android-user | `accounts.android_user_id` |
| State (badge) | active 🟢 / cooldown 🟡 / needs_refresh 🟠 / waiting_refresh 🔵 / dead 🔴 |
| Cooldown until | `accounts.cooldown_until` (relative) |
| Last polled | `accounts.last_polled_at` (relative) |
| Consecutive cooldowns | `accounts.consecutive_cooldowns` |
| Last 403 body | если есть, expandable |

Endpoint в `routers.py`: `GET /settings/accounts` → render template, данные из `pool.list_active_accounts()` + аналогичный `list_all_accounts()` (включая cooldown/dead).

Действий нет.

## 8. Data flows (5 ключевых сценариев)

### 8.1 — Polling tick happy path

```
scheduler.tick → polling.poll_profile
  └─ claim_for_poll → xapi atomic claim (LRU) → account A
     └─ fetch_subscription_items(filter, A.id) → 200
        └─ report(A.id, 200) → reset counters
profile_run.success
```

### 8.2 — Ban detection

```
poll → A → 403 → report(A, 403, body) → A.state=cooldown(20m)
  └─ retry (attempt 1) → claim → SKIP A (state≠active) → account B
     └─ fetch via B → 200 → report(B, 200)
profile_run.success

Если B тоже 403 → pool drained → profile_run.skipped_no_account
```

### 8.3 — Post-cooldown refresh

```
health_checker tick (каждые 30с):
  A.state=cooldown, A.cooldown_until < NOW
  └─ A.state ← needs_refresh
     └─ device_switcher.switch_to(A.android_user_id) [+8s sleep]
        └─ create_refresh_command(A.last_device_id)
           └─ A.state ← waiting_refresh, waiting_since=NOW

[в Android-user N foreground]
AvitoSessionManager APK A долгопулит → получает cmd
  └─ открывает Avito-app A intent
     └─ Avito-app A: POST Avito /token/refresh
        └─ новый JWT в SharedPrefs
           └─ APK A POST xapi /api/v1/sessions
              └─ resolve_or_create_account → A
                 └─ deactivate old sessions WHERE account_id=A.id
                    └─ insert new session
                       └─ A.state ← active

next polling tick → claim берёт A снова в LRU.
```

### 8.4 — Proactive refresh (без bans)

```
health_checker:
  A.state=active, A.expires_at < NOW+3m
  └─ device_switcher.switch_to(A.android_user_id) [+8s]
     └─ create_refresh_command
        └─ A.state ← waiting_refresh

(дальше как 8.3 от шага «APK A ловит cmd»)
```

### 8.5 — Sync autosearches

```
autosearch_sync.sync_all_autosearches():
  for acc in pool.list_active_accounts():
    session = pool.claim_for_sync(acc.id)  # 409 если cooldown — skip
    autosearches = xapi.list_subscriptions(account_id=acc.id)
    for a in autosearches:
        upsert search_profiles.owner_account_id=acc.id
        sleep(2s)
```

Sync **не блокирует** polling — claim_for_sync читает session, но не помечает account «занятым». Polling параллельно может идти через тот же account.

## 9. Concurrency / locks

| Race | Защита |
|---|---|
| Двое workers `poll-claim` одновременно | `SELECT … FOR UPDATE SKIP LOCKED` в БД |
| `device_switcher.switch_to` параллельно | Singleton `asyncio.Lock` в DeviceSwitcher |
| `report(403)` приходит после `health_checker` уже перевёл state | UPDATE `WHERE id=X` (last-write-wins) — допустимо |
| POST /sessions в момент `waiting_refresh` | Атомарный UPDATE `state='active' WHERE id=X` рядом с INSERT session |

## 10. Error handling matrix

| Класс ошибки | Behaviour |
|---|---|
| Avito 200 | success, reset counters |
| Avito 403 | report → cooldown (ratchet), one retry с другим acc |
| Avito 401 | report (no state change), retry; параллельно triggers refresh path |
| Avito 429 | xapi rate_limiter handles, прозрачно |
| Avito 5xx | one retry с тем же acc через 5с; если опять 5xx → run.failed |
| Avito network/timeout | retry с тем же acc; run.failed если повторно |
| ADB не отвечает | TG-alert «ADB-канал отвалился», refresh откладывается до починки |
| switch-user timeout 5s | retry один раз; 3 подряд fail'а → alert |
| APK не сделал ack за 5 мин | state=dead + TG-alert «открой Android-user X вручную» |
| Avito refresh_token мёртв | APK не делает POST /sessions → 5min timeout → dead path |
| Новый токен сразу 403 | normal cooldown ratchet (consecutive не сбрасывается, потому что не было 200) |
| Pool drained (все cooldown) | poll-claim 409, profile_run.skipped_no_account; one-shot TG-alert при transition «всё мёртво» |
| Supabase 5xx | tenacity retry 3×2s в monitor; run.failed если все три |

## 11. Logging / observability

```json
{"event":"account.state_change","account":"Clone",
 "from":"active","to":"cooldown",
 "reason":"report_403","consecutive_cooldowns":1,
 "cooldown_until":"...","body_excerpt":"..."}
```

Метрики V1 — плотный structured лог (no Prometheus инфры на homelab пока).
Если позже поднимем — события уже структурированы и легко превратить в counter:
- `account_state_total{nickname,state}` — gauge
- `account_403_total{nickname}` — counter
- `account_refresh_total{nickname,outcome=success|timeout|dead}` — counter
- `account_pool_drained_total` — counter

Prometheus → Grafana — V1.5 расширение.

UI `/settings/accounts` + TG-уведомления — human-facing observability.

## 12. Testing

### 12.1 — Unit (mock'и допустимы)

- `DeviceSwitcher`: `switch_to` no-op когда уже там, retry, asyncio.Lock сериализация. Mock `subprocess.run`.
- `AccountPool` client: claim/report/sync 200/409 paths. Mock `httpx.MockTransport`.
- State machine как pure функция `compute_next_state(state, event) → state` — таблица unit-тестов.

### 12.2 — Integration (реальная test Postgres)

- `poll-claim` атомарность под параллельными запросами
- `POST /sessions` deactivation скоупится account_id, не tenant_id
- `POST /sessions` waiting_refresh → active transition атомарен
- `resolve_or_create_account` создаёт row для unknown user_id
- Migration 0005 idempotent
- 403 ratchet через 4 cycle'а: 20m → 40m → 80m → 160m → 24h+alert

### 12.3 — Health-checker timing (freezegun)

- cooldown expired → needs_refresh
- waiting_refresh > 5 мин → dead + TG-alert (mock client)
- active expires_at < NOW+3min → refresh path

### 12.4 — E2E checklist (manual после deploy)

```
□ pool из 2 accounts, оба state=active в /settings/accounts
□ Polling tick'и round-robin между ними (logs: account_id чередуется)
□ Force cooldown одного → polling переключается на второй
□ cooldown_until=NOW+30s → через минуту → needs_refresh →
   foreground переключился → APK получил cmd → POST /sessions →
   state=active → polling возобновился
□ Force state=dead → TG-alert приходит, в /settings/accounts → 🔴
□ Reboot worker'а → pool state восстанавливается из БД
□ Отключение USB → TG-alert «ADB-канал отвалился», pool продолжает на текущих токенах
□ Чиним 5 health_checker tests (русские vs английские строки) — попутно
```

### 12.5 — Не тестируем

- Реальные Avito-запросы в CI (не хотим ban'ы аккаунтов)
- Реальный adb в CI (нет hardware)
- Visual UI tests (smoke endpoint 200 достаточно)

## 13. Migration runbook

Порядок применения:

1. Применить Supabase migration 0005 (CREATE table + ALTER + DO $$ block + DROP/CREATE indexes).
2. Manual UPDATE: `nickname` и `android_user_id` для двух known аккаунтов.
3. Применить avito-monitor Alembic 0005 (ADD COLUMN owner_account_id + UPDATE backfill).
4. Deploy xapi с новыми эндпойнтами + расширенный health_checker + device_switcher.
5. LXC config: USB passthrough + проверить `adb get-state` из контейнера → `device`.
6. Deploy avito-monitor с AccountPool + изменения в polling/autosearch_sync + UI route.
7. Smoke test: одновременные polling tick'и → /settings/accounts показывает round-robin.
8. Manual E2E checklist (12.4).

Rollback: SQL `ALTER TABLE avito_sessions DROP COLUMN account_id; DROP TABLE avito_accounts;` + восстановить старый код xapi/monitor. Old `tenant_id`-based path в session_reader не удалён (deprecated wrapper) — система продолжит работать на pool-of-1.

## 14. Acceptance criteria

V1 этого спека считается завершённым, когда:

- [ ] Schema migrations применены, два known accounts видны в /settings/accounts с корректными nickname/android_user_id
- [ ] Polling tick'и round-robin'ятся между accounts (10 последовательных runs распределены ровно)
- [ ] Forced 403 на одном account → второй подхватывает в течение одного scheduler tick'а
- [ ] Forced cooldown → automatic refresh через device_switcher → state=active без ручного вмешательства (5 раз подряд успешно)
- [ ] APK timeout 5 мин → state=dead → TG-alert приходит
- [ ] ADB unplug → TG-alert приходит, polling продолжается на cached токенах
- [ ] Reboot всех контейнеров → pool восстанавливается, polling возобновляется автоматически
- [ ] Sync autosearches успешно тянет subscriptions от обоих accounts (после восстановления Main)

## 15. Возможные расширения (post-V1)

- ADB auto-reconnect daemon (systemd watchdog).
- "Карусель прогрева" NL — периодически переключать foreground между Android-юзерами.
- APK auto-detect `android_user_id` через `Process.myUserHandle()` → POST /sessions.
- Аналитика 403-bans: отдельная таблица `avito_403_log` для статистики.
- Multi-tenant: вернуть tenant_id, обновить UNIQUE constraints.
- V2 messenger flow использует `search_profiles.owner_account_id`.
- Metrics в Prometheus → Grafana dashboard.
