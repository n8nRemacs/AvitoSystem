# Техническое задание V1
## Система мониторинга Avito и ценовой разведки

**Версия:** 1.2 (двойная вилка + market intelligence + двухступенчатый LLM)
**Дата:** 25.04.2026
**Статус:** К реализации

> **Что нового в 1.2 (vs 1.1).** Расширен модуль мониторинга:
> - **Двойная ценовая вилка** (ADR-008): search-вилка для широкого мониторинга рынка, alert-вилка для фильтра уведомлений. Search автоматически = alert ± 25%.
> - **Market intelligence** (ADR-009): инструмент превращается из «охоты за лотом» в рыночную разведку — медианы, тренды, распределение состояний, графики, 6 новых типов уведомлений-инсайтов (price_drop, market_trend, historical_low, supply_surge, condition_mix_change, price_dropped_into_alert).
> - **Двухступенчатый LLM** (ADR-010): дешёвый `classify_condition` на всех лотах для отделения мусора (iCloud-locked, broken, parts only) от нормальных, тяжёлый `match_criteria` только в alert-зоне с проходящим состоянием. Очищенные метрики не искажаются долей мусорных лотов.
> 
> Затронуты разделы 4.1 (поля профиля), 4.4 (LLM Analyzer — 3 метода), 4.5 (Notifier — 9 типов), 4.6 (Worker), 4.7 (Дашборд), 5.1 (БД: расширен listings, profile_runs, profile_listings, новая profile_market_stats), 5.2 (индексы), 8.1 (OpenRouter), 14 (критерии приёмки).

> **Что изменилось в 1.1.** После исследования официального и реверс-API Avito (см. `DOCS/avito_api_snapshots/`) радикально упрощены модули профилей поиска и MCP-сервера: вместо генерации фильтров через таксономию Avito юзер копирует готовый URL поиска, поверх которого применяются опциональные overlay-параметры. MCP-tools сокращены с 23 до 4 для V1, таксономия и manage-my-listings отложены в V2. Все изменения зафиксированы в `DOCS/DECISIONS.md` (ADR-001 – ADR-007). Затронуты разделы 4.1, 4.3.3, 5.1, 13.

---

## 1. Общая информация

### 1.1. Назначение системы

Разрабатываемая система — это персональный инструмент для одного пользователя (владельца homelab-сервера), решающий две бизнес-задачи:

1. **Охота за покупкой:** автоматический мониторинг Avito по заданным критериям (в первую очередь iPhone) с LLM-анализом описаний и фотографий, умной фильтрацией и моментальными уведомлениями в Telegram о подходящих объявлениях.
2. **Ценовая разведка:** анализ конкурентов в регионе для собственных объявлений пользователя с рекомендацией оптимальной цены, выявлением плюсов/минусов конкурирующих лотов и построением ценовой вилки.

Управление системой осуществляется через веб-дашборд, доставка результатов — через Telegram.

### 1.2. Пользователи

В V1 — **один пользователь** (владелец). Мультипользовательский режим не требуется, но архитектура должна это допускать в будущем (все сущности привязываются к `user_id`).

### 1.3. Границы V1

**Входит в V1:**
- Модуль мониторинга объявлений с гибкими профилями поиска
- LLM-анализ описаний и фотографий объявлений
- Модуль ценовой разведки по собственным объявлениям
- Веб-дашборд для настройки и просмотра истории
- Telegram-бот для уведомлений и управления
- Периодический polling с настраиваемым интервалом и расписанием работы
- Docker-развёртывание на homelab

**НЕ входит в V1 (уйдёт в V2):**
- Автоответчик первым сообщением в чате Avito
- Квалифицирующие вопросы клиентам
- Фильтрация «мёртвых» лидов через диалог

**V3 (будущее):**
- Мультипользовательский режим с биллингом
- Интеграция с другими маркетплейсами (Юла, Ozon)
- Продвинутая аналитика и прогноз цен

### 1.4. Предоставляемые материалы

Программисту дополнительно передаются:
- Спецификации API Avito (официальное API + реверс-инжиниринг)
- Исходный код существующего прототипа взаимодействия с Avito
- Примеры ответов API для ключевых эндпоинтов

Эти материалы интегрируются как модуль `avito_client` (см. раздел 4.3).

---

## 2. Технологический стек

### 2.1. Бэкенд
- **Язык:** Python 3.12+
- **Веб-фреймворк:** FastAPI 0.115+
- **Валидация:** Pydantic v2
- **ORM:** SQLAlchemy 2.0 (async)
- **Миграции:** Alembic
- **Telegram-бот:** aiogram 3.x
- **HTTP-клиент:** httpx (async)
- **Headless-браузер (если потребуется):** Playwright (async)
- **Очередь задач/планировщик:** TaskIQ с Redis брокером (современная альтернатива Celery с нативной поддержкой async). Если команда предпочитает — допустимо Celery 5 + Redis.
- **MCP SDK:** официальный `mcp` Python-пакет от Anthropic для построения MCP-сервера Avito (см. раздел 4.3).
- **LLM-клиент:** работа с OpenRouter через OpenAI-совместимый клиент (`openai` пакет) или LiteLLM для гибкости моделей.
- **Логирование:** structlog + стандартный logging
- **Тестирование:** pytest, pytest-asyncio, pytest-mock, httpx для интеграционных тестов

### 2.2. Хранилище
- **Основная БД:** PostgreSQL 16+
- **Кеш и очередь:** Redis 7+
- **Файловое хранилище:** локальная ФС (для миниатюр изображений при необходимости кеширования)

### 2.3. Фронтенд (дашборд)
- **Подход:** server-rendered + интерактивность на HTMX, чтобы не плодить отдельный SPA
- **Шаблонизатор:** Jinja2
- **Интерактивность:** HTMX 2.x + Alpine.js
- **Стили:** TailwindCSS + компоненты DaisyUI (минимум работы по дизайну)
- **Графики (для ценовой разведки):** Chart.js

**Обоснование:** проект для одного пользователя на homelab. SPA на React создаст лишний overhead. HTMX-подход даёт быстрый старт, один процесс, один репозиторий, лёгкий деплой.

### 2.4. Инфраструктура
- **Контейнеризация:** Docker + Docker Compose
- **Обратный прокси:** Caddy (автоматические сертификаты) или Traefik
- **Секреты:** `.env` + pydantic-settings
- **Мониторинг:** Healthcheck эндпоинты + (опционально) Prometheus метрики через `prometheus-fastapi-instrumentator`
- **Логи:** Loki + Promtail или просто JSON-логи в stdout

### 2.5. Требования к среде разработки
- VS Code с Claude Code
- uv или Poetry для управления зависимостями (предпочтительно uv)
- Ruff для линтинга и форматирования
- Mypy для статической типизации
- Pre-commit хуки

---

## 3. Архитектура системы

### 3.1. Общая схема

Система состоит из следующих логических компонентов, разворачиваемых как отдельные сервисы в Docker Compose:

1. **`app`** — FastAPI-приложение: API дашборда + server-rendered страницы + REST-эндпоинты
2. **`worker`** — TaskIQ/Celery воркер: выполнение задач мониторинга, LLM-анализа, отправки уведомлений
3. **`scheduler`** — TaskIQ/Celery beat: постановка периодических задач в очередь согласно расписанию
4. **`bot`** — Telegram-бот (aiogram), обрабатывающий команды пользователя
5. **`avito-mcp`** — **MCP-сервер Avito** (см. раздел 4.3): инкапсулирует всю работу с Avito (API + реверс), предоставляет инструменты и ресурсы через Model Context Protocol. Используется бэкендом как единая точка доступа, а также может подключаться к Claude Desktop / Claude Code для ручных операций и отладки.
6. **`db`** — PostgreSQL
7. **`redis`** — Redis
8. **`proxy`** — Caddy/Traefik (опционально для HTTPS)

### 3.2. Поток данных: мониторинг покупок

```
[Scheduler] → ставит задачу "обойти профиль поиска #N"
     ↓
[Worker] получает задачу
     ↓
[MCP-клиент] → вызывает инструмент avito_search на avito-mcp сервере
     ↓
[avito-mcp] → обращается к Avito (API / реверс), возвращает список объявлений
     ↓
Для каждого нового объявления (проверка по avito_id в БД):
  ↓
[MCP-клиент] → вызывает avito_get_listing на avito-mcp
     ↓
[LLMAnalyzer.analyze()] → проверка соответствия критериям (описание + фото)
     ↓
Если подходит → [Notifier.send_to_telegram()]
     ↓
Сохранение в таблицу listings + notifications
```

### 3.3. Поток данных: ценовая разведка

```
[User] в дашборде создаёт запрос анализа для своего объявления
     ↓
[MCP-клиент] → avito_get_my_listing (получение эталона по id)
     ↓
[MCP-клиент] → avito_search (поиск аналогов в регионе)
     ↓
[LLMAnalyzer.compare()] → сравнивает каждый аналог с эталоном
     ↓
Построение отчёта: вилка цен, плюсы/минусы конкурентов, рекомендация
     ↓
Отображение в дашборде + опциональная отправка в Telegram
```

### 3.4. Принципы

- **Идемпотентность задач:** повторный запуск задачи не создаёт дубли (проверка по `avito_id`).
- **Дедупликация LLM-анализа:** кеширование результатов анализа по хешу (avito_id + updated_at).
- **Graceful degradation:** при недоступности LLM система продолжает собирать объявления, помечая их как «ожидают анализа».
- **Rate limiting:** все обращения к Avito и OpenRouter проходят через rate limiter во избежание блокировок.
- **Observability:** structured-логи с корреляционным ID для трассировки задач.

---

## 4. Функциональные требования

### 4.1. Модуль «Профили поиска» (Search Profiles)

**Подход (см. ADR-001 и ADR-002 в `DECISIONS.md`):** профиль строится поверх **готового URL поиска**, скопированного пользователем напрямую из веб-Avito. Система не реконструирует фильтры из таксономии Avito — это снимает огромный пласт работы с XML-каталогами, маппингом slug→category_id, динамическими формами зависимых выпадашек. Гибкость обеспечивается опциональными overlay-параметрами, которые накладываются на URL перед запросом.

**Сущность:** профиль = «URL поиска Avito» + LLM-критерии + расписание + опциональные overlay-параметры.

**Поля профиля:**
- `id` (uuid)
- `name` (строка, человекочитаемое имя — например, «iPhone 12 Pro Max до 13.5K»)
- `avito_search_url` (text, **обязательное**) — URL поиска, скопированный пользователем из Avito. Категорийные фильтры (бренд, модель, состояние, память, цвет) уже зашиты в URL самим Avito.
- `region_slug` (str, nullable) — overlay: первый сегмент path (`all`, `moskva`, `sankt-peterburg`, ...). Если задан — заменяет регион в URL.

**Двойная ценовая вилка** (см. ADR-008):
- `search_min_price`, `search_max_price` (int, nullable) — **широкая** вилка для URL Avito (`?pmin/pmax`). Что грузим в БД для статистики.
- `alert_min_price`, `alert_max_price` (int, nullable) — **узкая** вилка постфильтра. Что показываем в Telegram и анализируем глубоким LLM.

