# Avito System — Структура базы данных

## Обзор

Backend (Part 1) использует **SQLite** — файловая БД без отдельного сервера.

**Файл:** `data/avito.db`
**ORM:** SQLAlchemy
**Миграции:** Alembic (опционально, для production)

```
data/avito.db
├── sessions        # Токены авторизации Avito
├── searches        # Поисковые запросы
├── rules           # AI-правила (красные флаги)
├── items           # Найденные товары
├── dialogs         # Диалоги с продавцами
└── messages        # Сообщения в диалогах
```

---

## ER-диаграмма

```
┌──────────────┐
│   sessions   │     Токены от Part 5/6
│──────────────│     (одна активная запись)
│ id           │
│ session_token│
│ fingerprint  │
│ device_id    │
│ expires_at   │
│ ...          │
└──────────────┘

┌──────────────┐      ┌──────────────┐
│   searches   │      │    rules     │
│──────────────│      │──────────────│
│ id        PK │      │ id        PK │
│ query        │      │ text         │
│ price_min    │      │ enabled      │
│ price_max    │      │ is_preset    │
│ enabled      │      │ created_at   │
│ ...          │      └──────────────┘
└──────┬───────┘        Worker берёт enabled=true
       │                и передаёт AI при анализе
       │ search_id (FK)
       ▼
┌──────────────┐
│    items     │      Найденные товары
│──────────────│
│ id        PK │ ← Avito item ID
│ search_id FK │ → searches.id
│ title        │
│ price        │
│ ai_verdict   │  OK / RISK / SKIP / PENDING
│ ai_score     │  1-10
│ ai_defects   │  JSON array
│ greeted      │  Приветствие отправлено?
│ channel_id   │  ID чата в Avito
│ ...          │
└──────┬───────┘
       │ channel_id
       ▼
┌──────────────┐
│   dialogs    │      Диалоги с продавцами
│──────────────│
│ id        PK │
│ channel_id   │ ← Avito channel ID (u2i-xxx)
│ item_id   FK │ → items.id
│ seller_id    │
│ status       │  new → greeted → replied → deal → done
│ ...          │
└──────┬───────┘
       │ dialog_id (FK)
       ▼
┌──────────────┐
│   messages   │      Сообщения
│──────────────│
│ id        PK │
│ dialog_id FK │ → dialogs.id
│ direction    │  incoming / outgoing
│ text         │
│ type         │  text / image / voice / file
│ avito_msg_id │  ID сообщения в Avito
│ created_at   │
└──────────────┘
```

---

## Таблицы

### 1. sessions — Токены авторизации

Хранит текущую активную сессию Avito. Обновляется Part 5 (Token Bridge) или Part 6 (Android Token).

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|----------|
| `id` | INTEGER | PK, AUTOINCREMENT | ID записи |
| `session_token` | TEXT | NOT NULL | JWT (HS512, 24ч) |
| `refresh_token` | TEXT | | Токен обновления |
| `fingerprint` | TEXT | NOT NULL | Заголовок `f` для API |
| `device_id` | TEXT | | UUID устройства |
| `remote_device_id` | TEXT | | Remote device ID |
| `user_id` | INTEGER | | Avito user ID (из JWT) |
| `user_hash` | TEXT | | Hash для WebSocket |
| `expires_at` | INTEGER | NOT NULL | Unix timestamp истечения JWT |
| `cookies` | TEXT | | JSON: {1f_uid, u, v, _avisc} |
| `synced_at` | INTEGER | | Unix timestamp последней синхронизации |
| `source` | TEXT | | "bridge" (Part 5) или "android" (Part 6) |
| `created_at` | TIMESTAMP | DEFAULT NOW | |
| `updated_at` | TIMESTAMP | DEFAULT NOW | |

**Индексы:**
- `idx_sessions_expires` ON (expires_at)

**Примечания:**
- Обычно одна активная запись (latest by synced_at)
- При POST `/api/v1/sessions` — upsert (обновляет или создаёт)
- Worker и Messenger берут последнюю валидную сессию

