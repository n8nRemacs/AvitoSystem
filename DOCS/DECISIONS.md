# Architecture Decisions Log

Лог ключевых решений по проекту мониторинга Avito (V1). Формат: контекст → решение → последствия.

Каждое решение имеет статус: **Accepted** (принято и действует), **Superseded** (отменено новым), **Proposed** (предложено, не утверждено).

---

## ADR-001 — URL-based профили поиска вместо генерации фильтров

**Дата:** 2026-04-25  
**Статус:** Accepted

**Контекст.** Изначальная редакция ТЗ V1 (раздел 4.1) предполагала, что профиль поиска хранит параметры фильтра (`category`, `avito_filters` jsonb с brand/model/memory/color и т.д.), а дашборд динамически рендерит форму с зависимыми выпадашками (бренд → модель → конфигурация). Чтобы это работало, в БД нужны таблицы таксономии Avito: `avito_categories`, `avito_category_parameters`, `avito_param_values` (≈ 5500 записей только для мобильной техники), плюс sync-задача обновления + хирургия с XML-каталогами Avito + хардкод-фолбэки.

**Решение.** Профиль хранит **готовый URL поиска**, скопированный пользователем напрямую из веб-интерфейса Avito. Система берёт URL как-есть и использует для polling (плюс overlay-параметры — см. ADR-002).

**Последствия.**
- Из БД-схемы убираются 3 таблицы метаданных и весь sync-механизм
- Из дашборда убирается динамическая форма категорий, остаётся одно поле URL
- MCP-сервер сокращается с 23 tools (раздел 4.3.3 ТЗ) до 4 (см. ADR-006)
- Спринт 0B упрощается: не надо реверсить XML-каталоги и mapping slug→category_id для построения запросов
- Цена: пользователь должен сам уметь настроить фильтр в Avito и скопировать URL — это не проблема в персональной системе для одного юзера
- Расширение на новые категории (авто, недвижимость) не требует доработок — любой URL Avito работает

---

## ADR-002 — Overlay-параметры поверх скопированного URL

**Дата:** 2026-04-25  
**Статус:** Accepted

**Контекст.** ADR-001 ограничивает гибкость: чтобы сменить регион или ценовую вилку, юзер должен переоткрыть Avito, поправить фильтр, скопировать новый URL. Для часто меняющихся параметров это неудобно.

**Анализ структуры URL.** Декодирование `f=` параметра показало: бинарный фильтр содержит только категорийные параметры (бренд, модель, состояние). Цена, регион, доставка, сортировка живут параллельно как стандартные query-params (`pmin`, `pmax`, `d`, `s`) и в slug пути (`/all/` vs `/moskva/`). Их можно **накладывать** на любой URL без изменения бинарного `f=`.

**Решение.** В таблице `search_profiles` хранятся 5 опциональных overlay-полей:
- `region_slug` (str, nullable) — заменяет первый сегмент path
- `min_price`, `max_price` (int, nullable) — пишутся в `?pmin/pmax`
- `only_with_delivery` (bool, nullable) — `?d=1`
- `sort` (int, nullable) — `?s=N`

Перед каждым polling-запросом функция `apply_overlay(url, profile)` модифицирует URL.

**Последствия.**
- Один скопированный URL «iPhone 12 Pro Max» → много профилей с разной географией/ценой/сортировкой
- Дашборд: рядом с полем URL — компактная секция «Переопределения» (5 полей)
- Список регион-slug-ов кладётся в seed-файл `app/data/avito_regions.json` (≈ 85 регионов + города-миллионники)
- В backlog: «хирургический нож» для вырезания ценового блока из `f=`, если эмпирически выяснится, что Avito приоритизирует `f=` над query-params

---

## ADR-003 — Двухуровневая работа с Avito API (реверс + официальный)

**Дата:** 2026-04-25  
**Статус:** Accepted

**Контекст.** Исследование официального API (`api.avito.ru` через OAuth2 client_credentials) показало:
- Официальный API **не имеет поиска чужих объявлений** (`/core/v1/items` возвращает только собственные)
- Покрыто официально: свои объявления, статистика, баланс, услуги продвижения, мессенджер, call tracking, taxonomy через Autoload (`/autoload/v1/user-docs/tree` + `/fields/{slug}`)
- Поиск чужих объявлений и просмотр карточки чужого лота — **только реверс mobile API** (`app.avito.ru/api/11/items`, `/19/items/{id}`) или парсинг web-страниц

**Решение.** MCP-сервер `avito-mcp` поддерживает два независимых блока:
1. **Реверс-блок** (V1): polling выдачи поиска через web-страницы (по URL пользователя из ADR-001), детали публичных лотов через mobile API. TLS-fingerprint Chrome120 (curl_cffi).
2. **Официальный блок** (V2): autoload-таксономия, свои объявления, статистика, ценовая разведка через официальный API. OAuth2 + Bearer-токен.

