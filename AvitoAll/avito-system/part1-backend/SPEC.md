# Part 1: Backend API

## Обзор

Центральный HTTP-сервер системы. Хранит все данные, предоставляет REST API для остальных компонентов.

**Порт:** 8080
**Стек:** Python 3.11+ / FastAPI / SQLite / SQLAlchemy
**Папка:** `part1-backend/`

## Структура файлов

```
part1-backend/
├── SPEC.md
├── requirements.txt
├── .env.example
└── src/
    ├── server.py          # Точка входа, FastAPI app, CORS
    ├── config.py          # Настройки из .env
    ├── database.py        # SQLAlchemy engine, session, Base
    ├── models.py          # ORM-модели таблиц
    └── routers/
        ├── sessions.py    # POST/GET /api/v1/sessions
        ├── searches.py    # CRUD /api/v1/searches
        ├── rules.py       # CRUD /api/v1/rules
        ├── items.py       # CRUD /api/v1/items
        ├── dialogs.py     # CRUD /api/v1/dialogs
        └── stats.py       # GET /api/v1/stats
```

## .env.example

```env
API_KEY=avito_sync_key_2026
DATABASE_URL=sqlite:///./data/avito.db
HOST=0.0.0.0
PORT=8080
```

## База данных (SQLite)

### Таблица: sessions
```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    device_id TEXT NOT NULL,
    remote_device_id TEXT DEFAULT '',
    user_hash TEXT DEFAULT '',
    user_id INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    cookies_json TEXT DEFAULT '{}',
    synced_at INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Таблица: searches
```sql
CREATE TABLE searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    price_min INTEGER,
    price_max INTEGER,
    delivery BOOLEAN DEFAULT 1,
    location_id INTEGER DEFAULT 621540,
    category_id INTEGER,
    enabled BOOLEAN DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Таблица: rules
```sql
CREATE TABLE rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    is_preset BOOLEAN DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Таблица: items
```sql
CREATE TABLE items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    price INTEGER DEFAULT 0,
    location TEXT DEFAULT '',
    url TEXT NOT NULL,
    image_urls_json TEXT DEFAULT '[]',
    delivery BOOLEAN DEFAULT 0,
    seller_id TEXT DEFAULT '',
    reserved BOOLEAN DEFAULT 0,
    description TEXT DEFAULT '',
    ai_verdict TEXT DEFAULT 'PENDING',
    ai_score INTEGER DEFAULT 0,
    ai_summary TEXT DEFAULT '',
    ai_defects_json TEXT DEFAULT '[]',
    search_id INTEGER REFERENCES searches(id),
    greeted BOOLEAN DEFAULT 0,
    channel_id TEXT,
    found_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Таблица: dialogs
