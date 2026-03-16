# AvitoSystem — Tenant Auth System

## Архитектура

AvitoSystem — SaaS-платформа с API-доступом к Avito. Состоит из трёх Docker-контейнеров:

| Сервис | Порт | Назначение |
|--------|------|-----------|
| `avito-xapi` | 8080 | Основной API-шлюз к Avito (сессии, мессенджер, звонки, поиск, ферма) |
| `tenant-auth` | 8090 | Микросервис авторизации тенантов (регистрация, JWT, OTP, биллинг, команда) |
| `frontend` | 3000 | Vue.js фронтенд (nginx) |

Все сервисы используют общую Supabase PostgreSQL БД (проект `bkxpajeqrkutktmtmwui`).
Доступ к БД — через PostgREST API Supabase с service_role ключом (обходит RLS).

---

## Две схемы авторизации

Система поддерживает два метода авторизации, оба разрешаются в один `TenantContext`:

### 1. API-ключ (X-Api-Key) — для интеграций
```
GET /api/v1/sessions/current
X-Api-Key: ak_xxxxxxxxxxxxx
```
- Ключ хэшируется SHA-256 и ищется в таблице `api_keys`
- Формат ключа: `ak_` + 32 символа URL-safe base64
- Ключ виден пользователю только один раз при создании
- В БД хранится только `key_hash`

### 2. JWT Bearer — для админки
```
GET /api/v1/sessions/current
Authorization: Bearer eyJhbGciOi...
```
- JWT создаётся микросервисом `tenant-auth` при верификации OTP
- Валидируется локально через shared secret (без сетевого вызова)
- Алгоритм: HS256

**Приоритет в xapi:** JWT проверяется первым. Если заголовок `Authorization: Bearer` присутствует и `JWT_SECRET` настроен — валидация JWT. При невалидном JWT — fallback на API-ключ. Если ни один метод не предоставлен — 401.

### JWT Access Token payload
```json
{
  "sub": "user-uuid",
  "tenant_id": "tenant-uuid",
  "role": "owner",
  "type": "access",
  "exp": 1700000000,
  "iat": 1700000000
}
```

### Общие настройки JWT (должны совпадать в обоих сервисах)
| Параметр | Env-переменная | Значение |
|----------|---------------|----------|
| Secret | `JWT_SECRET` | одинаковый в tenant-auth и avito-xapi |
| Алгоритм | `JWT_ALGORITHM` | `HS256` |
| Access TTL | `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 30 мин |
| Refresh TTL | `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | 30 дней |

---

## Схема БД

### Таблицы из 001_init.sql (существовали ранее)

```
supervisors         — партнёры/реселлеры
  id UUID PK, name, email, is_active, settings JSONB

toolkits            — наборы фич (supervisor → tenants)
  id UUID PK, supervisor_id FK, name, features JSONB, limits JSONB, price_monthly

tenants             — SaaS-клиенты
  id UUID PK, supervisor_id FK, toolkit_id FK, name, email, is_active,
  subscription_until, settings JSONB, billing_plan_id FK, phone TEXT
  (billing_plan_id и phone добавлены миграцией 003)

api_keys            — API-ключи тенантов
  id UUID PK, tenant_id FK, key_hash UNIQUE, name, is_active, last_used_at

avito_sessions      — Avito-токены тенанта
  id UUID PK, tenant_id FK, tokens JSONB, fingerprint, device_id,
  user_id BIGINT, source ('android'|'redroid'|'manual'|'farm'|'browser'), is_active

audit_log           — лог действий
  id BIGSERIAL PK, tenant_id FK, action, details JSONB

farm_devices        — физические Android-устройства
  id UUID PK, name, model, serial UNIQUE, max_profiles, api_key_hash UNIQUE, status

account_bindings    — привязка Avito-аккаунта к профилю Android
  id UUID PK, tenant_id FK, farm_device_id FK, android_profile_id, avito_user_id, status
```

### Таблицы из 003_tenant_auth.sql (новые)

