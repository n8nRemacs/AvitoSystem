# Auth & Tokens Reference

**Компилировано:** 2026-04-28. **Refresh Hardening update:** 2026-04-30 (D.2/D.3/E/G/H/I).
**Manual refresh model:** 2026-05-02 (D.2/D.3 переписаны, refresh-cycle удалён).
**Server migration:** 2026-05-04 (E/G.3/I финал-cleanup, deploy на VPS 81.200.119.132 + Cloud Supabase Frankfurt).
**Pool state refresh:** 2026-05-06 (G.3 — pool drained, нужен manual login Avito-app в user_0 под 157920214).
**Источники:** AVITO-API.md Блок 1+8, token_farm_system.md, AvitoAll/API_AUTH.md,
  CONTINUE.md §3 + §8, DECISIONS.md, avito-xapi/src/routers/sessions.py,
  avito-xapi/src/routers/device_commands.py, avito-xapi/src/routers/accounts.py,
  avito-monitor/app/services/health_checker/account_tick.py,
  account-pool-design.md §2.1, refresh-hardening plan (DOCS/superpowers/plans/2026-04-30-refresh-hardening.md)

---

## A. JWT Session Token — структура

**Алгоритм:** HS512 (не HS256!)
**Время жизни:** ровно 24 часа (exp = iat + 86400)
**Хранение на устройстве:** SharedPreferences ключ `session`
**Хранение в нашей БД:** `avito_sessions.tokens.session_token`

Payload (декодированный пример):
```json
{
  "exp": 1770104756,
  "iat": 1770018356,
  "u": 157920214,          // Avito user_id (BIGINT)
  "p": 28109599,           // Avito profile_id
  "s": "dd1ce4a4ccfb4bb6bb24395a9546cade.1770018356",  // session hash
  "h": "NDZkMTc5NjljZTFi...",   // hash (base64)
  "d": "a8d7b75625458809", // device_id (= X-DeviceId header)
  "pl": "android",
  "extra": null
}
```

Декодирование без верификации (мы не знаем server-side secret):
```python
# avito-xapi/src/workers/jwt_parser.py
import base64, json
def decode_jwt_payload(token: str) -> dict:
    parts = token.split('.')
    payload = parts[1]
    payload += '=' * (4 - len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))
```

---

## B. Полная структура сессии

Все поля, которые мы храним в `avito_sessions.tokens` (Supabase JSONB):

```json
{
  "session_token": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "5c5b31d4b70e997ac188ad7723b395b4",   // 32-hex
  "device_id": "a8d7b75625458809",                        // 16-hex
  "fingerprint": "A2.a541fb18def1032c46e8ce9356bf78870fa9c764...",
  "remote_device_id": "kSCwY4Kj4HUfwZHG.dETo5G6mASWYj1o8WQV7G9AoYQm3OBc...android",
  "user_hash": "9b82afc1ab1e2419981f7a9d9d2b6af9",        // 32-hex
  "cookies": {
    "1f_uid": "uuid",
    "u": "string",
    "v": "timestamp"
  }
}
```

Где берётся каждое поле (SharedPreferences Avito-app):

| Поле | SharedPrefs ключ | Обязательное |
|---|---|---|
| `session_token` | `session` | да |
| `refresh_token` | `refresh_token` | нет (для справки) |
| `device_id` | `device_id` | да |
| `fingerprint` | `fpx` | да |
| `remote_device_id` | `remote_device_id` | нет |
| `user_hash` | `user_hash` | нет |
| cookies | `1f_uid`, `u_cookie`, `v_cookie` | нет |

Путь к SharedPrefs на устройстве:
`/data/user/{androidUserId}/com.avito.android/shared_prefs/com.avito.android_preferences.xml`

---

## C. Два разных "refresh_token" — важное разграничение

Источник: `account-pool-design.md §2.1`

| Термин | Где живёт | Кто использует |
|---|---|---|
| **Avito-app refresh_token** | SharedPreferences Avito-app в `/data/user/N/com.avito.android/...` | Avito-app сам, при `POST /token/refresh` к серверам Avito. Это путь обновления access_token. |
| **наш `tokens.refresh_token`** в `avito_sessions.tokens` | Supabase | Хранится для записи и debugging. **Сами не используем для refresh** — Avito-app делает всё со своей копией. |

