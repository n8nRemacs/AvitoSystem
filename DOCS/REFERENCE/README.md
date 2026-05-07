# AvitoSystem — Reference Documentation Index

**Создано:** 2026-04-28 (компиляция из всех source-файлов перед удалением старых ТЗ).
**Обновлено:** 2026-05-07 (account pool hardening + URL parser fix + search-query-formation reference + post-filter listings).
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

---

## Дополнительные source-файлы (не в этой папке)

| Файл/Папка | Что там | Обновляется ли |
|---|---|---|
| `DOCS/avito_api_snapshots/` | JSON/XML-снимки Official API (categories_tree.json, fields_*.json, phone_catalog.xml) | Нет (2026-04-25 snapshot) |
| `DOCS/avito_api_snapshots/autosearches/README.md` | Полный реверс /5/subscriptions + /2/subscriptions/{id} с live-validated примерами | Нет |
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