При создании профиля по URL Avito с `pmin/pmax`:
- `alert_min/max` берутся из URL
- `search_min/max` авто-расчёт: `round(alert_min * 0.75)` / `round(alert_max * 1.25)` — расширение ±25%

В дашборде оба значения редактируемые. Если `search_min/max` пусты — overlay не применяется к URL, фильтрация остаётся как в исходном URL.

**Прочие overlay:**
- `only_with_delivery` (bool, nullable) — overlay: `?d=1`/`?d=0`
- `sort` (int, nullable) — overlay: `?s=N` (104=по дате, 1=по цене↑, 2=по цене↓ — точные коды уточняются в Спринте 0B)

**LLM и фильтр состояния** (см. ADR-010):
- `custom_criteria` (text) — произвольные критерии на естественном языке для глубокого LLM («аккумулятор >85%, без серьёзных царапин, не реплика»)
- `allowed_conditions` (jsonb, default `["working"]`) — список classes лота, которые проходят в alert-зону. По умолчанию только нормальные рабочие лоты. Юзер может расширить: `["working", "broken_screen"]` если ищет «на запчасти».
- `llm_model` (text, nullable — если null, берётся из system_settings)
- `llm_classify_model` (text, nullable — модель для дешёвой классификации состояния, default haiku)
- `analyze_photos` (bool — анализировать ли фото объявления мультимодальной моделью на этапе match_criteria)

**Управление и расписание:**
- `poll_interval_minutes` (int — 2/5/10/15/30/60)
- `active_hours` (JSON — расписание, например `{"mon-fri": "09:00-23:00", "sat-sun": "10:00-22:00"}`)
- `is_active` (bool)
- `blocked_sellers` (jsonb — список avito_user_id продавцов в чёрном списке)
- `notification_settings` (jsonb) — пороги для уведомлений-инсайтов из ADR-009. Пример:
  ```json
  {
    "min_confidence": 0.7,
    "price_drop_threshold_pct": 10,
    "trend_threshold_pct": 5,
    "supply_surge_threshold_pct": 30,
    "historical_low_window_days": 30,
    "condition_mix_threshold_pct": 10,
    "enabled_types": ["new_listing", "price_drop_listing", "market_trend_down", "historical_low"]
  }
  ```
- `created_at`, `updated_at`
- `user_id` (для будущей мультитенантности)

**Денормализация для UI** (парсер URL заполняет автоматически): `parsed_category` (например, «Телефоны / Мобильные»), `parsed_brand`, `parsed_model`. Чисто декоративные.

**Применение overlay** — функция `apply_overlay(url, profile)` в `app/services/search_profiles.py`:
- Заменяет первый сегмент path, если задан `region_slug`
- Перезаписывает `pmin`/`pmax` в query-string значениями `search_min_price`/`search_max_price`
- Перезаписывает `?d` / `?s` из соответствующих полей
- Возвращает финальный URL для запроса

**Операции (CRUD через дашборд и REST API):**
- Создать/редактировать/удалить/клонировать профиль
- Включить/выключить профиль
- Запустить вручную (ad-hoc прогон)
- Посмотреть статистику: количество найденных, отфильтрованных, уведомлений за период

**Acceptance criteria:**
- При сохранении профиля парсер вытаскивает из URL читаемое описание (бренд/модель/категория) и показывает его юзеру для подтверждения, что URL валиден
- Профиль сохраняется и корректно подхватывается планировщиком без перезапуска воркера
- При отключении профиля запланированные задачи по нему отменяются
- Изменение `poll_interval_minutes` применяется к следующему циклу
- Изменение overlay-параметров применяется к следующему циклу без переписывания исходного URL

### 4.2. Модуль «Ценовая разведка» (Price Intelligence)

**Сущность:** запрос ценовой разведки = эталонное объявление + параметры сравнения.

**Варианты эталона:**
- Ссылка на собственное объявление на Avito (система получает данные через API)
- Ручной ввод характеристик (модель, состояние, комплект, регион)

**Характеристики запроса:**
- `id` (uuid)
- `name`
- `reference_listing_url` (опционально)
- `reference_data` (JSON — характеристики эталона)
- `search_region` (код региона Avito)
- `search_radius_km` (опционально)
- `competitor_filters` (JSON — параметры поиска аналогов)
- `max_competitors` (int, по умолчанию 30)
- `llm_model`
- `schedule` (опционально — периодический перезапуск, например «каждый понедельник»)

**Алгоритм анализа:**
1. По фильтрам получить список аналогов в регионе.
2. Для каждого аналога получить детали.
3. LLM сравнивает каждый аналог с эталоном и выдаёт:
   - Оценку соответствия (0–100)
   - Ключевые плюсы относительно эталона
   - Ключевые минусы
   - Оценённое «справедливое» отклонение цены от эталона
4. Построение отчёта:
   - Вилка: минимум/медиана/максимум среди «сопоставимых»
   - Топ-5 конкурентов дешевле (с минусами)
   - Топ-5 конкурентов дороже (с плюсами)
   - Рекомендованная цена с обоснованием

**Представление:**
- Страница отчёта в дашборде: сводка + интерактивная таблица + график распределения цен (Chart.js).
- Экспорт отчёта в Markdown и отправка в Telegram по запросу.

**Acceptance criteria:**
- Один прогон на 30 конкурентов завершается за разумное время (цель ≤ 3 минут при использовании быстрой LLM-модели).
- Отчёт содержит все перечисленные блоки.
- Повторный прогон того же запроса переиспользует кеш LLM-анализа там, где объявление не менялось.

### 4.3. MCP-сервер Avito (`avito-mcp`)

**Назначение:** отдельный сервис, инкапсулирующий всю логику работы с Avito (официальное API + реверс-инжиниринг + при необходимости headless-браузер) и предоставляющий её через **Model Context Protocol** (MCP). Это единая точка доступа к Avito для:

- Основного бэкенда системы (через MCP-клиент).
- Разработчика во время работы (подключение к Claude Code / Claude Desktop для ручных операций, отладки, изучения ответов).
- Будущих агентов и расширений (V2 с автоответчиком, V3 с интеграциями).

**Почему отдельный сервис, а не библиотека:**
- Изоляция зависимостей и секретов Avito.
- Возможность перезапускать / обновлять интеграцию, не трогая основной бэкенд.
- Стандартный протокол — любой MCP-клиент может подключиться.
- Упрощение отладки: разработчик в VS Code через Claude Code может дёргать инструменты сервера напрямую.

#### 4.3.1. Транспорты

Сервер должен поддерживать два транспорта одновременно:
1. **stdio** — для локального использования разработчиком через Claude Code / Claude Desktop. Запускается командой или процессом-потомком.
2. **HTTP + SSE (streamable HTTP)** — для работы из Docker-сети: основной бэкенд, воркеры и боты подключаются по сети.

Конфигурация транспорта — через переменные окружения (`AVITO_MCP_TRANSPORT=stdio|http`, `AVITO_MCP_HTTP_PORT`, `AVITO_MCP_HTTP_HOST`).

#### 4.3.2. Аутентификация MCP-сервера

- Для HTTP-транспорта: обязательный токен в заголовке `Authorization: Bearer <token>` (переменная `AVITO_MCP_AUTH_TOKEN`).
- Для stdio: полагаемся на доверие локальной среде.
- Все операции логируются с указанием вызывающего клиента (по токену или идентификатору процесса).

#### 4.3.3. Набор MCP-инструментов (Tools)

**Решение по составу — см. ADR-006 в `DECISIONS.md`.** В V1 после перехода на URL-based профили (ADR-001) большая часть исходного списка инструментов теряет смысл (search по фильтрам, метаданные категорий, manage my listings — всё откладывается в V2/V3). Реальный V1-набор сокращён до 4 tools.

**V1 (реализуется):**

| Tool | Вход | Выход | Назначение |
|---|---|---|---|
| `avito_fetch_search_page` | `url` (str), `page` (int=1) | `{items: [ListingShort], total: int, has_more: bool}` | Фетч страницы поиска по готовому URL пользователя (с применённым overlay), парсинг JSON-стейта (`window.__initialData__` или эквивалент), возврат списка карточек |
| `avito_get_listing` | `item_id_or_url` (int \| str) | `ListingDetail` | Детали публичного лота: описание, фото, параметры, продавец |
| `avito_get_listing_images` | `item_id` (int) | `[{url, width, height, index}]` | URL всех фото в оригинальном качестве (для LLM-анализа) |
| `avito_health_check` | — | `{avito_reachable, rate_limit_remaining, last_error}` | Проверка доступности Avito и rate limit |

Эти 4 tools покрывают весь polling-цикл: вытащил выдачу → для каждого нового лота вытащил детали → передал в LLM-анализатор.

**V2 (задел, в V1 не реализуется):**

Через **официальное API Avito** (OAuth2 client_credentials, см. ADR-003):

- **Свои объявления:** `avito_list_my_listings`, `avito_get_my_listing`, `avito_create_listing`, `avito_update_listing`, `avito_archive_listing`, `avito_restore_listing`, `avito_delete_listing`
- **Аналитика:** `avito_get_listing_stats`, `avito_get_account_balance`, `avito_get_promotion_options`
- **Таксономия (Autoload):** `avito_get_categories`, `avito_get_category_fields`, `avito_get_param_catalog`
- **Продавцы:** `avito_get_seller`, `avito_get_seller_listings`

V2-мессенджер (`avito_list_chats`, `avito_get_chat_messages`, `avito_send_message`, `avito_mark_read`) — отложен до решения о платном messenger-доступе.

> Архитектура `avito-mcp` должна быть готова к добавлению V2-tools без рефакторинга (см. 4.3.6): отдельные модули в `tools/` и `integrations/`, общие модели в `shared/`.

#### 4.3.4. MCP-ресурсы (Resources)

Помимо инструментов, сервер предоставляет ресурсы для чтения в декларативном стиле:

- `avito://listings/{avito_id}` — детали объявления.
- `avito://my-listings` — индекс моих объявлений.
- `avito://my-listings/{id}` — детали моего объявления.
- `avito://categories` — дерево категорий.
- `avito://regions` — дерево регионов.
- `avito://health` — живая сводка статуса интеграции.

#### 4.3.5. MCP-промпты (Prompts)

Сервер публикует вспомогательные промпты-шаблоны, которые могут использовать MCP-клиенты:

- `search_iphone` — параметризованный промпт «помоги найти iPhone с такими характеристиками».
- `analyze_competitor` — промпт сравнения конкурентного объявления с эталоном.

Эти промпты также используются основным бэкендом, чтобы обеспечить единый источник правды.

#### 4.3.6. Нефункциональные требования к MCP-серверу

