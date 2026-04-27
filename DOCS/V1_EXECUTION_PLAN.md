# V1 Execution Plan

**Назначение:** план реализации V1 в формате «что я (Claude Code) делаю → что пользователь проверяет → переход к следующему блоку». Заменяет календарные сроки из раздела 13 ТЗ для нашего темпа работы. Раздел 13 ТЗ остаётся как human-baseline reference.

**Перед чтением этого файла обязательно** прочитай:
1. `DOCS/TZ_Avito_Monitor_V1.md` (актуальная версия — 1.2)
2. `DOCS/DECISIONS.md` (10 ADR с обоснованиями ключевых решений — особенно ADR-001, 008, 010)
3. `CLAUDE.md` в корне репо

**Контекст пользователя:** владелец homelab (213.108.170.194), координирует разработку, **не пишет код**. Обратная связь даётся быстро, но детальные UX-решения нужно предлагать.

---

## Pre-flight — автоматический

Pre-flight выполняется **автоматически** при старте каждой сессии Claude Code через SessionStart hook (`.claude/settings.json` → `scripts/session_preflight.sh`). Скрипт:

- Проверяет SOCKS5-туннель к homelab. Если нет — поднимает (`ssh -D 1081 -N -f homelab`)
- Проверяет, запущен ли Docker Desktop (предупреждает если нет)
- Проверяет, установлен ли uv (предупреждает если нет)

Hook идемпотентный — повторный запуск не дублирует туннели. Отчёт виден в начале сессии. Если есть `❌` или `⚠️` — пользователь решает что делать (обычно: запустить Docker Desktop вручную, поставить uv).

**Что должно быть до этого** (один раз):
- [ ] SSH-алиас `homelab` настроен в `~/.ssh/config` (используется для туннеля)
- [ ] `.env` в корне `c:\Projects\Sync\AvitoSystem\` содержит `AVITO_OFFICIAL_CLIENT_ID/SECRET` (уже сделано)
- [ ] Python 3.12+ установлен на хосте

Подробности туннеля и ручной запуск — `DOCS/RU_PROXY_SETUP.md`.

---

## Структура нового монорепо

Создаётся в `c:\Projects\Sync\AvitoSystem\avito-monitor\` (рядом с существующими `avito-xapi/`, `AvitoBayer/` и т.д.). Не трогает существующий код, переиспользует через копирование/импорт.

Скелет — раздел 10 ТЗ. Ключевое:
```
avito-monitor/
├── pyproject.toml          # uv workspace
├── docker-compose.yml      # app + worker + scheduler + bot + avito-mcp + db + redis
├── .env.example
├── alembic.ini
├── alembic/versions/
├── shared/                 # Pydantic-модели, общие для app и avito_mcp
├── avito_mcp/              # MCP-сервер
│   ├── __main__.py         # stdio | HTTP transport
│   ├── server.py
│   ├── tools/              # 4 V1 tools
│   └── integrations/       # перенос из avito-xapi/src/workers/
├── app/                    # FastAPI + worker
│   ├── main.py
│   ├── api/, web/, db/, services/, tasks/, prompts/, integrations/
│   └── data/avito_regions.json
└── tests/
```

---

## Блок 0 — Каркас

**Цель:** запускается `docker compose up`, открывается `http://localhost:8000`, страница логина рендерится.

**Что я делаю:**
1. Создание `avito-monitor/` со структурой раздела 10 ТЗ
2. `pyproject.toml` с зависимостями (FastAPI, SQLAlchemy 2.0 async, asyncpg, alembic, taskiq, taskiq-redis, aiogram, jinja2, htmx, pydantic-settings, structlog, argon2-cffi)
3. `docker-compose.yml` (минимум: app + db + redis), `Dockerfile` мультистейдж
4. `app/main.py` с FastAPI, lifespan, structured-logging
5. `app/config.py` через pydantic-settings, читает `.env`
6. Alembic init + первая миграция (таблицы `users`, `system_settings`)
7. Базовый layout Jinja2 + Tailwind через CDN (DaisyUI), HTMX подключён
8. Страница `/login` + auth с argon2 + httponly cookie сессия
9. Скрипт `scripts/create_admin.py`
10. Makefile с `make up`, `make migrate`, `make migration name=`, `make logs`
11. README с инструкцией старта

**Deliverable:**
- `cd avito-monitor && cp .env.example .env && make up` поднимает 3 контейнера
- `make migrate` применяет миграции
- `make admin user=owner pass=...` создаёт админа
- `http://localhost:8000/login` отдаёт форму, успешный логин ставит куку, редирект на `/`

**Проверочная точка:** пользователь открывает в браузере, логинится, видит пустой dashboard с надписью «V1.2».

**Время моей работы:** 30–60 мин.

---

## Блок 1 — avito-mcp (4 tools)

**Цель:** MCP-сервер запускается отдельным сервисом, отдаёт 4 tools, основной бэкенд может его дёрнуть.

**Что я делаю:**
1. `avito_mcp/integrations/` — перенос из `avito-xapi/src/workers/`:
   - `http.py` — curl_cffi Chrome120 base client
   - `rate_limiter.py` — TokenBucket
   - `auth.py` — JWT-парсер