```
billing_plans       — тарифные планы
  id UUID PK, name UNIQUE, price_monthly DECIMAL, max_api_keys INT,
  max_sessions INT, max_sub_users INT, features JSONB, is_active

tenant_users        — пользователи тенанта (phone-based auth)
  id UUID PK, tenant_id FK, phone UNIQUE, email, email_verified BOOL,
  phone_verified BOOL, name, avatar_url, role ('owner'|'admin'|'manager'|'viewer'),
  settings JSONB, is_active, created_at, updated_at

verification_codes  — OTP-коды
  id UUID PK, target, target_type ('phone'|'email'),
  code, channel ('sms'|'telegram'|'whatsapp'|'vk_max'|'email'|'console'),
  purpose ('register'|'login'|'verify_email'|'change_phone'|'change_email'),
  attempts INT, max_attempts INT (=5), is_used BOOL, expires_at

refresh_tokens      — JWT refresh-токены (сессии)
  id UUID PK, token_hash UNIQUE, user_id FK→tenant_users,
  device_info JSONB, is_revoked BOOL, expires_at

tenant_invites      — приглашения sub-пользователей
  id UUID PK, tenant_id FK, invited_by FK→tenant_users,
  phone, email, role ('admin'|'manager'|'viewer'),
  status ('pending'|'accepted'|'cancelled'|'expired'),
  token_hash UNIQUE, expires_at

notification_preferences — настройки уведомлений
  id UUID PK, user_id FK→tenant_users,
  channel ('sms'|'telegram'|'whatsapp'|'vk_max'|'email'),
  event_type TEXT, is_enabled BOOL
  UNIQUE(user_id, channel, event_type)

notification_history — история уведомлений
  id BIGSERIAL PK, user_id FK→tenant_users,
  channel, event_type, title, body, is_read BOOL, created_at
```

### Связи между таблицами
```
supervisors ──1:N──> toolkits
supervisors ──1:N──> tenants
toolkits    ──1:N──> tenants (через toolkit_id)
billing_plans ─1:N─> tenants (через billing_plan_id)
tenants     ──1:N──> api_keys
tenants     ──1:N──> avito_sessions
tenants     ──1:N──> tenant_users
tenants     ──1:N──> tenant_invites
tenant_users ─1:N──> refresh_tokens
tenant_users ─1:N──> tenant_invites (invited_by)
tenant_users ─1:N──> notification_preferences
tenant_users ─1:N──> notification_history
```

### Seed-данные (004_tenant_auth_seed.sql)

| Сущность | ID | Детали |
|----------|-----|--------|
| Billing Plan free | `e0000000-...-000001` | 0 руб, 1 ключ, 1 сессия, 1 пользователь |
| Billing Plan starter | `e0000000-...-000002` | 990 руб, 3 ключа, 5 сессий, 3 пользователя |
| Billing Plan pro | `e0000000-...-000003` | 2990 руб, 10 ключей, 20 сессий, 10 пользователей |
| Test Supervisor | `a0000000-...-000001` | DevSupervisor |
| Test Tenant | `c0000000-...-000001` | TestTenant, plan=free |
| Test User | `f0000000-...-000001` | +79991234567, owner, verified |
| Test API Key | `d0000000-...-000001` | plaintext: `test_dev_key_123` |

---

## API tenant-auth (порт 8090)

Все эндпоинты имеют префикс `/auth/v1`.
Формат ответов — JSON. Ошибки: `{"detail": "текст ошибки"}`.

### Публичные эндпоинты (без авторизации)

#### POST /auth/v1/register
Регистрация нового тенанта. Создаёт tenant + tenant_user (owner), отправляет OTP на телефон.
```json
// Request
{"phone": "+79991234567", "email": "user@example.com", "name": "My Company", "otp_channel": "sms"}

// otp_channel: "sms" | "telegram" | "whatsapp" | "vk_max" | "console"
// phone: формат "+XXXXXXXXXXX" (от 10 до 15 цифр после +)

// Response 200
{"message": "OTP sent for registration", "channel": "console", "expires_in": 300}

// Errors: 409 (phone exists), 429 (rate limit)
```

#### POST /auth/v1/login
Запрос OTP для входа существующего пользователя.
```json
// Request
{"phone": "+79991234567", "otp_channel": "sms"}

// Response 200
{"message": "OTP sent for login", "channel": "console", "expires_in": 300}

// Errors: 404 (phone not found), 403 (deactivated), 429 (rate limit)
```