Когда в документации написано «refresh_token мёртв» — речь об Avito-app копии. Полный logout Avito-сервера → Avito-app не может обновиться → нужен ручной re-login → `state=dead`.

---

## D. Session Lifecycle — от создания до смерти

### D.1 Получение новой сессии

1. Пользователь логинится в Avito-app (вручную, один раз)
2. Avito-app записывает JWT + fingerprint + device_id в SharedPreferences
3. AvitoSessionManager APK (com.avitobridge.sessionmanager) триггерится push-уведомлением о login/refresh
4. APK читает SharedPrefs через root (`su -c cat /data/user/N/...`)
5. APK POST `xapi /api/v1/sessions` — xapi деактивирует старые сессии аккаунта и вставляет новую

```python
# avito-xapi/src/routers/sessions.py:30-106 (upload_session)
# Деактивирует все is_active=true WHERE account_id=account.id
# INSERT новую строку с account_id FK
# Если account.state == 'waiting_refresh' → 'active', waiting_since=NULL
```

**ВАЖНО:** AvitoSessionManager **НЕ читает SharedPreferences самостоятельно при старте.** Он триггерится push-уведомлением. Если push пропущен (NL-доступ выдан после login) — нужен workaround: прямой `cat` SharedPreferences через root + POST на `/api/v1/sessions`.

Workaround-скрипт: `register_clone_session.py` (читает `/data/user/10/...`, парсит XML, POSTит в xapi).

### D.2 Health-checker (one-stale alerts only, no automatic refresh)

После Phase 4 (manual refresh model) `account_tick.py` НЕ триггерит refresh.
Раз в 30 сек проверяет всех аккаунтов и эмитит TG-alert один раз на переход
fresh → stale:

- 1 stale: «📩 Аккаунт X протух, polling на Y, обнови Avito-app в user_N»
- Все stale: «🚨 Polling DOWN, открой Avito-app на phone'е»

Stale = `expires_at IS NULL OR expires_at < NOW()`. Reset alert state когда
аккаунт снова становится fresh.

Источник: `avito-monitor/app/services/health_checker/account_tick.py`.

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

### D.4 APK long-poll protocol

Endpoint: `GET /api/v1/devices/me/commands?wait=60`

Статусы команды: `pending` → `delivered` → `done`/`failed`/`expired`

APK получает команду → `POST /api/v1/devices/me/commands/{id}/ack` с `{ok: true/false, error?, payload?}`

Источник: `avito-xapi/src/routers/device_commands.py`

---

## E. Account State Machine

```
                 (POST /sessions от APK после ручного refresh)
                      │
                      ▼
    ┌───────────────► active ◄──────────────┐
    │                  │                    │
    │              (403 report)         (POST /sessions
    │                  │                 после ручного refresh)
    │                  ▼                    │
    │              cooldown                 │
    │                  │                    │
    │              (TG-alert при            │
    │               expires_at < NOW)       │
    │                  │                    │
    │                  ▼                    │
    │                dead                   │
    │                  │                    │
    │       (юзер открыл Avito-app          │
    │        → APK поймал push              │
    │        → POST /sessions)              │
    └──────────────────┴────────────────────┘

active, expires_at < NOW → one-stale TG-alert (manual refresh model)
active, 401/403 на запросе → cooldown с ratchet
```

**Состояние `waiting_refresh`** в CHECK-constraint осталось от старой автоматической
схемы (refresh-cycle через ADB+APK long-poll). После manual refresh model 2026-05-02
оно больше не достигается runtime-кодом — поток теперь:
`active → cooldown` (на 403) → `dead` (ручное PATCH или soak без recovery) → 
`active` (когда APK POSTит свежий session_token).

Источники: `avito-xapi/src/services/account_state.py` (pure state-machine),
`avito-monitor/app/services/health_checker/account_tick.py` (runtime — only emits
TG alerts, never triggers refresh).

