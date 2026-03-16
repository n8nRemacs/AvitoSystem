# Avito System — Полное описание подсистемы

## Оглавление

1. [Общая архитектура](#1-общая-архитектура)
2. [Подсистемы и их расположение](#2-подсистемы-и-их-расположение)
3. [Backend (avito-xapi)](#3-backend-avito-xapi)
4. [Frontend (avito-frontend)](#4-frontend-avito-frontend)
5. [Farm Agent (avito-farm-agent)](#5-farm-agent-avito-farm-agent)
6. [База данных (Supabase)](#6-база-данных-supabase)
7. [Потоки данных и взаимодействие](#7-потоки-данных-и-взаимодействие)
8. [Аутентификация и авторизация](#8-аутентификация-и-авторизация)
9. [Внешний API для интеграции](#9-внешний-api-для-интеграции)
10. [Деплой и инфраструктура](#10-деплой-и-инфраструктура)
11. [Ключевые технические решения](#11-ключевые-технические-решения)

---

## 1. Общая архитектура

```
                                     ┌──────────────────┐
                                     │    Cloudflare     │
                                     │  avito.newlcd.ru  │
                                     └────────┬─────────┘
                                              │
                                     ┌────────┴─────────┐
                                     │   VPS (Nginx)     │
                                     │  155.212.221.67   │
                                     │  SSL termination  │
                                     └───┬─────────┬────┘
                                  /api/  │         │  /
                           ┌─────────────┘         └──────────────┐
                           │ SSH tunnel :8080            :3000     │
                    ┌──────┴──────────┐          ┌────────────────┴─┐
                    │  Backend (xapi) │          │  Frontend (Vue)   │
                    │  FastAPI :8080  │◄─────────│  Vite/Nginx :3000 │
                    │  Python 3.14   │  HTTP     │  Vue 3 + Pinia    │
                    └──┬──────┬──────┘          └───────────────────┘
                       │      │
              ┌────────┘      └──────────┐
              │                          │
     ┌────────┴────────┐      ┌──────────┴──────────┐
     │   Supabase      │      │   Avito API          │
     │   (PostgreSQL)  │      │   app.avito.ru       │
     │   PostgREST     │      │   socket.avito.ru    │
     │   8 таблиц      │      │   www.avito.ru       │
     └─────────────────┘      └──────────┬──────────┘
                                         │
                              ┌──────────┴──────────┐
                              │   Farm Agent         │
                              │   (Android device)   │
                              │   Frida + ADB        │
                              └─────────────────────┘
```

**Принцип:** Avito System — SaaS-платформа, предоставляющая API-доступ к функциям Avito (мессенджер, поиск, звонки). Каждый клиент (тенант) получает API-ключ и работает через единый HTTP API. Backend маршрутизирует запросы к Avito, имитируя мобильное приложение.

---

## 2. Подсистемы и их расположение

| # | Подсистема | Расположение | Технологии | Назначение |
|---|-----------|-------------|------------|-----------|
| 1 | **Backend API** | `avito-xapi/` | FastAPI, Python 3.14, curl_cffi | HTTP/WS Gateway к Avito API |
| 2 | **Frontend SPA** | `avito-frontend/` | Vue 3, Vite, Pinia, TailwindCSS | Панель управления для тенанта |
| 3 | **Farm Agent** | `avito-farm-agent/` | Python, Frida, ADB | Автообновление токенов на устройствах |
| 4 | **База данных** | Supabase Cloud | PostgreSQL, PostgREST | Хранение тенантов, сессий, аудита |
| 5 | **SQL миграции** | `supabase/migrations/` | SQL | Схема БД |
| 6 | **Документация** | `DOCS/` | Markdown | API-спеки, архитектура, моки |

### Дерево файлов

```
AvitoSystem/
├── avito-xapi/                          # BACKEND
│   ├── src/
│   │   ├── main.py                      # Точка входа FastAPI
│   │   ├── config.py                    # Pydantic Settings (.env)
│   │   ├── dependencies.py              # DI: get_current_tenant()
│   │   ├── middleware/
│   │   │   ├── auth.py                  # API Key → Tenant resolution
│   │   │   └── error_handler.py         # Structured JSON errors
│   │   ├── models/
│   │   │   ├── common.py                # ErrorResponse, HealthResponse
│   │   │   ├── tenant.py                # Tenant, Toolkit, ApiKeyInfo, TenantContext
│   │   │   ├── session.py               # SessionUpload, SessionStatus, AlertInfo
│   │   │   ├── messenger.py             # Channel, Message, SendMessageReq
│   │   │   ├── calls.py                 # CallRecord, CallHistoryResponse
│   │   │   └── search.py                # ItemCard, ItemDetail, SearchResponse
│   │   ├── routers/
│   │   │   ├── health.py                # GET /health, /ready
│   │   │   ├── sessions.py              # CRUD сессий Avito
│   │   │   ├── auth_browser.py          # WebSocket: удалённый браузер
│   │   │   ├── messenger.py             # Каналы, сообщения, typing
│   │   │   ├── calls.py                 # История звонков, записи
│   │   │   ├── search.py                # Поиск объявлений
│   │   │   └── farm.py                  # Token Farm: устройства, привязки
│   │   ├── workers/
│   │   │   ├── jwt_parser.py            # Декодирование JWT без верификации
│   │   │   ├── rate_limiter.py          # TokenBucket (async)
│   │   │   ├── session_reader.py        # SessionData из Supabase
│   │   │   ├── base_client.py           # Headers, curl_cffi, rate limit
│   │   │   ├── http_client.py           # HTTP REST вызовы к Avito
│   │   │   ├── ws_client.py             # WebSocket JSON-RPC к Avito
│   │   │   ├── token_monitor.py         # Мониторинг TTL токенов
│   │   │   └── browser_auth.py          # Playwright: браузер для авторизации
│   │   └── storage/
│   │       └── supabase.py              # PostgREST клиент (не SDK)
│   └── tests/                           # 84 теста (pytest)
│
├── avito-frontend/                      # FRONTEND
│   ├── src/
│   │   ├── App.vue                      # Layout + Router
│   │   ├── api/index.js                 # Axios + X-Api-Key interceptor
│   │   ├── router/index.js              # 4 маршрута: auth, messenger, search, farm
│   │   ├── stores/                      # Pinia stores (auth, messenger, search, farm)
│   │   ├── views/                       # 4 страницы (Auth, Messenger, Search, Farm)
│   │   └── components/                  # 17 Vue-компонентов
│   └── vite.config.js
│
├── avito-farm-agent/                    # FARM AGENT
│   ├── agent.py                         # Daemon: heartbeat + schedule + refresh
│   ├── grab_token.js                    # Frida: извлечение токенов
│   ├── spoof_fingerprint.js             # Frida: подмена fingerprint
│   ├── sniff_fingerprint.js             # Frida: разведка fingerprint
│   ├── refresh.sh                       # Shell: запуск/остановка Avito
│   └── config.json                      # Конфигурация агента
│
├── supabase/migrations/                 # SQL МИГРАЦИИ
│   ├── 001_init.sql                     # 8 таблиц + индексы + RLS
│   └── 002_seed.sql                     # Тестовые данные
│
├── docker-compose.yml                   # Оркестрация: xapi + frontend
└── DOCS/                                # Документация
```

---

## 3. Backend (avito-xapi)

### 3.1. Слои архитектуры

```
Входящий запрос
      │
      ▼
┌── Middleware ───────────────────────────────────┐
│  ErrorHandlerMiddleware → ловит все исключения  │
│  ApiKeyAuthMiddleware   → X-Api-Key → tenant    │
│  CORSMiddleware         → CORS headers          │
└──────────────────────────┬─────────────────────┘
                           │
                           ▼
┌── Routers ─────────────────────────────────────┐
│  health.py    → /health, /ready                │
│  sessions.py  → /api/v1/sessions/*             │
│  messenger.py → /api/v1/messenger/*            │
│  calls.py     → /api/v1/calls/*                │
│  search.py    → /api/v1/search/*               │
│  farm.py      → /api/v1/farm/*                 │
│  auth_browser → ws://.../api/v1/auth/browser   │
└──────────────────────────┬─────────────────────┘
                           │
                           ▼
┌── Workers (бизнес-логика) ─────────────────────┐
│  session_reader.py → загрузка сессий из БД     │
│  http_client.py    → HTTP запросы к Avito      │
│  ws_client.py      → WebSocket к socket.avito  │
│  jwt_parser.py     → парсинг JWT               │
│  token_monitor.py  → алерты по TTL             │
│  rate_limiter.py   → TokenBucket               │
│  browser_auth.py   → Playwright менеджер       │
│  base_client.py    → общие headers + TLS       │
└──────────────────────────┬─────────────────────┘
                           │
                           ▼
┌── Storage ─────────────────────────────────────┐
│  supabase.py → PostgREST клиент               │
│  .table().select().eq().execute()              │
└────────────────────────────────────────────────┘
```

### 3.2. Роутеры и эндпоинты

#### Health (`routers/health.py`)
| Метод | Путь | Описание | Авторизация |
|-------|------|----------|-------------|
| GET | `/health` | Статус сервиса | Нет |
| GET | `/ready` | Готовность (проверка Supabase) | Нет |

#### Sessions (`routers/sessions.py`)
| Метод | Путь | Описание | Feature |
|-------|------|----------|---------|
| POST | `/api/v1/sessions` | Загрузить сессию (JWT + cookies) | `avito.sessions` |
| GET | `/api/v1/sessions/current` | Текущая сессия: user_id, TTL, источник | `avito.sessions` |
| DELETE | `/api/v1/sessions` | Деактивировать сессию | `avito.sessions` |
| GET | `/api/v1/sessions/history` | История всех сессий тенанта | `avito.sessions` |
| GET | `/api/v1/sessions/token-details` | Декодированный JWT (header + payload) | `avito.sessions` |
| GET | `/api/v1/sessions/alerts` | Алерты по TTL (warning / critical / expired) | `avito.sessions` |

#### Messenger (`routers/messenger.py`)
| Метод | Путь | Описание | Feature |
|-------|------|----------|---------|
| GET | `/api/v1/messenger/channels` | Список чатов (пагинация) | `avito.messenger` |
| GET | `/api/v1/messenger/channels/{id}` | Детали канала | `avito.messenger` |
| GET | `/api/v1/messenger/channels/{id}/messages` | История сообщений | `avito.messenger` |
| POST | `/api/v1/messenger/channels/{id}/messages` | Отправить текст | `avito.messenger` |
| POST | `/api/v1/messenger/channels/{id}/read` | Прочитать чат | `avito.messenger` |
| POST | `/api/v1/messenger/channels/{id}/typing` | Индикатор набора | `avito.messenger` |
| POST | `/api/v1/messenger/channels/by-item` | Создать чат по item_id | `avito.messenger` |
| POST | `/api/v1/messenger/channels/by-user` | Создать чат по user_hash | `avito.messenger` |
| GET | `/api/v1/messenger/unread-count` | Кол-во непрочитанных | `avito.messenger` |

#### Calls (`routers/calls.py`)
| Метод | Путь | Описание | Feature |
|-------|------|----------|---------|
| GET | `/api/v1/calls/history` | История звонков | `avito.calls` |
| GET | `/api/v1/calls/{id}/recording` | Запись звонка (MP3) | `avito.calls` |

#### Search (`routers/search.py`)
| Метод | Путь | Описание | Feature |
|-------|------|----------|---------|
| GET | `/api/v1/search/items` | Поиск объявлений (query, цена, город) | `avito.search` |
| GET | `/api/v1/search/items/{id}` | Карточка объявления | `avito.search` |

#### Farm (`routers/farm.py`)
| Метод | Путь | Описание | Feature |
|-------|------|----------|---------|
| POST | `/api/v1/farm/tokens` | Загрузка токена от Farm Agent | `avito.farm` |
| GET | `/api/v1/farm/schedule` | Расписание refresh для устройств | `avito.farm` |
| POST | `/api/v1/farm/heartbeat` | Heartbeat от устройства | Без auth |
| GET | `/api/v1/farm/devices` | Список устройств фермы | `avito.farm` |
| POST | `/api/v1/farm/devices` | Зарегистрировать устройство | `avito.farm` |
| GET | `/api/v1/farm/bindings` | Привязки аккаунтов | `avito.farm` |
| POST | `/api/v1/farm/bindings` | Привязать аккаунт | `avito.farm` |
| DELETE | `/api/v1/farm/bindings/{id}` | Отвязать аккаунт | `avito.farm` |

#### Browser Auth (`routers/auth_browser.py`)
| Метод | Путь | Описание | Авторизация |
|-------|------|----------|-------------|
| WS | `/api/v1/auth/browser?api_key=xxx` | Удалённый браузер для авторизации | API Key в query |

**Протокол WebSocket (Browser Auth):**
```
Client → Server:
  {"type": "start"}                      — Запустить браузер
  {"type": "click", "x": 100, "y": 200} — Клик по координатам
  {"type": "key", "key": "Enter"}        — Нажатие клавиши
  {"type": "text", "text": "hello"}      — Ввод текста
  {"type": "close"}                      — Закрыть сессию

Server → Client:
  {"type": "status", "status": "started"}     — Браузер запущен
  {"type": "screenshot", "data": "base64..."} — Скриншот (JPEG)
  {"type": "auth_complete", "tokens": {...}}  — Авторизация успешна
  {"type": "error", "message": "..."}         — Ошибка
```

### 3.3. Workers (ядро бизнес-логики)

#### `base_client.py` — Базовый HTTP-клиент Avito
- **TLS-имперсонация**: `curl_cffi` с профилем `chrome120` для обхода QRATOR
- **12+ обязательных заголовков**: User-Agent, X-Session, X-DeviceId, X-RemoteDeviceId, fingerprint (`f`), X-App, X-Platform, X-AppVersion, Cookie, X-Date, Accept-Encoding
- **Rate limiting**: TokenBucket (настраивается через `settings.rate_limit_rps`)
- **URL**: `https://app.avito.ru/api`

#### `http_client.py` — HTTP REST вызовы
- Наследует `BaseAvitoClient`
- Методы: `get_channels()`, `get_messages()`, `send_text()`, `mark_read()`, `send_typing()`, `create_channel_by_item()`, `create_channel_by_user()`, `get_unread_count()`, `get_call_history()`, `get_call_recording()`, `search_items()`, `get_item_details()`
- **Нормализация** (выполняется в роутерах):
  - `body.text.text` → `text`
  - `authorId` → `author_id`
  - `createdAt` (nanoseconds) → ISO 8601 datetime
  - `isRead` → `is_read`
  - `category=1` всегда (category=0 вызывает HTTP 500 у Avito)

#### `ws_client.py` — WebSocket JSON-RPC к Avito
- **Протокол**: JSON-RPC 2.0 через `wss://socket.avito.ru/socket`
- **TLS**: curl_cffi с Chrome 120 импёрсонацией
- **Фоновые потоки**: `_recv_loop` (приём), `_ping_loop` (ping каждые 25с)
- **Реконнект**: экспоненциальный backoff, до 5 попыток, макс. задержка 30с
- **Событийная система**: `on(event, handler)` для `message`, `typing`, `read`, `connected`, `disconnected`
- **RPC-методы**: `get_chats()`, `get_messages()`, `send_text_message()`, `send_typing()`, `mark_read()`, `create_channel_by_item()`, `get_unread_count()` и др.
- **Request/Response корреляция**: через `concurrent.futures.Future` и `msg_id`

#### `jwt_parser.py` — Парсинг JWT
- Декодирование header и payload через base64 (без верификации подписи HS512)
- `is_expired(token)`, `time_left(token)` в секундах
- Поля: `user_id`, `sub`, `iat`, `exp`, `install_id`, `client_id`, `platform`

#### `token_monitor.py` — Мониторинг TTL
- Пороги: warning (30 мин), critical (10 мин), expired (0)
- `get_alerts_for_session(session)` → список алертов

#### `session_reader.py` — Загрузка сессий
- `SessionData` dataclass: session_token, refresh_token, device_id, fingerprint, user_id, cookies и др.
- `load_active_session(tenant_id)` — последняя активная сессия из Supabase
- `load_session_history(tenant_id)` — вся история (до 50)

#### `browser_auth.py` — Playwright менеджер
- Headless Chromium с мобильным viewport (420x900)
- Стриминг скриншотов (JPEG base64, ~2 кадра/сек)
- Relay событий клавиатуры/мыши от фронтенда
- Автоматическое извлечение cookies/tokens после логина
- Реестр сессий: одна активная сессия на тенанта

#### `rate_limiter.py` — Async TokenBucket
- Настраиваемые `rate` (RPS) и `burst`
- `await wait_and_acquire()` — ожидание токена перед запросом

### 3.4. Storage (`supabase.py`)

Лёгкий PostgREST клиент вместо официального `supabase-py` SDK (SDK не компилируется на Python 3.14 из-за зависимости `pyroaring`).

**API (совместим с supabase-py):**
```python
sb = get_supabase()
sb.table("tenants").select("*").eq("id", tenant_id).execute()
sb.table("avito_sessions").insert({...}).execute()
sb.table("audit_log").update({...}).eq("id", id).execute()
sb.table("account_bindings").delete().eq("id", id).execute()
```

**Поддерживаемые операции**: `select`, `insert`, `update`, `delete`, `eq`, `neq`, `order`, `limit`

### 3.5. Middleware

#### `auth.py` — ApiKeyAuthMiddleware
**Цепочка авторизации (4 запроса к Supabase на каждый вызов):**
```
X-Api-Key header
    → SHA-256 хэширование
    → SELECT api_keys WHERE key_hash = hash AND is_active = true
    → SELECT tenants WHERE id = key.tenant_id
    → Проверка: is_active, subscription_until
    → SELECT toolkits WHERE id = tenant.toolkit_id
    → UPDATE api_keys SET last_used_at = now()
    → request.state.tenant_context = TenantContext(tenant, toolkit, api_key)
```

**Пропускаемые пути**: `/health`, `/ready`, `/docs`, `/openapi.json`, `/redoc`, всё что не `/api/v1/*`

**Feature-гейтинг**: `require_feature(request, "avito.messenger")` — проверяет наличие фичи в toolkit тенанта.

#### `error_handler.py` — ErrorHandlerMiddleware
- Ловит все необработанные исключения
- Возвращает `{"detail": "..."}` с соответствующим HTTP-кодом

---

## 4. Frontend (avito-frontend)

### 4.1. Стек

- **Vue 3** (Composition API + Options API)
- **Vite** — сборщик
- **Pinia** — state management
- **TailwindCSS** — стили (тёмная тема `bg-avito-*`)
- **Axios** — HTTP-клиент

### 4.2. Маршрутизация

| Путь | View | Описание |
|------|------|----------|
| `/auth` | AuthView | Управление сессиями и авторизация |
| `/messenger` | MessengerView | Мессенджер (каналы + чат) |
| `/search` | SearchView | Поиск объявлений |
| `/farm` | FarmView | Управление фермой токенов |

### 4.3. Pinia stores

| Store | Файл | Данные | Ключевые actions |
|-------|------|--------|------------------|
| `auth` | `stores/auth.js` | session, tokenDetails, alerts, history | fetchStatus(), uploadSession(), deleteSession(), startPolling(30с) |
| `messenger` | `stores/messenger.js` | channels, messages, activeChannel, unreadCount | fetchChannels(), fetchMessages(), sendMessage(), markRead() |
| `search` | `stores/search.js` | items, searchParams, selectedItem | searchItems(), getItemDetails(), loadMore() |
| `farm` | `stores/farm.js` | devices, bindings | fetchDevices(), fetchBindings(), createDevice(), createBinding() |

### 4.4. Компоненты

**Layout:**
- `AppSidebar.vue` — боковая навигация (4 раздела)
- `AppHeader.vue` — верхняя панель: статус сессии + ввод API Key

**Auth (6 компонентов):**
- `AlertBanner.vue` — баннер при TTL < 30мин или expired
- `TokenStatus.vue` — статус: active/inactive, user_id, TTL прогресс-бар
- `RemoteBrowser.vue` — удалённый браузер (WebSocket → скриншоты → клик/клавиатура)
- `SessionUpload.vue` — загрузка JSON сессии (drag-drop + textarea)
- `TokenDetails.vue` — декодированный JWT (expandable)
- `SessionHistory.vue` — таблица истории сессий

**Messenger (5 компонентов):**
- `ChannelList.vue` — список каналов с поиском и бейджами
- `ChatWindow.vue` — история сообщений, auto-scroll
- `MessageBubble.vue` — пузырьки сообщений (in/out)
- `ComposeBox.vue` — поле ввода + отправка
- `CallHistory.vue` — таблица звонков

**Search (3 компонента):**
- `SearchForm.vue` — фильтры: запрос, цена, город, сортировка
- `ItemCard.vue` — карточка объявления (grid)
- `ItemDetail.vue` — модальное окно с деталями

**Farm (2 компонента):**
- `DeviceList.vue` — таблица устройств фермы
- `BindingTable.vue` — привязки аккаунтов

### 4.5. API-клиент (`api/index.js`)

```javascript
const api = axios.create({ baseURL: '/api/v1' })

// Интерцептор: X-Api-Key из localStorage
api.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('x-api-key')
  if (apiKey) config.headers['X-Api-Key'] = apiKey
  return config
})
```

**WebSocket (RemoteBrowser):** Подключается напрямую к `ws://host/api/v1/auth/browser?api_key=xxx`, минуя axios.

---

## 5. Farm Agent (avito-farm-agent)

### 5.1. Назначение

Автономный daemon на рутованном Android-устройстве. Автоматически обновляет токены Avito для всех привязанных аккаунтов.

### 5.2. Архитектура

```
Farm Agent (agent.py)
    │
    ├── Heartbeat thread     ─── POST /farm/heartbeat (каждые 5 мин)
    │
    └── Schedule loop        ─── GET /farm/schedule (каждые 5 мин)
          │
          └── refresh_profile(profile_id)
                │
                ├── am start --user {id}     ← Запуск Avito в профиле
                ├── sleep 90s                ← Ждём авто-refresh токена
                ├── frida -l grab_token.js   ← Извлечение нового токена
                ├── am force-stop            ← Остановка Avito
                └── POST /farm/tokens        ← Загрузка в X-API
```

### 5.3. Frida-скрипты

| Скрипт | Назначение | Триггер |
|--------|-----------|---------|
| `grab_token.js` | Извлечение session_token, refresh_token, fingerprint из SharedPreferences Avito | Во время refresh |
| `spoof_fingerprint.js` | Подмена IMEI, Android ID, MAC, Build.MODEL и др. per-profile | При запуске Avito |
| `sniff_fingerprint.js` | R&D: логирование всех системных API, которые вызывает Avito | Ручной запуск |

### 5.4. Конфигурация (`config.json`)

```json
{
  "device_name": "OnePlus-8T-1",
  "xapi_url": "https://avito.newlcd.ru/api/v1",
  "api_key": "...",
  "heartbeat_interval_sec": 300,
  "schedule_poll_interval_sec": 300,
  "refresh_lead_time_sec": 60,
  "avito_launch_wait_sec": 90,
  "avito_package": "com.avito.android"
}
```

### 5.5. Взаимодействие с X-API

Farm Agent общается с backend через 3 HTTP-эндпоинта:

| Направление | Эндпоинт | Данные |
|-------------|----------|--------|
| Agent → X-API | `POST /farm/heartbeat` | `{"device_id": "..."}` |
| Agent ← X-API | `GET /farm/schedule` | Список binding'ов с TTL |
| Agent → X-API | `POST /farm/tokens` | `{device_id, profile_id, session_token, ...}` |

---

## 6. База данных (Supabase)

### 6.1. Схема таблиц

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ supervisors  │────▶│  toolkits    │     │ farm_devices │
│              │     │ features[]   │     │              │
│ id, name     │     │ limits{}     │     │ id, name     │
│ email        │     │ price        │     │ model, serial│
└──────┬───────┘     └──────────────┘     └──────┬───────┘
       │                                         │
       ▼                                         │
┌──────────────┐     ┌──────────────┐     ┌──────┴───────┐
│   tenants    │────▶│  api_keys    │     │  account_    │
│              │     │              │     │  bindings    │
│ toolkit_id   │     │ key_hash     │     │              │
│ subscription │     │ is_active    │     │ profile_id   │
└──────┬───────┘     └──────────────┘     │ avito_user_id│
       │                                  └──────────────┘
       ▼
┌──────────────┐     ┌──────────────┐
│avito_sessions│     │  audit_log   │
│              │     │              │
│ tokens JSONB │     │ action       │
│ user_id      │     │ details JSONB│
│ source       │     │              │
│ is_active    │     │              │
└──────────────┘     └──────────────┘
```

### 6.2. Связи

| Таблица | FK → | Тип связи |
|---------|------|-----------|
| `toolkits.supervisor_id` | `supervisors.id` | Many-to-One |
| `tenants.supervisor_id` | `supervisors.id` | Many-to-One |
| `tenants.toolkit_id` | `toolkits.id` | Many-to-One |
| `api_keys.tenant_id` | `tenants.id` | Many-to-One |
| `avito_sessions.tenant_id` | `tenants.id` | Many-to-One |
| `audit_log.tenant_id` | `tenants.id` | Many-to-One |
| `account_bindings.tenant_id` | `tenants.id` | Many-to-One |
| `account_bindings.farm_device_id` | `farm_devices.id` | Many-to-One |

### 6.3. Иерархия доступа

```
Супервайзер (supervisor)
  └── Набор инструментов (toolkit)    ← features + limits + price
        └── Тенант (tenant)           ← клиент SaaS
              ├── API Key (api_keys)  ← SHA-256 хэш
              ├── Сессия Avito        ← JWT + cookies
              ├── Audit Log           ← все действия
              └── Account Binding     ← привязка к farm
```

### 6.4. Таблица `avito_sessions.tokens` (JSONB)

```json
{
  "session_token": "eyJ...",
  "refresh_token": "...",
  "device_id": "...",
  "fingerprint": "A2.{hex}",
  "remote_device_id": "...",
  "user_hash": "...",
  "cookies": {"sessid": "...", "other": "..."}
}
```

### 6.5. Допустимые значения `source`

| Source | Описание | Приоритет |
|--------|---------|-----------|
| `farm` | Автоматически от Farm Agent через Frida | 1 (основной) |
| `android` | APK-мост мониторит SharedPreferences | 2 |
| `redroid` | Redroid ADB extract (палится как эмулятор) | 3 |
| `browser` | Удалённый браузер (Playwright) | 4 |
| `manual` | Ручная загрузка через UI | 5 (fallback) |

---

## 7. Потоки данных и взаимодействие

### 7.1. Поток: Авторизация через удалённый браузер

```
┌─────────┐    WS: start     ┌──────────┐   Playwright    ┌─────────┐
│ Frontend │ ──────────────▶ │ Backend  │ ──────────────▶ │ avito.ru│
│ Remote   │                 │ auth_    │                 │  /login │
│ Browser  │ ◀────────────── │ browser  │ ◀────────────── │         │
│ .vue     │  WS: screenshot │ .py      │   Screenshot    │         │
│          │ ──────────────▶ │          │ ──────────────▶ │         │
│          │  WS: click/key  │          │   Mouse/Key     │         │
│          │ ◀────────────── │          │ ◀────────────── │         │
│          │  WS: auth_done  │          │   Cookies       │         │
└─────────┘                  └────┬─────┘                 └─────────┘
                                  │ Supabase
                                  ▼
                           avito_sessions
```

### 7.2. Поток: Запрос к мессенджеру Avito

```
┌─────────┐    GET /channels   ┌──────────┐                ┌──────────────┐
│ Frontend │ ───────────────▶  │ Backend  │  Supabase      │              │
│ Messenger│                   │ router   │ ◀───────────── │ Supabase DB  │
│ Store    │                   │          │  session_token  │ (sessions)   │
│          │                   │          │                 └──────────────┘
│          │                   │          │
│          │                   │  worker  │  curl_cffi      ┌──────────────┐
│          │                   │  http_   │ ──────────────▶ │ app.avito.ru │
│          │                   │  client  │ ◀────────────── │ /api/1/...   │
│          │                   │          │  JSON response   └──────────────┘
│          │                   │          │
│          │ ◀──────────────── │  router  │  normalize
│          │   normalized JSON │          │  body.text.text → text
└─────────┘                    └──────────┘  authorId → author_id
```

### 7.3. Поток: Автообновление токена (Farm)

```
┌────────────┐  GET /schedule   ┌──────────┐  SELECT    ┌───────────┐
│ Farm Agent │ ──────────────▶ │ Backend  │ ────────▶ │ Supabase  │
│ (Android)  │ ◀────────────── │ farm.py  │ ◀──────── │ bindings  │
│            │  TTL per binding │          │           │ sessions  │
│            │                  └──────────┘           └───────────┘
│            │
│  if TTL ≤ 60s:
│            │
│  ┌─────────────────────────────────────────────────┐
│  │ 1. am start --user {profile_id}                  │
│  │ 2. Avito auto-refreshes token (~90s)             │
│  │ 3. frida -l grab_token.js → TOKEN_DATA|{json}   │
│  │ 4. am force-stop                                 │
│  └────────────────────────────────────┬────────────┘
│            │                          │
│            │  POST /farm/tokens       │
│            │ ──────────────────────▶  │
│            │                   ┌──────┴──────┐  INSERT  ┌───────────┐
│            │                   │ Backend     │ ───────▶ │ Supabase  │
│            │                   │ farm.py     │          │ sessions  │
│            │                   └─────────────┘          └───────────┘
└────────────┘
```

### 7.4. Поток: WebSocket real-time (подготовлен)

```
┌─────────┐                     ┌──────────┐    JSON-RPC 2.0    ┌─────────────┐
│ Future   │                    │ Backend  │  wss://socket.     │ socket.     │
│ clients  │  (не реализовано   │ ws_      │  avito.ru/socket   │ avito.ru    │
│ (WS от   │   на уровне       │ client   │ ◀───────────────▶  │             │
│ frontend)│   роутера,         │ .py      │  chrome120 TLS     │ Push events:│
│          │   ws_client.py     │          │                    │ newMessage  │
│          │   готов)           │          │                    │ typing      │
│          │                    │          │                    │ read        │
└─────────┘                     └──────────┘                    └─────────────┘
```

---

## 8. Аутентификация и авторизация

### 8.1. Внешняя авторизация (клиент → X-API)

```
HTTP Header: X-Api-Key: <plaintext_key>
    │
    ▼
SHA-256(key) → key_hash
    │
    ▼
SELECT api_keys WHERE key_hash = ? AND is_active = true
    │  ❌ → 401 Invalid API key
    ▼
SELECT tenants WHERE id = api_keys.tenant_id
    │  ❌ → 401 Tenant not found
    │  is_active = false → 403 Tenant deactivated
    │  subscription_until < now() → 403 Subscription expired
    ▼
SELECT toolkits WHERE id = tenants.toolkit_id
    │
    ▼
request.state.tenant_context = {tenant, toolkit, api_key}
    │
    ▼
Каждый эндпоинт вызывает require_feature("avito.messenger")
    │  feature ∉ toolkit.features → 403 Feature not available
    ▼
Запрос обрабатывается
```

### 8.2. Feature-гейтинг

Toolkit содержит массив `features`:
```json
["avito.sessions", "avito.messenger", "avito.search", "avito.calls", "avito.farm"]
```

Каждый роутер проверяет свою фичу через `require_feature(request, "avito.<feature>")`.

### 8.3. Авторизация в Avito (X-API → Avito)

X-API использует `session_token` из `avito_sessions` тенанта для авторизации в Avito API:
- В HTTP-заголовках: `X-Session`, `Cookie: sessid=<token>`
- В WebSocket: те же заголовки при подключении

**Токен НЕ обновляется X-API.** Обновление происходит только через приложение Avito (Farm Agent или ручной запуск).

---

## 9. Внешний API для интеграции

### 9.1. Как подключиться извне

Любая внешняя система (Telegram-бот, CRM, Worker, другой сервис) может взаимодействовать с Avito System через HTTP API:

**Base URL:** `https://avito.newlcd.ru/api/v1`

**Авторизация:**
```
Header: X-Api-Key: <your_api_key>
```

### 9.2. Примеры интеграции

#### Telegram-бот → получить новые сообщения
```bash
# Получить список каналов
curl -H "X-Api-Key: $KEY" https://avito.newlcd.ru/api/v1/messenger/channels

# Получить сообщения канала
curl -H "X-Api-Key: $KEY" https://avito.newlcd.ru/api/v1/messenger/channels/{id}/messages

# Отправить сообщение
curl -X POST -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text": "Здравствуйте!"}' \
  https://avito.newlcd.ru/api/v1/messenger/channels/{id}/messages
```

#### CRM → проверить статус сессии
```bash
# Текущая сессия
curl -H "X-Api-Key: $KEY" https://avito.newlcd.ru/api/v1/sessions/current
# → {"is_active": true, "user_id": 12345, "ttl_seconds": 67200, "source": "farm"}

# Алерты
curl -H "X-Api-Key: $KEY" https://avito.newlcd.ru/api/v1/sessions/alerts
# → {"alerts": [{"level": "warning", "message": "Token expires in 28 min"}]}
```

#### Worker → загрузить токен
```bash
curl -X POST -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "session_token": "eyJ...",
    "source": "android",
    "device_id": "abc123"
  }' \
  https://avito.newlcd.ru/api/v1/sessions
```

#### Поиск → найти объявления
```bash
curl -H "X-Api-Key: $KEY" \
  "https://avito.newlcd.ru/api/v1/search/items?query=iPhone+15&price_max=80000"
```

### 9.3. Коды ответов

| Код | Описание |
|-----|---------|
| 200 | Успех |
| 201 | Создано (POST) |
| 401 | Нет API-ключа / невалидный ключ |
| 403 | Тенант деактивирован / подписка истекла / фича недоступна |
| 404 | Нет активной сессии / ресурс не найден |
| 422 | Невалидные данные (напр. невалидный JWT) |
| 500 | Внутренняя ошибка |

### 9.4. Формат ошибок

```json
{"detail": "Missing X-Api-Key header"}
```

### 9.5. Суpabase напрямую

Любое приложение может работать с Supabase напрямую для чтения/записи данных тенантов (помимо X-API):

```
URL: https://bkxpajeqrkutktmtmwui.supabase.co
Key: <anon_key или service_role_key>
```

Это позволяет, например, Telegram-боту проверять подписку тенанта или n8n workflow записывать в audit_log.

---

## 10. Деплой и инфраструктура

### 10.1. Топология

```
┌─────────────────────────────────────────────────────────────┐
│ Homelab (Proxmox, 16 cores / 32GB RAM)                      │
│                                                             │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Docker                                            │       │
│  │  ┌──────────────┐   ┌──────────────────┐         │       │
│  │  │  xapi:8080   │   │  frontend:3000   │         │       │
│  │  │  FastAPI      │   │  Nginx + Vue SPA │         │       │
│  │  └──────┬───────┘   └────────┬─────────┘         │       │
│  │         │                    │                    │       │
│  └─────────┼────────────────────┼────────────────────┘       │
│            │                    │                            │
│  ┌─────────┴────────────────────┴────────────────────┐       │
│  │ SSH Tunnel (autossh → VPS:155.212.221.67)          │       │
│  │  :8080 → remote :8080                              │       │
│  │  :3000 → remote :3000                              │       │
│  └────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ VPS (155.212.221.67, Ubuntu 22.04)                           │
│                                                             │
│  Nginx:                                                     │
│    avito.newlcd.ru/api/*  → localhost:8080  (→ tunnel → xapi) │
│    avito.newlcd.ru/*      → localhost:3000  (→ tunnel → SPA)  │
│    SSL via Certbot (valid until 2026-05-07)                 │
│                                                             │
│  DNS: avito.newlcd.ru → 155.212.221.67 (Cloudflare, no proxy)│
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Supabase Cloud (bkxpajeqrkutktmtmwui)                        │
│  PostgreSQL + PostgREST + Auth + Storage                     │
│  8 таблиц, RLS enabled                                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Android Device (rooted, Farm Agent)                          │
│  Python + Frida + ADB                                       │
│  HTTPS → avito.newlcd.ru/api/v1/farm/*                       │
└─────────────────────────────────────────────────────────────┘
```

### 10.2. Docker Compose

```yaml
services:
  xapi:
    build: ./avito-xapi
    ports: ["8080:8080"]
    env_file: ./avito-xapi/.env
    restart: unless-stopped

  frontend:
    build: ./avito-frontend
    ports: ["3000:80"]
    depends_on: [xapi]
    restart: unless-stopped
```

### 10.3. Переменные окружения (avito-xapi/.env)

| Переменная | Описание | Пример |
|-----------|---------|--------|
| `SUPABASE_URL` | URL Supabase PostgREST | `https://bkx...supabase.co` |
| `SUPABASE_KEY` | Anon или Service Role Key | `eyJ...` |
| `HOST` | Адрес FastAPI | `0.0.0.0` |
| `PORT` | Порт FastAPI | `8080` |
| `LOG_LEVEL` | Уровень логирования | `info` |
| `CORS_ORIGINS` | Разрешённые origins | `["https://avito.newlcd.ru"]` |
| `RATE_LIMIT_RPS` | Лимит запросов/сек к Avito | `5.0` |
| `RATE_LIMIT_BURST` | Burst для rate limiter | `10` |

---

## 11. Ключевые технические решения

### 11.1. TLS-имперсонация (curl_cffi)

Avito использует QRATOR для защиты API. Стандартные HTTP-клиенты (requests, httpx) блокируются по TLS fingerprint. Решение — `curl_cffi` с `impersonate="chrome120"`, который повторяет TLS handshake Chrome 120.

### 11.2. PostgREST вместо SDK

Официальный `supabase-py` SDK не компилируется на Python 3.14 (зависимость `pyroaring` не собирается). Написан собственный легковесный клиент в `storage/supabase.py`, использующий `httpx` для прямых вызовов Supabase PostgREST API. Интерфейс совместим: `.table().select().eq().execute()`.

### 11.3. JWT без верификации

Avito подписывает JWT алгоритмом HS512. Секрет нам неизвестен. Мы декодируем только header и payload через base64 (без проверки подписи) для извлечения `user_id`, `exp`, `iat` и др.

### 11.4. Нормализация данных

Avito API возвращает данные в разных форматах через HTTP и WebSocket:
- HTTP: `body.text.text` / WS: `body.text` → нормализуем в `text`
- HTTP: `authorId` / WS: `fromUid` → нормализуем в `author_id`
- Timestamps в наносекундах → ISO 8601

### 11.5. category=1 всегда

В запросах к мессенджеру Avito `category=0` вызывает HTTP 500. Всегда используем `category=1`.

### 11.6. Токены не обновляются X-API

X-API **мониторит** TTL, но **не обновляет** токены самостоятельно. Обновление происходит только через запуск приложения Avito на устройстве (Farm Agent, APK-мост, или ручной запуск). X-API алертит за 30/10 минут до истечения.

### 11.7. BaseHTTPMiddleware на Python 3.14

На Python 3.14 `raise HTTPException(...)` внутри `BaseHTTPMiddleware.dispatch()` вызывает `ExceptionGroup`. Решение: использовать `return JSONResponse(status_code=..., content=...)` вместо raise.

### 11.8. Один профиль = один аккаунт = одно устройство

Привязка аккаунта Avito к Android-профилю на конкретном устройстве **жёсткая** (fingerprint). Перенос аккаунта между устройствами = перерегистрация fingerprint, что может привести к бану.

---

## Приложение: Быстрый справочник для интеграции

### Минимальный пример (Python)

```python
import requests

BASE = "https://avito.newlcd.ru/api/v1"
HEADERS = {"X-Api-Key": "your_api_key"}

# Проверить сессию
r = requests.get(f"{BASE}/sessions/current", headers=HEADERS)
print(r.json())  # {"is_active": true, "user_id": 123, "ttl_seconds": 50000, ...}

# Получить каналы
r = requests.get(f"{BASE}/messenger/channels", headers=HEADERS)
channels = r.json()["channels"]

# Отправить сообщение
r = requests.post(f"{BASE}/messenger/channels/{channels[0]['id']}/messages",
                  headers=HEADERS, json={"text": "Привет!"})

# Поиск
r = requests.get(f"{BASE}/search/items", headers=HEADERS, params={"query": "iPhone 15"})
items = r.json()["items"]
```

### Минимальный пример (JavaScript / Node.js)

```javascript
const BASE = 'https://avito.newlcd.ru/api/v1';
const headers = { 'X-Api-Key': 'your_api_key' };

// Статус сессии
const session = await fetch(`${BASE}/sessions/current`, { headers }).then(r => r.json());

// Каналы
const { channels } = await fetch(`${BASE}/messenger/channels`, { headers }).then(r => r.json());

// Отправить сообщение
await fetch(`${BASE}/messenger/channels/${channels[0].id}/messages`, {
  method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' },
  body: JSON.stringify({ text: 'Привет!' })
});
```
