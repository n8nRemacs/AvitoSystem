# V1 Blocks — ТЗ с контекстом для запуска в отдельных сессиях

**Назначение:** этот документ — карта оставшихся блоков V1 с точечным ТЗ на каждый. Каждая секция «Block N» **самодостаточна** и может быть скопирована в новую сессию Claude Code (или передана subagent через `Agent` tool) — в ней есть весь нужный контекст, ссылки на файлы, явный список зависимостей и проверочная точка.

**Версия документа:** 1.0
**Дата:** 2026-04-25
**Текущая дата проекта:** 2026-04-25

---

## 0. Текущее состояние проекта

### 0.1. Что готово

| Блок | Статус | Где смотреть |
|---|---|---|
| Block 0 — каркас FastAPI + auth + Avito-Cosplay тема | ✅ done | `avito-monitor/` |
| UI design spec + Claude Design мокапы | ✅ done | `DOCS/UI_DESIGN_SPEC_V1.md`, `AvitoSystemUI.zip` |
| Block 2 — Search Profiles (БД, CRUD, sidebar+форма+список+история) | ✅ done | `avito-monitor/app/{db,services,api,web,schemas}` |

Коммит финальный: `0c2be7f avito-monitor V1: Block 0 + Block 1 (UI design spec) + Block 2`.

### 0.2. Что осталось (7 блоков + инфра)

| Блок | Цель | Время моей работы |
|---|---|---|
| P (preflight) | Root OnePlus 8t, AvitoSessionManager APK, развёртка avito-xapi на homelab | 2-3 ч (вместе) |
| Block 1 | avito-mcp — MCP-сервер с 4 tools (тонкая обёртка над xapi) | 1.5–2 ч |
| Block 3 | LLM Analyzer (OpenRouter, 3 метода, кеш, бюджет) | 2 ч |
| Block 4 | Worker pipeline (TaskIQ + scheduler, polling + LLM-цепочка) | 2.5–3 ч |
| Block 5 | Telegram bot (aiogram 3.x, 9 типов уведомлений, inline-кнопки) | 1.5–2 ч |
| Block 6 | Stats dashboard (Chart.js: line / histogram / donut + market events) | 1.5–2 ч |
| Block 7 | Price Intelligence (4-шаговый алгоритм, отчёт) | 1.5–2 ч |
| Block 8 | Polish + deploy + 72h soak | 2–3 ч + soak |

**Итого:** ~12–17 часов кодинга + инфра + 72 ч прогона.

---

## 1. Граф зависимостей блоков

```
                  ┌─── Block 0 ✅ ───┐
                  │                  │
            ┌─────┴──┐         ┌─────┴──┐
            │Block 2 ✅│         │  P    │  (инфраструктура)
            │ profiles│         │OnePlus│
            └────┬────┘         │  +    │
                 │               │ xapi  │
                 │               └───┬───┘
                 │                   │
                 │               ┌───┴────┐
                 │               │Block 1 │
                 │               │avito-  │
                 │               │  mcp   │
                 │               └───┬────┘
                 │                   │
                 │   ┌────────────┐  │
                 │   │ Block 3    │  │  (LLM Analyzer — НЕ ЗАВИСИТ от Avito,
                 │   │OpenRouter  │  │   можно делать в любой момент)
                 │   └─────┬──────┘  │
                 │         │         │
                 └─────┬───┴─────────┘
                       │
                  ┌────┴─────┐
                  │ Block 4  │
                  │  worker  │
                  │ pipeline │
                  └────┬─────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   ┌────┴───┐    ┌────┴────┐    ┌────┴────┐
   │Block 5 │    │Block 6  │    │Block 7  │   (могут идти параллельно
   │   TG   │    │ stats   │    │  price  │    после правильного prep)
   │  bot   │    │ charts  │    │  intel  │
   └────┬───┘    └────┬────┘    └────┬────┘
        │             │              │
        └─────────────┼──────────────┘
                      │
                ┌─────┴─────┐
                │  Block 8  │
                │  deploy   │
                │  + polish │
                └───────────┘
```

### 1.1. Жёсткие зависимости (что ОБЯЗАТЕЛЬНО должно быть готово)

- **Block 1 требует:** P (xapi работает, токен льётся с телефона)
- **Block 3 не требует ничего** кроме `OPENROUTER_API_KEY` в `.env`
- **Block 4 требует:** Block 1 (источник лотов) + Block 3 (для classify/match)
- **Block 5 требует:** Block 4 (генерирует notifications). Можно частично с заглушкой
- **Block 6 требует:** Block 4 (данные в `profile_market_stats`). Можно начать с sample data
- **Block 7 требует:** Block 1 (поиск конкурентов) + Block 3 (compare_to_reference)
- **Block 8 требует:** все предыдущие

### 1.2. Что можно делать параллельно

**Без какой-либо подготовки:**
- **Block 1 ⊥ Block 3** — разные файлы (avito_mcp/ vs services/llm_analyzer.py + integrations/openrouter/), нет пересечений

**После Block 4 (нужен препроцессинг — см. §3):**
- **Block 5 ⊥ Block 6 ⊥ Block 7** — могут идти параллельно ПОСЛЕ выполнения preflight по разделу 3

### 1.3. Конфликтные файлы (пересечения)

| Файл | Кто трогает | Решение |
|---|---|---|
| `app/web/routers.py` | Block 5, 6, 7, 8 | Pre-flight split на sub-routers (см. §3.1) |
| `app/main.py` | Block 1, 4, 5 (регистрация таскеров) | Pre-flight: подготовить структуру `app/main.py` со всеми include_router заглушками заранее |
| `docker-compose.yml` | Block 1 (avito-mcp), Block 4 (worker+scheduler), Block 5 (bot), Block 8 (caddy) | Pre-flight: добавить все сервисы заглушками заранее, блоки только меняют content/command |
| `pyproject.toml` | Block 1 (mcp SDK), Block 3 (openai SDK), Block 5 (уже есть aiogram) | Pre-flight: добавить все зависимости сразу |
| `app/db/models/__init__.py` | Не трогает никто из оставшихся блоков | OK |
| `alembic/versions/` | Только Block 4 если нужны новые таблицы (вряд ли — все есть) | OK |

---

## 2. Pre-block инфраструктура (P1-P6)

**Когда:** до Block 1, тоже до Block 7. **Не блокирует** Block 3 (LLM).

### P1. Root OnePlus 8t (ты, ~30-60 мин)

1. Разлочить bootloader (если ещё не)
2. Поставить Magisk (через TWRP или Magisk-patched boot.img)
3. Verify root: `adb shell su -c id` → `uid=0(root)`

### P2. Avito-app + логин (ты, ~5 мин)

1. Установить Avito из Play Store (или сайт-APK, если в RU PS заблочен)
2. Залогиниться твоим аккаунтом
3. **Важно:** открыть вкладку «Сообщения» хотя бы раз — иначе токены не запишутся в SharedPrefs (см. `AvitoAll/Avito_Redroid_Token/CLAUDE.md`)