---

## F. Ban Detection — что знаем

**Эмпирически подтверждено:**
- Бан **per-account**, не per-IP. Юзер с того же IP, но другой аккаунт/устройство работал нормально; наш banned токен с любого IP не работал. Источник: `CONTINUE.md §3`
- Прецедент: burst 14 запросов на `/5/subscriptions` за 5 секунд → ban аккаунта. Источник: `CONTINUE.md §3`

**Cooldown ratchet:**
`20 мин → 40 мин → 80 мин → 160 мин → 24 ч + TG-alert`

Счётчик `consecutive_cooldowns` сбрасывается на первый успешный 200.

**Что означает 403 в response:**
- `state=active, 403` → `report(account_id, 403)` → `state=cooldown`
- Тело 403 сохраняется в `avito_accounts.last_403_body` (overwrite)

**Что означает 401:**
- Не cooldown — триггерит refresh path. `SET expires_at=NOW` → health_checker подхватывает на следующем tick'е

Источник: `account-pool-design.md §3.D2, §10`

---

## G. Multi-Account Pool

### G.1 DB Schema (avito_accounts)

```sql
-- Supabase migration 007_avito_accounts_pool.sql (создание),
-- migration 008_avito_accounts_multidevice.sql (UNIQUE → пара u+device).
CREATE TABLE avito_accounts (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nickname               TEXT NOT NULL,
    avito_user_id          BIGINT NOT NULL,
    last_device_id         TEXT,           -- Avito device_id для refresh-cmd
    phone_serial           TEXT NOT NULL DEFAULT '',   -- ADB serial телефона
    android_user_id        INTEGER NOT NULL DEFAULT 0,
    state                  TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active','cooldown','needs_refresh','waiting_refresh','dead')),
    cooldown_until         TIMESTAMPTZ,
    consecutive_cooldowns  INTEGER NOT NULL DEFAULT 0,
    last_polled_at         TIMESTAMPTZ,
    last_session_at        TIMESTAMPTZ,
    waiting_since          TIMESTAMPTZ,
    last_403_body          TEXT,
    last_403_at            TIMESTAMPTZ,
    UNIQUE (avito_user_id, last_device_id)   -- migration 008 (2026-04-30): multi-device per Avito-user
);
```

Источник: `account-pool-design.md §6.1` + `supabase/migrations/008_*` (Refresh Hardening).

### G.2 Polling — round-robin LRU

`POST /api/v1/accounts/poll-claim` → атомарно берёт аккаунт с наименьшим `last_polled_at`.
**Стратегия:** optimistic compare-and-swap на `last_polled_at` (PostgREST не имеет
`SELECT FOR UPDATE`). Алгоритм: SELECT LRU active row → UPDATE WHERE `last_polled_at`
совпадает с прочитанным → если 0 rows updated, другой worker нас обогнал, retry со
следующим LRU. До `_CLAIM_MAX_ATTEMPTS=3` попыток, иначе 503 contention exhausted.
Две одновременные claim-операции никогда не вернут один и тот же аккаунт.

Ответ: `{account_id, session_token, device_id, fingerprint, phone_serial, android_user_id}`.
При полностью дренированном pool: `409 {detail: {"error": "pool_drained", "accounts": [...]}}`.

После request: `POST /api/v1/accounts/{id}/report` с `{status_code: int, body_excerpt: str|null}`
— feed в state-machine `compute_next_state` (см. §E).

Альтернативный read-only claim (для autosearch_sync, не двигает `last_polled_at`):
`GET /api/v1/accounts/{id}/session-for-sync` → 200 / 404 / 409 (state≠active или no_session).

### G.3 Текущее состояние pool (2026-05-06)

| Аккаунт | Android-user | state | expires_at | live? |
|---|---|---|---|---|
| Clone (`42c179db…`) | user_10 | dead | 2026-05-01 18:27 UTC | -3д+ |
| auto-157920214 (`b5cbf28b…`) | user_0 | cooldown | 2026-05-05 11:32 UTC | exp |
| auto-431483569 (`14ac…`) | user_0 | cooldown | 2026-05-05 15:08 UTC | exp |