- **Rate limiter** (настраиваемый, по умолчанию 1 запрос/секунду к Avito, единый на весь сервер вне зависимости от того, сколько клиентов к нему подключено).
- **Ретраи** с экспоненциальным backoff на сетевые ошибки.
- **Ротация User-Agent**, опциональная поддержка прокси через `HTTPS_PROXY`.
- **Структурные исключения:** `AvitoAuthError`, `AvitoRateLimitError`, `AvitoNotFoundError`, `AvitoServerError` — мапятся в стандартные MCP-ошибки с осмысленными кодами и сообщениями.
- **Кеш ответов:** опциональный (например, категории и регионы кешируются на 24 часа в Redis).
- **Логирование:** structured JSON, каждый tool call — с длительностью и статусом.
- **Метрики:** счётчики вызовов, ошибок, 429, средняя latency по каждому инструменту.
- **Graceful shutdown:** при остановке корректно завершает активные запросы.

#### 4.3.7. Модели данных

Все Pydantic-модели (`SearchFilters`, `ListingShort`, `ListingDetail`, `Category`, `Parameter`, `Region`, `SellerInfo`, `ListingStats`, ...) выносятся в общий пакет, который используется и MCP-сервером, и клиентом бэкенда. Это обеспечивает type-safety на обоих концах.

#### 4.3.8. Использование MCP-сервера из основного бэкенда

Основной бэкенд (`app`, `worker`) использует **MCP-клиент** (`mcp` SDK, HTTP transport) для вызова инструментов. В коде это выглядит как:

```python
from app.integrations.avito_mcp_client import AvitoMCPClient

async with AvitoMCPClient(url, token) as client:
    listings = await client.call_tool("avito_search", filters.model_dump())
```

Обёртка `AvitoMCPClient` изолирует MCP-детали и предоставляет типизированные методы — тот же интерфейс `AvitoClient` Protocol, как и раньше, но под капотом он теперь HTTP-вызов к MCP-серверу. Это позволяет:

- В тестах мокать на уровне `AvitoClient` без реальной сети.
- Легко переключить реализацию (локальный stub, моки для разработки).

#### 4.3.9. Использование из Claude Code и Claude Desktop

Разработчик должен получить инструкции (в `docs/mcp_usage.md`), как подключить сервер:

1. **Claude Code** — через конфигурацию `.mcp.json` или `claude mcp add`. Сервер можно поднять в режиме stdio и указать путь к бинарю/скрипту запуска. Даёт возможность прямо из VS Code попросить Claude «покажи три свежих iPhone 14 в Москве дешевле 60 тысяч» и он вызовет `avito_search`.
2. **Claude Desktop** — добавление записи в `claude_desktop_config.json`. Полезно для ручных операций с объявлениями (быстро отредактировать цену, посмотреть статистику без лазания в админку Avito).

#### 4.3.10. Acceptance criteria MCP-сервера

- Сервер проходит MCP compliance (валидные схемы инструментов, ресурсов, корректная обработка ошибок).
- Все инструменты из 4.3.3 реализованы и покрыты unit-тестами.
- Основной бэкенд (`app`, `worker`) работает только через MCP-клиента, нигде не обращается к Avito напрямую.
- Подключение из Claude Code локально работает — разработчик демонстрирует 2–3 ручных вызова.
- При недоступности Avito сервер возвращает корректные MCP-ошибки, клиент их обрабатывает без падения.
- Rate limiter единый для всего сервера и реально ограничивает параллельные запросы от нескольких клиентов.
- Логи и метрики собираются по каждому вызову.

### 4.4. Модуль «LLM Analyzer»

**Назначение:** абстракция над OpenRouter для трёх задач — классификация состояния (дешёвый префильтр), глубокий анализ соответствия критериям и сравнение с эталоном для price intelligence.

**Двухступенчатая модель** (см. ADR-010): дешёвый текстовый classify_condition прогоняется на **всех** новых лотах в search-зоне, тяжёлый match_criteria (опц. с фото) — только на лотах в alert-зоне с подходящим состоянием. Это даёт корректную «чистую» статистику и при этом контролирует расходы.

**Интерфейс:**

```python
class LLMAnalyzer(Protocol):
    async def classify_condition(
        self,
        listing: ListingDetail,
        model: str,
    ) -> ConditionClassification: ...
    
    async def match_criteria(
        self,
        listing: ListingDetail,
        criteria: str,
        analyze_photos: bool,
        model: str,
    ) -> MatchResult: ...
    
    async def compare_to_reference(
        self,
        competitor: ListingDetail,
        reference: ListingDetail | ReferenceData,
        model: str,
    ) -> ComparisonResult: ...
```

**`ConditionClassification`:**
- `condition_class: Literal["working", "blocked_icloud", "blocked_account", "not_starting", "broken_screen", "broken_other", "parts_only", "unknown"]`
- `confidence: float` (0–1)
- `reasoning: str` (1-2 предложения почему присвоен класс)
- `tokens_used: int`
- `cost_usd: float`

**`MatchResult`:**
- `is_match: bool`
- `confidence: float` (0–1)
- `summary: str` (2–3 предложения для Telegram)
- `matched_criteria: list[str]`
- `concerns: list[str]` (что вызвало сомнения)
- `red_flags: list[str]` (признаки мошенничества/восстановленного устройства)
- `tokens_used: int`
- `cost_usd: float`

**`ComparisonResult`:**
- `similarity_score: float` (0–1)
- `pros_vs_reference: list[str]`
- `cons_vs_reference: list[str]`
- `fair_price_delta: float` (насколько цена конкурента должна отличаться от эталона)
- `tokens_used: int`
- `cost_usd: float`

**Работа с фото:**
- Только в `match_criteria` при `analyze_photos=True`. Classify фото не использует — текстового описания достаточно для определения состояния.
- Загружаются первые N фото (настраиваемо, по умолчанию 5).
- Мультимодальная модель OpenRouter (Claude Sonnet 4.7 или GPT-4o).

**Промпты:**
- Хранятся в `app/prompts/*.md` в виде шаблонов Jinja2.
- Версионируются (каждый промпт имеет `version` tag для аналитики эффективности).
- Файлы: `classify_condition.md`, `match_listing.md`, `compare_listings.md`, `summarize_for_telegram.md`.

**Кеширование** — таблица `llm_analyses` (см. 5.1):
- Тип записи: `condition` | `match` | `compare`
- Ключ кеша: `hash(avito_id + updated_at + criteria_hash + model + prompt_version + analysis_type)`
- При повторном запросе того же лота с теми же параметрами LLM не вызывается

**Бюджет:**
- `OPENROUTER_DAILY_USD_LIMIT` (default $10) — мягкий лимит. При превышении: новые classify останавливаются, существующие listings продолжают match_criteria до завершения, в Telegram отправляется уведомление.
- Метрики `cost_usd` агрегируются в дашборде (страница `/settings` блок «Расходы LLM»).

**Acceptance criteria:**
- При повторном запросе того же лота с теми же параметрами LLM не вызывается (cache hit регистрируется в `llm_analyses`)
- При недоступности OpenRouter classify падает мягко, лот помечается `condition_class=unknown` и повторная попытка через 10 минут
- Все вызовы логируются: тип, модель, токены, стоимость, длительность
- Distribution `condition_class` корректно отражается в дашборде на странице профиля

### 4.5. Модуль «Notifier»

**Канал:** Telegram (aiogram).

**Типы уведомлений** (расширены по ADR-009):

1. **`new_listing` — новый подходящий лот:**
   - Триггер: лот в alert-зоне, прошёл фильтр `allowed_conditions`, `match_criteria.is_match=True`, `confidence ≥ min_confidence`
   - Формат: заголовок, цена, регион, condition tag, 2–3 строки summary от LLM, red_flags если есть, ссылка
   - Фото не прикладываются
   - Inline-кнопки: «Просмотрено», «Скрыть продавца», «Не показывать этот лот»

2. **`price_drop_listing` — конкретный лот подешевел:**
   - Триггер: цена существующего лота упала на ≥ `price_drop_threshold_pct` (default 10%) с момента предыдущей фиксации
   - Формат: «iPhone 12 Pro Max за 11500 (было 13500, **-15%**)» + ссылка
   - Inline-кнопки: «Просмотрено», «Не показывать»

3. **`price_dropped_into_alert` — лот вошёл в alert-зону:**
   - Триггер: лот раньше был в `market_data` (search-зона), теперь его цена попала в alert-вилку
   - Формат: «Лот вошёл в зону уведомлений: 12000 (был 14500)» + summary LLM (если уже есть)

4. **`market_trend_down` / `market_trend_up` — рынок изменился:**
   - Триггер: clean-медиана за неделю изменилась на ≥ `trend_threshold_pct` (default 5%) относительно предыдущей недели
   - Формат: «Средняя цена iPhone 12 Pro Max **упала на 8%** за неделю (12500 → 11500). Текущий минимум: 9800 ₽»
   - Дедупликация: не чаще одного раза в 24 часа

5. **`historical_low` — минимум за период:**
   - Триггер: цена лота ниже минимальной за `historical_low_window_days` (default 30) дней
   - Формат: «**Минимум за 30 дней**: 9800 ₽. Предыдущий минимум 10500 был 15 дней назад»

6. **`supply_surge` — всплеск предложения:**
   - Триггер: число активных лотов выросло на ≥ `supply_surge_threshold_pct` (default 30%) за день
   - Формат: «Много новых лотов: **+40%** за день (47 → 66 активных)»

7. **`condition_mix_change` — изменилось распределение состояний:**
   - Триггер: доля working лотов изменилась на ≥ `condition_mix_threshold_pct` (default 10%) за неделю
   - Формат: «Доля рабочих лотов **снизилась** с 65% до 50% за неделю — выросло предложение неисправных»

8. **`error` — ошибка системы:**
   - Падение доступа к Avito, исчерпание квоты OpenRouter, превышение `OPENROUTER_DAILY_USD_LIMIT`
   - Дедупликация: не чаще раза в 30 минут

9. **`price_report` — отчёт ценовой разведки (по запросу):**
   - Markdown-сводка из `price_analysis_runs.report` + ссылка на дашборд

**Глобальные настройки** (для каждого юзера в system_settings + override на уровне профиля через `notification_settings.enabled_types`): отключить любой тип, переопределить пороги.

**Настройки пользователя:**
- Chat_id, получаемый через команду `/start` в боте.
- Возможность включить/отключить каждый тип уведомлений.
- Тихие часы (не беспокоить с 23:00 до 09:00, настраиваемо).

**Acceptance criteria:**
- Нажатие «Скрыть продавца» добавляет продавца в чёрный список профиля поиска, будущие лоты от него игнорируются.
- Нажатие «Больше не показывать этот лот» помечает объявление как скрытое и не уведомляет повторно.
- При сбое отправки в Telegram уведомление ставится в очередь ретраев.

### 4.6. Модуль «Scheduler / Worker»

**Задачи планировщика:**
- Каждую минуту проверяет активные профили поиска и их расписание.
- Ставит задачу `poll_profile(profile_id)` в очередь, если подошло время и профиль активен в данный час.
- Поддерживает «тихие окна»: не ставит задачи вне `active_hours`.
- Учитывает глобальный флаг `system_active` (можно приостановить систему целиком).

**Задачи воркера** (обновлены под ADR-008/009/010):

