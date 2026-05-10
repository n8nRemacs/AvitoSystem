# AvitoSystem — Reference Documentation Index

**Создано:** 2026-04-28 (компиляция из всех source-файлов перед удалением старых ТЗ).
**Обновлено:** 2026-05-08 (утро) — после полного APK v222.5 reverse engineering: добавлены файлы 07/08/09 с Retrofit API classes, data models, deeplinks.
**Обновлено:** 2026-05-08 (вечер) — `06-structured-params-discovery.md` §6.5 + `10-blob-decoder.md`: расколот формат `f=AS...` blob (LEB128 + zigzag, header `01 28 01 02 02 02 0X 44`). Catalog для category 84: `params[110617]=model`, `params[110618]=brand`, `params[110680]=type`. 50 iPhone моделей засеяны.
**Обновлено:** 2026-05-09/10 — большой UX/pipeline-инкремент:
- **Pagination + humanization** в polling: до 25 страниц с jitter 2-5 сек, page=1 incremental раз в 5 мин, full-walk раз в час, active-hours 8-23 Moscow, random breaks 8-12 polls / 20-40 мин. См. миграцию `0011_polling_humanization`.
- **Reservation tracking**: `listings.reservation_status / reservation_changed_at / reserved_at_price` + новая таблица `listing_status_events` (мигр. `0012_reservation_tracking`) + новый task `refresh_listing_detail` (без LLM). xapi normalizer пробрасывает `reservation_status` (TODO field-name confirmation после первого reserved-event).
- **Pool ladder** capped at 60 мин (было 24 ч после 5 cooldowns), 429 routed в pool как 403, decay −1 после 30 мин quiet — `account_state.py`.
- **API-killer pre-check** в `analysis.py` — 5 правил по `listing.parameters`: «Работа устройства = Не включается / Не звонит / Не работает сенсор», «Аккумулятор = Не заряжается», «Не работают функции», «Не работают датчики» (allowlist «Приближения к уху»), «Камера = Не работает». Skip LLM целиком — `bucket=red` сразу. На текущей выдаче 35 / 78 листингов уходят через api-killer без LLM-вызова.
- **Two new LLM criteria**: `modem_broken` (не видит SIM, нет сети, не звонит — текстом без структурного флага) и `biometric_broken` (Face ID / Touch ID не работают / нестабильно). Дополняют api-killers: API-flag → instant red, plain-text description → LLM.
- **Auto-red blacklist убран**: red bucket теперь визуальный signal, лот видим в выдаче. Только manual «✗ Отклонить» (reason='rejected') реально hides.
- **UI bulk decisions**: 3-state toggle (✗/—/✓) на каждой карточке + sticky bar с per-action counters + одна Apply-кнопка на пачку. Filters preserved через `return_to`.
- **Lightbox v2**: TaoBao-style magnifier (lens 120px + zoom-window 340px на 3×), wheel-zoom с anchored cursor, drag-to-pan, сетка thumbnails. Полная галерея всех фото из detail endpoint (раньше cover-only).
- **Bucket chips** теперь цветные (emerald / slate / red) с tab-aware counts.
**Назначение:** Structured knowledge base по реверс-инжинирингу Avito API, Android-setup и auth.

---

## Production runtime — quick reference

