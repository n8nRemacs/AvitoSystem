# X-API — Avito Gateway API

Наш собственный REST API, который оборачивает реверс-инженерное API Avito в чистые, документированные эндпоинты. Доступен через Swagger UI.

**Стек:** Python 3.11+ / FastAPI / curl_cffi / SQLite
**Порт:** 8080
**Swagger UI:** `http://localhost:8080/docs`
**Продакшн:** `https://avito.newlcd.ru/docs`

---

## Содержание

1. [Блок 1: Системные эндпоинты](#блок-1-системные-эндпоинты)
2. [Блок 2: Управление сессиями](#блок-2-управление-сессиями)
3. [Блок 3: Мессенджер](#блок-3-мессенджер)
4. [Блок 4: IP-телефония](#блок-4-ip-телефония)
5. [Блок 5: Поиск объявлений](#блок-5-поиск-объявлений)
6. [Архитектура](#архитектура)
7. [Авторизация](#авторизация)
8. [Модели данных](#модели-данных)
9. [Конфигурация](#конфигурация)

---

## Авторизация

Все `/api/v1/*` эндпоинты требуют заголовок:

```
X-Api-Key: <ваш_ключ>
```

Без заголовка или с неверным ключом → `401 Unauthorized`.

Эндпоинты `/health`, `/ready`, `/docs` — без авторизации.

---

## Блок 1: Системные эндпоинты

Мониторинг и документация. Авторизация НЕ требуется.

### GET /health

Проверка работоспособности сервера.

**Ответ 200:**
```json
{
  "status": "ok",
  "timestamp": 1770062500,
  "version": "1.0.0"
}
```

### GET /ready

Проверка готовности — валидна ли текущая сессия Avito.

**Ответ 200 (готов):**
```json
{
  "ready": true,
  "session_valid": true,
  "token_hours_left": 12.5
}
```

**Ответ 503 (не готов):**
```json
{
  "ready": false,
  "session_valid": false,
  "reason": "No active session"
}
```

### GET /docs

Swagger UI — интерактивная документация с "Try it out".

### GET /openapi.json

OpenAPI 3.0 спецификация в JSON.

---

## Блок 2: Управление сессиями

Загрузка, просмотр и обновление токенов Avito. Токены приходят из Token Bridge (Redroid) или Android-приложения.

### POST /api/v1/sessions

Загрузить/обновить сессию. Вызывается Token Bridge или Android-приложением.

**Запрос:**
```json
{
  "session_token": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "5c5b31d4b70e997ac188ad7723b395b4",
  "fingerprint": "A2.a541fb18def1032c46e8ce9356bf78870fa9c764...",
  "device_id": "a8d7b75625458809",
  "remote_device_id": "kSCwY4Kj4HUfwZHG...",
  "user_hash": "9b82afc1ab1e2419981f7a9d9d2b6af9",
  "user_id": 157920214,
  "expires_at": 1770104756,
  "cookies": {
    "1f_uid": "uuid",
    "u": "string",
    "v": "timestamp"
  }
}
```

**Обязательные поля:** `session_token`, `fingerprint`, `device_id`, `expires_at`

**Ответ 200:**
```json
{
  "success": true,
  "expires_at": 1770104756,
  "hours_left": 12.5,
  "user_id": 157920214
}
```

### GET /api/v1/sessions/current

Получить статус текущей сессии (без раскрытия полного токена).

**Ответ 200:**
```json
{
  "exists": true,
  "user_id": 157920214,
  "expires_at": 1770104756,
  "hours_left": 12.5,
  "is_valid": true,
  "token_preview": "eyJhbGciOiJIUzUxMi...первые 20 символов",
  "synced_at": 1770058954
}
```

**Ответ 404:**
```json
{
  "exists": false,
  "reason": "No session uploaded"
}
```

### POST /api/v1/sessions/refresh

Запросить обновление токена (если есть Redroid/Android). Trigger-метод.

**Ответ 200:**
```json
{
  "triggered": true,
  "message": "Refresh requested, check status in 60 seconds"
}
```

### DELETE /api/v1/sessions

Удалить текущую сессию.

**Ответ 200:**
```json
{"success": true}
```

---

## Блок 3: Мессенджер

Полный доступ к Avito Messenger через HTTP. Нормализованные ответы — одинаковый формат независимо от того, получены данные через HTTP REST или WebSocket.

### GET /api/v1/messenger/channels

Список чатов с пагинацией.

**Query параметры:**

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| limit | int | 30 | Макс 30 |
| offset_timestamp | int | null | Пагинация: sortingTimestamp последнего |
| category | int | 1 | 1=все, 6=избранные |

**Ответ 200:**
```json
{
  "channels": [
    {
      "id": "u2i-gFdm0fc~KmiXS21tNQV_~g",
      "participants": [
        {"id": "68066a9daa4df0b3", "name": "Артём"},
        {"id": "4c48533419806d79", "name": "РемАкс"}
      ],
      "unread_count": 0,
      "is_read": true,
      "item_title": "iPhone 12",
      "last_message": {
        "id": "msg_123",
        "text": "Договорились",
        "author_id": "4c48533419806d79",
        "type": "text",
        "created_at": 1768300000,
        "is_mine": true
      },
      "updated_at": 1768300000
    }
  ],
  "has_more": true,
  "next_offset": 1768300000
}
```

### GET /api/v1/messenger/channels/{channel_id}

Детали одного канала.

**Ответ 200:** Объект `Channel` (см. выше)

### GET /api/v1/messenger/channels/{channel_id}/messages

История сообщений канала.

**Query параметры:**

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| limit | int | 50 | Макс 100 |
| before | string | null | ID сообщения для пагинации назад |

**Ответ 200:**
```json
{
  "messages": [
    {
      "id": "12f70ec959e9ff29",
      "channel_id": "u2i-xxx",
      "author_id": "4c48533419806d79",
      "author_name": "РемАкс",
      "type": "text",
      "text": "Привет!",
      "media": null,
      "created_at": 1768299248,
      "is_read": true,
      "is_mine": true
    }
  ],
  "has_more": false
}
```

### POST /api/v1/messenger/channels/{channel_id}/messages

Отправить текстовое сообщение.

**Запрос:**
```json
{
  "text": "Здравствуйте! Интересует ваш товар.",
  "quote_message_id": null
}
```

**Ответ 200:**
```json
{
  "success": true,
  "message": {
    "id": "new_msg_hash",
    "channel_id": "u2i-xxx",
    "author_id": "4c48533419806d79",
    "type": "text",
    "text": "Здравствуйте! Интересует ваш товар.",
    "created_at": 1768300500,
    "is_mine": true
  }
}
```

### POST /api/v1/messenger/channels/{channel_id}/read

Пометить канал как прочитанный.

**Ответ 200:**
```json
{"success": true}
```

### POST /api/v1/messenger/channels/{channel_id}/typing

Отправить индикатор набора.

**Ответ 200:**
```json
{"success": true}
```

### POST /api/v1/messenger/channels/create-by-item

Создать чат по ID объявления.

**Запрос:**
```json
{
  "item_id": "7867391303"
}
```

**Ответ 200:**
```json
{
  "success": true,
  "channel": { ... }
}
```

### POST /api/v1/messenger/channels/create-by-user

Создать чат с пользователем по hash.

**Запрос:**
```json
{
  "user_hash": "b5b928d9b300d15526cf829b93962213"
}
```

**Ответ 200:**
```json
{
  "success": true,
  "channel": { ... }
}
```

### GET /api/v1/messenger/unread-count

Общее количество непрочитанных сообщений.

**Ответ 200:**
```json
{
  "unread_count": 5
}
```

---

## Блок 4: IP-телефония

История звонков и записи разговоров. Работает только через browser cookie (sessid), без fingerprint.

### GET /api/v1/calls/history

История звонков с фильтрацией и пагинацией.

**Query параметры:**

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| date_from | string | 30 дней назад | ISO date (YYYY-MM-DD) |
| date_to | string | сегодня | ISO date |
| limit | int | 50 | Кол-во |
| offset | int | 0 | Смещение |
| sort_direction | string | "desc" | "asc" / "desc" |
| filter_type | string | "all" | "all" / "new" / "repeated" |
| filter_status | string | "all" | "all" / "received" / "missed" |
| show_spam | bool | true | Показывать спам |

**Ответ 200:**
```json
{
  "calls": [
    {
      "id": 1108478743,
      "caller": "+7 927 576-67-88",
      "receiver": "+7 917 170-80-77",
      "duration": "0:42",
      "waiting_time": "0:05",
      "has_recording": true,
      "is_new": false,
      "is_spam": false,
      "is_callback": false,
      "created_at": "2026-01-13T13:06:26+03:00",
      "item_id": 123456,
      "item_title": "iPhone 12"
    }
  ],
  "total": 150,
  "has_more": true
}
```

### GET /api/v1/calls/{call_id}/recording

Скачать запись разговора.

**Ответ 200:** `audio/mpeg` (MP3 файл)

**Ответ 404:** Запись не найдена

---

## Блок 5: Поиск объявлений

Поиск товаров на Avito и получение деталей объявлений.

### GET /api/v1/search/items

Поиск объявлений.

**Query параметры:**

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| query | string | *обязательный* | Поисковый запрос |
| price_min | int | null | Мин. цена |
| price_max | int | null | Макс. цена |
| location_id | int | 621540 | Регион (621540 = вся Россия) |
| with_delivery | bool | true | Только с Авито Доставкой |
| limit | int | 30 | Кол-во результатов |
| page | int | 1 | Страница |

**Ответ 200:**
```json
{
  "items": [
    {
      "id": "7867391303",
      "title": "iPhone 12 Pro, 128 ГБ",
      "price": 15000,
      "price_text": "15 000 ₽",
      "location": "Москва",
      "image_url": "https://...",
      "delivery": true,
      "seller_id": "abc123",
      "url": "https://www.avito.ru/7867391303"
    }
  ],
  "total": 150,
  "page": 1,
  "has_more": true
}
```

### GET /api/v1/search/items/{item_id}

Детали объявления.

**Ответ 200:**
```json
{
  "id": "7867391303",
  "title": "iPhone 12 Pro, 128 ГБ",
  "price": 15000,
  "description": "Полное описание объявления...",
  "location": "Москва",
  "images": ["https://...", "https://..."],
  "delivery": true,
  "reserved": false,
  "seller_id": "abc123",
  "url": "https://www.avito.ru/7867391303"
}
```

> **Примечание:** Endpoint карточки товара (`/api/19/items/{id}`) не полностью подтверждён. Может потребовать дополнительный реверс.

---

## Архитектура

```
Клиенты (curl, Frontend, Telegram Bot)
         │
         │  X-Api-Key auth
         ▼
┌──────────────────────┐
│  X-API (FastAPI)      │  :8080
│  /docs → Swagger UI   │
│                        │
│  routers/              │  Эндпоинты (sessions, messenger, calls, search)
│      │                 │
│      ▼                 │
│  workers/              │  Микроворкеры (чистый Python, без FastAPI)
│  ├─ base_client.py     │  Заголовки, curl_cffi, rate limit
│  ├─ http_client.py     │  Avito HTTP REST
│  ├─ ws_client.py       │  Avito WebSocket JSON-RPC
│  ├─ jwt_parser.py      │  Декодирование JWT
│  ├─ rate_limiter.py    │  Token bucket
│  └─ token_manager.py   │  Обновление токенов
│                        │
│  storage/              │  SQLite (только sessions)
└──────────┬─────────────┘
           │
           │  curl_cffi (impersonate="chrome120")
           ▼
    Avito APIs
    ├─ app.avito.ru      (HTTP REST)
    ├─ socket.avito.ru   (WebSocket)
    └─ www.avito.ru      (Call Tracking)
```

### Принцип нормализации

X-API нормализует ответы Avito, скрывая различия между HTTP REST и WebSocket:

| Avito HTTP | Avito WS Push | X-API (нормализовано) |
|------------|---------------|----------------------|
| `body.text.text` | `body.text` | `text` |
| `authorId` | `fromUid` | `author_id` |
| `createdAt` (nanosec) | `created` (millisec) | `created_at` (seconds) |
| `idempotencyKey` | `randomId` | (внутреннее, не возвращается) |

---

## Модели данных

### SessionData (внутренняя)

```python
class SessionData:
    session_token: str       # JWT HS512
    refresh_token: str | None
    fingerprint: str         # A2.{hex}
    device_id: str           # 16 hex chars
    remote_device_id: str
    user_hash: str           # 32 hex chars
    user_id: int
    expires_at: int          # Unix timestamp
    cookies: dict[str, str]  # 1f_uid, u, v
```

### Channel

```python
class Channel:
    id: str                  # "u2i-xxx"
    participants: list[Participant]
    unread_count: int
    is_read: bool
    item_title: str | None
    last_message: Message | None
    updated_at: int | None
```

### Message

```python
class Message:
    id: str
    channel_id: str
    author_id: str
    author_name: str | None
    type: str                # text, image, voice, video, file, location
    text: str | None
    media: MediaInfo | None
    created_at: int          # Unix timestamp (seconds)
    is_read: bool
    is_mine: bool
```

### CallRecord

```python
class CallRecord:
    id: int
    caller: str
    receiver: str
    duration: str            # "M:SS"
    has_recording: bool
    is_spam: bool
    created_at: str          # ISO 8601
    item_id: int | None
    item_title: str | None
```

### ErrorResponse

```python
class ErrorResponse:
    error: str               # Код ошибки
    message: str             # Описание
    status_code: int
```

---

## Конфигурация (.env)

```env
# X-API
API_KEY=your_secret_api_key
HOST=0.0.0.0
PORT=8080
LOG_LEVEL=INFO

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/xapi.db

# Session
SESSION_FILE=./data/avito_session.json   # опционально: загрузить при старте
AUTO_REFRESH_ENABLED=true
AUTO_REFRESH_CHECK_INTERVAL=300          # секунд
AUTO_REFRESH_THRESHOLD=3600             # рефреш когда < 1ч

# Rate Limiting (к Avito)
RATE_LIMIT_RPS=0.5                       # запросов/сек к Avito
RATE_LIMIT_BURST=3                       # burst
RATE_LIMIT_BACKOFF=30                    # секунд при 429

# CORS
CORS_ORIGINS=http://localhost:3000,https://avito.newlcd.ru
```

---

## Ошибки X-API

| HTTP код | Тело | Причина |
|----------|------|---------|
| 401 | `{"error": "unauthorized", "message": "Invalid API key"}` | Неверный X-Api-Key |
| 404 | `{"error": "not_found", "message": "No active session"}` | Сессия не загружена |
| 422 | `{"error": "validation", "message": "..."}` | Ошибка валидации |
| 429 | `{"error": "rate_limit", "message": "Avito rate limit hit"}` | Лимит Avito |
| 502 | `{"error": "avito_error", "message": "..."}` | Ошибка от Avito API |
| 503 | `{"error": "session_expired", "message": "Token expired"}` | JWT истёк |