- `poll_profile(profile_id)` — основной цикл:
  1. Применяет `apply_overlay()` к URL профиля
  2. Через MCP `avito_fetch_search_page(url, page=N)` получает страницы выдачи (пагинация до пустой страницы или лимита)
  3. Дедупликация по `avito_id` против БД, новые лоты сохраняются как `status=fetched`
  4. Изменение цены существующего лота — фиксируется в `last_price_change_at`, генерирует `price_drop_listing` если выше порога
  5. Для каждого нового лота — постановка `analyze_listing(listing_id)` в очередь
  6. Запись агрегатов прогона в `profile_runs` (price_median_raw, listings_count и т.д.)

- `analyze_listing(listing_id)` — двухступенчатый LLM:
  1. `MCP.avito_get_listing(item_id)` → детали
  2. `LLMAnalyzer.classify_condition()` → `condition_class`
  3. Лот в alert-зоне И `condition_class IN profile.allowed_conditions`?
     - Да: `LLMAnalyzer.match_criteria()` → если match → создаётся notification
     - Нет: `status=market_data`, без полного анализа
  4. Проверка триггеров `historical_low`, `price_dropped_into_alert` — генерация notification если применимо

- `send_notification(notification_id)` — отправка в Telegram с ретраями (3 попытки, exp backoff)

- `compute_market_stats(profile_id, granularity)` (новая, см. ADR-009) — раз в сутки/неделю/месяц:
  1. Сворачивает `profile_runs` за период в одну запись `profile_market_stats`
  2. Считает `condition_distribution`, `working_share`, clean-медиану
  3. Сравнивает с предыдущим периодом — генерирует `market_trend_*`, `condition_mix_change`, `supply_surge` если триггеры сработали

- `run_price_analysis(analysis_id)` — прогон ценовой разведки (раздел 4.2)

- `cleanup_old_listings()` — ежесуточно (см. ADR-009):
  - Удаление `market_data` старше 30 дней
  - Удаление `analyzed` старше 90 дней
  - `notified` сохраняются бессрочно

**Очереди:**
- `high` — уведомления (быстрая отправка)
- `default` — polling
- `llm_classify` — лёгкие classify_condition (concurrency = 5-10)
- `llm_match` — тяжёлые match_criteria + compare_to_reference (concurrency = 2-3 для контроля бюджета)
- `analytics` — compute_market_stats, price_intelligence

### 4.7. Дашборд

**Страницы:**

1. **/** — главная. Сводка: количество активных профилей, лотов за 24 часа, уведомлений отправлено, последние события.
2. **/search-profiles** — список профилей поиска, фильтры, поиск по имени.
3. **/search-profiles/new** и **/search-profiles/{id}** — форма создания/редактирования профиля.
4. **/search-profiles/{id}/runs** — история прогонов профиля, детали каждого запуска (сколько найдено, ошибки).
4a. **/search-profiles/{id}/stats** — рыночная статистика профиля (см. ADR-009):
   - График Chart.js: clean-медиана / min / max за 30 дней + alert-вилка пунктиром
   - Гистограмма распределения цен сейчас (с разделением working / non-working)
   - `condition_distribution` сейчас и тренд
   - Лента рыночных событий (last 20)
   - Кнопка «Применить рекомендуемую alert-вилку» (на основе текущей clean-медианы ± 1 IQR)
5. **/listings** — общий просмотр всех собранных объявлений с фильтрами (по профилю, по статусу, по дате, по `condition_class`).
6. **/listings/{id}** — детали объявления, результат LLM-анализа, кнопки действий.
7. **/price-intelligence** — список запросов ценовой разведки.
8. **/price-intelligence/new** и **/price-intelligence/{id}** — создание и просмотр отчёта.
9. **/settings** — глобальные настройки: LLM (модели по умолчанию, API ключи), Telegram, тихие часы, режим работы системы (активна/пауза), настройки Avito-клиента.
10. **/logs** — просмотр последних логов системы (только критичные события).
11. **/login** — страница входа (см. раздел про авторизацию).

**Требования к UI:**
- Адаптивная вёрстка (работа с мобильного браузера).
- Тёмная тема по умолчанию (DaisyUI).
- Живое обновление статусов без перезагрузки (HTMX polling или SSE).
- Формы валидируются на клиенте и сервере (Pydantic).

### 4.8. Авторизация дашборда

- Одна учётка (логин/пароль), хранение хеша пароля (argon2).
- Сессии через защищённую куку (httponly, samesite=strict).
- Поддержка 2FA (TOTP) — опционально, но желательно.
- Basic auth на уровне reverse proxy как дополнительный слой — опционально.
- Telegram-бот требует `chat_id` из whitelist (только владелец может управлять).

---

## 5. Схема базы данных

### 5.1. Таблицы

**`users`**
- `id` (uuid, pk)
- `username` (unique)
- `password_hash`
- `telegram_chat_id` (unique, nullable)
- `totp_secret` (nullable)
- `created_at`

**`search_profiles`** (см. ADR-001/002)
- `id` (uuid, pk)
- `user_id` (fk users)
- `name` (text)
- `avito_search_url` (text, NOT NULL) — URL поиска, скопированный пользователем из Avito
- `region_slug` (text, nullable) — overlay: первый сегмент path (`all`, `moskva`, ...)
- `min_price`, `max_price` (int, nullable) — overlay: `?pmin/pmax`
- `only_with_delivery` (bool, nullable) — overlay: `?d`
- `sort` (int, nullable) — overlay: `?s`
- `parsed_category`, `parsed_brand`, `parsed_model` (text, nullable) — денормализация для UI (заполняются парсером URL)
- `custom_criteria` (text)
- `llm_model` (text, nullable — если null, брать из настроек)
- `analyze_photos` (bool, default false)
- `poll_interval_minutes` (int, default 15)
- `active_hours` (jsonb, default `{}`)
- `is_active` (bool, default true)
- `notification_settings` (jsonb — например, `{"min_confidence": 0.7}`)
- `blocked_sellers` (jsonb — список avito_user_id)
- `created_at`, `updated_at`

**`profile_runs`** — история прогонов профиля (расширено по ADR-009)
- `id` (uuid, pk)
- `profile_id` (fk)
- `started_at`, `finished_at`
- `status` (enum: running, success, failed, partial)
- `listings_found` (int)
- `listings_new` (int)
- `listings_in_alert_zone` (int) — попавшие в узкую вилку
- `listings_classified` (int) — прошедшие classify_condition
- `listings_analyzed_full` (int) — прошедшие match_criteria
- `listings_matched` (int) — `is_match=True`
- `notifications_sent` (int)
- `price_median_raw`, `price_median_clean` (numeric, nullable)
- `price_mean`, `price_min`, `price_max` (numeric, nullable)
- `price_p25_clean`, `price_p75_clean` (numeric, nullable)
- `working_share` (numeric, 0..1)
- `condition_distribution` (jsonb, nullable — `{"working": 0.65, "blocked_icloud": 0.15, ...}`)
- `total_llm_cost_usd` (numeric)
- `error_message` (text, nullable)

**`profile_market_stats`** — агрегаты за периоды (новая, ADR-009)
- `id` (uuid, pk)
- `profile_id` (fk)
- `granularity` (enum: day, week, month)
- `period_start`, `period_end` (timestamp)
- `listings_count` (int)
- `new_listings_count` (int) — появились за период
- `disappeared_listings_count` (int) — закрылись за период
- `avg_listing_lifetime_hours` (numeric, nullable)
- `price_median_raw`, `price_median_clean` (numeric)
- `price_mean`, `price_min`, `price_max` (numeric)
- `price_p25_clean`, `price_p75_clean` (numeric)
- `working_share` (numeric)
- `condition_distribution` (jsonb)
- `created_at` (timestamp)
- unique constraint: (profile_id, granularity, period_start)

**`listings`** (расширено по ADR-008/009/010)
- `id` (uuid, pk)
- `avito_id` (unique)
- `title`
- `price` (numeric)
- `initial_price` (numeric) — цена при `first_seen_at`, для расчёта `price_drop_listing`
- `last_price_change_at` (timestamp, nullable)
- `currency` (default RUB)
- `region`
- `url`
- `description` (text)
- `images` (jsonb — список url)
- `seller_id` (text)
- `seller_type` (enum: private, company)
- `seller_info` (jsonb)
- `parameters` (jsonb)
- `condition_class` (enum: working, blocked_icloud, blocked_account, not_starting, broken_screen, broken_other, parts_only, unknown — заполняется LLM classify) 
- `condition_confidence` (float, 0..1)
- `condition_reasoning` (text)
- `avito_created_at`
- `avito_updated_at`
- `first_seen_at`
- `last_seen_at`
- `status` (enum: active, closed, removed)
- `raw_data` (jsonb — полный снимок ответа API)

**`profile_listings`** — связь профилей и объявлений (M:N) (расширено по ADR-008/010)
- `profile_id` (fk)
- `listing_id` (fk)
- `discovered_at`
- `processing_status` (enum: fetched, classified, market_data, pending_match, analyzed, notified, failed) — этап обработки в pipeline
- `in_alert_zone` (bool) — лот попал в alert-вилку при сборе
- `condition_classification_id` (fk llm_analyses, nullable) — ссылка на classify результат
- `match_result_id` (fk llm_analyses, nullable) — ссылка на match_criteria результат
- `user_action` (enum: pending, viewed, hidden, flagged, nullable)
- pk (profile_id, listing_id)

**`llm_analyses`** (расширено по ADR-010)
- `id` (uuid, pk)
- `listing_id` (fk)
- `type` (enum: condition, match, compare)
- `reference_id` (uuid, nullable — для compare)
- `model`
- `prompt_version`
- `cache_key` (text, indexed)
- `input_tokens` (int)
- `output_tokens` (int)
- `cost_usd` (numeric)
- `result` (jsonb) — структура зависит от `type`: ConditionClassification / MatchResult / ComparisonResult
- `latency_ms` (int)
- `created_at`

**`notifications`**
- `id` (uuid, pk)
- `user_id` (fk)
- `type` (enum: new_listing, error, price_report)
- `payload` (jsonb)
- `status` (enum: pending, sent, failed)
- `sent_at` (nullable)
- `error_message` (text, nullable)
- `retry_count` (int)
- `related_listing_id` (fk, nullable)

**`price_analyses`**
- `id` (uuid, pk)
- `user_id` (fk)
- `name`
- `reference_listing_url` (nullable)
- `reference_data` (jsonb)
- `search_region`
- `competitor_filters` (jsonb)
- `max_competitors`
- `llm_model`
- `schedule` (text, nullable — cron)
- `created_at`, `updated_at`

**`price_analysis_runs`**
- `id` (uuid, pk)
- `analysis_id` (fk)
- `started_at`, `finished_at`
- `status`
- `report` (jsonb — сводка, вилка цен, рекомендации)
- `competitor_data` (jsonb — детали по каждому конкуренту)
- `error_message`

**`system_settings`** — key-value
- `key` (pk)
- `value` (jsonb)
- `updated_at`

**`audit_log`**
- `id` (uuid, pk)
- `user_id` (fk)
- `action`
- `entity_type`, `entity_id`
- `details` (jsonb)
- `created_at`

