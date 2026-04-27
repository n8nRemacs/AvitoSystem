# avito-xapi

**Назначение:** Мультитенантный FastAPI-шлюз к мобильному API Avito. Оборачивает реверс-инженерное API в чистые REST-эндпоинты с авторизацией по API-ключу, rate limiting, WS real-time и управлением сессиями.

**Статус:** working. Прод-качество. Развёрнут на `https://avito.newlcd.ru`.

**Стек:** Python 3.12, FastAPI, curl_cffi (Chrome120 TLS fingerprint), Pydantic v2, Playwright (browser auth), Supabase PostgREST (кастомная обёртка без supabase-py).

---

## Структура

```
src/
  main.py           — точка входа FastAPI, lifespan, middleware стек
  config.py         — pydantic-settings (порт 8080, JWT, rate limits, CORS)
  dependencies.py   — get_current_tenant() dependency
  workers/          — клиенты Avito: HTTP REST + WS + session/token логика
  routers/          — эндпоинты API (prefix /api/v1/*)
  models/           — Pydantic-схемы запросов/ответов
  middleware/       — авторизация (ApiKey + JWT) + error handler
  storage/          — суперлёгкая обёртка PostgREST (httpx, без supabase-py)
tests/
  conftest.py       — make_authed_sb(), make_mock_sb(), run_request()
  fixtures/         — JSON-снимки реальных ответов Avito API
```

---

## Точки входа

```bash
cd avito-xapi
pip install -r requirements.txt

# Dev
uvicorn src.main:app --reload --port 8080

# Docker
docker compose up xapi

# Тесты
pytest tests/ -v
```

Swagger UI: `http://localhost:8080/docs`

---

## Связи

- **Вызывают:** AvitoBayer (`xapi_client.py`), avito-frontend (API-запросы)
- **Вызывает:** Avito API (`app.avito.ru/api`), Supabase self-hosted (сессии, тенанты)
- **Зависит от:** tenant-auth — общий JWT_SECRET для Bearer-токенов
- **Порт:** 8080 (Docker), `https://avito.newlcd.ru` (прод)

---

## Конвенции / предупреждения

- `http_client.py` — методы `async`, но внутри используют **синхронный** `curl_cffi.requests.Session`. Это намеренно: curl_cffi не поддерживает async. Не заменять на `httpx.AsyncClient` — сломается TLS fingerprint.
- `ws_client.py` — WebSocket тоже синхронный в фоновом треде, соединён с async через `asyncio.Queue` + `call_soon_threadsafe`.
- `storage/supabase.py` — кастомный QueryBuilder (не supabase-py). Причина: конфликт зависимостей на Python 3.14.
- Авторизация: `X-Api-Key` → SHA-256 хэш ищется в таблице `api_keys`. Альтернативно Bearer JWT от tenant-auth.
- Фича-флаги тенанта хранятся в `toolkits.features` (JSON array). `require_feature("avito.search")` — декоратор в `middleware/auth.py`.
- `tests/fixtures/` — только данные (JSON), CLAUDE.md там не нужен.

---

## Связано с ТЗ V1

Соответствует роли `avito-mcp` (раздел 3.1 и 4.3 ТЗ). В V1 будет использоваться как HTTP-бэкенд для MCP-сервера Avito — главной точки доступа к данным. Переиспользуется напрямую, не переписывается.