2. `avito_mcp/integrations/reverse_api.py`:
   - `fetch_search_page(url, page)` — fetch HTML, извлечение `__initialData__` или JSON-стейта
   - `get_listing(item_id_or_url)` — детали через mobile API
   - Поддержка `AVITO_PROXY_URL` (для dev — `socks5://127.0.0.1:1081`)
3. `shared/models/` — Pydantic-модели `ListingShort`, `ListingDetail`, `SearchPageResult`
4. `avito_mcp/server.py` — FastMCP с регистрацией 4 tools (см. ТЗ 4.3.3 V1)
5. `avito_mcp/__main__.py` — stdio | HTTP transport через env
6. AUTH-токен для HTTP, опциональный
7. Docker сервис `avito-mcp:9000`
8. `mcp_configs/claude_code.mcp.json` — для подключения из Claude Code
9. `app/integrations/avito_mcp_client/` — типизированный HTTP-клиент
10. `docs/mcp_usage.md`
11. Тесты: VCR-кассета на одну реальную выдачу + моки

**Deliverable:**
- Подключение к `avito-mcp` из Claude Code через `mcp_configs/claude_code.mcp.json` — видны 4 tools
- Вызов `avito_fetch_search_page` с URL «iPhone 12 Pro Max» возвращает список лотов
- Вызов `avito_get_listing` возвращает детали
- В docker compose всё работает

**Проверочная точка:** пользователь даёт реальный URL Avito, я через MCP вытаскиваю выдачу, показываем результат в JSON.

**Время моей работы:** 1–2 часа (+ возможно итерация на парсинг `__initialData__` если структура неожиданная).

---

## Блок 2 — Search Profiles (БД + CRUD + дашборд)

**Цель:** через UI можно создать профиль по URL Avito, увидеть список профилей, ad-hoc запустить.

**Что я делаю:**
1. SQLAlchemy 2.0 модели по разделу 5.1 ТЗ:
   - `users` (уже есть из блока 0), `system_settings`
   - `search_profiles` с полями двойной вилки + overlay (см. ТЗ 4.1)
   - `listings`, `profile_listings`, `profile_runs`, `llm_analyses`, `notifications`, `audit_log`
   - `profile_market_stats` (новая, ADR-009)
2. Alembic миграции для всех таблиц
3. Repositories в `app/db/repositories/`
4. Pydantic-модели в `app/schemas/` для валидации
5. `app/services/search_profiles.py`:
   - `create_profile(data)` — парсинг URL, авто-расчёт search-вилки ±25% от alert
   - `apply_overlay(url, profile)` — применение overlay перед polling
   - `parse_avito_url(url)` — extraction parsed_brand/model/category для UI
6. REST API `app/api/search_profiles.py` — CRUD + toggle + run-now (см. ТЗ 6.2)
7. HTMX-страницы:
   - `/search-profiles` — список
   - `/search-profiles/new` — форма создания (URL + alert-вилка + overlay + LLM-критерии + расписание)
   - `/search-profiles/{id}` — редактирование
   - `/search-profiles/{id}/runs` — история (заглушка пока без реального воркера)
8. Seed `app/data/avito_regions.json` (~30 регионов)

**Deliverable:**
- Юзер копирует URL «iPhone 12 Pro Max до 13.5K» из Avito, вставляет в форму
- Парсер показывает «Apple / iPhone 12 Pro Max / 11000–13500»
- Авто-заполняется search-вилка 8250–16875
- Профиль сохраняется в БД
- Список профилей виден в дашборде

**Проверочная точка:** пользователь создаёт 2 профиля через UI, я показываю что в БД.

**Время моей работы:** 2–3 часа.

---

## Блок 3 — LLM Analyzer

**Цель:** есть рабочий `LLMAnalyzer` с тремя методами, кешем, бюджетом.

**Что я делаю:**
1. `app/integrations/openrouter/client.py` — OpenRouter через openai SDK (base_url override)
2. `app/services/llm_analyzer.py` с тремя методами (см. ТЗ 4.4)
3. Промпты в `app/prompts/`:
   - `classify_condition.md`
   - `match_listing.md`
   - `compare_listings.md`
   - `summarize_for_telegram.md`
4. Кеш через `llm_analyses` (таблица уже создана в блоке 2)
5. Учёт расходов в `cost_usd`, мягкий лимит `OPENROUTER_DAILY_USD_LIMIT`
6. Тесты с mock OpenRouter responses на 5–10 синтетических лотов

**Deliverable:**
- Скрипт `scripts/test_llm.py` принимает avito_id, делает classify_condition + match_criteria, печатает результат
- Кеш работает: повторный вызов не идёт в OpenRouter

**Проверочная точка:** прогон на 10 реальных лотах, юзер смотрит правильность классификации (правильно ли вытащился blocked_icloud / broken_screen).

**Время моей работы:** 1–2 часа кодинга + 30 мин на промпт-инжиниринг.

---

## Блок 4 — Worker pipeline (TaskIQ)

**Цель:** профили автоматически опрашиваются по расписанию, новые лоты проходят через classify → match → notification.