### 5.2. Индексы

- `listings.avito_id` (unique)
- `listings.status + first_seen_at` (составной, для cleanup)
- `listings.condition_class` (для clean-метрик и фильтрации в дашборде)
- `profile_listings.profile_id + discovered_at` (для ленты)
- `profile_listings.profile_id + processing_status` (для очередей задач)
- `profile_listings.profile_id + in_alert_zone` (для быстрого подсчёта alert-листинга)
- `llm_analyses.cache_key` (для быстрого lookup кеша)
- `llm_analyses.listing_id + type` (для агрегации по типам)
- `profile_market_stats.profile_id + granularity + period_start` (unique, для графиков)
- `profile_runs.profile_id + started_at` (для истории прогонов)
- `notifications.status + retry_count` (для воркера ретраев)

---

## 6. REST API

Все эндпоинты требуют авторизации (кука сессии), кроме `/auth/login` и `/health`.

### 6.1. Auth

- `POST /auth/login` — body: `{username, password, totp_code?}`, возвращает куку сессии.
- `POST /auth/logout`
- `GET /auth/me`

### 6.2. Search Profiles

- `GET /api/search-profiles` — список с пагинацией.
- `POST /api/search-profiles` — создание.
- `GET /api/search-profiles/{id}`
- `PATCH /api/search-profiles/{id}`
- `DELETE /api/search-profiles/{id}`
- `POST /api/search-profiles/{id}/toggle` — включить/выключить.
- `POST /api/search-profiles/{id}/run-now` — ad-hoc прогон.
- `GET /api/search-profiles/{id}/runs` — история.
- `GET /api/search-profiles/{id}/stats?period=24h|7d|30d` — статистика.

### 6.3. Listings

- `GET /api/listings?profile_id=&status=&date_from=&date_to=&page=` — лента.
- `GET /api/listings/{id}` — детали + LLM-результат.
- `POST /api/listings/{id}/actions` — body: `{action: "hide"|"flag"|"view"}`.
- `POST /api/listings/{id}/re-analyze` — форсировать новый LLM-анализ.

### 6.4. Price Intelligence

- `GET /api/price-analyses`
- `POST /api/price-analyses`
- `GET /api/price-analyses/{id}`
- `PATCH /api/price-analyses/{id}`
- `DELETE /api/price-analyses/{id}`
- `POST /api/price-analyses/{id}/run`
- `GET /api/price-analyses/{id}/runs/{run_id}` — отчёт.
- `POST /api/price-analyses/{id}/runs/{run_id}/send-to-telegram`

### 6.5. Avito Metadata (вспомогательные)

- `GET /api/avito/categories`
- `GET /api/avito/categories/{key}/parameters`
- `GET /api/avito/regions?q=`

### 6.6. Settings

- `GET /api/settings`
- `PATCH /api/settings`
- `POST /api/settings/test-telegram`
- `POST /api/settings/test-llm`
- `POST /api/settings/system/pause`
- `POST /api/settings/system/resume`

### 6.7. Telegram Webhook (если выбран webhook-режим)

- `POST /tg/webhook/{secret}` — приём обновлений от Telegram.

### 6.8. Health

- `GET /health` — live (просто 200).
- `GET /health/ready` — проверка БД, Redis, OpenRouter.

---

## 7. Telegram-бот

### 7.1. Команды

- `/start` — приветствие, регистрация `chat_id`. Проверка whitelist по `tg_user_id` в `system_settings.allowed_telegram_users`.
- `/status` — статус системы, количество активных профилей, последняя активность.
- `/pause` — приостановить все профили.
- `/resume` — возобновить.
- `/profiles` — список профилей (inline-кнопки: toggle, run now).
- `/report` — запросить отчёт по выбранному price analysis.
- `/help`
- `/silent <minutes>` — временно выключить уведомления.

### 7.2. Inline-кнопки под уведомлениями

- «✓ Просмотрено»
- «🚫 Скрыть продавца»
- «❌ Не показывать лот»
- «🔍 Повторный LLM-анализ»

### 7.3. Безопасность

- Все апдейты фильтруются по whitelist пользователей.
- Неавторизованным — короткое сообщение «Доступ запрещён» и логирование попытки.

---

## 8. Интеграции

### 8.1. OpenRouter

- **Библиотека:** `openai` с base_url OpenRouter (или LiteLLM для мультипровайдерности).
- **Ключ API:** через `.env`.
- **Заголовки:** `HTTP-Referer` и `X-Title` (как требует OpenRouter для аналитики).
- **Модели по умолчанию (конфигурируемо, см. ADR-010):**
  - **Classify состояния** (этап 1, дешёвый, на всех лотах): `anthropic/claude-haiku-4.5` (~$0.0001 на лот)
  - **Match критериев** (этап 2, текст): `anthropic/claude-haiku-4.5` или `openai/gpt-4o-mini`
  - **Match критериев с фото** (этап 2, мультимодальный): `anthropic/claude-sonnet-4.7` или `openai/gpt-4o`
  - **Сравнение** (price intelligence): `anthropic/claude-sonnet-4.7`
- **Промпты** (Jinja2 шаблоны в `app/prompts/`):
  - `classify_condition.md` — классификация состояния (новый, для всех лотов)
  - `match_listing.md` — оценка соответствия критериям
  - `compare_listings.md` — сравнение с эталоном
  - `summarize_for_telegram.md` — генерация короткого summary для уведомления
- **Учёт стоимости:** каждый вызов пишется в `llm_analyses` с `cost_usd` (рассчитывается по прайсу OpenRouter — можно брать из response headers или жёстко из конфига).
- **Лимиты:** `OPENROUTER_DAILY_USD_LIMIT` (default $10) — мягкий лимит. При превышении: classify останавливается на новых лотах, текущие match-задачи завершаются. Уведомление в Telegram (`error` тип).

### 8.2. Avito

- См. раздел 4.3. Детали — в предоставляемых материалах.
- **Прокси:** поддержка через `HTTPS_PROXY` env-переменную (опционально).
- **Sticky session:** при использовании реверс-API желательно сохранять cookies между запросами.

### 8.3. Telegram Bot API

- Бот запускается либо в режиме long polling (проще для homelab), либо webhook (если есть публичный HTTPS через Caddy).
- Рекомендуется long polling для упрощения.

---

## 9. Конфигурация

### 9.1. Переменные окружения (`.env`)

```
# App
APP_ENV=production
APP_SECRET_KEY=<random 64 chars>
APP_BASE_URL=https://monitor.local

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/avito_monitor

# Redis
REDIS_URL=redis://redis:6379/0

# Auth
ADMIN_USERNAME=owner
ADMIN_PASSWORD_HASH=<argon2 hash>
SESSION_LIFETIME_HOURS=168

# Telegram
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_ALLOWED_USER_IDS=123456789

# OpenRouter
OPENROUTER_API_KEY=<key>
OPENROUTER_DEFAULT_TEXT_MODEL=anthropic/claude-haiku-4.5
OPENROUTER_DEFAULT_VISION_MODEL=anthropic/claude-sonnet-4.7
OPENROUTER_DAILY_USD_LIMIT=10.00

# Avito
AVITO_OFFICIAL_CLIENT_ID=<id>
AVITO_OFFICIAL_CLIENT_SECRET=<secret>
AVITO_REVERSE_TOKEN=<если нужен>
AVITO_PROXY_URL=
AVITO_REQUEST_RATE_LIMIT=1.0   # запросов в секунду

# Avito MCP Server
AVITO_MCP_TRANSPORT=http            # http | stdio
AVITO_MCP_HTTP_HOST=0.0.0.0
AVITO_MCP_HTTP_PORT=9000
AVITO_MCP_AUTH_TOKEN=<random 32+ chars>
AVITO_MCP_URL=http://avito-mcp:9000/mcp   # для клиентов внутри docker-сети
AVITO_MCP_CACHE_TTL_SECONDS=86400   # кеш категорий/регионов

# System
SYSTEM_PAUSED=false
LOG_LEVEL=INFO
LOG_FORMAT=json
TIMEZONE=Europe/Moscow
```

### 9.2. Пример `config.yaml` для неизменяемых настроек

(Опционально, если часть настроек лучше хранить в файле, а не в БД — например, дефолтные лимиты и модели.)

---

## 10. Структура репозитория

Проект организован как монорепозиторий с двумя приложениями: основное (`app`) и MCP-сервер (`avito_mcp`), плюс общий пакет моделей (`shared`).

```
avito-monitor/
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── .dockerignore
├── docker-compose.yml
├── docker-compose.dev.yml
├── Dockerfile                     # мультистейдж: app и avito-mcp из одной базы
├── Makefile
├── README.md
├── CHANGELOG.md
├── alembic.ini
├── alembic/
│   └── versions/
├── shared/                        # общие модели и утилиты для app и avito-mcp
│   ├── __init__.py
│   ├── models/                    # Pydantic: SearchFilters, ListingShort, ListingDetail, ...
│   └── errors.py                  # общие исключения
├── avito_mcp/                     # MCP-сервер Avito (раздел 4.3)
│   ├── __init__.py
│   ├── __main__.py                # точка входа: stdio или HTTP в зависимости от env
│   ├── server.py                  # регистрация tools, resources, prompts
│   ├── config.py
│   ├── tools/                     # реализация MCP-инструментов
│   │   ├── __init__.py
│   │   ├── search.py
│   │   ├── listings.py
│   │   ├── my_listings.py
│   │   ├── stats.py
│   │   ├── metadata.py
│   │   ├── sellers.py
│   │   └── service.py             # health, rate limit, refresh auth
│   ├── resources/                 # MCP-ресурсы
│   │   └── handlers.py
│   ├── prompts/                   # MCP-промпты
│   │   └── templates.py
│   ├── integrations/              # низкий уровень (перенос из прототипа)
│   │   ├── official_api.py
│   │   ├── reverse_api.py
│   │   ├── auth.py                # OAuth, cookies, токены
│   │   ├── rate_limiter.py
│   │   └── http.py                # httpx-клиент, ретраи, прокси
│   └── tests/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app entrypoint
│   ├── config.py                  # pydantic-settings
│   ├── deps.py
│   ├── logging_config.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── search_profiles.py
│   │   ├── listings.py
│   │   ├── price_analyses.py
│   │   ├── settings.py
│   │   └── avito_meta.py          # прокси к avito-mcp для UI (категории, регионы)
│   ├── web/
│   │   ├── __init__.py
│   │   ├── routers.py
│   │   └── templates/
│   ├── static/
│   ├── db/
│   │   ├── base.py
│   │   ├── models/
│   │   └── repositories/
│   ├── services/
│   │   ├── search_profiles.py
│   │   ├── listings.py
│   │   ├── price_intelligence.py
│   │   ├── notifications.py
│   │   └── llm_analyzer.py
│   ├── integrations/
│   │   ├── avito_mcp_client/      # клиент MCP-сервера (подключение по HTTP)
│   │   │   ├── __init__.py
│   │   │   ├── client.py          # обёртка над mcp SDK
│   │   │   └── typed_methods.py   # типизированные методы, удобные для бэкенда
│   │   ├── openrouter/
│   │   │   └── client.py
│   │   └── telegram/
│   │       ├── bot.py
│   │       ├── handlers/
│   │       └── keyboards.py
│   ├── tasks/
│   │   ├── broker.py
│   │   ├── scheduler.py
│   │   ├── polling.py
│   │   ├── analysis.py
│   │   ├── notifications.py
│   │   └── price.py
│   ├── prompts/
│   │   ├── match_listing.md
│   │   ├── compare_listings.md
│   │   └── summarize.md
│   ├── utils/
│   └── schemas/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── scripts/
│   ├── create_admin.py
│   ├── seed_demo_data.py
│   └── backup_db.sh
├── mcp_configs/                   # примеры конфигов для MCP-клиентов
│   ├── claude_code.mcp.json
│   └── claude_desktop.json
└── docs/
    ├── architecture.md
    ├── deployment.md
    ├── api.md
    ├── mcp_usage.md               # как подключить avito-mcp к Claude Code/Desktop
    └── avito_client_interface.md
```