В V1 реализуется только реверс-блок. Официальный — задел в Спринтах 4–5.

**Последствия.**
- В V1 не используются client_id/secret официального API, но сохранены в `.env` для V2
- Отчёт об исследовании API сохранён, snapshots taxonomy лежат в `DOCS/avito_api_snapshots/` для использования в V2
- Платный тариф Avito (требуется для официального API) уже подключён владельцем — V2 разблокирован

---

## ADR-004 — SOCKS5-туннель через homelab для разработки с зарубежной машины

**Дата:** 2026-04-25  
**Статус:** Accepted

**Контекст.** Avito firewall (QRATOR) блокирует HTTP-запросы с зарубежных IP к `www.avito.ru`, `m.avito.ru`, публичным XML-каталогам — даже Chrome120-impersonate возвращает HTTP 429. Без работающего обхода невозможно ни тестировать парсинг выдачи в V1, ни добывать seed-данные для V2.

**Решение.** SSH dynamic forwarding через homelab (`213.108.170.194`, Россия):

```bash
ssh -D 127.0.0.1:1081 -N -f homelab
```

Все Avito-запросы при разработке идут через `socks5://127.0.0.1:1081`. Прокси не требуется в продакшене (avito-monitor разворачивается на том же homelab — RU IP получается автоматически).

**Последствия.**
- Документация запуска: `DOCS/RU_PROXY_SETUP.md`
- В Python-коде Avito-клиента — параметр `proxy` опциональный, читается из `AVITO_PROXY_URL` в `.env`. В прод — пусто, в dev — `socks5://127.0.0.1:1081`
- Все эндпоинты, ранее блокированные 429, теперь подтверждены работающими через туннель (включая 3 XML-каталога: phone_catalog, tablets, brendy_fashion)

---

## ADR-005 — PostgreSQL + SQLAlchemy 2.0 async + Alembic вместо Supabase PostgREST

**Дата:** 2026-04-25  
**Статус:** Accepted (зафиксировано ТЗ, явно отсюда)

**Контекст.** Существующие подпроекты (`avito-xapi`, `tenant-auth`, `AvitoBayer`) работают с Supabase через самописные httpx-клиенты к PostgREST. ТЗ V1 требует SQLAlchemy 2.0 async + Alembic + чистый PostgreSQL.

**Решение.** Новый проект `avito-monitor` использует PostgreSQL 16 напрямую (без Supabase). ORM — SQLAlchemy 2.0 в async-режиме. Миграции — Alembic с автогенерацией.

**Последствия.**
- Проще homelab-деплой: один контейнер `postgres:16-alpine` без Supabase Studio/Kong/PostgREST
- Type-safe запросы через mapped_column + relationships
- Не переиспользуем `supabase_client.py` из AvitoBayer и `storage/supabase.py` из avito-xapi — пишем repository pattern с нуля
- Существующие SQL-миграции (`migration_leads.sql`, `001_init.sql`) — referенс структуры, не источник для импорта

---

## ADR-006 — Минимальный набор MCP-tools в V1

**Дата:** 2026-04-25  
**Статус:** Accepted

**Контекст.** ТЗ раздел 4.3.3 описывает ~23 MCP tools (search, get_listing, my_listings × 7, stats × 3, metadata × 4, sellers × 2, service × 3, V2 messenger × 4). После ADR-001 + ADR-003 большая часть этих инструментов теряет смысл в V1.

**Решение.** В V1 реализуются 4 tools:

1. `avito_fetch_search_page(url, page=1)` — фетч страницы поиска по готовому URL, парсинг JSON-стейта, возврат списка объявлений
2. `avito_get_listing(item_id_or_url)` — детали лота (описание, фото, продавец, параметры)
3. `avito_get_listing_images(item_id)` — URL фото в оригинальном качестве
4. `avito_health_check` — проверка доступности Avito + статус rate limit

В V2 добавляются tools под официальный API: `avito_get_categories`, `avito_get_category_fields`, `avito_list_my_listings`, `avito_get_my_listing`, `avito_get_listing_stats`, `avito_get_account_balance`, `avito_get_promotion_options`, плюс create/update/archive/restore/delete для своих объявлений.

V2-мессенджер (4 tools) откладывается до решения о платной интеграции.

**Последствия.**
- Спринт 1 (avito-mcp) сокращается с 5–7 до 2–3 дней
- MCP-сервер компактный, легко тестируется
- Ресурсы (`avito://listings/...`, `avito://categories`) и промпты (`search_iphone`, `analyze_competitor`) тоже сокращаются под V1-скоуп