```sql
CREATE TABLE dialogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT UNIQUE NOT NULL,
    item_id TEXT REFERENCES items(id),
    item_title TEXT DEFAULT '',
    item_price INTEGER DEFAULT 0,
    seller_name TEXT DEFAULT '',
    status TEXT DEFAULT 'new',
    our_message TEXT DEFAULT '',
    search_query TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Таблица: messages
```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    channel_id TEXT REFERENCES dialogs(channel_id),
    from_us BOOLEAN DEFAULT 0,
    text TEXT DEFAULT '',
    msg_type TEXT DEFAULT 'text',
    created_at REAL
);
CREATE INDEX idx_messages_channel ON messages(channel_id);
```

## API Endpoints

### Sessions

**POST /api/v1/sessions** — Сохранить/обновить токены
- Header: `X-Api-Key`
- Body: `SessionSchema` (см. contracts/session.schema.json)
- Response: `{"success": true, "expires_at": 1770104756}`
- Логика: INSERT или UPDATE последнюю запись

**GET /api/v1/session** — Получить актуальные токены
- Header: `X-Api-Key`
- Response: `SessionSchema` (последняя запись)
- 404 если нет токенов

### Searches

**GET /api/v1/searches** — Список поисков
- Query: `?enabled=true` (опционально)
- Response: `[SearchSchema, ...]`

**POST /api/v1/searches** — Создать
- Body: `{query, price_min?, price_max?, delivery?, location_id?, category_id?}`
- Response: `SearchSchema` с id

**PUT /api/v1/searches/{id}** — Обновить
- Body: частичное обновление полей
- Response: `SearchSchema`

**DELETE /api/v1/searches/{id}** — Удалить
- Response: `{"success": true}`

### Rules

**GET /api/v1/rules** — Список правил
- Query: `?enabled=true`
- Response: `[RuleSchema, ...]`

**POST /api/v1/rules** — Создать
- Body: `{text, enabled?, is_preset?}`
- Response: `RuleSchema`

**PUT /api/v1/rules/{id}** — Обновить
- Response: `RuleSchema`

**DELETE /api/v1/rules/{id}** — Удалить
- Нельзя удалить `is_preset=true`
- Response: `{"success": true}`

### Items

**GET /api/v1/items** — Список товаров
- Query: `?search_id=1&verdict=OK&limit=50&offset=0`
- Response: `[ItemSchema, ...]`
- Сортировка: по `found_at` DESC

**GET /api/v1/items/{id}** — Детали товара
- Response: `ItemSchema`

**POST /api/v1/items** — Сохранить найденный товар
- Body: `ItemSchema`
- Response: `ItemSchema`
- Логика: INSERT OR REPLACE (по id)

**GET /api/v1/items/new** — Новые товары для уведомлений
- Query: `?since=<ISO timestamp>`
- Response: `[ItemSchema, ...]`
- Только товары с `ai_verdict != 'PENDING'`

### Dialogs

**GET /api/v1/dialogs** — Список диалогов
- Query: `?status=greeted&limit=20`
- Response: `[DialogSchema with messages, ...]`

**POST /api/v1/dialogs** — Создать диалог
- Body: `{channel_id, item_id, item_title, item_price, seller_name, our_message, search_query}`

**PUT /api/v1/dialogs/{channel_id}** — Обновить статус
- Body: `{status: "replied"}`
- Допустимые статусы: new, greeted, replied, deal, shipped, done

### Stats

**GET /api/v1/stats** — Статистика
- Response:
```json
{
  "searches_active": 5,
  "items_total": 150,
  "items_today": 12,
  "items_by_verdict": {"OK": 30, "RISK": 50, "SKIP": 70},
  "dialogs_total": 20,
  "dialogs_by_status": {"greeted": 10, "replied": 5, "deal": 3},
  "token_valid": true,
  "token_expires_at": 1770104756,
  "token_hours_left": 12.5
}
```

### Health

**GET /health**
- Response: `{"status": "ok", "timestamp": 1770058954}`

## Авторизация

Middleware проверяет `X-Api-Key` заголовок на всех `/api/v1/*` endpoints.
`/health` — без авторизации.

## CORS

Разрешить `http://localhost:3000` и `*` для dev.

## При первом запуске

1. Создать БД и таблицы (SQLAlchemy create_all)
2. Вставить предустановленные rules:
   - "iCloud Lock / Activation Lock — пропустить"
   - "Разбит экран / трещины дисплея — пропустить"
   - "Разбита задняя крышка — пропустить"
   - "Не включается / чёрный экран — пропустить"
   - "Подозрительно низкая цена (< 30% от рыночной) — предупредить"
   - "Продавец без отзывов / рейтинг < 3.0 — предупредить"

## Зависимости (requirements.txt)

```
fastapi>=0.104.0
uvicorn>=0.24.0
sqlalchemy>=2.0.0
pydantic>=2.0.0
python-dotenv>=1.0.0
```

## Запуск

```bash
cd part1-backend
pip install -r requirements.txt
cp .env.example .env
python src/server.py
# → http://0.0.0.0:8080
```