### P3. Сборка AvitoSessionManager APK (я, ~10 мин)

```
cd C:/Projects/Sync/AvitoSystem/AvitoAll/AvitoSessionManager
set JAVA_HOME=C:/Program Files/Android/Android Studio/jbr
gradlew.bat assembleDebug
```

Артефакт: `app/build/outputs/apk/debug/app-debug.apk`. Можно делать **сегодня**, не зависит от рута.

### P4. Установка APK + конфиг (вместе, ~10 мин)

```
adb install -r app-debug.apk
```

В UI приложения:
- **Server URL:** `http://<homelab_ip>:8080` (xapi после P5)
- **API Key:** генерируется по соглашению с xapi (см. P5)
- **Auto-sync:** ON
- **Auto-launch Avito:** ON

### P5. Развёртка avito-xapi на homelab (я, ~30-60 мин)

```bash
ssh homelab
cd /mnt/projects/repos/AvitoSystem/avito-xapi
docker compose up -d xapi  # порт 8080
```

Проверить:
- БД таблиц `avito_sessions`, `tenants`, `api_keys` есть в Supabase (см. `c:/Projects/Sync/CLAUDE.md` → Supabase Tenant System)
- Создать тенант для нашего пользователя + API key (хэш в `api_keys`)
- Health: `curl http://213.108.170.194:8080/health` → 200

### P6. End-to-end проверка токен-флоу (вместе, ~30 мин)

1. На телефоне нажать «Sync Now» в AvitoSessionManager
2. На xapi проверить что прилёт: `psql ... select user_id, expires_at from avito_sessions where is_active`
3. Через xapi сделать тест-поиск: `curl -H "X-Api-Key: ..." "http://homelab:8080/api/v1/search/items?query=iPhone%2012%20Pro%20Max&price_min=11000&price_max=13500"` → 200 + список лотов

---

## 3. Pre-flight для параллелизации (~30-45 мин)

**Когда:** перед запуском Block 5/6/7 параллельно. Отдельная мини-сессия.

**Цель:** убрать конфликты по `routers.py`, `docker-compose.yml`, `pyproject.toml`, `main.py`.

### 3.1. Split `app/web/routers.py` на sub-routers

Текущий `routers.py` (442 строки) разделить:

```
app/web/
├── __init__.py
├── routers.py         # ТОЛЬКО include_router всех sub-routers
├── auth_routes.py     # /login, /logout
├── dashboard_routes.py # /
├── profile_routes.py  # /search-profiles/*
├── listings_routes.py # /listings (Block 6 расширяет)
├── stats_routes.py    # /search-profiles/{id}/stats (Block 6 наполняет)
├── prices_routes.py   # /price-intelligence/* (Block 7 наполняет)
├── stub_routes.py     # /logs, /settings (Block 8 наполняет /settings)
└── _layout_context.py # _layout_context() helper
```

После split каждый Block N трогает только свой файл — нет конфликтов.

### 3.2. Заглушки docker-compose

В `docker-compose.yml` сразу добавить все сервисы:
- `app` (есть)
- `db` (есть)
- `redis` (есть)
- `worker` — `command: tail -f /dev/null` (Block 4 заменит на TaskIQ worker)
- `scheduler` — `command: tail -f /dev/null` (Block 4 заменит)
- `bot` — `command: tail -f /dev/null` (Block 5 заменит)
- `avito-mcp` — `command: tail -f /dev/null` (Block 1 заменит)

Все на одной shared network. Volume bind-mounts для всех.

### 3.3. Зависимости в pyproject.toml

Добавить все нужные пакеты сразу (они уже почти все есть):
- `mcp>=1.0` (Block 1)
- `openai>=1.55` (Block 3)
- `aiogram>=3.13` ✅ есть
- `taskiq>=0.11` ✅ есть
- `taskiq-redis>=1.0` ✅ есть

`uv sync` пересоберёт lockfile один раз.

### 3.4. Регистрация в main.py

В `app/main.py` зарегистрировать все будущие роутеры заранее (с заглушками `pass` если нужно). Так Block 5/6/7 не трогают `main.py` вообще.

---

## 4. Per-block ТЗ (для копирования в отдельные сессии)

### Как использовать

Каждая секция ниже — **самодостаточный промпт для новой Claude Code сессии**. Скопируй секцию целиком, вставь в новый чат, агент выполнит блок до проверочной точки.

Перед каждым блоком в новой сессии Claude Code должен:
1. Прочитать `c:/Projects/Sync/CLAUDE.md` (глобальные секреты + homelab)
2. Прочитать `c:/Projects/Sync/AvitoSystem/CLAUDE.md` (карта подпроектов)
3. Прочитать `DOCS/V1_EXECUTION_PLAN.md` (план сверху)
4. Прочитать `DOCS/DECISIONS.md` (10 ADR — особенно ADR-001, 008, 010)
5. Прочитать `DOCS/TZ_Avito_Monitor_V1.md` (главное ТЗ)

**Все эти файлы уже на месте.** Контекст-блок ниже добавляет только специфику блока.

---

### 🟦 Block 1 — avito-mcp

