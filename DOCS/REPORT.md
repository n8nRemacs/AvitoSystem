# AvitoSystem — Отчёт о проделанной работе

**Дата:** 2026-02-08
**Проект:** AvitoSystem SaaS Platform
**Статус:** Разработка завершена, деплой не выполнен

---

## 1. Что было создано

### Общая архитектура

```
Клиент (браузер / внешняя система)
    │
    ▼
avito.newlcd.ru (Nginx + SSL)
    │
    ├── /api/v1/*  →  avito-xapi (FastAPI, порт 8080)
    │                    ├── REST API (сессии, мессенджер, звонки, поиск, ферма)
    │                    ├── SSE real-time (WebSocket Avito → SSE клиентам)
    │                    └── Browser Auth (Playwright)
    │
    └── /*  →  avito-frontend (Vue 3 SPA, порт 3000)
                 └── Dashboard с мессенджером, поиском, фермой

Supabase (облачная PostgreSQL)
    └── Хранение: тенанты, API-ключи, сессии, устройства фермы

Avito Mobile API
    └── REST + WebSocket (socket.avito.ru)
        └── TLS impersonation через curl_cffi (Chrome 120)
```

### Компоненты

| Компонент | Технологии | Файлы | Статус |
|-----------|-----------|-------|--------|
| **Backend (avito-xapi)** | FastAPI, Python 3.14, curl_cffi | 35 исходников + 15 тестов | Готов |
| **Frontend (avito-frontend)** | Vue 3, Pinia, TailwindCSS, Vite | 23 Vue + 7 JS | Готов |
| **Farm Agent (avito-farm-agent)** | Python daemon + Frida скрипты | 1 Python + 3 JS | Готов |
| **Миграция БД** | SQL (PostgreSQL) | 2 файла | Написана, не применена |
| **Docker Compose** | docker-compose.yml | 1 файл | Готов |

**Итого:** ~84 файла кода

---

## 2. Backend — подробно

### Роутеры (8 штук)

| Роутер | Префикс | Эндпоинтов | Назначение |
|--------|---------|-----------|------------|
| `health` | `/health`, `/ready` | 2 | Healthcheck |
| `sessions` | `/api/v1/sessions` | 6 | Загрузка/управление сессиями Avito |
| `messenger` | `/api/v1/messenger` | 8 | Каналы, сообщения, отправка, typing |
| `realtime` | `/api/v1/messenger/realtime` | 3 | SSE события, статус, остановка WS |
| `calls` | `/api/v1/calls` | 2 | История звонков |
| `search` | `/api/v1/search` | 3 | Поиск объявлений, детали |
| `farm` | `/api/v1/farm` | 7 | Управление фермой устройств |
| `auth_browser` | `/api/v1/auth/browser` | 3 | Авторизация через Playwright |

### Middleware

| Middleware | Назначение |
|-----------|------------|
| `ApiKeyAuthMiddleware` | Аутентификация по X-Api-Key (header или query param) |
| `ErrorHandlerMiddleware` | Глобальный перехват ошибок |
| `CORSMiddleware` | CORS для фронтенда |

### Workers

| Модуль | Назначение |
|--------|------------|
| `ws_client.py` | WebSocket клиент к socket.avito.ru (JSON-RPC 2.0, curl_cffi) |
| `ws_manager.py` | Per-tenant WS lifecycle + fan-out в asyncio.Queue |
| `http_client.py` | HTTP клиент к Avito REST API (curl_cffi) |
| `session_reader.py` | Загрузка сессий из Supabase |
| `jwt_parser.py` | Парсинг JWT токенов Avito |
| `token_monitor.py` | Мониторинг срока действия токенов |
| `rate_limiter.py` | Token bucket rate limiter |
| `browser_auth.py` | Playwright авторизация в Avito |

### Real-time система (последняя реализация)

```
socket.avito.ru (WS JSON-RPC 2.0)
        │ push: messenger.newMessage / typing / read
        ▼
AvitoWsClient (recv_thread, sync)
        │ _emit("message", data)
        ▼
WsManager (singleton, ws_manager.py)
        │ loop.call_soon_threadsafe(queue.put_nowait, event)
        ▼
asyncio.Queue (per subscriber)
        │
        ▼
GET /api/v1/messenger/realtime/events (SSE)
        │ text/event-stream
        ▼
Frontend EventSource
```

**Ключевые особенности:**
- Auto-start WS при первом подписчике, auto-stop при отключении последнего
- Keepalive каждые 30 секунд (против таймаутов nginx/proxy)
- SSE формат: `event: new_message\ndata: {...}\n\n`
- Fallback на polling при недоступности SSE (10 попыток exp backoff)