---

## 11. Развёртывание

### 11.1. Docker Compose

```yaml
services:
  app:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    environment:
      - AVITO_MCP_URL=http://avito-mcp:9000/mcp
      - AVITO_MCP_AUTH_TOKEN=${AVITO_MCP_AUTH_TOKEN}
    depends_on: [db, redis, avito-mcp]
    
  worker:
    build: .
    command: taskiq worker app.tasks.broker:broker
    environment:
      - AVITO_MCP_URL=http://avito-mcp:9000/mcp
      - AVITO_MCP_AUTH_TOKEN=${AVITO_MCP_AUTH_TOKEN}
    depends_on: [db, redis, avito-mcp]
    
  scheduler:
    build: .
    command: taskiq scheduler app.tasks.broker:scheduler
    depends_on: [db, redis]
    
  bot:
    build: .
    command: python -m app.integrations.telegram.bot
    environment:
      - AVITO_MCP_URL=http://avito-mcp:9000/mcp
      - AVITO_MCP_AUTH_TOKEN=${AVITO_MCP_AUTH_TOKEN}
    depends_on: [db, redis, avito-mcp]
    
  avito-mcp:
    build: .
    command: python -m avito_mcp
    environment:
      - AVITO_MCP_TRANSPORT=http
      - AVITO_MCP_HTTP_HOST=0.0.0.0
      - AVITO_MCP_HTTP_PORT=9000
      - AVITO_MCP_AUTH_TOKEN=${AVITO_MCP_AUTH_TOKEN}
      - AVITO_OFFICIAL_CLIENT_ID=${AVITO_OFFICIAL_CLIENT_ID}
      - AVITO_OFFICIAL_CLIENT_SECRET=${AVITO_OFFICIAL_CLIENT_SECRET}
      - AVITO_REVERSE_TOKEN=${AVITO_REVERSE_TOKEN}
      - AVITO_REQUEST_RATE_LIMIT=1.0
      - HTTPS_PROXY=${AVITO_PROXY_URL}
      - REDIS_URL=redis://redis:6379/1   # отдельная БД Redis под кеш MCP
    depends_on: [redis]
    
  db:
    image: postgres:16-alpine
    volumes: [db_data:/var/lib/postgresql/data]
    
  redis:
    image: redis:7-alpine
    
  proxy:
    image: caddy:2-alpine
    ports: ["80:80", "443:443"]
    volumes: [./Caddyfile:/etc/caddy/Caddyfile, caddy_data:/data]
    depends_on: [app]
```

### 11.2. Makefile

- `make dev` — поднять dev-окружение
- `make test` — запустить тесты
- `make lint` — ruff + mypy
- `make migrate` — alembic upgrade head
- `make migration name=...` — новая миграция
- `make seed` — заполнить демо-данными
- `make logs service=app`
- `make backup`

### 11.3. Homelab-специфика

- Возможность отключать всё окружение по расписанию (cron: `docker compose stop` ночью, `start` утром).
- Автозапуск через systemd-unit, который дёргает docker compose.
- Переменная окружения `SYSTEM_PAUSED` для «мягкой» паузы без остановки контейнеров.

---

## 12. Нефункциональные требования

### 12.1. Производительность
- Обработка одного профиля поиска (30 объявлений, LLM-анализ 10 из них) должна укладываться в 2 минуты.
- Отклик любой страницы дашборда < 500 мс при типовой нагрузке.
- Система должна переваривать до 50 активных профилей поиска без деградации.

### 12.2. Надёжность
- При падении воркера задачи восстанавливаются (at-least-once delivery).
- Повторная отправка уведомлений идемпотентна (по `notification_id`).
- БД имеет ежесуточный бэкап (скрипт `backup_db.sh` + cron).

### 12.3. Безопасность
- Все секреты только через env, никаких хардкодов.
- Пароли только в виде argon2-хешей.
- HTTPS через Caddy (или полагаться на внутренний VPN homelab).
- SQL-инъекций нет (все запросы через ORM).
- Защита от CSRF в формах дашборда.
- Rate limiting на уровне FastAPI для всех публичных эндпоинтов (даже за прокси).

### 12.4. Наблюдаемость
- Structured JSON-логи во всех сервисах.
- Корреляционный ID в задачах воркера.
- Endpoint `/health/ready` для мониторинга снаружи.
- Дашборд страницы `/logs` — последние N событий уровня WARNING и выше.

### 12.5. Тестируемость
- Покрытие unit-тестами ключевых сервисов ≥ 70%.
- Интеграционные тесты на критический путь (создание профиля → прогон → уведомление) с моками Avito и OpenRouter.
- Тесты запускаются в CI при каждом коммите (GitHub Actions — конфиг в репозитории).

### 12.6. Документация
- `README.md` — быстрый старт, как развернуть локально.
- `docs/architecture.md` — описание архитектуры и принципов.
- `docs/deployment.md` — гид по развёртыванию на homelab.
- `docs/api.md` — автогенерируемая из FastAPI (`/docs`), плюс ручные дополнения.

---

## 13. План реализации

> **Важно:** до начала кодинга разработчик обязан пройти два подготовительных спринта (0A и 0B). Они выполняются **параллельно**: пока ведутся работы по инфраструктуре (0A), можно проверять доступность Avito API (0B). По итогам оба спринта должны быть приняты заказчиком — это gate для начала разработки.

### Спринт 0A (1–2 дня) — Preflight: инфраструктура homelab

**Цель:** убедиться, что сервер готов принять проект, всё необходимое ПО установлено и доступы выданы. Полный чек-лист — в Приложении C.

**Задачи:**
1. **Получить доступы:**
   - SSH-доступ к homelab-серверу (или RDP, если Windows).
   - VPN-доступ, если сервер не в публичной сети.
   - Доступ к DNS/маршрутизатору для проброса портов, если нужен внешний HTTPS.
   - Аккаунт Git-хостинга (GitHub/Gitea/self-hosted).
2. **Провести аудит среды:**
   - ОС, версия, ресурсы (CPU, RAM, диск, свободное место).
   - Установленное ПО: Docker, Docker Compose, Python, PostgreSQL, Redis, Nginx/Caddy/Traefik.
   - Запущенные сервисы, занятые порты.
   - Сетевые настройки: firewall, прокси, NAT.
3. **Установить недостающее ПО** (по результатам аудита):
   - Docker Engine ≥ 24 + Compose plugin.
   - Git, make, curl, jq (для скриптов).
   - PostgreSQL 16+ (можно в контейнере проекта, но если есть системный — использовать его или создать отдельную БД).
   - Redis 7+ (аналогично — системный или контейнерный).
   - Caddy/Traefik для HTTPS (если нужен внешний доступ).
   - Python 3.12+ на хосте (только для утилит и отладки; основная среда — Docker).
4. **Настроить базу данных и Redis:**
   - Создать пользователя и БД `avito_monitor` в PostgreSQL (или подготовить конфиг для контейнерного варианта).
   - Проверить, что Redis отвечает на ping.
   - Снять строки подключения (DSN) для `.env`.
5. **Настроить безопасность:**
   - Убедиться, что открыты только нужные порты.
   - Проверить fail2ban/аналог.
   - Настроить бэкапы (минимум — дамп Postgres раз в сутки по cron).
6. **Проверить исходящую сеть:**
   - Доступ до `openrouter.ai`, `api.telegram.org`, `www.avito.ru`, `m.avito.ru`, `api.avito.ru`.
   - Если сервер за провайдерским NAT/блокировками — проверить VPN/прокси.
   - Замерить latency и стабильность.
7. **Подготовить среду деплоя:**
   - Создать сервисного пользователя ОС (`avito-monitor`) с минимальными правами.
   - Создать директорию проекта (например, `/opt/avito-monitor`).
   - Настроить ротацию логов (logrotate или Docker log driver с лимитами).
8. **Подготовить dev-workflow:**
   - Удалённая разработка через VS Code Remote — SSH (проверить коннект).
   - Убедиться, что Claude Code может работать в этой среде.
9. **Сдача спринта:**
   - Короткий отчёт (markdown) с версиями ПО, хостами, портами, строками подключения (без секретов), результатами сетевых тестов.
   - Подтверждение заказчика.

**Acceptance:**
- Все пункты чек-листа в Приложении C отмечены.
- Разработчик может запустить `docker run hello-world` на сервере удалённо.
- Успешный тестовый коннект к PostgreSQL и Redis с локальной машины разработчика (или с самого сервера).
- Отчёт сдан и принят.

### Спринт 0B (1–2 дня, параллельно с 0A) — Preflight: верификация Avito API

**Цель:** до погружения в разработку подтвердить, что все эндпоинты из предоставленных спек (официальный API + реверс-инжиниринг) реально работают, и задокументировать их актуальное состояние. Полный чек-лист — в Приложении D.

**Задачи:**
1. **Изучить предоставленные материалы:**
   - Спецификации официального API Avito.
   - Спецификации реверс-инжиниринга.
   - Код прототипа, прогнать локально.
2. **Составить реестр эндпоинтов:**
   - Таблица: метод, URL, назначение, требуемая авторизация, ограничения (rate limit).
3. **Протестировать каждый эндпоинт:**
   - Создать Postman/Bruno/Insomnia коллекцию или набор pytest-скриптов.
   - Для каждого эндпоинта: успешный кейс, типовая ошибка, ответ при недоступности.
   - Собрать реальные примеры ответов (JSON-снимки), сохранить в репозиторий в `tests/fixtures/avito/`.
4. **Проверить авторизацию:**
   - Официальный API: получить `client_id` / `client_secret`, проверить OAuth-flow, срок жизни токена, рефреш.
   - Реверс: проверить, как получаются cookies/токены, сколько живут, как обновляются.
5. **Оценить rate limits:**
   - Экспериментально определить пороги блокировки (где начинаются 429 или капчи).
   - Зафиксировать безопасный rate (запросов/секунду) в документации.
   - Оценить, нужен ли прокси для V1.
