# avito-xapi / src / routers

**Назначение:** HTTP-роутеры FastAPI. Каждый файл — отдельная группа эндпоинтов с префиксом `/api/v1/`.

**Статус:** working.

---

## Роутеры

- `health.py` — `GET /health`, `GET /ready` — без авторизации
- `sessions.py` — управление Avito-сессиями тенанта: текущая, история, загрузка JSON, деактивация
- `search.py` — `GET /api/v1/search/items?query=...&location_id=...` — поиск объявлений, нормализация через `_normalize_item_card()`
- `messenger.py` — каналы, сообщения, отправка, create_chat_by_item, mark_read
- `calls.py` — IP-телефония (call tracking Avito)
- `realtime.py` — SSE-стрим событий мессенджера через `WsManager`
- `farm.py` — `/api/v1/farm/*` — API для Android farm-агента: heartbeat, schedule, tokens upload
- `auth_browser.py` — `/api/v1/auth-browser/*` — управление Playwright-сессией браузерной авторизации

---

## Конвенции

- Каждый роутер получает `TenantContext` через `Depends(get_current_tenant)` из `dependencies.py`
- Фича-флаги проверяются декоратором `@require_feature("avito.search")` из `middleware/auth.py`
- `search.py` использует `load_active_session()` напрямую (не через dependency) — исторически, не менять без причины
- Все ошибки Avito API проксируются через `ErrorHandlerMiddleware`, не оборачивать вручную в try/except

---

## Связано с ТЗ V1

`search.py` — основа для `avito_search` MCP tool (раздел 4.3 ТЗ). `sessions.py` + `farm.py` — управление токенами (раздел 6 ТЗ, token farm).