---

## ADR-008 — Двойная ценовая вилка: search vs alert

**Дата:** 2026-04-25  
**Статус:** Accepted

**Контекст.** Если у профиля одна ценовая вилка и она совпадает с фильтром Avito — мы видим только лоты в этом окне. При падении рыночной цены ниже нашего нижнего порога мы перестаём получать выдачу и **не замечаем тренд**. Продолжаем «искать дорогие устройства, хотя цена уже упала».

**Решение.** Каждый профиль имеет две независимые вилки:

- **Search-вилка** (широкая) — `search_min_price`, `search_max_price`. Применяется к URL Avito (`?pmin=/pmax=`). Что грузим из выдачи в БД для построения «карты рынка».
- **Alert-вилка** (узкая) — `alert_min_price`, `alert_max_price`. Постфильтр на собранных лотах. Что показываем юзеру в Telegram-уведомлениях и анализируем глубоким LLM.

При создании профиля по URL Avito с `pmin/pmax`:
- `alert_min/max` берутся из URL
- `search_min/max` рассчитываются автоматически: `search_min = round(alert_min * 0.75)`, `search_max = round(alert_max * 1.25)` (расширение ±25%)

В дашборде оба значения редактируемые. Если `search_min/max` оставлены пустыми — фильтрация только по URL без расширения.

**Последствия.**
- При полностью схлопнувшемся рынке (цены просели за нижний alert-порог) система продолжает видеть выдачу за счёт search-вилки, фиксирует тренд и шлёт уведомление через ADR-009
- Лоты в search-зоне, но вне alert-зоны — попадают в БД со статусом `market_data` и не дают Telegram-уведомлений
- Лот, перешедший из market_data в alert (цена упала вниз через границу) — генерирует особое уведомление `price_dropped_into_alert`
- Это база для расчёта медианы рынка и трендов (ADR-009)

---

## ADR-009 — Market statistics и уведомления-инсайты

**Дата:** 2026-04-25  
**Статус:** Accepted

**Контекст.** Из ADR-008 вытекает, что у нас в БД накапливаются полные снимки рынка по каждому профилю. Это бесплатный материал для рыночной аналитики, которая превращает инструмент из «охоты за лотом» в «рыночную разведку».

**Решение.** На каждом polling-прогоне рассчитываются и сохраняются агрегаты в `profile_runs`. Раз в сутки задача `compute_market_stats(profile_id)` сворачивает данные за период в отдельную таблицу `profile_market_stats` (granularity: day/week/month).

**Метрики:**
- `price_median_raw` / `price_median_clean` (clean = только working, см. ADR-010)
- `price_mean`, `price_min`, `price_max`, `price_p25`, `price_p75`
- `listings_count` (объём предложения)
- `new_listings_count` (появились за период)
- `disappeared_listings_count` (status стал `closed`/`removed`)
- `avg_listing_lifetime_hours` (proxy для скорости продажи)
- `condition_distribution` (jsonb — `{"working": 0.65, "blocked_icloud": 0.15, ...}`)

**Новые типы Telegram-уведомлений** (дополняют 4.5 ТЗ):
- `price_drop_listing` — цена конкретного лота упала на ≥ N% (default 10%)
- `price_dropped_into_alert` — лот вошёл в alert-зону снизу
- `market_trend_down` / `market_trend_up` — медиана за неделю изменилась на ≥ N% (default 5%)
- `historical_low` — цена лота ниже минимальной за N дней (default 30)
- `supply_surge` — резкий рост числа активных лотов (default ≥ 30%)
- `condition_mix_change` — доля working лотов изменилась на ≥ 10% за неделю

Пороги настраиваются в `notification_settings` (jsonb) на уровне профиля, дефолты в system_settings.

**Дашборд** — на странице профиля:
- График Chart.js: медиана/min/max за 30 дней + alert-вилка пунктиром
- Гистограмма распределения цен (сейчас) с разделением working / non-working
- Лента рыночных событий
- Авто-рекомендация alert-вилки на основе текущей медианы (опциональная кнопка «применить»)

**Cleanup-стратегия:**
- Лоты `status=market_data` неактивные более 30 дней — удаляются (агрегаты в `profile_market_stats` сохраняются)
- Лоты `status=analyzed` (LLM-анализ был) — 90 дней
- Лоты `status=notified` (отправлено в Telegram) — бессрочно (для аудита)

**Последствия.**
- Линейный рост таблиц — управляемый. Прирост `profile_market_stats` ≈ 1 запись/день/профиль
- Визуализация занимает 1 дополнительный день в Спринте 5
- `compute_market_stats` — отдельная очередь TaskIQ `analytics`

---

## ADR-010 — Двухступенчатый LLM-анализ для очищенной статистики