#### POST /auth/v1/verify-otp
Подтверждение OTP-кода. Возвращает JWT-пару.
```json
// Request
{"phone": "+79991234567", "code": "123456", "purpose": "register"}
// purpose: "register" | "login" | "verify_email" | "change_phone" | "change_email"
// email: опционально (для verify_email)

// Response 200
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "random-url-safe-string-86-chars",
  "token_type": "bearer",
  "expires_in": 1800
}

// Errors: 400 (wrong code / expired / too many attempts), 404 (user not found)
```

**Логика по purpose:**
- `register` — ставит phone_verified=true, отправляет OTP на email для верификации, возвращает JWT
- `login` — возвращает JWT
- `verify_email` — ставит email_verified=true, возвращает JWT

#### POST /auth/v1/refresh
Ротация refresh-токена. Старый токен инвалидируется, выдаётся новая пара.
```json
// Request
{"refresh_token": "old-refresh-token-string"}

// Response 200
{"access_token": "...", "refresh_token": "new-refresh-token", "token_type": "bearer", "expires_in": 1800}

// Errors: 401 (invalid / revoked / expired)
```

#### POST /auth/v1/logout
Отзыв одного refresh-токена.
```json
// Request
{"refresh_token": "token-to-revoke"}

// Response 200
{"message": "Logged out"}
```

#### POST /auth/v1/logout-all
Отзыв всех refresh-токенов пользователя (все устройства).
```json
// Request
{"refresh_token": "any-valid-refresh-token-of-user"}

// Response 200
{"message": "Revoked 3 sessions"}

// Errors: 401 (invalid token)
```

#### GET /auth/v1/billing/plans
Список тарифных планов (публичный).
```json
// Response 200
[
  {"id": "uuid", "name": "free", "price_monthly": 0.0, "max_api_keys": 1, "max_sessions": 1, "max_sub_users": 1, "features": {}},
  {"id": "uuid", "name": "starter", "price_monthly": 990.0, ...},
  {"id": "uuid", "name": "pro", "price_monthly": 2990.0, ...}
]
```

#### POST /auth/v1/team/invites/{token}/accept
Принять приглашение в команду (публичный, токен в URL).
```json
// Request
{"phone": "+79990001111", "name": "New Member"}

// Response 200
{"message": "Invite accepted", "user_id": "uuid", "tenant_id": "uuid"}

// Errors: 400 (invalid/expired invite, phone taken)
```

---

### Защищённые эндпоинты (требуют JWT)

Заголовок: `Authorization: Bearer <access_token>`

#### Профиль

| Метод | Путь | Описание | Роли |
|-------|------|----------|------|
| GET | `/auth/v1/profile` | Получить профиль текущего пользователя | любая |
| PATCH | `/auth/v1/profile` | Обновить name, avatar_url, settings | любая |
| POST | `/auth/v1/profile/change-phone` | Запрос смены телефона (OTP на новый номер) | любая |
| POST | `/auth/v1/profile/verify-phone` | Подтверждение нового телефона | любая |
| POST | `/auth/v1/profile/change-email` | Запрос смены email (OTP на новый email) | любая |
| POST | `/auth/v1/profile/verify-email` | Подтверждение нового email | любая |

```json
// GET /auth/v1/profile — Response
{
  "id": "uuid", "tenant_id": "uuid", "phone": "+79991234567",
  "email": "user@example.com", "email_verified": true, "phone_verified": true,
  "name": "John", "avatar_url": null, "role": "owner",
  "settings": {}, "created_at": "2025-01-01T00:00:00+00:00"
}

// PATCH /auth/v1/profile — Request
{"name": "New Name", "avatar_url": "https://...", "settings": {"theme": "dark"}}
// Все поля опциональные, отправляются только изменяемые

// POST /auth/v1/profile/change-phone — Request
{"new_phone": "+79990009999", "otp_channel": "sms"}

// POST /auth/v1/profile/verify-phone — Request
{"code": "123456"}

// POST /auth/v1/profile/change-email — Request
{"new_email": "new@example.com"}

// POST /auth/v1/profile/verify-email — Request
{"code": "123456"}
```