```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_token TEXT NOT NULL,
    refresh_token TEXT,
    fingerprint TEXT NOT NULL,
    device_id TEXT,
    remote_device_id TEXT,
    user_id INTEGER,
    user_hash TEXT,
    expires_at INTEGER NOT NULL,
    cookies TEXT,
    synced_at INTEGER,
    source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 2. searches — Поисковые запросы

Создаются через Web Panel (Part 2) или Telegram Bot (Part 4, команда `/add`).

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|----------|
| `id` | INTEGER | PK, AUTOINCREMENT | ID поиска |
| `query` | TEXT | NOT NULL | Поисковый запрос ("iPhone 12 Pro") |
| `price_min` | INTEGER | | Минимальная цена (₽) |
| `price_max` | INTEGER | | Максимальная цена (₽) |
| `delivery` | BOOLEAN | DEFAULT true | С Авито Доставкой |
| `location_id` | INTEGER | DEFAULT 621540 | ID региона (621540 = вся Россия) |
| `category_id` | INTEGER | | ID категории Avito |
| `enabled` | BOOLEAN | DEFAULT true | Активен ли поиск |
| `created_at` | TIMESTAMP | DEFAULT NOW | |
| `updated_at` | TIMESTAMP | DEFAULT NOW | |

**Индексы:**
- `idx_searches_enabled` ON (enabled)

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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 3. rules — AI-правила (красные флаги)

5 предустановленных + пользовательские. Worker передаёт все enabled=true правила в промпт AI.

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|----------|
| `id` | INTEGER | PK, AUTOINCREMENT | ID правила |
| `text` | TEXT | NOT NULL | Описание красного флага |
| `enabled` | BOOLEAN | DEFAULT true | Активно ли правило |
| `is_preset` | BOOLEAN | DEFAULT false | Предустановленное (нельзя удалить) |
| `created_at` | TIMESTAMP | DEFAULT NOW | |

**Предустановленные правила (seed data):**

| id | text | Вердикт |
|----|------|---------|
| 1 | iCloud Lock / Activation Lock — пропустить | SKIP |
| 2 | Разбит экран / трещины дисплея — пропустить | SKIP |
| 3 | Разбита задняя крышка — пропустить | SKIP |
| 4 | Не включается / чёрный экран — пропустить | SKIP |
| 5 | Подозрительно низкая цена (< 30% от рыночной) — предупредить | RISK |

```sql
CREATE TABLE rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    is_preset BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed data
INSERT INTO rules (text, enabled, is_preset) VALUES
    ('iCloud Lock / Activation Lock — пропустить', 1, 1),
    ('Разбит экран / трещины дисплея — пропустить', 1, 1),
    ('Разбита задняя крышка — пропустить', 1, 1),
    ('Не включается / чёрный экран — пропустить', 1, 1),
    ('Подозрительно низкая цена (< 30% от рыночной) — предупредить', 1, 1);