**Что я делаю:**
1. `app/tasks/broker.py` — TaskIQ + Redis broker, 5 очередей (high, default, llm_classify, llm_match, analytics)
2. `app/tasks/scheduler.py` — TaskIQ scheduler, минутный тик
3. Задачи (см. ТЗ 4.6):
   - `poll_profile(profile_id)`
   - `analyze_listing(listing_id)` — двухступенчатый
   - `compute_market_stats(profile_id, granularity)`
   - `cleanup_old_listings()`
   - `send_notification(notification_id)` (заглушка для блока 5)
4. Обработка триггеров уведомлений (price_drop, historical_low, supply_surge — см. ADR-009)
5. Docker сервисы `worker` + `scheduler`

**Deliverable:**
- Активный профиль с интервалом 5 минут — автоматически опрашивается
- Новые лоты идут в `listings` с `condition_class`, в alert-зоне получают `match_result`
- В `profile_runs` пишутся метрики

**Проверочная точка:** запустили тестовый профиль на iPhone 12 Pro Max, через 10 минут видим в БД 30+ лотов с классификацией.

**Время моей работы:** 2–3 часа.

---

## Блок 5 — Telegram bot (aiogram)

**Цель:** уведомления летят в Telegram с правильным форматом и inline-кнопками.

**Что я делаю:**
1. `app/integrations/telegram/bot.py` — aiogram 3.x, long polling
2. Команды: `/start`, `/status`, `/pause`, `/resume`, `/profiles`, `/silent`, `/help` (см. ТЗ 7.1)
3. Whitelist по `TELEGRAM_ALLOWED_USER_IDS`
4. 9 типов уведомлений (см. ТЗ 4.5 расширенный) с шаблонами в `app/prompts/telegram/*.md`
5. Inline-кнопки + callback handlers (просмотрено / скрыть продавца / не показывать)
6. Docker сервис `bot`
7. Тихие часы

**Deliverable:**
- В Telegram приходит уведомление о подходящем лоте
- Нажатие inline-кнопки меняет состояние в БД

**Проверочная точка:** юзер получает первое реальное уведомление по своему профилю.

**Время моей работы:** 1–2 часа.

---

## Блок 6 — Дашборд statistics

**Цель:** на странице профиля видны графики и инсайты рынка.

**Что я делаю:**
1. Страница `/search-profiles/{id}/stats` (см. ТЗ 4.7 пункт 4a)
2. Chart.js: график clean-медианы / min / max за 30 дней + alert-вилка пунктиром
3. Гистограмма распределения цен + condition_class разбивка
4. Лента рыночных событий (последние 20 уведомлений типа market_*)
5. Кнопка авто-рекомендации alert-вилки
6. Страница `/listings` с фильтрами по condition_class
7. Базовая страница `/logs`

**Deliverable:**
- Графики рендерятся, тренды видны, события в ленте

**Проверочная точка:** пользователь смотрит дашборд за неделю, оценивает качество визуализации.

**Время моей работы:** 1–2 часа.

---

## Блок 7 — Price Intelligence

**Цель:** работает модуль ценовой разведки (ТЗ раздел 4.2).

**Что я делаю:**
1. SQLAlchemy: `price_analyses`, `price_analysis_runs` (уже создано в блоке 2)
2. `app/services/price_intelligence.py` — алгоритм 4 шагов (4.2 ТЗ)
3. Страницы `/price-intelligence/new`, `/price-intelligence/{id}`
4. Использует `LLMAnalyzer.compare_to_reference`

**Deliverable:**
- Юзер вводит URL своего объявления, получает отчёт с вилкой и топ-5 конкурентов

**Проверочная точка:** прогон на реальном объявлении пользователя.

**Время моей работы:** 1–2 часа.

---

## Блок 8 — Polish + deploy

**Цель:** production-ready, развёрнуто на homelab.

**Что я делаю:**
1. E2E-тесты ключевых сценариев
2. `make backup` + cron для ежесуточного `pg_dump`
3. Caddy reverse proxy в docker-compose (опционально)
4. `docs/deployment.md`
5. Обновление README с актуальными инструкциями
6. `lint` + типы (ruff + mypy)
7. Деплой на homelab по `docs/deployment.md`
8. Прогон 72 часа без вмешательства

**Deliverable:**
- Система работает на `https://213.108.170.194` (или домене), бэкапы идут, всё стабильно

**Проверочная точка:** acceptance criteria раздела 14 ТЗ — все 17 пунктов.

**Время моей работы:** 1–2 часа кодинга + проверка.

---

## Резюме

8 блоков × 1–3 часа = **11–19 часов моей работы**. С учётом feedback-петель и реального тестирования — **2–4 рабочих сессии**.

Распределение по сессиям (предложение):
- **Сессия 1:** блоки 0+1+2 → к концу есть профиль в БД и можно вызвать MCP
- **Сессия 2:** блоки 3+4+5 → к концу первое реальное Telegram-уведомление
- **Сессия 3:** блоки 6+7+8 → к концу деплой на homelab

Конкретные блоки можно объединять/разделять в зависимости от темпа feedback пользователя.