#### API-ключи

| Метод | Путь | Описание | Роли | Доп. требования |
|-------|------|----------|------|----------------|
| GET | `/auth/v1/api-keys` | Список ключей тенанта | owner, admin | — |
| POST | `/auth/v1/api-keys` | Создать ключ | owner, admin | email_verified |
| PATCH | `/auth/v1/api-keys/{id}` | Обновить name/is_active | owner, admin | — |
| DELETE | `/auth/v1/api-keys/{id}` | Деактивировать ключ | owner, admin | — |
| POST | `/auth/v1/api-keys/{id}/rotate` | Ротация ключа (старый → новый) | owner, admin | email_verified |

```json
// POST /auth/v1/api-keys — Request
{"name": "Production Key"}

// POST /auth/v1/api-keys — Response 200 (plaintext_key виден только один раз!)
{
  "id": "uuid", "tenant_id": "uuid", "name": "Production Key",
  "is_active": true, "last_used_at": null, "created_at": "...",
  "plaintext_key": "ak_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}

// GET /auth/v1/api-keys — Response (plaintext_key НЕ возвращается)
[{"id": "uuid", "tenant_id": "uuid", "name": "Production Key", "is_active": true, "last_used_at": "...", "created_at": "..."}]

// PATCH /auth/v1/api-keys/{id} — Request
{"name": "Renamed Key", "is_active": false}
```

#### JWT-сессии

| Метод | Путь | Описание | Роли |
|-------|------|----------|------|
| GET | `/auth/v1/sessions` | Активные сессии (устройства) | любая |
| DELETE | `/auth/v1/sessions/{id}` | Отозвать конкретную сессию | любая |
| DELETE | `/auth/v1/sessions` | Отозвать все сессии | любая |

```json
// GET /auth/v1/sessions — Response
{
  "sessions": [
    {"id": "uuid", "device_info": {}, "created_at": "...", "expires_at": "..."}
  ]
}
```

#### Команда (Sub-пользователи)

| Метод | Путь | Описание | Роли | Доп. |
|-------|------|----------|------|------|
| GET | `/auth/v1/team` | Список пользователей тенанта | любая | — |
| POST | `/auth/v1/team/invite` | Пригласить по phone/email | owner, admin | email_verified |
| GET | `/auth/v1/team/invites` | Pending-приглашения | owner, admin | — |
| DELETE | `/auth/v1/team/invites/{id}` | Отменить приглашение | owner, admin | — |
| PATCH | `/auth/v1/team/{user_id}/role` | Сменить роль | owner, admin | — |
| DELETE | `/auth/v1/team/{user_id}` | Удалить из команды | owner, admin | — |

```json
// GET /auth/v1/team — Response
[{"id": "uuid", "tenant_id": "uuid", "phone": "+7...", "email": "...", "name": "...", "role": "admin", "is_active": true, "created_at": "..."}]

// POST /auth/v1/team/invite — Request
{"phone": "+79990001111", "email": "invite@example.com", "role": "manager"}
// role: "admin" | "manager" | "viewer"  (owner нельзя назначить через invite)
// phone или email — хотя бы одно обязательно

// PATCH /auth/v1/team/{user_id}/role — Request
{"role": "admin"}
// Нельзя менять роль owner
```

#### Биллинг (защищённые)

| Метод | Путь | Описание | Роли |
|-------|------|----------|------|
| GET | `/auth/v1/billing/current` | Текущий план + использование | любая |
| POST | `/auth/v1/billing/upgrade` | Смена плана | owner |
| GET | `/auth/v1/billing/usage` | Детальная статистика | любая |

```json
// GET /auth/v1/billing/current — Response
{
  "plan": {"id": "uuid", "name": "free", "price_monthly": 0.0, "max_api_keys": 1, "max_sessions": 1, "max_sub_users": 1, "features": {}},
  "usage": {"api_keys_used": 1, "api_keys_limit": 1, "sessions_used": 0, "sessions_limit": 1, "sub_users_used": 1, "sub_users_limit": 1}
}

// POST /auth/v1/billing/upgrade — Request
{"plan_id": "e0000000-0000-0000-0000-000000000002"}
```

