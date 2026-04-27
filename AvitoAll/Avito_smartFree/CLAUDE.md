# Avito_smartFree — SaaS-прототип (многопользовательский)

**Назначение:** Прототип SaaS-платформы для интеграции Avito Messenger с Telegram на 1000+ клиентов. Два сервера: Token Farm (ARM, Redroid) + MCP Server (VPS, WebSocket + Telegram Bot).

**Статус:** prototype — архитектура продумана, частично реализована, но компоненты не интегрированы (Avito Client ↔ Telegram Bot изолированы). SMS-регистрация не реализована. Не запускался в production.

**Стек/технологии:** Python, FastAPI, aiogram 3, aiohttp, SQLAlchemy 2.0 (async), PostgreSQL, Docker (Redroid, ARM).

## Что внутри

| Путь | Что это |
|------|---------|
| `shared/models.py` | SQLAlchemy ORM: Account, Session, TelegramUser, Proxy, Message |
| `shared/utils.py` | `build_avito_headers()`, `build_ws_url()`, `parse_jwt()`, `generate_device_id()`, `RateLimiter` |
| `shared/database.py` | Async PostgreSQL: Database class, Repository CRUD, context managers |
| `token-farm/api_server.py` | FastAPI REST для управления аккаунтами |
| `token-farm/farm_manager.py` | Оркестратор Redroid-контейнеров + ADBController |
| `token-farm/avito_prefs_parser.py` | Парсер SharedPrefs XML → `AvitoSession` dataclass |
| `token-farm/docker-compose.yml` | 5 Redroid-контейнеров с разными device-профилями |
| `mcp-server/avito_client.py` | WebSocket + HTTP клиент Avito; `AvitoClientPool`; auto-reconnect; rate limit |
| `mcp-server/telegram_bot.py` | aiogram 3 бот: /start, /link, /chats, /status |
| `mcp-server/mcp_manager.py` | Оркестратор: загрузка аккаунтов, роутинг Avito ↔ Telegram |
| `token-farm-x86/` | Вариант для x86 серверов (экспериментальный) |
| `ARCHITECTURE.md` | Полная архитектура с SQL-схемой, масштабированием, антифрод-мерами |
| `CONTEXT.md` | Краткий AI-контекст (что реализовано, что нет) |

## Что полезно для V1

- **`shared/utils.py`** — `build_avito_headers()` и `RateLimiter` — готовые утилиты, порт в avito-xapi.
- **`mcp-server/avito_client.py`** — `AvitoClientPool` с auto-reconnect и exponential backoff, WebSocket JSON-RPC клиент Avito. Наиболее зрелая реализация WS-клиента в этом репо.
- **`token-farm/avito_prefs_parser.py`** — `AvitoSession` dataclass + `is_expired()` / `time_until_expiry()`.
- **`ARCHITECTURE.md`** — SQL-схема с индексами (accounts, sessions, telegram_users, proxies, messages) — готовая для адаптации.

## Что НЕ использовать

- `token-farm-x86/` — экспериментальный вариант, не доведён до конца
- Весь `token-farm/farm_manager.py` — завязан на ARM Redroid, не портируем без ARM-сервера
- Интеграция Avito ↔ Telegram в `mcp_manager.py` — заглушка, не реализована

## Ссылки

- `ARCHITECTURE.md` — детальная документация (SQL, масштабирование, антифрод)
- `CONTEXT.md` — краткий AI-контекст
- `../AvitoSessionManager/` — альтернативный источник токенов (рут-телефон)
