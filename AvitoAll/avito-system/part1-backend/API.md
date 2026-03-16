# Part 1: Backend API — Описание и API

## Назначение

Центральный сервер системы. Хранит все данные в SQLite и предоставляет REST API для всех остальных компонентов. Единственный компонент, который работает с базой данных напрямую.

## Функционал

- Хранение токенов авторизации Avito (от Token Bridge)
- CRUD поисковых запросов (от Frontend, Telegram)
- CRUD AI-правил / красных флагов (от Frontend)
- Хранение найденных товаров с результатами AI-анализа (от Worker)
- Хранение диалогов с продавцами (от Worker)
- Предоставление статистики (для Frontend, Telegram)

## Кто вызывает

| Клиент | Что делает |
|--------|-----------|
| Token Bridge | `POST /api/v1/sessions` — синхронизирует токены |
| Worker | `GET /api/v1/session` — получает токены |
| Worker | `GET /api/v1/searches` — получает активные поиски |
| Worker | `GET /api/v1/rules` — получает AI-правила |
| Worker | `POST /api/v1/items` — сохраняет найденные товары |
| Worker | `POST /api/v1/dialogs` — создаёт диалоги |
| Frontend | Все CRUD endpoints |
| Telegram | `GET/POST/DELETE /api/v1/searches` |
| Telegram | `GET /api/v1/items/new` — новые товары для уведомлений |

---

## API Reference

### Авторизация

Все endpoints `/api/v1/*` требуют заголовок:
```
X-Api-Key: <ключ из .env>
```

Без заголовка или с неверным ключом → `401 Unauthorized`

Исключение: `GET /health` — без авторизации.

---

## Sessions (Токены)

### POST /api/v1/sessions

Сохранить или обновить токены авторизации Avito.

**Кто вызывает:** Token Bridge

**Request:**
```http
POST /api/v1/sessions
Content-Type: application/json
X-Api-Key: <key>

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
    "1f_uid": "...",
    "u": "...",
    "v": "..."
  }
}
```

**Response 200:**
```json
{
  "success": true,
  "expires_at": 1770104756,
  "hours_left": 12.5
}
```

**Response 422:** Validation error (пропущены обязательные поля)

**Логика:** INSERT если таблица пуста, UPDATE последней записи если есть.

---

### GET /api/v1/session

Получить актуальные токены.

**Кто вызывает:** Worker

**Request:**
```http
GET /api/v1/session
X-Api-Key: <key>
```

**Response 200:**
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
  "cookies": {...},
  "synced_at": 1770058954
}
```

**Response 404:**
```json
{
  "detail": "No session found"
}
```

---

## Searches (Поиски)

### GET /api/v1/searches

Список поисковых запросов.

**Кто вызывает:** Frontend, Worker, Telegram

**Request:**
```http
GET /api/v1/searches
GET /api/v1/searches?enabled=true
X-Api-Key: <key>
```

**Query params:**
- `enabled` (bool, optional) — фильтр по активности

**Response 200:**
```json
[
  {
    "id": 1,
    "query": "iPhone 12 Pro",
    "price_min": 10000,
    "price_max": 25000,
    "delivery": true,
    "location_id": 621540,
    "category_id": null,
    "enabled": true,
    "created_at": "2026-02-03T12:00:00"
  },
  {
    "id": 2,
    "query": "Samsung S24",
    "price_min": 30000,
    "price_max": 50000,
    "delivery": true,
    "location_id": 621540,
    "category_id": null,
    "enabled": true,
    "created_at": "2026-02-03T13:00:00"
  }
]
```

---

### POST /api/v1/searches

Создать новый поиск.

**Кто вызывает:** Frontend, Telegram

**Request:**
```http
POST /api/v1/searches
Content-Type: application/json
X-Api-Key: <key>

{
  "query": "iPhone 12 Pro",
  "price_min": 10000,
  "price_max": 25000,
  "delivery": true,
  "location_id": 621540
}
```

**Обязательные поля:** `query`

**Опциональные поля (defaults):**
- `price_min`: null
- `price_max`: null
- `delivery`: true
- `location_id`: 621540
- `category_id`: null
- `enabled`: true

**Response 200:**
```json
{
  "id": 3,
  "query": "iPhone 12 Pro",
  "price_min": 10000,
  "price_max": 25000,
  "delivery": true,
  "location_id": 621540,
  "category_id": null,
  "enabled": true,
  "created_at": "2026-02-03T15:30:00"
}
```

**Response 422:** Validation error

---

### PUT /api/v1/searches/{id}

Обновить поиск.

**Кто вызывает:** Frontend

**Request:**
```http
PUT /api/v1/searches/1
Content-Type: application/json
X-Api-Key: <key>