#### Уведомления

| Метод | Путь | Описание | Роли |
|-------|------|----------|------|
| GET | `/auth/v1/notifications/preferences` | Настройки уведомлений | любая |
| PUT | `/auth/v1/notifications/preferences` | Обновить настройки (полная замена) | любая |
| GET | `/auth/v1/notifications/history` | История уведомлений (?limit=50) | любая |

```json
// PUT /auth/v1/notifications/preferences — Request
{
  "preferences": [
    {"channel": "telegram", "event_type": "session_expired", "is_enabled": true},
    {"channel": "email", "event_type": "new_login", "is_enabled": false}
  ]
}
// channel: "sms" | "telegram" | "whatsapp" | "vk_max" | "email"
```

---

### Внутренний API (между сервисами)

Защищён заголовком `X-Internal-Secret` (значение из env `INTERNAL_SECRET`).

#### GET /auth/v1/tenants/{tenant_id}/params
Параметры тенанта для xapi.
```json
// Response
{"tenant": {...}, "toolkit": {...}, "billing_plan": {...}}
```

#### GET /auth/v1/tenants/by-api-key-hash/{hash}
Резолв тенанта по SHA-256 хэшу API-ключа.
```json
// Response
{"tenant": {...}, "api_key": {"id": "uuid", "tenant_id": "uuid", "name": "...", "is_active": true}}
```

---

## Флоу авторизации

### Регистрация нового тенанта
```
1. POST /auth/v1/register {"phone": "+79991234567", "email": "u@x.com", "name": "Co", "otp_channel": "console"}
   → 200 {"message": "OTP sent for registration", "channel": "console", "expires_in": 300}
   → В логах сервера: OTP CODE = 123456

2. POST /auth/v1/verify-otp {"phone": "+79991234567", "code": "123456", "purpose": "register"}
   → phone_verified = true
   → OTP отправлен на email для verify_email
   → 200 {"access_token": "eyJ...", "refresh_token": "xxx", "token_type": "bearer", "expires_in": 1800}

3. POST /auth/v1/verify-otp {"phone": "+79991234567", "code": "654321", "purpose": "verify_email"}
   → email_verified = true
   → Полный доступ (API-ключи, приглашения, биллинг)
```

### Вход существующего пользователя
```
1. POST /auth/v1/login {"phone": "+79991234567", "otp_channel": "console"}
   → 200 {"message": "OTP sent for login", ...}

2. POST /auth/v1/verify-otp {"phone": "+79991234567", "code": "123456", "purpose": "login"}
   → 200 {"access_token": "...", "refresh_token": "...", ...}
```

### Обновление access_token
```
POST /auth/v1/refresh {"refresh_token": "текущий-refresh-token"}
→ Старый refresh инвалидируется, выдаётся новая пара
→ 200 {"access_token": "...", "refresh_token": "новый-refresh", ...}
```

### Использование JWT в avito-xapi
```
# Вместо X-Api-Key можно использовать JWT:
GET http://localhost:8080/api/v1/sessions/current
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...

# Оба метода разрешаются в одинаковый TenantContext
```

---

## Система ролей

| Роль | Профиль | API-ключи | Команда | Биллинг | Сессии |
|------|---------|-----------|---------|---------|--------|
| owner | read/write | CRUD | CRUD + invite | upgrade | read/revoke |
| admin | read/write | CRUD | CRUD + invite | read | read/revoke |
| manager | read/write | read | read | read | read/revoke |
| viewer | read | — | — | — | read |

- `owner` — создаётся автоматически при регистрации тенанта; один на тенант; нельзя удалить и нельзя сменить роль
- Sub-пользователи приглашаются через `/auth/v1/team/invite` с ролью `admin`, `manager` или `viewer`

---

## Ограничения безопасности

### OTP
- Макс. 5 попыток ввода на один код (`otp_max_attempts`)
- Макс. 5 кодов в час на один телефон/email (`otp_max_codes_per_hour`)
- Код истекает через 5 минут (`otp_expire_minutes`)
- При превышении попыток код помечается is_used=true