**Дата:** 2026-04-25  
**Статус:** Accepted

**Контекст.** На вторичном рынке смартфонов значительная доля лотов — заблокированные iCloud-айфоны, разбитые, не включающиеся, «на запчасти». Их цена резко ниже нормальных лотов. Если считать медиану по всему массиву — получаем статистику, искажённую долей «мусора». Тренды по такой «грязной» медиане не отражают реальный рынок: рост может означать просто уменьшение числа битых лотов, а не реальное удорожание работающих.

**Решение.** Перед глубоким LLM-анализом каждый лот проходит **дешёвую классификацию состояния** (claude-haiku, текст-only, ~$0.0001 на лот). Класс сохраняется в БД и используется как фильтр для расчёта clean-метрик и для решения «делать ли полный LLM-анализ».

**LLMAnalyzer Protocol** — три метода вместо двух:

```python
class LLMAnalyzer(Protocol):
    async def classify_condition(
        self, listing: ListingDetail, model: str
    ) -> ConditionClassification: ...
    
    async def match_criteria(
        self, listing: ListingDetail, criteria: str,
        analyze_photos: bool, model: str
    ) -> MatchResult: ...
    
    async def compare_to_reference(
        self, competitor: ListingDetail,
        reference: ListingDetail | ReferenceData, model: str
    ) -> ComparisonResult: ...
```

`ConditionClassification`:
- `condition_class` (enum: `working`, `blocked_icloud`, `blocked_account`, `not_starting`, `broken_screen`, `broken_other`, `parts_only`, `unknown`)
- `confidence` (0..1)
- `reasoning` (короткий текст)
- `tokens_used`, `cost_usd`

**Промпты** — в `app/prompts/`:
- `classify_condition.md` (новый, для всех лотов)
- `match_listing.md` (как было, для лотов в alert-зоне с подходящим состоянием)
- `compare_listings.md` (как было, для price intelligence)

**Поток обработки в воркере:**

```
fetch_search_page (URL с применённым overlay)
    ↓
для каждого нового avito_id:
    ↓
  fetch_listing (детали)
    ↓
  classify_condition (haiku, ~$0.0001)
    ↓
  store listing с condition_class
    ↓
  если в alert-зоне И condition фильтр пройден (по умолчанию только `working`):
    ├── match_criteria (полный LLM, опц. с фото)
    ├── если match → создаётся notification
    └── status = analyzed | notified
  иначе:
    └── status = market_data
```

**Метрики** — clean = только лоты с `condition_class IN profile.allowed_conditions` (по умолчанию `["working"]`). Юзер может в настройках профиля разрешить другие классы (например, `["working", "broken_screen"]` если ищет на запчасти).

**Последствия.**
- LLM-затраты на 1000 лотов/день: ~$0.10 на classify + ~$1-3 на match только подходящих → бюджет раздела 8.1 (`OPENROUTER_DAILY_USD_LIMIT=10.00`) комфортно покрывает
- Все лоты в БД имеют осмысленное состояние, отображаются в дашборде с тегом
- В `llm_analyses` тип `condition` дополняет существующие `match` и `compare`
- Возникает новый вопрос для UI: показывать ли non-working лоты в основной ленте? Решение: фильтр по умолчанию = working, но переключатель «показать всё» доступен. Этот UX уточняется в Спринте 2

---

## ADR-007 — Avito таксономия добыта, но используется только в V2

**Дата:** 2026-04-25  
**Статус:** Accepted

**Контекст.** В ходе исследования API получены:
- `categories_tree.json` (222 КБ) — полное дерево категорий Avito
- 5 файлов `fields_*.json` — описание полей всех категорий мобильной техники (Vendor, Model, Memory, Color, RamSize и т.д.)
- 3 XML-каталога: `phone_catalog.xml` (524 бренда / 16149 моделей), `tablets.xml` (486 / 7391), `brendy_fashion.xml` (7522 fashion-бренда)

После ADR-001 эти данные не нужны для V1 polling.

**Решение.** Snapshots сохранены в `DOCS/avito_api_snapshots/` как референс. В V1 не используются. В V2 при разработке модуля «Свои объявления и ценовая разведка» — становятся источником seed-данных:
- Для подсказок при создании/редактировании своих лотов через autoload (валидные комбинации Vendor+Model+Memory+Color)
- Для парсинга outhof URL пользователя (extract бренда+модели из slug для отображения в дашборде)

**Последствия.**
- 10 МБ XML в репо как fixtures (приемлемо)
- В V2 — sync-задача через autoload API раз в сутки (`AVITO_MCP_CACHE_TTL_SECONDS=86400` уже в `.env`)
- Документация структуры — в `DOCS/avito_api_snapshots/README.md`