| Что | Где |
|---|---|
| VPS | `81.200.119.132` (Beget RU, **2c/4GB**/15GB Ubuntu 24.04, Docker 29). Upgrade с 1c/2GB после OOM 2026-05-05. |
| Public URL | `https://avitosystem.duckdns.org` |
| 13 контейнеров | caddy, avito-xapi, avito-monitor (web UI), avito-mcp, redis, scheduler, health-checker, telegram-bot **+ 5×worker** (`worker-1, 4, 5, 6, 7, 8` — нумерация после force-recreate) |
| БД | Cloud Supabase project `drwgozasaypgphkxyizt` (Frankfurt). Pooler 6543 + `connect_args={"prepared_statement_cache_size": 0}` (pgbouncer-mode) — query string не работает в SQLAlchemy 2.x async, фикс в `app/db/base.py:50` + `alembic/env.py:53`. |
| Phone | OnePlus 8T `110139ce`, USB к Windows ПК; APK в user_0+user_10 |
| Refresh model | Manual (юзер открывает Avito-app → APK push'ит сессию). Детали — `02-auth-and-tokens.md` §D. |
| LLM pipeline | **V2** (flag-based + 3 buckets) — Phase A shipped 2026-05-05. Default `evaluate_strategy='per_criterion'`. ADR-010 двухступенчатый суперседнут (см. `~/.claude/plans/sequential-seeking-trinket.md`). |
| Deploy artifacts | `ops/server/{docker-compose.yml,Caddyfile,.env.template}` |
| Migration audit | `ops/migration-2026-05-02/README.md` |
| Phase B observability | `ops/v2-soak-metrics.sh` — one-shot dump (bucket distribution, LLM cost, auto-red blacklist rate, polling success, pool state) |

См. `CONTINUE.md` корневого репо для actual production state, backlog, команд проверки.

---

## Файлы в этой папке

### `01-avito-api.md` — API Reference
Полный справочник Avito API (мобильный реверс + официальный).

Когда обращаться:
- Хочешь узнать endpoint для поиска, подписок, деталей лота, мессенджера
- Нужна точная структура заголовков и параметров запросов
- Ищешь какой метод делает что в нашем коде (`avito-xapi/src/workers/http_client.py`)

### `02-auth-and-tokens.md` — Auth & Session Lifecycle
JWT-структура, refresh flow (**manual model** post 2026-05-02 — никаких ADB-monkey-scroll, никакого `/refresh-cycle`), ban detection, multi-account pool.

Когда обращаться:
- Вопросы про истечение/обновление токенов
- Как работает AvitoSessionManager APK (push catcher → POST /sessions)
- Настройка нового аккаунта в pool
- Что делать при бане (403 flow)
- Понимание health-checker scenarios A-I (после `92079da` + `a5d566a` каждый сценарий пишет конкретный `details["reason"]` с deadlines/ms/HTTP-кодами вместо абстрактного «скоро») и one-stale TG-alerts

### `03-android-setup.md` — Android Device Setup
Физическая инфраструктура: OnePlus 8T, System Clone, Magisk, ADB passthrough.

Когда обращаться:
- Добавить новый Android-user (System Clone)
- Выдать Magisk root grant новому APK (учти `multiuser_mode=1` для secondary-user grants)
- Настроить ADB (post-migration phone подключен к Windows ПК пользователя, не к homelab)
- Проблемы с NotificationListener (granted через `settings put secure enabled_notification_listeners`)
- Patch APK SharedPrefs (`server_url`, `api_key`, `mcp_url`, `mcp_auth_token`, `auto_launch_avito=false`)

### `04-reverse-engineering-howto.md` — Методология реверс-инжиниринга
Пошаговый гайд по инструментам, процессу и подводным камням при реверсе Avito Android APK.

Когда обращаться:
- Нужно открыть новый endpoint который ещё не задокументирован
- Настроить jadx / frida-server / curl_cffi с нуля
- Понять почему QRATOR блокирует и что делать
- Нужна инструкция по extraction токенов с устройства
- Хочешь повторить autosearch-реверс на новой версии APK

### `05-search-query-formation.md` — Web URL → Mobile API
Как корректно сформировать поисковый запрос к Avito mobile-API так, чтобы получать те же результаты что Avito-app (а не fuzzy-text мусор). Описывает корень mismatch'а web URL ↔ mobile params, 3 пути решения (decode `f=AS...` blob / subscription flow / mitm capture), известные параметр-ID'ы (110617=brand, 110618=model, 110680=condition), refresh-flow gap, что починено 2026-05-07.

Когда обращаться:
- Polling возвращает мусорные результаты (чайники, формы для склейки, рюмки) при правильно выглядящем URL
- Нужно понять разницу web `categoryId=87` vs mobile `categoryId=84`
- Хочется внедрить декодирование `f=AS...` filter token'а или subscription_id flow
- Планируется capture mobile-app трафика для построения brand/model ID mapping

### `06-structured-params-discovery.md` — Catalog endpoint discovery
Полная методология добычи parameter-ID и values из Avito API: subscription deeplink mining (Variant A) / catalog endpoint discovery (Variant B) / mitm (Variant C) / jadx reverse (Variant D). После APK v222.5 reverse — секция §5 с 5 ranked candidate endpoints + curl-команды Phase 1-4 (§6) + что НЕ работает (§7). **§6.5 — empirical findings 2026-05-08:** все 3 candidate `dicts/parameters` endpoints exist (POST!), JSON body не подходит, plan для form-urlencoded test с fresh JWT. **§6.5.4 — точные curl-команды для следующего теста.**

Когда обращаться:
- Нужно превратить fuzzy `query="iPhone"` в structured `params[110617]=491590&params[110618]=...`
- Расширяешь monitoring на не-phone категории
- Тестируешь catalog candidate endpoints когда есть fresh JWT

### `07-retrofit-api-classes.md` — Retrofit Api Classes (APK v222.5)
**Новый, 2026-05-08.** Полный dump 263 auto-generated Retrofit Api classes из APK v222.5 с verified method signatures. Naming convention (URL → method name через camelCase). Top кандидаты для catalog (NewCarsMarkModelFilterApi blueprint, FilterApi.subscriptionsMobileFilter, UserAdvertsApi.proFiltersInitV1). Cross-validation results 40/43 + 18/18.

Когда обращаться:
- Хочешь предсказать имя Retrofit method по URL (или наоборот)
- Нужны точные method signatures для catalog endpoints
- Планируешь добавить новый endpoint в xapi — проверить declared class
- Hypothesis-testing для legacy/manual interfaces

### `08-data-models.md` — Data Models (APK v222.5)
**Новый, 2026-05-08.** Структура data classes: `DictionaryEntity`, `SelectParameter` (10 inner forms), `ParametersTree`, `SimpleParametersTree`, `SearchParams` (33 fields), `SubscriptionListMobileApi`, `Filter`, `FilterValue`. Cross-validation table 18/18 PASS.

Когда обращаться:
- Нужно понять structure response от dicts/parameters / subscriptions endpoints
- Хочешь увидеть how Avito modelirues filter taxonomy at runtime
- Планируешь mapping в наши Pydantic модели

### `09-deeplinks-and-screens.md` — Deep Links & Screens
**Новый, 2026-05-08.** 5 уникальных deeplink paths (`1/item/show`, `1/beduin/v2/universalPage`, `1/globalCategories`, etc), 96+ DeepLink subtypes, Beduin server-driven UI (alternative path для catalog discovery), data flow inferred. Hardcoded location IDs (637640=Москва default, 621540=вся Россия).

Когда обращаться:
- Анализ subscription deeplinks (`ru.avito://1/items/search?...`)
- Расследование где filter taxonomy serves (Beduin vs `/dicts/parameters`)
- Нужно генерировать deeplinks для нашей системы

---

## Дополнительные source-файлы (не в этой папке)

| Файл/Папка | Что там | Обновляется ли |
|---|---|---|
| `DOCS/avito_api_snapshots/` | JSON/XML-снимки Official API (categories_tree.json, fields_*.json, phone_catalog.xml) | Нет (2026-04-25 snapshot) |
| `DOCS/avito_api_snapshots/autosearches/README.md` | Полный реверс /5/subscriptions + /2/subscriptions/{id} с live-validated примерами | Нет |
| `Reverse Avito/` (gitignored) | Полный workspace APK v222.5 reverse engineering: APK + unpacked DEX + 8 discovery скриптов + raw scan outputs (1408-line all_api_methods.txt + others). Сохранять но не коммитить | Нет (snapshot 2026-05-07) |
| `Reverse Avito/findings/INDEX.md` | Master-index для raw scans (если нужно deep-dive в `Reverse Avito/findings/raw/*.txt`) | Нет |
| `DOCS/superpowers/specs/2026-04-28-account-pool-design.md` | Детальный design spec AccountPool (state machine, DB schema, error matrix, testing) | Нет |
| `DOCS/superpowers/plans/2026-04-30-refresh-hardening.md` | План refresh hardening (D.2/D.3/E/G/H/I, выполнен) | Нет (исторический) |
| `DOCS/superpowers/plans/2026-05-02-server-migration.md` | 8-фазный план переноса на VPS + Cloud (выполнен) | Нет (исторический) |
| `~/.claude/plans/sequential-seeking-trinket.md` | **План V2 LLM pipeline** (Phase A done 2026-05-05, Phase B/C предстоят). Bucket-based evaluation, hot-switch стратегий per_listing ↔ per_criterion, 3 новые таблицы, library из 13 templates | Нет (исторический) |
| `ops/server/{docker-compose.yml,Caddyfile,.env.template}` | Production deploy artifacts | Да |
| `ops/v2-soak-metrics.sh` | Phase B V2 observability one-shot script (bucket distribution, LLM cost, auto-red rate) | Да |
| `ops/migration-2026-05-02/README.md` | Audit data migration (какие таблицы, сколько rows) | Нет |
| `DOCS/DECISIONS.md` | ADR-001..011 — архитектурные решения с контекстом. **ADR-010 (двухступенчатый LLM)** суперседнут V2 pipeline (Phase A 2026-05-05) — деривацию `condition_class` оставили из criteria-флагов для backward-compat метрик. **ADR-011** (auto_red blacklist reuse) задокументирован | Да |
| `DOCS/V1_EXECUTION_PLAN.md` | 8 блоков V1 — блок 4 (LLM pipeline) заменён V2 пайплайном | Да |
| `DOCS/TZ_Avito_Monitor_V1.md` | Главный ТЗ V1.2 — search profiles, LLM, worker pipeline, telegram bot | Нет |
| `avito-monitor/app/data/criteria_templates.yaml` | **Source of truth** для глобальной library criteria (13 templates: 8 criterion + 2 info_llm + 3 info_api). Бамп `version` в YAML + перенакат seed-миграции 0007 = автоинвалидация LLM cache | Да |
| `CONTINUE.md` | Актуальный статус сессии, operational заметки, команды (включая Phase B блокер: pool drained — нужен manual login Avito-app в user_0 под `157920214`) | Да |

---

## V2 LLM pipeline — где что искать

Phase A зашиплен 2026-05-05 (коммит `6840c74` + `cfeb99c` сменил default на `per_criterion`).
Канонический план — `~/.claude/plans/sequential-seeking-trinket.md`. Краткая карта артефактов:

| Слой | Файлы | Что |
|---|---|---|
| Миграции | `avito-monitor/alembic/versions/20260505_1000_v2_llm_pipeline_schema.py` | 3 новые таблицы: `criteria_templates`, `profile_criteria`, `profile_listing_evaluations` (non-destructive) |
|   | `..._1010_v2_seed_criteria_library.py` | Seed library из YAML + auto-конверсия 7 legacy профилей в `profile_criteria` rows |
|   | `..._1100_v2_relax_blacklist_reason.py` | `user_listing_blacklist.reason` varchar(96) для `auto_red:<key>` |
|   | `..._1200_drop_legacy_v2_artifacts.py` | **Phase C destructive — НЕ применена.** Drops `custom_criteria`, `allowed_conditions`, FKs `condition_classification_id`/`match_result_id`, legacy ProcessingStatus values, чистит `llm_analyses` type IN ('condition','match') |
| Library | `avito-monitor/app/data/criteria_templates.yaml` | Source of truth (13 templates) |
| Prompts | `app/prompts/evaluate_listing_batch.md` | per_listing strategy (один batch-вызов на лот) |
|   | `app/prompts/evaluate_criterion.md` | per_criterion strategy (отдельный вызов на criterion, **default**) |
|   | `app/prompts/extract_info.md` | info_llm всегда отдельным batch-вызовом |
|   | _удалены_: `classify_condition.md`, `match_listing.md` (ADR-010 legacy, выпилены в `a5d566a`) |
| Analyzer | `app/services/llm_analyzer.py` | `evaluate_listing(listing, criteria, info_fields, strategy, threshold)` — granular per-criterion cache (hot-switch стратегий не инвалидирует) |
| Worker | `app/tasks/analysis.py` | Task `evaluate_listing` → bucket (green/grey/red) → branch: green+alert_zone → Notification, red → auto-INSERT в `user_listing_blacklist` (reason=`auto_red:<first_red_key>`), grey → только UI |
| Polling | `app/tasks/polling.py` | Routes на v2 если `notification_settings.llm_pipeline_v2=true` (env override `LLM_PIPELINE=v2`) |
| UI | `app/web/templates/profiles/form.html` | Раздел «V2 пайплайн» — chips library + params-формы для memory_gte/title_matches_model + custom rows + slider confidence_threshold |
|   | `app/web/templates/listings.html` | Bucket badge (green/grey/red) + filter chips + query param `?bucket=` |

**Bucket алгоритм** (вычисляется в Python, не у LLM):
- `red` если любой criterion `red` ≥ `confidence_threshold` (default 0.7)
- `green` если ВСЕ criteria `green` ≥ threshold
- иначе `grey` (unknown / низкий confidence)

**Hot-switch стратегий** без рестарта:
```sql
UPDATE search_profiles SET evaluate_strategy='per_listing' WHERE name='iPhone 12 Pro';
```
Cache reuse: criteria_eval rows подходят обоим режимам.

---

## Удалённые файлы (содержимое перенесено сюда)

После создания этих файлов удалены:
- `DOCS/AVITO-API.md` → в `01-avito-api.md`
- `DOCS/REVERSE-GUIDE.md` → в `01-avito-api.md` (QRATOR, Frida-подходы)
- `DOCS/AVITO-FINGERPRINT.md` → в `01-avito-api.md` (fingerprint) + `03-android-setup.md`
- `DOCS/X-API.md` → в `01-avito-api.md` (xapi endpoints)
- `DOCS/token_farm_system.md` → в `02-auth-and-tokens.md` + `03-android-setup.md`
- `DOCS/TENANT_AUTH_SYSTEM.md` → выжимка в `02-auth-and-tokens.md`
- `app/prompts/classify_condition.md` + `match_listing.md` → суперседнуты тремя V2 prompt-файлами (см. таблицу выше)