### JWT
- Access token: 30 минут TTL
- Refresh token: 30 дней TTL
- Refresh rotation: каждый POST /refresh инвалидирует старый токен и выдаёт новый
- Refresh хранится в БД как SHA-256 хэш

### Email verification
Обязательна для:
- Создания API-ключей (POST /auth/v1/api-keys)
- Ротации API-ключей (POST /auth/v1/api-keys/{id}/rotate)
- Приглашения в команду (POST /auth/v1/team/invite)

---

## OTP-провайдеры

Настройка: env `OTP_PROVIDER`.

| Значение | Поведение |
|----------|-----------|
| `console` (default) | Логирует OTP-код в stdout сервера |
| `sms` | SMS через smsru/smsc (stub) |
| `telegram` | Telegram Bot API (stub) |
| `whatsapp` | WhatsApp Business API (stub) |
| `vk_max` | VK MAX Bot API (stub) |
| `email` | SMTP (stub) |

При `OTP_PROVIDER=console` все каналы перенаправляются в консоль, в БД `channel` записывается как `"console"`.

---

## Конфигурация (env-переменные)

### tenant-auth/.env
```
SUPABASE_URL=https://bkxpajeqrkutktmtmwui.supabase.co
SUPABASE_KEY=<service_role_key>
HOST=0.0.0.0
PORT=8090
LOG_LEVEL=info
JWT_SECRET=<shared-secret-min-32-chars>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30
OTP_PROVIDER=console
OTP_LENGTH=6
OTP_EXPIRE_MINUTES=5
INTERNAL_SECRET=<secret-for-inter-service-calls>
CORS_ORIGINS=["http://localhost:3000","https://avito.newlcd.ru"]
```

### avito-xapi/.env (добавить)
```
JWT_SECRET=<тот же shared-secret что и в tenant-auth>
JWT_ALGORITHM=HS256
```

---

## Структура файлов tenant-auth

```
tenant-auth/
├── Dockerfile
├── requirements.txt
├── .env.example
├── src/
│   ├── main.py                         # FastAPI app, middleware, роутеры
│   ├── config.py                       # Pydantic BaseSettings
│   ├── dependencies.py                 # get_current_user(), require_role(), require_email_verified(), require_internal_secret()
│   ├── middleware/
│   │   ├── error_handler.py            # Глобальный обработчик ошибок
│   │   └── jwt_auth.py                 # JWT Bearer middleware (пропускает публичные пути)
│   ├── models/
│   │   ├── auth.py                     # RegisterRequest, LoginRequest, VerifyOtpRequest, RefreshRequest, TokenPair, OtpSentResponse, LogoutRequest
│   │   ├── user.py                     # UserProfile, UserUpdate, ChangePhoneRequest, ChangeEmailRequest, VerifyChangeRequest
│   │   ├── api_key.py                  # ApiKeyCreate, ApiKeyUpdate, ApiKeyResponse, ApiKeyCreatedResponse
│   │   ├── invite.py                   # InviteCreate, InviteResponse, InviteAcceptRequest, TeamMemberResponse, RoleUpdateRequest
│   │   ├── billing.py                  # PlanInfo, CurrentPlanResponse, UsageStats, UpgradeRequest
│   │   ├── notification.py            # NotificationPref, NotificationPrefResponse, NotificationPrefsUpdate, NotificationHistoryItem
│   │   └── common.py                  # ErrorResponse, HealthResponse, ReadyResponse
│   ├── routers/
│   │   ├── health.py                   # GET /health, /ready
│   │   ├── auth.py                     # register, login, verify-otp, refresh, logout, logout-all
│   │   ├── profile.py                  # профиль, смена phone/email
│   │   ├── api_keys.py                 # CRUD API-ключей
│   │   ├── sessions.py                 # JWT-сессии (refresh tokens)
│   │   ├── invites.py                  # команда / sub-пользователи
│   │   ├── billing.py                  # планы, использование, upgrade
│   │   ├── notifications.py           # настройки уведомлений, история
│   │   └── tenant_params.py           # внутренний API для xapi
│   ├── services/
│   │   ├── otp_service.py              # генерация, отправка, валидация OTP, rate limiting
│   │   ├── jwt_service.py              # create/verify access+refresh tokens, ротация, revoke
│   │   ├── user_service.py             # CRUD пользователей, команда
│   │   ├── api_key_service.py          # генерация, хэширование, CRUD ключей
│   │   ├── invite_service.py           # приглашения sub-пользователей
│   │   ├── billing_service.py          # тарифы, использование, upgrade
│   │   └── notification_service.py    # preferences, history
│   ├── providers/
│   │   ├── base.py                     # ABC: send_otp(target, code, purpose) -> bool
│   │   ├── console.py                  # Dev: логирует OTP в stdout
│   │   ├── sms.py                      # SMS stub
│   │   ├── telegram.py                 # Telegram stub
│   │   ├── whatsapp.py                 # WhatsApp stub
│   │   ├── vk_max.py                   # VK MAX stub
│   │   └── email_provider.py          # Email stub
│   └── storage/
│       └── supabase.py                 # PostgREST wrapper (QueryBuilder, SupabaseClient)
└── tests/
    ├── conftest.py
    ├── test_health.py
    ├── test_auth.py
    └── test_jwt_service.py
```