6. **Проверить критические сценарии:**
   - Поиск по категории «телефоны» с фильтрами (регион Москва, iPhone, ценовой диапазон) — получить реальную выдачу.
   - Получение деталей одного объявления, включая все фото.
   - Получение списка собственных объявлений (для price intelligence).
   - Получение метаданных: категорий, параметров категории, регионов.
7. **Задокументировать риски:**
   - Какие эндпоинты работают нестабильно.
   - Какие поля в ответах опциональны/часто отсутствуют.
   - Какие элементы защиты Avito сейчас активны (Cloudflare, bot-детект, капча).
8. **Подготовить абстракцию:**
   - Первичный черновик интерфейса `AvitoClient` (см. раздел 4.3) на основе того, что реально умеет текущий прототип.
   - Список методов, которые точно нужны для V1, и оценка их готовности.
9. **Сдача спринта:**
   - Отчёт с реестром эндпоинтов, статусом каждого, рекомендациями по rate limit, выявленными рисками.
   - Pytest-набор или Postman-коллекция для регресс-проверок.
   - Подтверждение заказчика.

**Acceptance:**
- Все эндпоинты, заявленные в спеках, проверены и статус каждого зафиксирован в отчёте.
- Определён безопасный rate limit.
- Получены и сохранены реальные примеры ответов для всех критических сценариев V1.
- Чек-лист Приложения D закрыт.
- Отчёт сдан и принят.

### Спринт 0 (1–2 дня) — фундамент
- Инициализация репозитория, `pyproject.toml`, Docker, CI
- Alembic + первая миграция с таблицами `users`, `system_settings`
- Базовый FastAPI-скелет, логирование, конфиг
- Jinja2 + HTMX + Tailwind базовый layout
- Страница логина и auth-механизм
- Скрипт `create_admin.py`

### Спринт 1 (2–3 дня) — MCP-сервер Avito (V1-набор)

**Сокращён** относительно исходных оценок (5–7 дней) после ADR-001 и ADR-006: V1-набор инструментов уменьшен до 4, таксономия и manage-my-listings отложены в V2.

- Отдельный пакет `avito_mcp` с точкой входа на stdio и HTTP-транспортах
- Перенос кода Avito-клиента в `avito_mcp/integrations/`:
  - `http.py` — curl_cffi Chrome120 (из `avito-xapi/src/workers/base_client.py`)
  - `rate_limiter.py` — TokenBucket (из `avito-xapi/src/workers/rate_limiter.py`)
  - `reverse_api.py` — методы fetch_search_page (HTML/JSON-парсинг) + get_listing (mobile API `/19/items/{id}`)
  - Опциональная поддержка прокси через `AVITO_PROXY_URL` (см. ADR-004 — для разработки с зарубежной машины)
- Общие Pydantic-модели в `shared/models/`: `ListingShort`, `ListingDetail`, `ListingImage`, `SellerInfo`
- Реализация 4 MCP-инструментов из раздела 4.3.3:
  - `avito_fetch_search_page`, `avito_get_listing`, `avito_get_listing_images`, `avito_health_check`
- Auth-токен для HTTP-транспорта
- Метрики и structured-логи
- Dockerfile / сервис в docker-compose
- Unit-тесты с моками + VCR-кассетой на реальный фикстурный набор `tests/fixtures/avito/` (позаимствовать из `avito-xapi/tests/fixtures/`)
- Клиент `AvitoMCPClient` в `app/integrations/avito_mcp_client/` с типизированными методами
- Конфиги для Claude Code и Claude Desktop в `mcp_configs/`
- Документация `docs/mcp_usage.md`
- Демонстрация: разработчик из Claude Code вызывает 3 инструмента (search_page, get_listing, health) и показывает результат заказчику

### Спринт 2 (3–4 дня) — Search Profiles + базовый мониторинг
- Модели и миграции: `search_profiles`, `listings`, `profile_listings`, `profile_runs`
- CRUD API и страницы дашборда
- TaskIQ broker + scheduler
- Задача `poll_profile`, сохранение новых объявлений (без LLM пока)
- Ручной запуск прогона через кнопку в UI

### Спринт 3 (3–4 дня) — LLM Analyzer + Notifier
- OpenRouter-клиент
- Промпты, кеширование
- Таблица `llm_analyses`
- Интеграция в цикл мониторинга
- Telegram-бот (long polling), команды, уведомления
- Inline-кнопки действий

### Спринт 4 (3–4 дня) — Price Intelligence
- Модели и миграции: `price_analyses`, `price_analysis_runs`
- Формы создания и запуска
- Страница отчёта с таблицей и графиком
- Отправка отчёта в Telegram по запросу

### Спринт 5 (2–3 дня) — Polish
- Тихие часы, паузы, лимиты расходов
- Страница `/logs`
- E2E-тесты ключевых сценариев
- `docs/` и `README`
- Прогон на homelab, бэкапы

**Итого ориентировочно:** 2–4 дня preflight (0A + 0B, параллельно) + 17–25 дней основной разработки (включая расширенный Спринт 1 на MCP-сервер). Всего 19–29 дней на одного разработчика full-time.

---

## 14. Критерии приёмки V1

Система считается готовой к сдаче, если:

1. Создан минимум один профиль поиска iPhone, который раз в настроенный интервал собирает объявления с Avito.
2. Новые объявления проходят LLM-анализ и подходящие улетают в Telegram с ссылкой и summary.
3. Нажатие inline-кнопок в Telegram корректно меняет состояние лота в БД.
4. Работает запрос ценовой разведки: по эталону строится отчёт с вилкой цен, плюсами/минусами конкурентов и рекомендацией.
5. Дашборд доступен по HTTPS, требует логина, содержит все указанные страницы.
6. Система корректно переживает перезапуск Docker Compose (ни одно уведомление не теряется, задачи возобновляются).
7. Все секреты — в `.env`, никаких хардкодов в коде.
8. Прохождение `make lint` и `make test` без ошибок.
9. Развёрнута на homelab-сервере, работает минимум 72 часа без вмешательства.
10. Есть рабочий бэкап БД.
11. **MCP-сервер Avito запущен как отдельный сервис, основной бэкенд обращается к Avito только через него.**
12. **Разработчик успешно подключил MCP-сервер к Claude Code и продемонстрировал вызов минимум 3 инструментов.**
13. **Профиль создаётся по URL поиска Avito** (см. ADR-001) — копипаст работает на всех 6 категориях мобильной техники.
14. **Двойная ценовая вилка работает** (ADR-008): лоты вне alert-зоны попадают в БД со статусом `market_data` и не дают Telegram-уведомлений. При падении цены лота из market_data в alert-зону приходит `price_dropped_into_alert`.
15. **Классификация состояния работает** (ADR-010): для каждого нового лота определён `condition_class`, в дашборде на странице профиля видна distribution по классам, clean-медиана отличается от raw-медианы при наличии non-working лотов.
16. **График цены за 30 дней** отрисовывается в дашборде (страница профиля /stats), точки берутся из `profile_market_stats`.
17. **Уведомление-инсайт работает**: за тестовую неделю минимум одно срабатывание `market_trend_*` или `price_drop_listing` зафиксировано или подтверждена корректность пороговой логики на синтетических данных.

---

## 15. Риски и их митигация

| Риск | Митигация |
|---|---|
| Avito блокирует запросы | Rate limit + прокси + резервный режим headless-браузера |
| Изменение внутреннего API Avito | Покрытие интеграции тестами, быстрая замена через интерфейс `AvitoClient` |
| Исчерпание бюджета на LLM | Дневные лимиты, кеш анализа, дешёвые модели как префильтр |
| Ложные срабатывания LLM | Настраиваемый порог confidence, возможность re-analyze, логи решений |
| Падение homelab-сервера ночью | Возможность отключения по расписанию, задачи идемпотентны |
| Утечка секретов | .env в .gitignore, отдельное хранение на сервере, argon2 для паролей |

---

## 16. Что делать программисту прямо сейчас

1. **Получить от заказчика:**
   - Доступы к homelab-серверу (SSH/VPN, реквизиты для PostgreSQL/Redis, если они уже развёрнуты).
   - Спецификации API Avito (официальный + реверс) и код прототипа.
   - Токены: OpenRouter API key, Telegram Bot token (или инструкцию по их созданию).
   - `chat_id` получателя уведомлений (или инструкцию, что заказчик пришлёт после `/start`).
2. **Пройти Спринт 0A (Preflight Infrastructure)** — закрыть чек-лист Приложения C, сдать отчёт.
3. **Параллельно пройти Спринт 0B (Avito API Verification)** — закрыть чек-лист Приложения D, сдать отчёт.
4. **Дождаться формального «Go»** от заказчика по итогам preflight.
5. Создать репозиторий по структуре из раздела 10.
6. Пройти Спринт 0 и показать работающий каркас с логином.
7. Согласовать детали интерфейса `AvitoClient` перед полноценной интеграцией прототипа (на основе того, что выяснилось в Спринте 0B).
8. Согласовать стартовые промпты LLM (`match_listing.md`, `compare_listings.md`) — это критично для качества.
9. Дальше идти по спринтам, сдавая каждый спринт инкрементально.

---

## Приложение A. Пример промпта `match_listing.md`

```
Ты — опытный покупатель подержанных iPhone. Проанализируй объявление и определи,
соответствует ли оно критериям покупателя.

## Объявление
Заголовок: {{ listing.title }}
Цена: {{ listing.price }} ₽
Регион: {{ listing.region }}
Описание:
{{ listing.description }}

Параметры:
{% for k, v in listing.parameters.items() %}
- {{ k }}: {{ v }}
{% endfor %}

{% if analyze_photos and listing.images %}
## Фотографии
[прилагаются {{ listing.images | length }} фото]
{% endif %}

## Критерии покупателя
{{ criteria }}

## Задача
Верни строгий JSON со следующими полями:
- is_match: bool — подходит ли лот
- confidence: float (0..1) — уверенность
- summary: string — 2-3 предложения для Telegram (что это за лот, ключевое)
- matched_criteria: string[] — какие критерии покупателя выполнены
- concerns: string[] — что вызывает сомнения
- red_flags: string[] — признаки мошенничества или восстановленного устройства

Отвечай только валидным JSON, без пояснений.
```

---

## Приложение B. Ссылки на вспомогательные библиотеки

- FastAPI — https://fastapi.tiangolo.com/
- aiogram — https://docs.aiogram.dev/
- SQLAlchemy 2.0 async — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- TaskIQ — https://taskiq-python.github.io/
- HTMX — https://htmx.org/
- DaisyUI — https://daisyui.com/
- OpenRouter — https://openrouter.ai/docs
- pydantic-settings — https://docs.pydantic.dev/latest/concepts/pydantic_settings/

---

## Приложение C. Чек-лист Preflight: инфраструктура homelab

### C.1. Доступы
- [ ] SSH-ключ разработчика добавлен на сервер
- [ ] Проверен вход под сервисным пользователем
- [ ] Выдан `sudo` (или root) для установки ПО (временно, на период preflight)
- [ ] Настроен VPN / проброс портов (если применимо)
- [ ] Доступ к репозиторию проекта выдан
- [ ] Заведены / получены учётки для внешних сервисов: OpenRouter, Telegram BotFather, Avito (personal + developer)

