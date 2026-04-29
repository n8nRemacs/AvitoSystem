# Auth & Tokens Reference

**Компилировано:** 2026-04-28
**Источники:** AVITO-API.md Блок 1+8, token_farm_system.md, AvitoAll/API_AUTH.md,
  CONTINUE.md §3, DECISIONS.md, avito-xapi/src/routers/sessions.py,
  avito-xapi/src/routers/device_commands.py, account-pool-design.md §2.1

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
# avito-xapi/src/routers/sessions.py:46-73
# Деактивирует все is_active=true WHERE account_id=account.id
# INSERT новую строку с account_id FK
```

**ВАЖНО:** AvitoSessionManager **НЕ читает SharedPreferences самостоятельно при старте.** Он триггерится push-уведомлением. Если push пропущен (NL-доступ выдан после login) — нужен workaround: прямой `cat` SharedPreferences через root + POST на `/api/v1/sessions`.

Workaround-скрипт: `register_clone_session.py` (читает `/data/user/10/...`, парсит XML, POSTит в xapi).

### D.2 Health-checker (proactive refresh)

Запускается каждые 30 секунд. Обрабатывает аккаунты в трёх состояниях:

```
state=active, expires_at < NOW+3min → запуск refresh path
state=cooldown, cooldown_until < NOW → переводим в needs_refresh
state=waiting_refresh, waiting_since < NOW-5min → переводим в dead + TG-alert
```

Источник: `account-pool-design.md §7.4`

### D.3 Refresh Flow (полностью)

```
1. health_checker замечает expiry < 3 мин (или post-cooldown)
2. device_switcher.switch_to(phone_serial, android_user_id)   [+8 сек sleep]
3. POST xapi /api/v1/devices/me/commands  {"command": "refresh_token", ...}
4. account.state ← waiting_refresh, waiting_since = NOW

[На телефоне в Android-user N foreground:]
5. AvitoSessionManager APK long-poll GET /api/v1/devices/me/commands?wait=60
6. APK получает команду refresh_token
7. APK запускает Avito-app через intent
8. Avito-app: POST Avito /token/refresh с своим Avito-app refresh_token
9. Новый JWT записывается в SharedPreferences
10. APK (через NL push или прямое чтение) читает SharedPrefs
11. APK POST xapi /api/v1/sessions с новым токеном
12. resolve_or_create_account(payload.user_id) → account
13. deactivate old sessions WHERE account_id=account.id
14. INSERT new session
15. account.state ← active

Если шаг 11 не произошёл в течение 5 минут:
→ account.state ← dead → TG-alert "открой Android-user N вручную"
```

Источник: `account-pool-design.md §8.3`

### D.4 APK long-poll protocol

Endpoint: `GET /api/v1/devices/me/commands?wait=60`

Статусы команды: `pending` → `delivered` → `done`/`failed`/`expired`

APK получает команду → `POST /api/v1/devices/me/commands/{id}/ack` с `{ok: true/false, error?, payload?}`

Источник: `avito-xapi/src/routers/device_commands.py`

---

## E. Account State Machine

```
                 (POST /sessions)
                      │
                      ▼
    ┌───────────────► active ◄──────────────┐
    │                  │                    │
    │              (403 report)         (POST /sessions
    │                  │                 после refresh)
    │                  ▼                    │
    │              cooldown                 │
    │                  │                    │
    │           (cooldown_until < NOW)      │
    │                  ▼                    │
    │             needs_refresh             │
    │                  │                    │
    │     (device_switch + refresh cmd)     │
    │                  │                    │
    │                  ▼                    │
    │           waiting_refresh ────────────┘
    │                  │
    │             (5 min timeout)
    │                  ▼
    │                dead
    │                  │
    │       (ручной разогрев)
    └──────── (POST /sessions)

active, expires_at < NOW+3min → waiting_refresh (proactive)
active, 401 на запросе → waiting_refresh (reactive fallback)
```

Источник: `account-pool-design.md §5`

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
-- Supabase migration 0005
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
    UNIQUE (avito_user_id)
);
```

Источник: `account-pool-design.md §6.1`

### G.2 Polling — round-robin LRU

`POST /api/v1/accounts/poll-claim` → атомарно берёт аккаунт с наименьшим `last_polled_at`.
Использует `SELECT ... FOR UPDATE SKIP LOCKED` для защиты от race conditions.

Ответ: `{account_id, session_token, device_id, fingerprint, ...}`
При полностью дренированном pool: `409 {error: "pool_drained"}`

После request: `POST /api/v1/accounts/{id}/report` с `{status_code: 200|403|401, body_excerpt?}`.

### G.3 Текущее состояние pool (2026-04-28)

| Аккаунт | Android-user | phone_serial | state |
|---|---|---|---|
| Clone | 10 | 110139ce | active (polling идёт через него) |
| Main | 0 | 110139ce | dead (banned после burst-запросов) |

Backend round-robin (xapi /api/v1/accounts) **ещё не реализован** — pending task #13/#14.
Сейчас xapi берёт `MAX(created_at) WHERE is_active=true` — то есть всегда последнюю активную сессию.

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

Деактивирует все прежние active sessions **того же account_id** (не tenant_id — это изменение в pool-aware версии).

После account-pool deploy (migration 0005):
```python
# avito-xapi/src/routers/sessions.py (после изменений из account-pool-design.md §7.2)
account = resolve_or_create_account(payload.user_id, payload.device_id)
sb.table("avito_sessions").update({"is_active": False})
    .eq("account_id", account.id).eq("is_active", True).execute()
sb.table("avito_sessions").insert({"account_id": account.id, ...}).execute()
if account.state == 'waiting_refresh':
    sb.table("avito_accounts").update({"state": "active", "waiting_since": None}).execute()
```

До migration 0005 (текущее состояние): деактивирует по tenant_id.

---

## I. avito-monitor — AccountPool client

```python
# avito-monitor/app/services/account_pool.py (план)
class AccountPool:
    @asynccontextmanager
    async def claim_for_poll(self):
        resp = await self.xapi.post('/accounts/poll-claim')
        if resp.status_code == 409:
            raise NoAvailableAccountError(resp.json())
        yield resp.json()   # account dict

    async def report(self, account_id: str, status_code: int, body=None):
        await self.xapi.post(f'/accounts/{account_id}/report', json={...})
```

Источник: `account-pool-design.md §7.6`