---

## Работа с БД (Supabase PostgREST)

Оба сервиса используют лёгкий wrapper вместо supabase-py SDK.

```python
from src.storage.supabase import get_supabase

sb = get_supabase()

# SELECT
result = sb.table("tenant_users").select("*").eq("phone", "+79991234567").limit(1).execute()
user = result.data[0] if result.data else None

# INSERT
result = sb.table("tenant_users").insert({"phone": "+7...", "tenant_id": "uuid", "role": "owner"}).execute()
new_user = result.data[0]

# UPDATE
sb.table("tenant_users").update({"name": "New Name"}).eq("id", user_id).execute()

# DELETE
sb.table("api_keys").delete().eq("id", key_id).execute()

# Доступные фильтры: eq, neq, gt, gte, lt, lte
# Сортировка: .order("created_at", desc=True)
# Лимит: .limit(50)
```

---

## Docker

```yaml
# docker-compose.yml
services:
  xapi:
    build: ./avito-xapi
    ports: ["8080:8080"]
    env_file: ./avito-xapi/.env

  tenant-auth:
    build: ./tenant-auth
    ports: ["8090:8090"]
    env_file: ./tenant-auth/.env
    depends_on: [xapi]

  frontend:
    build: ./avito-frontend
    ports: ["3000:80"]
    depends_on: [xapi]
```

Запуск: `docker compose up -d --build`

---

## Быстрый тест (curl)

```bash
# 1. Регистрация
curl -X POST http://localhost:8090/auth/v1/register \
  -H "Content-Type: application/json" \
  -d '{"phone":"+79990001234","email":"test@test.com","name":"Test","otp_channel":"console"}'

# 2. Посмотреть OTP в логах tenant-auth
docker logs tenant-auth 2>&1 | grep "OTP CODE"

# 3. Верификация OTP
curl -X POST http://localhost:8090/auth/v1/verify-otp \
  -H "Content-Type: application/json" \
  -d '{"phone":"+79990001234","code":"XXXXXX","purpose":"register"}'
# → Получить access_token и refresh_token

# 4. Создать API-ключ (нужен email_verified, для теста используем seed-пользователя)
# Сначала логин seed-пользователя:
curl -X POST http://localhost:8090/auth/v1/login \
  -d '{"phone":"+79991234567","otp_channel":"console"}'
# Верификация:
curl -X POST http://localhost:8090/auth/v1/verify-otp \
  -d '{"phone":"+79991234567","code":"XXXXXX","purpose":"login"}'
# Сохранить access_token, затем:
curl -X POST http://localhost:8090/auth/v1/api-keys \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"My Key"}'
# → Получить plaintext_key (ak_...)

# 5. Использовать ключ в xapi
curl http://localhost:8080/api/v1/sessions/current \
  -H "X-Api-Key: ak_..."

# 6. Или использовать JWT в xapi
curl http://localhost:8080/api/v1/sessions/current \
  -H "Authorization: Bearer <access_token>"
```
