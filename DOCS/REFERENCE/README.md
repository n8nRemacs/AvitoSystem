# AvitoSystem — Reference Documentation Index

**Создано:** 2026-04-28 (компиляция из всех source-файлов перед удалением старых ТЗ).
**Обновлено:** 2026-05-04 (post Server Migration: VPS 81.200.119.132 + Cloud Supabase + manual refresh model + Avito-MCP public endpoint).
**Назначение:** Structured knowledge base по реверс-инжинирингу Avito API, Android-setup и auth.

---

## Production runtime — quick reference

| Что | Где |
|---|---|
| VPS | `81.200.119.132` (Beget RU, Ubuntu 24.04, Docker 29) |
| Public URL | `https://avitosystem.duckdns.org` |
| 9 контейнеров | caddy, avito-xapi, avito-monitor (web UI), avito-mcp, redis, worker, scheduler, health-checker, telegram-bot |
| БД | Cloud Supabase project `drwgozasaypgphkxyizt` (Frankfurt) |
| Phone | OnePlus 8T `110139ce`, USB к Windows ПК; APK в user_0+user_10 |
| Refresh model | Manual (юзер открывает Avito-app → APK push'ит сессию). Деталях — `02-auth-and-tokens.md` §D. |
| Deploy artifacts | `ops/server/{docker-compose.yml,Caddyfile,.env.template}` |
| Migration audit | `ops/migration-2026-05-02/README.md` |

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
- Понимание health-checker scenarios A-I и one-stale TG-alerts

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

---

## Дополнительные source-файлы (не в этой папке)

| Файл/Папка | Что там | Обновляется ли |
|---|---|---|
| `DOCS/avito_api_snapshots/` | JSON/XML-снимки Official API (categories_tree.json, fields_*.json, phone_catalog.xml) | Нет (2026-04-25 snapshot) |
| `DOCS/avito_api_snapshots/autosearches/README.md` | Полный реверс /5/subscriptions + /2/subscriptions/{id} с live-validated примерами | Нет |
| `DOCS/superpowers/specs/2026-04-28-account-pool-design.md` | Детальный design spec AccountPool (state machine, DB schema, error matrix, testing) | Нет |
| `DOCS/superpowers/plans/2026-05-02-server-migration.md` | 8-фазный план переноса на VPS + Cloud (выполнен) | Нет (исторический) |
| `ops/server/{docker-compose.yml,Caddyfile,.env.template}` | Production deploy artifacts | Да |
| `ops/migration-2026-05-02/README.md` | Audit data migration (какие таблицы, сколько rows) | Нет |
| `DOCS/DECISIONS.md` | ADR-001..011 — архитектурные решения с контекстом | Да |
| `DOCS/V1_EXECUTION_PLAN.md` | 8 блоков V1 — что делается, что проверяется. Текущий progress: блоки 0+1 done, 2-4 предстоят | Да |
| `DOCS/TZ_Avito_Monitor_V1.md` | Главный ТЗ V1.2 — search profiles, LLM, worker pipeline, telegram bot | Нет |
| `CONTINUE.md` | Актуальный статус сессии, operational заметки, команды | Да |

---

## Удалённые файлы (содержимое перенесено сюда)

После создания этих файлов удалены:
- `DOCS/AVITO-API.md` → в `01-avito-api.md`
- `DOCS/REVERSE-GUIDE.md` → в `01-avito-api.md` (QRATOR, Frida-подходы)
- `DOCS/AVITO-FINGERPRINT.md` → в `01-avito-api.md` (fingerprint) + `03-android-setup.md`
- `DOCS/X-API.md` → в `01-avito-api.md` (xapi endpoints)
- `DOCS/token_farm_system.md` → в `02-auth-and-tokens.md` + `03-android-setup.md`
- `DOCS/TENANT_AUTH_SYSTEM.md` → выжимка в `02-auth-and-tokens.md`