> **Контекст-промпт для новой сессии:**
>
> Ты работаешь над проектом `c:/Projects/Sync/AvitoSystem/avito-monitor/` — V1 системы мониторинга Avito. Block 0 + Block 2 уже сделаны (есть FastAPI + auth + БД + UI для search profiles). Сейчас твоя задача — **Block 1 из `DOCS/V1_EXECUTION_PLAN.md`**: написать `avito-mcp` MCP-сервер.
>
> **Критическое архитектурное решение:** в отличие от изначального плана, `avito-mcp` НЕ реализует реверс Avito API сам. Он — **тонкая обёртка над уже работающим `avito-xapi`** (см. `c:/Projects/Sync/AvitoSystem/avito-xapi/CLAUDE.md`). xapi уже умеет: загружать сессию из Supabase (которую льёт `AvitoSessionManager.apk` с рутового телефона), вызывать `app.avito.ru/api/11/items` (поиск) и `/19/items/{id}` (детали) с Chrome120 fingerprint через curl_cffi. Не переписывай эти куски — вызывай через HTTP.
>
> **Жёсткие зависимости:**
> - `avito-xapi` развёрнут и доступен (по умолчанию `http://213.108.170.194:8080` — homelab или локальный URL для разработки)
> - В `.env` есть `AVITO_XAPI_URL` и `AVITO_XAPI_API_KEY` (надо добавить)
> - Pre-flight (см. §3) выполнен — т.е. `avito-mcp` сервис в docker-compose.yml уже заглушкой, `mcp` SDK в pyproject.toml уже есть
>
> **Что делаешь:**
>
> 1. **Зависимости.** Убедись что `mcp>=1.0` и `httpx>=0.27` в `pyproject.toml`. Если нет — добавь.
>
> 2. **Создай структуру `avito_mcp/`** в корне `avito-monitor/`:
>    ```
>    avito-monitor/avito_mcp/
>    ├── __init__.py
>    ├── __main__.py         # точка входа: stdio | HTTP transport
>    ├── server.py           # FastMCP инстанс + регистрация tools
>    ├── config.py           # pydantic-settings: AVITO_XAPI_URL, AUTH_TOKEN, transport
>    ├── tools/
>    │   ├── __init__.py
>    │   ├── search.py       # avito_fetch_search_page
>    │   ├── listings.py     # avito_get_listing, avito_get_listing_images
>    │   └── service.py      # avito_health_check
>    └── integrations/
>        └── xapi_client.py  # async httpx клиент к xapi
>    ```
>
> 3. **`avito_mcp/integrations/xapi_client.py`** — `XapiClient` с методами:
>    - `async search_items(query, price_min, price_max, location_id, category_id, sort, page) -> dict`
>    - `async get_item(item_id: int) -> dict`
>    - `async health() -> dict` (статус сессии xapi)
>
>    URL и API key из env. Все запросы с `X-Api-Key` header.
>
> 4. **`avito_mcp/tools/search.py`** — реализация `avito_fetch_search_page`:
>    - Вход: `url: str` (Avito search URL), `page: int = 1`
>    - Использует `app.services.url_parser.parse_avito_url()` (импорт из основного приложения через shared/) ИЛИ копию парсера в `avito_mcp/integrations/url_parser.py`
>    - Парсит URL → params → дёргает `xapi_client.search_items(...)` с params + page
>    - Возвращает `{items: [ListingShort], total: int, has_more: bool}`
>    - **Важно:** если в URL только brand+filter slug без явного `?q=`, используй имя бренда + извлечённую модель как `query`
>
> 5. **`avito_mcp/tools/listings.py`** — `avito_get_listing(item_id_or_url)`:
>    - Если URL — извлеки числовой ID (последний сегмент в URL `/iphone_12_pro_max_1234567`)
>    - Дёргай `xapi_client.get_item(id)` → нормализуй в `ListingDetail` Pydantic
>
> 6. **`avito_mcp/tools/listings.py`** — `avito_get_listing_images(item_id)`:
>    - Дёргай `get_item`, извлеки `images[]` в оригинальном размере
>
> 7. **`avito_mcp/tools/service.py`** — `avito_health_check()`:
>    - Возвращает `{avito_reachable, xapi_reachable, session_ttl_hours, last_error}`
>    - Дёргает `xapi_client.health()`
>
> 8. **Pydantic-модели** в `avito-monitor/shared/models/avito.py` (можно создать новый файл):
>    - `ListingShort`: id, title, price, currency, region, url, images, seller_id, seller_type, first_seen
>    - `ListingDetail`: всё из Short + description, parameters, seller_info, raw_data
>    - `ListingImage`: url, width, height, index
>
> 9. **Транспорты** в `__main__.py`:
>    - `AVITO_MCP_TRANSPORT=stdio` → stdio (для локального Claude Code)
>    - `AVITO_MCP_TRANSPORT=http` → HTTP+SSE на порту 9000 (для backend)
>    - Auth-token обязателен для HTTP (`Authorization: Bearer <token>`)
>
> 10. **Docker-сервис.** Обнови `docker-compose.yml`: сервис `avito-mcp` с `command: python -m avito_mcp` и нужным env. Открой 9000:9000 наружу для отладки.
>
> 11. **MCP-конфиг** для Claude Code в `avito-monitor/mcp_configs/claude_code.mcp.json`:
>     ```json
>     {
>       "mcpServers": {
>         "avito-mcp": {
>           "command": "docker",
>           "args": ["exec", "-i", "avito-monitor-avito-mcp-1", "python", "-m", "avito_mcp"],
>           "env": { "AVITO_MCP_TRANSPORT": "stdio" }
>         }
>       }
>     }
>     ```
>
> 12. **Клиент в основном приложении.** `app/integrations/avito_mcp_client/client.py` с типизированными методами `fetch_search_page()`, `get_listing()` — используется в Block 4 worker.
>
> 13. **Тесты.** `tests/avito_mcp/test_tools.py` — 4 unit-теста с моком `XapiClient` (без сети). Один integration-тест с VCR-кассетой одного реального поиска (записывается один раз, потом replay).
>
> **Файлы которые ТОЧНО не трогать:**
> - `avito-monitor/app/web/templates/*` (UI)
> - `avito-monitor/app/services/search_profiles.py`, `url_parser.py` (Block 2 готов)
> - `avito-monitor/app/db/models/*` (нет новых таблиц)
> - `c:/Projects/Sync/AvitoSystem/avito-xapi/*` (это отдельный сервис, мы его только дёргаем)
>
> **Проверочная точка:**
> 1. `docker compose up -d avito-mcp` поднимает сервис без ошибок
> 2. Подключение Claude Code к `avito-mcp` через `mcp_configs/claude_code.mcp.json` — видны 4 tools
> 3. Вызов `avito_fetch_search_page` с URL `https://www.avito.ru/moskva/telefony/mobilnye_telefony/apple-ASgBAgICAUSwwQ2OWg?pmin=11000&pmax=13500` возвращает реальный список из ~20 лотов с правильными ценами в диапазоне 11–13.5K
> 4. `avito_get_listing` для одного из этих item_id возвращает details с описанием и фото
> 5. `avito_health_check` показывает `session_ttl_hours > 0`
>
> **Время:** 1.5–2ч.

---

### 🟪 Block 3 — LLM Analyzer