{
  "enabled": false
}
```

Можно обновить любое подмножество полей.

**Response 200:** Обновлённый объект Search

**Response 404:** `{"detail": "Search not found"}`

---

### DELETE /api/v1/searches/{id}

Удалить поиск.

**Кто вызывает:** Frontend, Telegram

**Request:**
```http
DELETE /api/v1/searches/1
X-Api-Key: <key>
```

**Response 200:**
```json
{
  "success": true
}
```

**Response 404:** `{"detail": "Search not found"}`

---

## Rules (AI-правила)

### GET /api/v1/rules

Список AI-правил (красных флагов).

**Кто вызывает:** Frontend, Worker

**Request:**
```http
GET /api/v1/rules
GET /api/v1/rules?enabled=true
X-Api-Key: <key>
```

**Response 200:**
```json
[
  {
    "id": 1,
    "text": "iCloud Lock / Activation Lock — пропустить",
    "enabled": true,
    "is_preset": true,
    "created_at": "2026-02-03T10:00:00"
  },
  {
    "id": 7,
    "text": "Без коробки и документов — предупредить",
    "enabled": true,
    "is_preset": false,
    "created_at": "2026-02-03T16:00:00"
  }
]
```

---

### POST /api/v1/rules

Создать пользовательское правило.

**Кто вызывает:** Frontend

**Request:**
```http
POST /api/v1/rules
Content-Type: application/json
X-Api-Key: <key>

{
  "text": "Без коробки и документов — предупредить"
}
```

**Response 200:**
```json
{
  "id": 7,
  "text": "Без коробки и документов — предупредить",
  "enabled": true,
  "is_preset": false,
  "created_at": "2026-02-03T16:00:00"
}
```

---

### PUT /api/v1/rules/{id}

Обновить правило (обычно toggle enabled).

**Кто вызывает:** Frontend

**Request:**
```http
PUT /api/v1/rules/1
Content-Type: application/json
X-Api-Key: <key>

{
  "enabled": false
}
```

**Response 200:** Обновлённый объект Rule

---

### DELETE /api/v1/rules/{id}

Удалить пользовательское правило.

**Кто вызывает:** Frontend

**Request:**
```http
DELETE /api/v1/rules/7
X-Api-Key: <key>
```

**Response 200:** `{"success": true}`

**Response 400:** `{"detail": "Cannot delete preset rule"}` — предустановленные нельзя удалить

**Response 404:** `{"detail": "Rule not found"}`

---

## Items (Товары)

### GET /api/v1/items

Список найденных товаров.

**Кто вызывает:** Frontend, Telegram

**Request:**
```http
GET /api/v1/items
GET /api/v1/items?verdict=OK&search_id=1&limit=20&offset=0
X-Api-Key: <key>
```

**Query params:**
- `verdict` (string, optional): OK, RISK, SKIP, PENDING
- `search_id` (int, optional): фильтр по поиску
- `limit` (int, default 50): количество
- `offset` (int, default 0): смещение

**Response 200:**
```json
[
  {
    "id": "7867391303",
    "title": "iPhone 12 Pro, 128 ГБ",
    "price": 15000,
    "location": "Москва",
    "url": "https://www.avito.ru/7867391303",
    "image_urls": ["https://..."],
    "delivery": true,
    "seller_id": "abc123",
    "reserved": false,
    "description": "Отличное состояние...",
    "ai_verdict": "OK",
    "ai_score": 8,
    "ai_summary": "Хорошее состояние, без дефектов",
    "ai_defects": [],
    "search_id": 1,
    "greeted": true,
    "channel_id": "ch_123456",
    "found_at": "2026-02-03T14:30:00"
  }
]
```

Сортировка: по `found_at` DESC (новые первыми).

---

### GET /api/v1/items/{id}

Детали товара.

**Request:**
```http
GET /api/v1/items/7867391303
X-Api-Key: <key>
```

**Response 200:** Полный объект Item

**Response 404:** `{"detail": "Item not found"}`

---

### POST /api/v1/items

Сохранить найденный товар.

**Кто вызывает:** Worker

**Request:**
```http
POST /api/v1/items
Content-Type: application/json
X-Api-Key: <key>

{
  "id": "7867391303",
  "title": "iPhone 12 Pro, 128 ГБ",
  "price": 15000,
  "location": "Москва",
  "url": "https://www.avito.ru/7867391303",
  "image_urls": ["https://..."],
  "delivery": true,
  "seller_id": "abc123",
  "reserved": false,
  "description": "Отличное состояние...",
  "ai_verdict": "OK",
  "ai_score": 8,
  "ai_summary": "Хорошее состояние, без дефектов",
  "ai_defects": [],
  "search_id": 1,
  "greeted": false,
  "channel_id": null
}
```

**Response 200:** Сохранённый объект Item

**Логика:** INSERT OR REPLACE по `id` — если товар уже есть, обновляет.

---

### PATCH /api/v1/items/{id}

Частичное обновление товара (например, после отправки приветствия).

**Кто вызывает:** Worker

**Request:**
```http
PATCH /api/v1/items/7867391303
Content-Type: application/json
X-Api-Key: <key>