Pool merged (`8e12434`, 2026-04-29) → Refresh Hardening (`5bc72d3`, 2026-04-30) →
**Server Migration** (feat/server-migration, 2026-05-04) — manual refresh model, VPS
deploy, Cloud Supabase. На 2026-05-06 pool полностью drained — **live polling не
работает**. Все 7 search_profiles `owner_account_id=42c179db` (Clone, dead) — autosearch_sync
импортировал их под этим аккаунтом. При попытке fetch через нового `431483569` Avito
возвращает 403 на `/subscriptions/{id}/items` — autosearch принадлежит старому Clone.

**Чтобы оживить:** юзер открывает Avito-app в user_0 под `157920214` (старый Clone)
→ Avito-app сам решит refresh near-expiry → APK NotificationListener поймает push
→ POST `/api/v1/sessions` → `b5cbf28b` перейдёт в `state=active`.

**Pool=1 фактически:** Main и Clone — один Avito-юзер 157920214 на разных device_id.
Per-account ban валит оба. Реальный pool=2 требует второго Avito-юзера (см. backlog #3
в `CONTINUE.md`). На user_0 сейчас активен залогиненный `431483569` (новый Avito-юзер,
не старый Clone), но autosearches принадлежат `157920214` → 403.

**Round-robin LRU реализован** в `POST /api/v1/accounts/poll-claim` (CAS на
`last_polled_at`, optimistic compare-and-swap, 3 retry attempts, 409 при `pool_drained`).

### G.4 Добавление нового аккаунта

```sql
UPDATE avito_accounts SET nickname='Clone',
    android_user_id=10, phone_serial='110139ce'
    WHERE avito_user_id=<clone-user-id>;
```

При добавлении 2-го физического телефона: подключить USB → `adb devices` показывает оба → задать `phone_serial` нового аккаунта на новый serial. Никаких code-changes.

Источник: `account-pool-design.md §6.1`

---

## H. POST /api/v1/sessions — поведение

Деактивирует все прежние active sessions **того же account_id** (pool-aware, после
migration 007). `tenant_id` сохраняется в строке как legacy-поле для backward-compat,
но deactivation делается по `account_id`.

```python
# avito-xapi/src/routers/sessions.py:30-106 (upload_session)
account = resolve_or_create_account(sb, avito_user_id=payload.u, device_id=body.device_id)
sb.table("avito_sessions").update({"is_active": False}) \
    .eq("account_id", account["id"]).eq("is_active", True).execute()
sb.table("avito_sessions").insert({"account_id": account["id"], ...}).execute()
if account.get("state") == "waiting_refresh":
    sb.table("avito_accounts").update({
        "state": "active", "waiting_since": None,
        "last_session_at": NOW
    }).eq("id", account["id"]).execute()
```

`resolve_or_create_account` после migration 008 ключует по паре `(avito_user_id, device_id)`
— разные device_id одного `u` дают разные pool rows.

---

## I. avito-monitor — AccountPool client

`avito-monitor/app/services/account_pool.py` — тонкая обёртка над xapi `/api/v1/accounts/*`.
Методы:

```python
class AccountPool:
    @asynccontextmanager
    async def claim_for_poll(self):
        # POST /api/v1/accounts/poll-claim → 409 NoAvailableAccountError при pool_drained

    async def report(self, account_id: str, status_code: int, body=None):
        # POST /api/v1/accounts/{id}/report — feed status_code в state-machine

    async def claim_for_sync(self, account_id: str) -> dict:
        # GET /api/v1/accounts/{id}/session-for-sync — read-only, не двигает last_polled_at;
        # для autosearch_sync (owner-specific, не должен конкурировать с round-robin)

    async def list_active_accounts(self) -> list[dict]:
    async def list_all_accounts(self) -> list[dict]:
        # GET /api/v1/accounts (с expires_at per row)

    async def patch_state(self, account_id: str, state: str, reason: str | None):
        # PATCH /api/v1/accounts/{id}/state — manual transition (используется для → dead)
```