> **Контекст-промпт для новой сессии:**
>
> Ты работаешь над `c:/Projects/Sync/AvitoSystem/avito-monitor/` — V1 мониторинга Avito. Block 0 + Block 2 готовы. Твоя задача — **Block 3: LLM Analyzer (OpenRouter)**.
>
> **ВАЖНО:** этот блок **НЕ ТРЕБУЕТ** ни Avito, ни xapi, ни телефона. Только OpenRouter API key. Можно делать в любой момент параллельно с Block 1.
>
> **Архитектурный контекст:**
> - ADR-010: двухступенчатый LLM. Дешёвый `classify_condition` (haiku, ~$0.0001/лот) на ВСЕХ лотах. Тяжёлый `match_criteria` (sonnet или haiku) ТОЛЬКО на лотах в alert-зоне с подходящим состоянием. См. `DOCS/DECISIONS.md` ADR-010 + `DOCS/TZ_Avito_Monitor_V1.md` §4.4 + §8.1
> - Кеш: таблица `llm_analyses` уже создана в Block 2 (см. `app/db/models/llm_analysis.py`). Есть поле `cache_key` с индексом
> - Бюджет: `OPENROUTER_DAILY_USD_LIMIT` (default 10) — мягкий лимит. При превышении — classify останавливается на новых лотах, текущие match завершаются, шлётся уведомление типа `error`
>
> **Жёсткие зависимости:**
> - `OPENROUTER_API_KEY` в `.env` (нужно получить https://openrouter.ai)
> - Блок 2 готов (есть таблица `llm_analyses`)
>
> **Что делаешь:**
>
> 1. **OpenRouter клиент** — `app/integrations/openrouter/__init__.py` и `client.py`:
>    - Использует пакет `openai` (`AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=...)`)
>    - Шлёт заголовки `HTTP-Referer: <APP_BASE_URL>` и `X-Title: Avito Monitor`
>    - Поддерживает мультимодальные вызовы (image_url для visual)
>    - Возвращает structured `LLMResponse(content, input_tokens, output_tokens, cost_usd, latency_ms)`
>
> 2. **Промпты** в `app/prompts/`:
>    - `classify_condition.md` — Jinja2 шаблон. Вход: title, description, parameters. Выход: JSON `{condition_class: enum, confidence: float, reasoning: str}` где enum = working/blocked_icloud/blocked_account/not_starting/broken_screen/broken_other/parts_only/unknown
>    - `match_listing.md` — Вход: listing detail + custom_criteria + allowed_conditions. Выход: `{matches: bool, score: int 0-100, reasoning: str, key_pros: [str], key_cons: [str]}`
>    - `compare_listings.md` — Вход: reference + competitor. Выход: `{comparable: bool, score: int, key_advantages: [str], key_disadvantages: [str], price_delta_estimate: int}`
>    - `summarize_for_telegram.md` — Вход: listing + match_result. Выход: 2-3 предложения для TG
>    - **Tone:** русский язык, deterministic temperature (0.0-0.2), structured JSON output
>
> 3. **`app/services/llm_analyzer.py`** — класс `LLMAnalyzer` с методами:
>    ```python
>    async def classify_condition(listing: ListingDetail, model: str | None = None) -> ConditionClassification: ...
>    async def match_criteria(listing: ListingDetail, criteria: str, allowed_conditions: list[str], analyze_photos: bool, model: str | None = None) -> MatchResult: ...
>    async def compare_to_reference(competitor: ListingDetail, reference: ListingDetail | dict, model: str | None = None) -> ComparisonResult: ...
>    ```
>    Pydantic-модели результатов в `app/schemas/llm.py` или `shared/models/llm.py`.
>    
>    Каждый метод:
>    - Считает `cache_key` (sha256 от model + prompt_version + listing.avito_id + listing.avito_updated_at + criteria_hash)
>    - Смотрит в `llm_analyses` по `cache_key` — если хит, возвращает кешированный результат
>    - Если miss — рендерит промпт через Jinja2, дёргает OpenRouter, парсит JSON-результат, пишет в `llm_analyses` с `type` (`condition`/`match`/`compare`), `cost_usd`, `latency_ms`
>    - Стоимость считаешь из OpenRouter response usage (поля `prompt_tokens`, `completion_tokens`) и хардкода price-tier per model в `app/integrations/openrouter/pricing.py`
>
> 4. **Бюджет** в `app/services/llm_budget.py`:
>    - `async check_budget() -> bool` — суммирует `cost_usd` из `llm_analyses` за последние 24ч, сравнивает с `settings.openrouter_daily_usd_limit`
>    - `LLMBudgetExceeded` exception
>    - В `LLMAnalyzer.classify_condition` если budget exceeded — raise (Block 4 worker ловит и пишет error notification)
>    - В `match_criteria` — пропускает (текущие задачи завершаются)
>
> 5. **Тесты** в `tests/services/test_llm_analyzer.py`:
>    - Mock `AsyncOpenAI` ответами на 5–10 синтетических лотов из `DOCS/UI_DESIGN_SPEC_V1.md` §3.2 (5 working iPhones, 3 blocked_icloud, 2 broken_screen, 1 parts_only)
>    - Проверяешь: classify правильно вытаскивает condition_class, match-результат логичен, кеш работает (повторный вызов = 0 OpenRouter calls), бюджет ловится
>
> 6. **CLI-скрипт** `scripts/test_llm.py`:
>    ```bash
>    python -m scripts.test_llm classify --avito-id 4823432
>    # или с моковым лотом:
>    python -m scripts.test_llm classify --mock blocked_icloud
>    ```
>    Печатает результат человекочитаемо.
>
> **Файлы которые ТОЧНО не трогать:**
> - `app/web/templates/*`
> - `app/db/models/*` (используй существующую `LLMAnalysis`)
> - `alembic/versions/*` (нет новых миграций)
> - `app/services/search_profiles.py`, `url_parser.py`
> - `avito_mcp/*`
>
> **Проверочная точка:**
> 1. `python -m scripts.test_llm classify --mock blocked_icloud` показывает `condition_class=blocked_icloud, confidence>0.8`
> 2. Повторный вызов с тем же входом — нет запроса в OpenRouter (cache hit), выдаёт за <50ms
> 3. На 10 синтетических лотах из UI spec — все 8 классов corretly detected
> 4. `LLMAnalyzer.match_criteria(listing, "аккумулятор >85%, без царапин", ["working"])` для разных лотов даёт разный score (working iPhone score>70, broken_screen score<30)
>
> **Время:** 2 ч (1.5ч кодинга + 30 мин промпт-инжиниринг)

---

### 🟫 Block 4 — Worker pipeline

> **Контекст-промпт для новой сессии:**
>
> Ты работаешь над `c:/Projects/Sync/AvitoSystem/avito-monitor/`. Готовы Block 0, 2, 1 (avito-mcp), 3 (LLM). Твоя задача — **Block 4: TaskIQ worker + scheduler**.
>
> **Архитектурный контекст:**
> - 5 очередей: `high`, `default`, `llm_classify`, `llm_match`, `analytics`. Разные приоритеты (см. `DOCS/TZ_Avito_Monitor_V1.md` §4.6)
> - Двухступенчатый LLM (ADR-010): для каждого нового лота сначала classify (haiku), потом ТОЛЬКО для лотов в alert-зоне с проходящим состоянием — match
> - Триггеры уведомлений (ADR-009): `price_drop_listing`, `price_dropped_into_alert`, `market_trend_down/up`, `historical_low`, `supply_surge`, `condition_mix_change` — пороги из `notification_settings` профиля
> - Cleanup стратегия: `market_data` лоты — 30 дней, `analyzed` — 90 дней, `notified` — бессрочно
>
> **Жёсткие зависимости:**
> - Block 1 (avito-mcp) работает — есть источник лотов
> - Block 3 (LLMAnalyzer) работает
> - Pre-flight (§3) выполнен: docker-compose имеет worker + scheduler сервисы заглушкой
>
> **Что делаешь:**
>
> 1. **`app/tasks/broker.py`** — TaskIQ broker + Redis result backend, объявление 5 очередей.
>
> 2. **`app/tasks/scheduler.py`** — TaskIQ scheduler. Минутный тик: смотрит `search_profiles where is_active=true`, для каждого считает следующий запуск по `poll_interval_minutes` + `active_hours`, ставит в `default` очередь `poll_profile(profile_id)`.
>
> 3. **`app/tasks/polling.py` — `poll_profile(profile_id)`:**
>    - Создаёт `ProfileRun` со status=running
>    - Через `AvitoMCPClient` (см. Block 1) дёргает `fetch_search_page(profile.build_polling_url())`
>    - Для каждого item: upsert в `listings` (по `avito_id`), upsert `profile_listings` link
>    - Лоту присваивается `in_alert_zone` = (alert_min ≤ price ≤ alert_max)
>    - Помечает прежние лоты которые исчезли как `status=closed`
>    - Если у лота цена изменилась — пишет `last_price_change_at`, проверяет триггер `price_drop_listing` (>= profile_threshold)
>    - Для каждого нового лота ставит `analyze_listing(listing_id, profile_id)` в `llm_classify` queue
>    - Обновляет `ProfileRun` со status=success + метрики
>
> 4. **`app/tasks/analysis.py` — `analyze_listing(listing_id, profile_id)`:**
>    - Дёргает `LLMAnalyzer.classify_condition()` → пишет condition_class на listing
>    - Если `condition_class in profile.allowed_conditions` AND `in_alert_zone`:
>      - Ставит в `llm_match` очередь `match_listing(listing_id, profile_id)` 
>      - Иначе помечает `processing_status=market_data`
>    - Если budget exceeded — ловит `LLMBudgetExceeded`, пишет `error` notification
>
> 5. **`app/tasks/analysis.py` — `match_listing(listing_id, profile_id)`:**
>    - Через `LLMAnalyzer.match_criteria()` оценивает лот по custom_criteria
>    - Если `matches=True AND score >= min_confidence_threshold`:
>      - Создаёт `Notification(type=new_listing, payload=...)` для каждого канала из `profile.notification_channels`
>      - Помечает `processing_status=notified`
>    - Иначе — `processing_status=analyzed`
>
> 6. **`app/tasks/analytics.py` — `compute_market_stats(profile_id, granularity='day')`:**
>    - Раз в сутки в `analytics` queue
>    - Считает медианы / quantiles / count / disappearing (за период)
>    - Пишет в `profile_market_stats`
>    - Сравнивает с предыдущим периодом → триггеры `market_trend_*`, `supply_surge`, `condition_mix_change`, `historical_low` → notifications
>
> 7. **`app/tasks/cleanup.py` — `cleanup_old_listings()`:**
>    - Раз в сутки. Удаляет лоты по правилам §3.3 ADR-009
>
> 8. **`app/tasks/notifications.py` — `send_notification(notification_id)`:**
>    - **Заглушка** до Block 5. Просто логирует.
>    - Делает `notification.status=sent` чтобы не залипало
>
> 9. **Docker сервисы:** обнови `docker-compose.yml` — `worker` (`taskiq worker app.tasks.broker:broker --workers 4`), `scheduler` (`taskiq scheduler app.tasks.broker:scheduler`).
>
> 10. **Тесты** `tests/tasks/`:
>     - `test_polling.py` — мок MCP клиента, проверяешь upsert лотов
>     - `test_analysis.py` — мок LLM, проверяешь что workflow доходит до notification
>     - `test_market_stats.py` — на синтетических 30 днях из `UI_DESIGN_SPEC §3.4` triggers `market_trend_down`
>
> **Файлы которые ТОЧНО не трогать:**
> - `app/web/templates/*` (UI)
> - `avito_mcp/*` (Block 1)
> - `app/services/llm_analyzer.py` (Block 3)
> - `alembic/versions/*` (все таблицы есть)
>
> **Проверочная точка:**
> 1. Активный профиль iPhone 12 Pro Max до 13.5K + AvitoMCP работает + OpenRouter
> 2. Спустя 5 минут после `make up` в БД есть 20+ лотов с `condition_class != unknown`
> 3. Лоты в alert-зоне с working состоянием получили `processing_status=notified` (notification создана)
> 4. Если симулировать «цену лота упала на 15%» → возникает `price_drop_listing` notification
> 5. После 2-х прогонов `compute_market_stats` triggers `market_trend_down` если медиана упала
>
> **Время:** 2.5–3 ч.

---

### 🟧 Block 5 — Telegram bot (aiogram)

> **Контекст-промпт для новой сессии:**
>
> Ты работаешь над `c:/Projects/Sync/AvitoSystem/avito-monitor/`. Готовы блоки 0, 1, 2, 3, 4. Твоя задача — **Block 5: Telegram bot (aiogram 3.x)**.
>
> **Архитектурный контекст:**
> - **Pluggable provider** (см. memory `project_messengers.md`): абстракция `MessengerProvider` Protocol + `TelegramProvider` impl сейчас + заглушка `MaxProvider` на будущее. Нотификации не зависят от конкретного канала
> - 9 типов уведомлений (см. `DOCS/TZ_Avito_Monitor_V1.md` §4.5 расширенный + ADR-009): new_listing, price_drop_listing, price_dropped_into_alert, market_trend_down, market_trend_up, historical_low, supply_surge, condition_mix_change, error
> - Шаблоны сообщений provider-агностичные (Markdown core), per-provider адаптация
> - Whitelist по `TELEGRAM_ALLOWED_USER_IDS` (CSV в env)
> - Long polling (homelab без публичного HTTPS — webhook не нужен)
>
> **Жёсткие зависимости:**
> - Block 4 готов (генерирует Notifications в БД)
> - `TELEGRAM_BOT_TOKEN` и `TELEGRAM_ALLOWED_USER_IDS` в .env
> - Pre-flight (§3): bot сервис в docker-compose как заглушка
>
> **Что делаешь:**
>
> 1. **Provider абстракция** в `app/integrations/messenger/`:
>    ```
>    base.py        # MessengerProvider Protocol + MessengerMessage dataclass
>    telegram.py    # TelegramProvider(MessengerProvider)
>    max_stub.py    # MaxProvider(MessengerProvider) — raise NotImplementedError
>    factory.py     # get_provider(channel: str) -> MessengerProvider
>    ```
>
> 2. **`app/integrations/telegram/bot.py`** — aiogram 3.x bot:
>    - Polling lifecycle через `aiogram.Dispatcher`
>    - Все хендлеры через `Router`-ы
>    - Whitelist middleware: проверяет `tg_user_id in TELEGRAM_ALLOWED_USER_IDS`, неавторизованных шлёт «Доступ запрещён» + лог попытки
>
> 3. **Команды бота** (`/start /status /pause /resume /profiles /silent /help`):
>    - `/start` — приветствие, регистрация chat_id в `system_settings.tg_user_chat_map`
>    - `/status` — кол-во активных профилей, последняя активность, LLM-расход
>    - `/pause` / `/resume` — глобальный `system_paused` toggle
>    - `/profiles` — список профилей с inline-кнопками `[⏸/▶] [🔄 Run] [📊 Stats]`
>    - `/silent <minutes>` — pause notifications на N минут (запись в Redis)
>    - `/help`
>
> 4. **Шаблоны сообщений** в `app/prompts/messenger/*.md` — 9 шаблонов, по одному на тип уведомления (см. `DOCS/UI_DESIGN_SPEC_V1.md` §3.7 — там 4 готовых текста для образца). Используй Jinja2.
>
> 5. **Inline-кнопки** под new_listing: «✓ Просмотрено», «🚫 Скрыть продавца», «❌ Не показывать», «🔍 Повторный LLM». Callback-handlers меняют `profile_listing.user_action` или `search_profile.blocked_sellers`.
>
> 6. **Замени заглушку `send_notification` из Block 4:**
>    - В `app/tasks/notifications.py` дёргает `MessengerProvider` для каждого канала из `notification.channel`
>    - При success: `notification.status=sent, sent_at=now`
>    - При TG error: `retry_count++`, exponential backoff
>    - **Тихие часы:** проверяет `system_settings.silent_until` или `profile.active_hours` — если не время, оставляет pending
>
> 7. **Docker сервис** `bot`: команда `python -m app.integrations.telegram.bot`, depends_on db+redis.
>
> 8. **Тесты** `tests/integrations/telegram/`:
>    - Whitelist filter работает
>    - Команды дают правильные ответы (мок Bot)
>    - Inline callback меняет user_action в БД
>
> **Файлы которые ТОЧНО не трогать:**
> - `app/web/templates/*`
> - `avito_mcp/*`
> - `app/services/search_profiles.py`, `llm_analyzer.py`
> - `app/tasks/polling.py`, `analysis.py`, `analytics.py`, `cleanup.py` (Block 4 — кроме `notifications.py`, который мы заменяем)
> - `alembic/versions/*`
>
> **Можно безопасно работать параллельно с:** Block 6, Block 7 (после pre-flight §3, разные dirs).
>
> **Проверочная точка:**
> 1. `/start` от тебя в TG — бот отвечает приветствием
> 2. Активный профиль с тестовым лотом → через минуту тебе в TG приходит карточка с inline-кнопками
> 3. Нажатие «✓ Просмотрено» → в БД `profile_listing.user_action=viewed`
> 4. `/silent 60` — следующий час уведомления приходят как `pending`, после — улетают
>
> **Время:** 1.5–2 ч.

---

### 🟩 Block 6 — Stats dashboard (Chart.js)

> **Контекст-промпт для новой сессии:**
>
> Ты работаешь над `c:/Projects/Sync/AvitoSystem/avito-monitor/`. Готовы блоки 0, 1, 2, 3, 4. Твоя задача — **Block 6: stats dashboard на странице профиля + полноценная страница Лоты**.
>
> **Архитектурный контекст:**
> - Главная визуальная фишка V1 — `/search-profiles/{id}/stats`. 4 виджета (см. `DOCS/UI_DESIGN_SPEC_V1.md` §4.4): line-график медианы 30 дней с alert-зоной пунктиром, гистограмма с разделением working/non-working, donut condition-distribution, лента market-событий
> - Style: Avito-Cosplay Light. Все CSS-токены в `app/web/templates/base.html`. Палитра + Chart.js конфиг = §6 UI Spec и `AvitoSystemUI/screens/profile-stats.jsx` как реф-имплементация (порт оттуда)
> - Data приходит из `profile_market_stats` (Block 4 наполняет) + `listings` + `notifications where type LIKE 'market_%'`
> - **Если данных пока мало (< 7 дней)** — page показывает плейсхолдер «копится статистика, прогон #N/30», без падения
>
> **Жёсткие зависимости:**
> - Block 4 готов (наполняет `profile_market_stats`)
> - Pre-flight (§3): `app/web/stats_routes.py` создан как заглушка
>
> **Что делаешь:**
>
> 1. **`app/services/profile_stats.py`** — собирает данные для UI:
>    - `async get_stats_data(profile_id, period_days=30) -> StatsData` — точки графика, гистограмма, donut, события
>    - `async recommend_alert_range(profile_id) -> tuple[int, int]` — на основе p25/p75 чистой медианы
>
> 2. **HTMX-страница** `/search-profiles/{id}/stats` в `app/web/stats_routes.py`:
>    - Заголовок (имя профиля, статус, мини-toolbar)
>    - 4-карточка KPI-полоса (lots/alert/median/working_share)
>    - Виджет 1: line-chart медианы (30 дней) + alert-band overlay (custom Chart.js plugin — портируй из `AvitoSystemUI/screens/profile-stats.jsx:60-90`)
>    - Виджет 2: histogram (текущий снимок цен с разделением working/прочее, alert-полоса под X)
>    - Виджет 3: donut condition_distribution
>    - Виджет 4: лента market-событий (последние 7 дней)
>    - Авто-рекомендация alert-вилки (carded button)
>
> 3. **Раскрой страницу `/listings`** (сейчас stub):
>    - Маршрут `app/web/listings_routes.py`
>    - Layout по `DOCS/UI_DESIGN_SPEC_V1.md` §4.5
>    - Фильтр-чипы: profile, condition_class, alert/market, period
>    - HTMX-обновление списка in-place (без полной перезагрузки)
>    - Ссылки на `/listings/{id}` (можно сразу или заглушка)
>    - Пагинация (load more)
>
> 4. **Базовая `/logs`** — простая таблица последних 100 событий из `audit_log` + `notifications where type=error`. Без сложной UI — ленту-таблицу.
>
> 5. **Chart.js** — подключение через CDN в `base.html` (или OOB в layout). Не SSR.
>
> 6. **Sample data режим:** если `profile.market_stats` пуст — fallback на `DOCS/UI_DESIGN_SPEC_V1.md` §3.4 (30-дневная история) с явной плашкой «📌 Demo data — реальные точки появятся после 30 прогонов».
>
> **Файлы которые ТОЧНО не трогать:**
> - `app/tasks/*` (Block 4)
> - `app/integrations/telegram/*` (Block 5)
> - `app/services/llm_analyzer.py`, `search_profiles.py`, `url_parser.py`
> - `avito_mcp/*`
> - `alembic/versions/*`
>
> **Можно безопасно работать параллельно с:** Block 5, Block 7 (после pre-flight §3 — разные routes файлы и templates dirs).
>
> **Проверочная точка:**
> 1. Активный профиль за неделю работы → `/search-profiles/{id}/stats` показывает все 4 виджета с реальными данными
> 2. Если данных нет — placeholder, без падения
> 3. `/listings` с фильтрами: переключение чипа condition_class обновляет список без полной перезагрузки страницы
> 4. Кнопка «Применить рекомендованную вилку» меняет `alert_min/max` в профиле + toast «применено»
>
> **Время:** 1.5–2 ч.

---

### 🟨 Block 7 — Price Intelligence

> **Контекст-промпт для новой сессии:**
>
> Ты работаешь над `c:/Projects/Sync/AvitoSystem/avito-monitor/`. Готовы блоки 0, 1, 2, 3, 4. Твоя задача — **Block 7: Price Intelligence (модуль ценовой разведки)**.
>
> **Архитектурный контекст:**
> - Полное ТЗ: `DOCS/TZ_Avito_Monitor_V1.md` §4.2
> - Алгоритм 4 шагов: (1) по фильтрам найти аналоги в регионе → (2) для каждого деталь → (3) LLM сравнение с эталоном → (4) построение отчёта (вилка / топ-5 дешевле / топ-5 дороже / рекомендация)
> - UI спека: `DOCS/UI_DESIGN_SPEC_V1.md` §4.6 + sample отчёт §3.6
>
> **Жёсткие зависимости:**
> - Block 1 (avito-mcp для поиска конкурентов и деталей)
> - Block 3 (`LLMAnalyzer.compare_to_reference`)
> - Pre-flight (§3): `app/web/prices_routes.py` как заглушка
>
> **Что делаешь:**
>
> 1. **Таблицы:** `price_analyses`, `price_analysis_runs` уже определены в Block 2 миграции? **ПРОВЕРЬ** (`alembic/versions/20260425_1300_search_profiles_and_co.py`). Если нет — добавь 3-ю миграцию с этими двумя таблицами по `DOCS/TZ_Avito_Monitor_V1.md` §5.1
>
> 2. **`app/services/price_intelligence.py`** — `PriceIntelligenceService`:
>    - `async create_analysis(data: PriceAnalysisCreate) -> PriceAnalysis`
>    - `async run_analysis(analysis_id) -> PriceAnalysisRun` — запуск 4-шагового алгоритма:
>      1. По filters (region, brand+model, диапазон) дёргает `avito_fetch_search_page` (Block 1) с пагинацией до `max_competitors`
>      2. Для каждого `avito_get_listing` (детали)
>      3. Для каждого `LLMAnalyzer.compare_to_reference(competitor, reference)`
>      4. Build report: квантили вилки, топ-5/-5 по `score`, рекомендованная цена (медиана сопоставимых × 0.95)
>    - Кеш: повторный прогон за <24ч переиспользует существующие `llm_analyses where type=compare`
>
> 3. **REST API** в `app/api/price_analyses.py`: CRUD + `/run`. Формат — как `app/api/search_profiles.py`.
>
> 4. **HTMX-страницы** в `app/web/prices_routes.py`:
>    - `/price-intelligence` — список запусков (карточки)
>    - `/price-intelligence/new` — форма (URL своего объявления ИЛИ ручной ввод characteristics + регион + макс конкурентов)
>    - `/price-intelligence/{id}` — отчёт (по UI Spec §4.6: вилка, гистограмма с твоей звездой, топ-5/-5 таблицы, рекомендация, кнопка «отправить в Telegram»)
>    - `/price-intelligence/{id}/runs/{run_id}/send-telegram` — POST → шлёт отчёт через MessengerProvider (Block 5)
>
> 5. **Экспорт в Markdown** в `app/services/price_intelligence.py` — `export_report_markdown(run_id) -> str`. Используется и для скачать-ссылки и для TG.
>
> 6. **Тесты** `tests/services/test_price_intelligence.py`:
>    - Мок MCPClient и LLMAnalyzer
>    - Прогон на синтетических 28 конкурентах (см. `DOCS/UI_DESIGN_SPEC_V1.md` §3.6)
>    - Проверяешь correctness вилки, топов, рекомендации
>
> **Файлы которые ТОЧНО не трогать:**
> - `app/tasks/*` (Block 4 — Price Intelligence синхронный, не через таск-очередь в V1)
> - `app/integrations/telegram/*` (Block 5 — используем через `MessengerProvider`)
> - `app/services/llm_analyzer.py`, `search_profiles.py`, `url_parser.py`, `profile_stats.py`
> - `avito_mcp/*`
> - `app/web/templates/profiles/*`, `dashboard.html`, `_layout.html`, `_macros.html`
>
> **Можно безопасно работать параллельно с:** Block 5, Block 6 (после pre-flight §3).
>
> **Проверочная точка:**
> 1. Создание PriceAnalysis через UI с твоим реальным объявлением (или sample reference из §3.6)
> 2. Прогон завершается за <3 минут на 30 конкурентах
> 3. Отчёт показывает: вилку (мин/p25/median/p75/max), две таблицы по 5 строк, рекомендованную цену с обоснованием
> 4. «Отправить в TG» отправляет суммарный отчёт в Markdown
>
> **Время:** 1.5–2 ч.

---

### ⬛ Block 8 — Polish + deploy + 72h soak

> **Контекст-промпт для новой сессии:**
>
> Ты работаешь над `c:/Projects/Sync/AvitoSystem/avito-monitor/`. Готовы блоки 0-7. Твоя задача — **Block 8: финальная полировка, деплой на homelab, 72-часовой soak**.
>
> **Архитектурный контекст:**
> - Acceptance criteria: `DOCS/TZ_Avito_Monitor_V1.md` §14 — все 17 пунктов должны выполняться
> - Деплой на homelab `213.108.170.194` под доменом (если есть) или прямо на IP. Caddy как reverse-proxy
> - Бэкап БД: `pg_dump` ежесуточно через cron, retention 14 дней
>
> **Жёсткие зависимости:**
> - Все предыдущие блоки готовы
>
> **Что делаешь:**
>
> 1. **Settings page** (`/settings`) — раскрой stub:
>    - Раздел «LLM»: модели по умолчанию, OPENROUTER_DAILY_USD_LIMIT, текущий расход / 24ч
>    - Раздел «Мессенджеры»: TG token, allowed_user_ids, Max-канал (заглушка-disabled)
>    - Раздел «Avito»: avito-mcp URL, токен, статус (через health_check)
>    - Раздел «Тихие часы»: глобальное расписание
>    - Раздел «System»: pause/resume, версия, последний прогон
>
> 2. **E2E тесты** `tests/e2e/`:
>    - Полный флоу: create profile via UI → wait poll → verify listings → check notifications
>    - Используй `httpx.AsyncClient` против запущенного docker-compose
>
> 3. **`make backup`:**
>    - `scripts/backup_db.sh`: `pg_dump` → `/var/backups/avito-monitor/$(date +%Y%m%d).sql.gz`
>    - Retention: удалять старше 14 дней
>    - В `Makefile` цель `backup`
>
> 4. **Cron на homelab:**
>    - `/etc/cron.d/avito-monitor-backup`: ежесуточно в 03:00 UTC
>
> 5. **Caddy** в `docker-compose.yml`:
>    - Сервис `proxy: caddy:2-alpine`
>    - `Caddyfile` с автосертификатами (если есть домен) или self-signed
>    - Ports 80, 443
>
> 6. **`docs/deployment.md`** — пошаговый гайд:
>    - Pre-requisites
>    - Установка Docker
>    - Клонирование репо
>    - .env заполнение
>    - `make up`, `make migrate`, `make admin`
>    - Установка APK на телефон, конфиг URL
>    - Caddy + домен
>    - Cron бэкап
>    - Logs / monitoring
>
> 7. **`make lint`** — `ruff check .` + `mypy app/`. Все warnings подавлены или явно `# type: ignore` с обоснованием.
>
> 8. **`make test`** — `pytest tests/ -v --cov`. Цель: ≥70% coverage критичных сервисов.
>
> 9. **README обновление:** актуальные инструкции, ссылки на `docs/deployment.md`, `DOCS/V1_BLOCKS_TZ.md` (этот файл) для разработки.
>
> 10. **Деплой на homelab:**
>     - SSH homelab
>     - clone repo
>     - `cp .env.example .env` + заполнить
>     - `make up && make migrate && make admin && make seed`
>     - Открыть в браузере, залогиниться
>     - Создать реальный профиль iPhone
>     - Дождаться первой нотификации в TG
>
> 11. **72-часовой soak:**
>     - Минимум 1 активный профиль
>     - 5-минутный интервал polling
>     - Никакого ручного вмешательства 72ч
>     - Проверить: ни одно уведомление не потеряно, миграции успешны при `make up` (idempotent), БД-размер растёт линейно (cleanup работает), token не истёк (или auto-refresh сработал)
>
> 12. **Финальная проверка по `DOCS/TZ_Avito_Monitor_V1.md` §14** — все 17 пунктов помечаются ✓.
>
> **Файлы которые ТОЧНО не трогать:**
> - Логику в `app/services/*` (если работает — не лезть)
> - Промпты в `app/prompts/*` (если результат нравится — не менять)
> - `alembic/versions/*` старые
>
> **Проверочная точка:** все 17 acceptance criteria из ТЗ §14 — пройдены.
>
> **Время:** 2–3 ч кодинга + 72ч soak (без вмешательства).

---

## 5. Матрица параллелизма (детальная)

Для координатора: что можно дать в работу одновременно без боязни мерж-конфликтов.

### 5.1. Можно в параллель сразу (без pre-flight)

| Pair | Почему безопасно |
|---|---|
| **Block 1 + Block 3** | Разные dirs: `avito_mcp/` vs `app/services/llm_analyzer.py` + `app/integrations/openrouter/`. `pyproject.toml` — обе блока добавляют разные deps, легко слить вручную. `docker-compose.yml` — Block 1 трогает `avito-mcp` сервис, Block 3 не трогает compose. |

### 5.2. Можно в параллель ПОСЛЕ pre-flight (§3)

| Pair / Triple | Почему безопасно с pre-flight |
|---|---|
| **Block 5 + Block 6** | Block 5 — `app/integrations/messenger/`, `app/integrations/telegram/`, `app/tasks/notifications.py`. Block 6 — `app/services/profile_stats.py`, `app/web/{stats,listings,logs}_routes.py`, `templates/profiles/stats.html`. **Без pre-flight конфликтует**: оба меняют `routers.py`. С pre-flight — каждый трогает свой sub-router. |
| **Block 5 + Block 7** | Block 7 — `app/services/price_intelligence.py`, `app/api/price_analyses.py`, `app/web/prices_routes.py`. Не пересекается с messenger/telegram. |
| **Block 6 + Block 7** | Разные шаблон-папки (`profiles/stats.html` vs `prices/*.html`). Разные routes-файлы. С pre-flight — не пересекаются. |
| **Block 5 + Block 6 + Block 7** одновременно | OK с pre-flight. Каждый получает свой routes-файл, свой templates-subdir, свой service. Только финальный мерж на main (или отдельных feature-веток). |

### 5.3. ВЕЗДЕ нельзя параллелить

| Block X + Block Y | Почему НЕТ |
|---|---|
| **Block 4 + Block 1/3/5/6/7** | Block 4 переписывает `app/tasks/notifications.py` для использования через провайдер (Block 5 потом докручивает). Block 4 хукается в `app/services/search_profiles.py` (модификация для polling URL build). Block 4 — централизатор, должен быть **готов** до Blocks 5/6/7. |
| **Block 8 + что-либо** | Финальный полировочный блок, должен идти **после всех остальных**. |

---

## 6. Рекомендуемое расписание сессий

### Вариант A — линейный (минимум координации)

| День | Сессия | Блоки | Время моей работы |
|---|---|---|---|
| Сегодня | 1 | Block 3 (LLM, без Avito) | 2 ч |
| Завтра | 2 | P1-P6 + Block 1 | 1 ч инфра + 2 ч |
| Завтра | 3 | Block 4 | 3 ч |
| Послезавтра | 4 | Pre-flight §3 + Block 5 | 0.5 + 2 ч |
| Послезавтра | 5 | Block 6 + Block 7 | 4 ч |
| +3 дня | 6 | Block 8 | 3 ч |
| +3..6 дней | 7 | 72 ч soak | мониторинг |

**Итого:** 4 рабочих сессии, ~17 ч кодинга, далее soak.

### Вариант B — с параллелизмом (требует subagent или несколько сессий)

| День | Параллельный пуск | Блоки |
|---|---|---|
| Сегодня | A: Block 3 | LLM |
| Завтра утро | — | P1-P6 |
| Завтра | A: Block 1 | avito-mcp |
| Завтра | (последовательно) | Block 4 |
| Послезавтра | — | Pre-flight §3 (≤30 мин) |
| Послезавтра | A: Block 5, B: Block 6, C: Block 7 | три сессии в параллель |
| +2 дня | A: Block 8 | polish + deploy |

**Итого:** 5 «слотов» вместо 7, но требует координации трёх параллельных потоков. Экономия ~3-4 часа wall-time за счёт параллелизма.

---

## 7. Чеклист для каждой новой сессии

При запуске сессии (новое контекстное окно) для конкретного блока:

1. ☐ Открой репо: `cd c:/Projects/Sync/AvitoSystem`
2. ☐ Проверь `git status` — текущее состояние (что закоммичено, что в WIP)
3. ☐ Скопируй секцию «Block N» из этого файла (раздел 4) в первый промпт
4. ☐ Агент должен прочитать перед стартом:
   - `c:/Projects/Sync/CLAUDE.md` (глобальные секреты)
   - `c:/Projects/Sync/AvitoSystem/CLAUDE.md` (карта проекта)
   - `DOCS/TZ_Avito_Monitor_V1.md` (главное ТЗ)
   - `DOCS/DECISIONS.md` (10 ADR)
   - `DOCS/V1_EXECUTION_PLAN.md` (план)
   - `DOCS/V1_BLOCKS_TZ.md` (этот файл, особенно §4 + матрица §5)
5. ☐ Перед коммитом: `git status` — убедиться что в стейдж попадают только файлы из «можно трогать»
6. ☐ Коммит с осмысленным сообщением (формат как в коммите `0c2be7f`)

---

**Конец документа.**