### Тесты

| Файл тестов | Тестов | Что покрывает |
|-------------|--------|---------------|
| `test_auth_middleware.py` | 7 | Аутентификация, feature gating |
| `test_jwt_parser.py` | 16 | Все функции JWT парсера |
| `test_rate_limiter.py` | 5 | Token bucket алгоритм |
| `test_session_reader.py` | 7 | Загрузка сессий из Supabase |
| `test_sessions.py` | 11 | Эндпоинты сессий |
| `test_messenger.py` | 9 | Нормализация + эндпоинты мессенджера |
| `test_realtime.py` | 5 | SSE статус, остановка, feature gating, query auth |
| `test_ws_manager.py` | 11 | WS lifecycle, fan-out, subscribe/unsubscribe |
| `test_calls.py` | 3 | Нормализация звонков |
| `test_search.py` | 5 | Нормализация объявлений |
| `test_farm_api.py` | 7 | CRUD устройств и биндингов |
| `test_token_monitor.py` | 5 | Алерты по токенам |
| **ИТОГО** | **100** | **Все проходят за <1с** |

---

## 3. Frontend — подробно

### Страницы (Views)

| View | Функционал |
|------|-----------|
| `DashboardView` | Статус сессии, алерты, быстрые метрики |
| `MessengerView` | Каналы + чат + индикатор Live/Polling |
| `SearchView` | Поиск объявлений Avito |
| `FarmView` | Управление фермой устройств |

### Stores (Pinia)

| Store | Назначение |
|-------|-----------|
| `auth.js` | Сессия, токены, алерты, polling |
| `messenger.js` | Каналы, сообщения, SSE + fallback polling, typing |
| `search.js` | Поиск и детали объявлений |
| `farm.js` | Устройства и биндинги фермы |

### Real-time в мессенджере

- **EventSource** подключается к `/api/v1/messenger/realtime/events?api_key=xxx`
- Обработка событий: `new_message` (обновление списка каналов + сообщений), `typing` (индикатор 3с), `read`
- Визуальный индикатор: зелёный "Live" / жёлтый "Polling"
- Typing indicator: анимированные точки под сообщениями

---

## 4. SaaS модель

```
Supervisor (партнёр)
    └── Toolkit (набор фич + лимиты + цена)
            └── Tenant (конечный клиент)
                    ├── API Key(s)
                    ├── Avito Session
                    └── Farm Bindings
```

**Фичи тулкита:** `avito.sessions`, `avito.messenger`, `avito.search`, `avito.calls`, `avito.farm`

Каждый запрос проходит: API Key → Tenant → Toolkit → Feature check.

---

## 5. Инфраструктура

| Сервис | URL | Где работает |
|--------|-----|-------------|
| Backend API | `avito.newlcd.ru/api/v1/*` | Homelab (Docker) |
| Frontend | `avito.newlcd.ru/` | Homelab (Docker) |
| Supabase | `bkxpajeqrkutktmtmwui.supabase.co` | Облако |
| Proxmox | `proxmox.newlcd.ru` | Homelab |
| n8n | `n8n.newlcd.ru` | Homelab (Docker) |

**SSH туннели (autossh):** 8006, 2222, 5678, 8080, 3000
**SSL:** Let's Encrypt через Certbot (до 2026-05-07)
**DNS:** Cloudflare, DNS only (без proxy)

---

## 6. База данных (Supabase)

**Проект:** `bkxpajeqrkutktmtmwui`

### Таблицы

| Таблица | Назначение |
|---------|------------|
| `supervisors` | Партнёры/реселлеры |
| `toolkits` | Наборы фич с лимитами |
| `tenants` | SaaS клиенты |
| `api_keys` | Ключи доступа (SHA-256 hash) |
| `avito_sessions` | Сессии Avito (токены, fingerprint, device_id) |
| `audit_log` | Лог действий |
| `farm_devices` | Физические Android устройства |
| `account_bindings` | Привязки Avito аккаунт ↔ профиль ↔ тенант |

### Миграции

- `001_init.sql` — Схема, индексы, RLS, триггеры
- `002_seed.sql` — Тестовые данные (supervisor, toolkit, tenant, API key)

**Статус: написаны, НЕ применены.**

---

## 7. Что НЕ сделано