### C.2. Аудит сервера
- [ ] Версия ОС и ядра зафиксирована
- [ ] Свободное место на диске (минимум 20 ГБ под проект + 20 ГБ под БД)
- [ ] Свободная RAM (минимум 2 ГБ под проект в работающем виде)
- [ ] Временнáя зона (желательно Europe/Moscow)
- [ ] Синхронизация времени работает (NTP)
- [ ] Список запущенных сервисов и занятых портов задокументирован

### C.3. Системное ПО
- [ ] Docker Engine ≥ 24 установлен
- [ ] Docker Compose plugin установлен
- [ ] Docker запускается без sudo для сервисного пользователя
- [ ] Git установлен
- [ ] make, curl, jq установлены
- [ ] (опционально) Python 3.12+ на хосте для локальных скриптов
- [ ] (опционально) uv или Poetry

### C.4. Базы данных
- [ ] PostgreSQL 16+ доступен (системный или контейнерный — выбран вариант)
- [ ] Создана БД `avito_monitor`
- [ ] Создан пользователь с правами на БД
- [ ] Проверено подключение с хоста и из Docker-сети
- [ ] Redis 7+ доступен
- [ ] Проверен `redis-cli PING` → PONG
- [ ] Если существующие PostgreSQL/Redis — не пересекаются с портами проекта

### C.5. HTTPS и доступ к дашборду
- [ ] Выбран способ HTTPS: Caddy, Traefik или отказ от внешнего доступа (только VPN)
- [ ] Проброшен / зарезервирован домен (например, `monitor.local` или внешний)
- [ ] Порт 443 (или альтернативный) доступен извне (если нужен внешний доступ)
- [ ] Сертификат либо выпущен, либо настроено автополучение

### C.6. Сетевые проверки
- [ ] `curl https://openrouter.ai` — 200 OK
- [ ] `curl https://api.telegram.org` — отвечает
- [ ] `curl https://www.avito.ru` — отвечает корректно (без блокировки от провайдера)
- [ ] `curl https://m.avito.ru` — отвечает
- [ ] Если нужен прокси для Avito — прокси настроен и протестирован
- [ ] Latency до Avito и OpenRouter приемлемы (< 300 мс до РФ-сервисов)

### C.7. Безопасность
- [ ] Firewall настроен, открыты только нужные порты
- [ ] SSH на нестандартном порту / только по ключам
- [ ] fail2ban или аналог установлен (опционально)
- [ ] Автообновления безопасности включены

### C.8. Backup и надёжность
- [ ] Скрипт `pg_dump` написан и протестирован
- [ ] Cron-задача на ежесуточный бэкап настроена
- [ ] Бэкапы складываются в отдельную директорию / внешнее хранилище
- [ ] Протестирована процедура восстановления из бэкапа (тестовый restore)
- [ ] Docker logging driver настроен с лимитами (max-size, max-file)
- [ ] logrotate или аналог настроен для системных логов

### C.9. Проектная директория
- [ ] Создан каталог `/opt/avito-monitor` (или согласованный)
- [ ] Права на каталог выданы сервисному пользователю
- [ ] Подготовлен пустой `.env` с заглушками
- [ ] Клонирован пустой репозиторий проекта (или заготовка)

### C.10. Dev-workflow
- [ ] Проверена работа VS Code Remote — SSH
- [ ] Проверена работа Claude Code в удалённой среде
- [ ] Git push/pull работает с учёткой разработчика
- [ ] Настроены SSH-ключи для git (deploy key или аккаунт)

### C.11. Отчёт
- [ ] Составлен `docs/infrastructure.md` с итогами аудита
- [ ] Зафиксированы версии: OS, Docker, PostgreSQL, Redis, Python
- [ ] Перечислены используемые хосты, порты, пути
- [ ] Сохранены (в vault/секретном хранилище, не в git) строки подключения
- [ ] Отчёт отправлен заказчику и принят

---

## Приложение D. Чек-лист Preflight: верификация Avito API

### D.1. Подготовка
- [ ] Получены и изучены спецификации официального API
- [ ] Получены и изучены спецификации реверс-инжиниринга
- [ ] Получен и запущен локально код прототипа
- [ ] Создана Postman / Bruno / Insomnia коллекция или pytest-набор для тестов
- [ ] Заведены credentials для официального API (client_id, client_secret)
- [ ] Получены актуальные cookies/токены для реверс-API (если требуется)

### D.2. Реестр эндпоинтов
- [ ] Составлена сводная таблица всех эндпоинтов из спек
- [ ] Для каждого указано: метод, URL, назначение, авторизация, параметры
- [ ] Отмечены эндпоинты, критичные для V1 (поиск, детали, мои объявления, метаданные)
- [ ] Отмечены эндпоинты, нужные для V2 (чаты, сообщения) — но не тестируются в V1

### D.3. Проверка официального API
- [ ] OAuth-flow работает, токен выдаётся
- [ ] Refresh-токен работает
- [ ] Запрос своих объявлений возвращает данные
- [ ] Запрос статистики работает (если применимо)
- [ ] Работа с балансом / тарифами работает (если применимо для V1)
- [ ] Зафиксирован rate limit официального API

### D.4. Проверка реверс-API
- [ ] Эндпоинт поиска по параметрам работает, возвращает выдачу
- [ ] Проверена фильтрация по категории «телефоны» с типовыми параметрами
- [ ] Проверена фильтрация по региону, цене, модели
- [ ] Эндпоинт получения деталей объявления возвращает полные данные
- [ ] Возвращаются URL всех фото, они доступны по прямой ссылке
- [ ] Метаданные категорий возвращаются
- [ ] Параметры конкретной категории возвращаются (для динамических форм фильтров)
- [ ] Список регионов / локаций возвращается
- [ ] Проверена обработка ошибок (404, 403, 429, 500)

### D.5. Rate limits и антибот
- [ ] Экспериментально определён порог, после которого появляется 429 / капча
- [ ] Определён безопасный rate (запросов в секунду) с запасом
- [ ] Проверено, срабатывает ли Cloudflare challenge при типовой активности
- [ ] Если срабатывает — зафиксирована стратегия обхода (headers, cookies, timing)
- [ ] Принято решение: нужен ли прокси для V1 (да/нет/опционально)

### D.6. Фиксация данных для тестов
- [ ] Сохранены примеры ответов для каждого критичного эндпоинта в `tests/fixtures/avito/`
- [ ] Отмечены опциональные поля и поля, которые могут отсутствовать
- [ ] Отмечены поля, структура которых нестабильна между объявлениями
- [ ] Собраны примеры разных типов продавцов (частник, компания)
- [ ] Собраны примеры объявлений с / без фото, с / без всех параметров

### D.7. Интерфейс AvitoClient
- [ ] Составлен черновик интерфейса (Python Protocol) в `docs/avito_client_interface.md`
- [ ] Для каждого метода интерфейса указано, какой реальный эндпоинт его реализует
- [ ] Отмечены ограничения и допущения

### D.8. Выявленные риски
- [ ] Задокументированы нестабильные эндпоинты
- [ ] Отмечены эндпоинты, требующие особой обработки (капча, задержки)
- [ ] Предложены fallback-стратегии (например, если поиск упал — пропустить цикл, не падать целиком)
- [ ] Оценена вероятность поломки интеграции в ближайшие 3–6 месяцев (субъективно)

### D.9. Отчёт
- [ ] Составлен `docs/avito_api_audit.md` с итогами
- [ ] Приложена сводная таблица эндпоинтов со статусом (✅ работает / ⚠ с оговорками / ❌ не работает)
- [ ] Приложены рекомендации по rate limit
- [ ] Приложён список рисков
- [ ] Приложена оценка готовности прототипа к использованию в V1
- [ ] Отчёт отправлен заказчику и принят

---

## Приложение E. MCP-сервер Avito: сводка инструментов и примеры конфигов

### E.1. Полный список MCP-инструментов V1

| Инструмент | Назначение | Авторизация |
|---|---|---|
| `avito_search` | Поиск по фильтрам | реверс |
| `avito_get_listing` | Детали публичного объявления | реверс |
| `avito_get_listing_images` | Список URL фото в оригинале | реверс |
| `avito_download_image` | Скачивание изображения через прокси | — |
| `avito_list_my_listings` | Список своих объявлений | официальное |
| `avito_get_my_listing` | Детали своего объявления | официальное |
| `avito_create_listing` | Создание объявления | официальное |
| `avito_update_listing` | Редактирование своего объявления | официальное |
| `avito_archive_listing` | Архивация | официальное |
| `avito_restore_listing` | Восстановление из архива | официальное |
| `avito_delete_listing` | Удаление | официальное |
| `avito_get_listing_stats` | Статистика по своему объявлению | официальное |
| `avito_get_account_balance` | Баланс кошелька | официальное |
| `avito_get_promotion_options` | Услуги продвижения | официальное |
| `avito_get_categories` | Дерево категорий | — |
| `avito_get_category_parameters` | Параметры категории | — |
| `avito_get_regions` | Дерево регионов | — |
| `avito_search_locations` | Автодополнение населённых пунктов | — |
| `avito_get_seller` | Информация о продавце | реверс |
| `avito_get_seller_listings` | Объявления продавца | реверс |
| `avito_health_check` | Проверка доступности и токенов | — |
| `avito_get_rate_limit_status` | Текущие лимиты | — |
| `avito_refresh_auth` | Принудительное обновление токенов | — |

### E.2. Пример конфига для Claude Code (`.mcp.json` в корне репозитория)

```json
{
  "mcpServers": {
    "avito": {
      "command": "docker",
      "args": [
        "compose", "run", "--rm",
        "-e", "AVITO_MCP_TRANSPORT=stdio",
        "avito-mcp",
        "python", "-m", "avito_mcp"
      ]
    }
  }
}
```

Альтернативный вариант — подключение к уже запущенному HTTP-серверу:

```json
{
  "mcpServers": {
    "avito": {
      "url": "http://localhost:9000/mcp",
      "headers": {
        "Authorization": "Bearer ${AVITO_MCP_AUTH_TOKEN}"
      }
    }
  }
}
```

### E.3. Пример конфига для Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "avito": {
      "command": "/usr/local/bin/avito-mcp",
      "env": {
        "AVITO_MCP_TRANSPORT": "stdio",
        "AVITO_OFFICIAL_CLIENT_ID": "...",
        "AVITO_OFFICIAL_CLIENT_SECRET": "...",
        "AVITO_REVERSE_TOKEN": "..."
      }
    }
  }
}
```

### E.4. Включить в Приложение D (Preflight Avito API) дополнительно

Отдельного Preflight-спринта под MCP не требуется, но в Спринте 0B добавляется пункт:
- [ ] Подтверждено, что все эндпоинты из спек, соответствующие инструментам MCP V1 (раздел E.1), либо работают, либо явно помечены как опциональные.
- [ ] Для официального API подтверждена возможность управления объявлениями (create/update/archive) — без этого часть инструментов не сможет быть реализована и это должно быть зафиксировано.

---

**Конец ТЗ V1 (с Preflight и MCP).**