{
  "greeted": true,
  "channel_id": "ch_123456"
}
```

**Response 200:** Обновлённый объект Item

---

### GET /api/v1/items/new

Новые товары для уведомлений (Telegram).

**Кто вызывает:** Telegram Bot

**Request:**
```http
GET /api/v1/items/new?since=2026-02-03T14:00:00
X-Api-Key: <key>
```

**Query params:**
- `since` (ISO 8601, required): timestamp последней проверки

**Response 200:**
```json
[
  {
    "id": "7867391303",
    "title": "iPhone 12 Pro, 128 ГБ",
    "price": 15000,
    "ai_verdict": "OK",
    "ai_score": 8,
    "ai_summary": "Хорошее состояние",
    "url": "https://www.avito.ru/7867391303",
    "greeted": true,
    "found_at": "2026-02-03T14:30:00"
  }
]
```

Только товары с `ai_verdict != 'PENDING'` и `found_at > since`.

---

## Dialogs (Диалоги)

### GET /api/v1/dialogs

Список диалогов с продавцами.

**Кто вызывает:** Frontend, Telegram

**Request:**
```http
GET /api/v1/dialogs
GET /api/v1/dialogs?status=greeted&limit=20
X-Api-Key: <key>
```

**Query params:**
- `status` (string, optional): new, greeted, replied, deal, shipped, done
- `limit` (int, default 20)

**Response 200:**
```json
[
  {
    "id": 1,
    "channel_id": "ch_123456",
    "item_id": "7867391303",
    "item_title": "iPhone 12 Pro, 128 ГБ",
    "item_price": 15000,
    "seller_name": "Александр",
    "status": "greeted",
    "our_message": "Здравствуйте! Интересует ваш iPhone...",
    "search_query": "iPhone 12 Pro",
    "created_at": "2026-02-03T14:35:00",
    "updated_at": "2026-02-03T14:35:00",
    "messages": [
      {
        "id": "msg_001",
        "from_us": true,
        "text": "Здравствуйте! Интересует ваш iPhone...",
        "msg_type": "text",
        "created_at": 1770062100.0
      }
    ]
  }
]
```

---

### POST /api/v1/dialogs

Создать диалог.

**Кто вызывает:** Worker

**Request:**
```http
POST /api/v1/dialogs
Content-Type: application/json
X-Api-Key: <key>

{
  "channel_id": "ch_123456",
  "item_id": "7867391303",
  "item_title": "iPhone 12 Pro, 128 ГБ",
  "item_price": 15000,
  "seller_name": "Александр",
  "our_message": "Здравствуйте! Интересует ваш iPhone...",
  "search_query": "iPhone 12 Pro"
}
```

**Response 200:** Созданный объект Dialog

**Response 409:** `{"detail": "Dialog already exists"}` — если channel_id уже есть

---

### PUT /api/v1/dialogs/{channel_id}

Обновить статус диалога.

**Кто вызывает:** Frontend, Telegram

**Request:**
```http
PUT /api/v1/dialogs/ch_123456
Content-Type: application/json
X-Api-Key: <key>

{
  "status": "replied"
}
```

**Допустимые статусы:** new, greeted, replied, deal, shipped, done

**Response 200:** Обновлённый объект Dialog

**Response 400:** `{"detail": "Invalid status"}`

---

### POST /api/v1/dialogs/{channel_id}/messages

Добавить сообщение в диалог.

**Кто вызывает:** Worker (при получении ответа от продавца)

**Request:**
```http
POST /api/v1/dialogs/ch_123456/messages
Content-Type: application/json
X-Api-Key: <key>

{
  "id": "msg_002",
  "from_us": false,
  "text": "Добрый день! Да, телефон в наличии",
  "msg_type": "text",
  "created_at": 1770062500.0
}
```

**Response 200:** `{"success": true}`

---

## Stats (Статистика)

### GET /api/v1/stats

Общая статистика системы.

**Кто вызывает:** Frontend, Telegram

**Request:**
```http
GET /api/v1/stats
X-Api-Key: <key>
```

**Response 200:**
```json
{
  "searches_active": 5,
  "searches_total": 8,
  "items_total": 150,
  "items_today": 12,
  "items_by_verdict": {
    "OK": 30,
    "RISK": 50,
    "SKIP": 65,
    "PENDING": 5
  },
  "dialogs_total": 25,
  "dialogs_by_status": {
    "new": 0,
    "greeted": 15,
    "replied": 7,
    "deal": 2,
    "shipped": 1,
    "done": 0
  },
  "token_valid": true,
  "token_expires_at": 1770104756,
  "token_hours_left": 12.5,
  "last_sync_at": 1770058954
}
```

---

## Health

### GET /health

Проверка работоспособности.

**Авторизация:** Не требуется

**Request:**
```http
GET /health
```

**Response 200:**
```json
{
  "status": "ok",
  "timestamp": 1770062500,
  "database": "ok"
}
```