```

---

### 4. items — Найденные товары

Worker записывает каждый найденный уникальный товар с результатом AI-анализа.

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|----------|
| `id` | TEXT | PK | Avito item ID (строка) |
| `search_id` | INTEGER | FK → searches.id | Какой поиск нашёл |
| `title` | TEXT | NOT NULL | Название товара |
| `price` | INTEGER | NOT NULL | Цена (₽) |
| `location` | TEXT | | Город |
| `url` | TEXT | NOT NULL | URL на Avito |
| `image_urls` | TEXT | | JSON array URL картинок |
| `delivery` | BOOLEAN | | С доставкой |
| `seller_id` | TEXT | | ID продавца |
| `description` | TEXT | | Описание объявления |
| `reserved` | BOOLEAN | DEFAULT false | Зарезервирован |
| `ai_verdict` | TEXT | DEFAULT 'PENDING' | OK / RISK / SKIP / PENDING |
| `ai_score` | INTEGER | | 1-10 |
| `ai_summary` | TEXT | | Краткий вывод AI |
| `ai_defects` | TEXT | | JSON array найденных дефектов |
| `greeted` | BOOLEAN | DEFAULT false | Приветствие отправлено |
| `channel_id` | TEXT | | ID чата в Avito (u2i-xxx) |
| `notified` | BOOLEAN | DEFAULT false | Telegram уведомление отправлено |
| `found_at` | TIMESTAMP | DEFAULT NOW | Когда найден |

**Индексы:**
- `idx_items_search` ON (search_id)
- `idx_items_verdict` ON (ai_verdict)
- `idx_items_found` ON (found_at DESC)
- `idx_items_notified` ON (notified) WHERE notified = 0

```sql
CREATE TABLE items (
    id TEXT PRIMARY KEY,
    search_id INTEGER REFERENCES searches(id),
    title TEXT NOT NULL,
    price INTEGER NOT NULL,
    location TEXT,
    url TEXT NOT NULL,
    image_urls TEXT,
    delivery BOOLEAN,
    seller_id TEXT,
    description TEXT,
    reserved BOOLEAN DEFAULT 0,
    ai_verdict TEXT DEFAULT 'PENDING',
    ai_score INTEGER,
    ai_summary TEXT,
    ai_defects TEXT,
    greeted BOOLEAN DEFAULT 0,
    channel_id TEXT,
    notified BOOLEAN DEFAULT 0,
    found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 5. dialogs — Диалоги с продавцами

Создаются при авто-приветствии (Worker/Messenger) или вручную.

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|----------|
| `id` | INTEGER | PK, AUTOINCREMENT | ID диалога |
| `channel_id` | TEXT | UNIQUE, NOT NULL | Avito channel ID (u2i-xxx) |
| `item_id` | TEXT | FK → items.id | Связанный товар |
| `seller_id` | TEXT | | ID/hash продавца |
| `seller_name` | TEXT | | Имя продавца |
| `status` | TEXT | DEFAULT 'new' | Статус диалога |
| `last_message_at` | TIMESTAMP | | Время последнего сообщения |
| `unread_count` | INTEGER | DEFAULT 0 | Непрочитанных |
| `created_at` | TIMESTAMP | DEFAULT NOW | |
| `updated_at` | TIMESTAMP | DEFAULT NOW | |

**Статусы диалога:**

```
new → greeted → replied → deal → shipped → done
                  │
                  └→ rejected (продавец отказал)
```

| Статус | Описание |
|--------|----------|
| `new` | Чат создан, сообщение не отправлено |
| `greeted` | Приветствие отправлено |
| `replied` | Продавец ответил |
| `deal` | Договорились о сделке |
| `shipped` | Товар отправлен |
| `done` | Завершено |
| `rejected` | Продавец отказал |

**Индексы:**
- `idx_dialogs_channel` ON (channel_id) — UNIQUE
- `idx_dialogs_item` ON (item_id)
- `idx_dialogs_status` ON (status)

```sql
CREATE TABLE dialogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT UNIQUE NOT NULL,
    item_id TEXT REFERENCES items(id),
    seller_id TEXT,
    seller_name TEXT,
    status TEXT DEFAULT 'new',
    last_message_at TIMESTAMP,
    unread_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 6. messages — Сообщения в диалогах

Каждое сообщение (входящее и исходящее) из Avito Messenger.

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|----------|
| `id` | INTEGER | PK, AUTOINCREMENT | ID записи |
| `dialog_id` | INTEGER | FK → dialogs.id, NOT NULL | Связанный диалог |
| `avito_msg_id` | TEXT | UNIQUE | ID сообщения в Avito |
| `direction` | TEXT | NOT NULL | `incoming` / `outgoing` |
| `type` | TEXT | DEFAULT 'text' | text / image / voice / location / file |
| `text` | TEXT | | Текст (для type=text) |
| `media_id` | TEXT | | imageId / voiceId / fileId |
| `media_name` | TEXT | | Имя файла (для type=file) |
| `media_size` | INTEGER | | Размер файла (байт) |
| `sender_hash` | TEXT | | Hash отправителя (fromUid) |
| `is_read` | BOOLEAN | DEFAULT false | Прочитано |
| `is_deleted` | BOOLEAN | DEFAULT false | Удалено |
| `created_at` | TIMESTAMP | DEFAULT NOW | Время создания |

**Индексы:**
- `idx_messages_dialog` ON (dialog_id, created_at DESC)
- `idx_messages_avito_id` ON (avito_msg_id) — UNIQUE

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dialog_id INTEGER NOT NULL REFERENCES dialogs(id),
    avito_msg_id TEXT UNIQUE,
    direction TEXT NOT NULL,
    type TEXT DEFAULT 'text',
    text TEXT,
    media_id TEXT,
    media_name TEXT,
    media_size INTEGER,
    sender_hash TEXT,
    is_read BOOLEAN DEFAULT 0,
    is_deleted BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Дополнительные таблицы

### 7. tracker (Worker, локальная) — Дедупликация

**Расположение:** Worker (Part 3), локальный SQLite `data/tracker.db` — НЕ в основной БД.

| Колонка | Тип | Описание |
|---------|-----|----------|
| `item_id` | TEXT PK | Avito item ID |
| `search_id` | INTEGER | ID поиска |
| `first_seen` | TIMESTAMP | Когда впервые увидели |

**Retention:** 7 дней, затем очистка.

```sql
CREATE TABLE tracker (
    item_id TEXT PRIMARY KEY,
    search_id INTEGER,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Очистка старых записей
DELETE FROM tracker WHERE first_seen < datetime('now', '-7 days');
```

---

## Связи между таблицами

```
sessions (1) ←── используется ──→ Worker, Messenger (read-only)

searches (1) ←──── search_id ────→ (N) items
items (1)    ←──── item_id ──────→ (0..1) dialogs
dialogs (1)  ←──── dialog_id ────→ (N) messages
rules        ←── нет FK, читается Worker при каждом анализе
```

## Потоки данных

### Запись (кто пишет в какую таблицу)

| Таблица | Part 1 | Part 2 | Part 3 | Part 4 | Part 5 | Part 6 | Part 7 |
|---------|:------:|:------:|:------:|:------:|:------:|:------:|:------:|
| sessions | — | — | — | — | **W** | **W** | — |
| searches | **W** | ← API | — | ← API | — | — | — |
| rules | **W** | ← API | — | — | — | — | — |
| items | **W** | — | ← API | — | — | — | — |
| dialogs | **W** | — | ← API | — | — | — | ← API |
| messages | **W** | — | — | — | — | — | ← API |

**W** = пишет напрямую, **← API** = пишет через Backend REST API.

### Чтение (кто читает какую таблицу)

| Таблица | Part 1 | Part 2 | Part 3 | Part 4 | Part 7 |
|---------|:------:|:------:|:------:|:------:|:------:|
| sessions | **R** | — | ← API | — | ← API |
| searches | **R** | ← API | ← API | ← API | — |
| rules | **R** | ← API | ← API | — | — |
| items | **R** | ← API | — | ← API | — |
| dialogs | **R** | ← API | — | — | ← API |
| messages | **R** | ← API | — | — | ← API |

---

## Миграции

### Создание БД

```python
# Part 1: Backend — при первом запуске
from sqlalchemy import create_engine
from models import Base

engine = create_engine("sqlite:///data/avito.db")
Base.metadata.create_all(engine)
```

### Seed данных

```python
# Предустановленные правила
def seed_rules(session):
    presets = [
        "iCloud Lock / Activation Lock — пропустить",
        "Разбит экран / трещины дисплея — пропустить",
        "Разбита задняя крышка — пропустить",
        "Не включается / чёрный экран — пропустить",
        "Подозрительно низкая цена (< 30% от рыночной) — предупредить",
    ]
    for text in presets:
        if not session.query(Rule).filter_by(text=text).first():
            session.add(Rule(text=text, enabled=True, is_preset=True))
    session.commit()
```

---

## Размеры и лимиты

| Параметр | Оценка |
|----------|--------|
| Средний размер записи items | ~2 KB |
| Средний размер записи messages | ~500 B |
| При 100 товарах/день | ~200 KB/день |
| При 1000 сообщений/день | ~500 KB/день |
| Очистка tracker | автоматическая, 7 дней |
| Backup | копирование `data/avito.db` |

SQLite поддерживает до **281 TB** на файл. Для данного проекта хватит на годы.

---

## Backup

```bash
# Простой backup
cp data/avito.db data/avito_backup_$(date +%Y%m%d).db

# С блокировкой (на production)
sqlite3 data/avito.db ".backup 'data/avito_backup.db'"
```