| # | Задача | Критичность | Комментарий |
|---|--------|-------------|------------|
| 1 | Применить миграцию SQL | **Блокер** | Без таблиц ничего не работает |
| 2 | Создать `.env` | **Блокер** | Скопировать `.env.example` → `.env` |
| 3 | Деплой на homelab | **Блокер** | `docker compose up -d --build` |
| 4 | Загрузить сессию Avito | **Блокер** | Нужен токен от реального аккаунта |
| 5 | Git-репозиторий | Важно | Проект не под контролем версий |
| 6 | Fingerprint данные | Для фермы | Запустить `sniff_fingerprint.js` на рутованном устройстве |
| 7 | Farm agent на Android | Для фермы | Установить daemon + Frida на устройство |
| 8 | Мониторинг/логирование | Желательно | Нет централизованного сбора логов |
| 9 | Backup стратегия | Желательно | Supabase free tier — нет автобэкапов |

---

## 8. Известные ограничения

| Ограничение | Причина | Workaround |
|-------------|---------|------------|
| Python 3.14 — нет `supabase-py` | pyroaring не собирается | Свой PostgREST wrapper в `src/storage/supabase.py` |
| Supabase free tier засыпает | Нет запросов 7 дней | Keepalive cron на VPS |
| ISP CGNAT | Нет публичного IP | SSH reverse tunnel через VPS |
| curl_cffi под Windows | Может не собираться | Docker решает проблему |
| EventSource не поддерживает headers | Спецификация SSE | API key через query param |

---

## 9. Файловая структура проекта

```
AvitoSystem/
├── avito-xapi/                    # Backend (FastAPI)
│   ├── src/
│   │   ├── main.py                # Точка входа, lifespan, роутеры
│   │   ├── config.py              # Настройки (pydantic-settings)
│   │   ├── dependencies.py        # FastAPI dependencies
│   │   ├── middleware/
│   │   │   ├── auth.py            # API Key → Tenant → Toolkit
│   │   │   └── error_handler.py   # Глобальная обработка ошибок
│   │   ├── models/                # Pydantic модели
│   │   │   ├── tenant.py
│   │   │   ├── messenger.py
│   │   │   ├── calls.py
│   │   │   └── search.py
│   │   ├── routers/               # API эндпоинты
│   │   │   ├── health.py
│   │   │   ├── sessions.py
│   │   │   ├── messenger.py
│   │   │   ├── realtime.py        # SSE real-time
│   │   │   ├── calls.py
│   │   │   ├── search.py
│   │   │   ├── farm.py
│   │   │   └── auth_browser.py
│   │   ├── workers/               # Бизнес-логика
│   │   │   ├── ws_client.py       # WS клиент Avito
│   │   │   ├── ws_manager.py      # WS lifecycle + fan-out
│   │   │   ├── http_client.py     # HTTP клиент Avito
│   │   │   ├── session_reader.py  # Загрузка сессий
│   │   │   ├── jwt_parser.py      # JWT парсер
│   │   │   ├── token_monitor.py   # Мониторинг токенов
│   │   │   ├── rate_limiter.py    # Rate limiter
│   │   │   ├── browser_auth.py    # Playwright auth
│   │   │   └── base_client.py     # Базовый HTTP клиент
│   │   └── storage/
│   │       └── supabase.py        # PostgREST wrapper
│   ├── tests/                     # 100 тестов
│   ├── .env.example
│   ├── Dockerfile
│   └── requirements.txt
│
├── avito-frontend/                # Frontend (Vue 3 SPA)
│   ├── src/
│   │   ├── views/                 # 4 страницы
│   │   ├── components/            # UI компоненты
│   │   ├── stores/                # Pinia stores
│   │   ├── api/                   # Axios instance
│   │   └── router/                # Vue Router
│   ├── Dockerfile
│   └── vite.config.js
│
├── avito-farm-agent/              # Farm Agent
│   ├── farm_daemon.py             # Python daemon
│   └── frida_scripts/
│       ├── sniff_fingerprint.js   # Снятие отпечатка
│       ├── grab_token.js          # Захват токена
│       └── spoof_fingerprint.js   # Подмена отпечатка
│
├── supabase/
│   └── migrations/
│       ├── 001_init.sql           # Схема
│       └── 002_seed.sql           # Тестовые данные
│
├── DOCS/                          # Документация
│   ├── ARCHITECTURE.md
│   ├── X-API.md
│   ├── AVITO-API.md
│   ├── SYSTEM.md
│   ├── EXTENDING.md
│   ├── MOCKS.md
│   ├── AVITO-FINGERPRINT.md
│   ├── token_farm_system.md
│   └── REPORT.md                  # ← Этот файл
│
└── docker-compose.yml             # Оркестрация
```
